"""Generic reader: one implementation for every delimited-text and Excel export.

The reader's contract: whatever the instrument's conventions, what comes out is
always the same thing, in SI units, with charge-positive current. Everything
downstream then has one convention to reason about, and the conversion that was
applied is recorded in the report rather than being implicit.

Nothing here is instrument-specific. An instrument is an ImportProfile.

Every problem the reader can see is collected as a Finding before it decides.
A refusal names all of them at once, so a file with three faults takes one run
to diagnose rather than three.

The data rows are read once, as a stream (P08f). A text file is decoded a block at a time, a
workbook sheet is walked row by row, and the rows go a chunk at a time into a column collector
(_Grid) that keeps only what a binding can use: each numeric column a profile may bind as a
float64 array built chunk by chunk, a step-type column as a list of strings, and the counts the
shape checks need (row widths, values under nameless header columns). The token grid of the
whole file never exists, so memory follows the number of rows times the number of bound columns,
not the size of the file. Every check, finding and number is the one the reader gave when it held
the whole grid; tests/test_readers_reference.py holds it to a reference captured before the
rewrite.
"""
from __future__ import annotations

import codecs
import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from itertools import chain, compress, islice, zip_longest
from pathlib import Path
from typing import Callable

import numpy as np

from .cells import excel_cell_text, parse_duration
from .checks import (Findings, check_counter_against_integral, check_plausible,
                    check_sign_against_voltage, check_single_channel, check_time)
from .profile import UNIT_DIMENSION, UNIT_FACTOR, Binding, ImportProfile, role_dimension
from .workbook import open_workbook

_NUM = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][+-]?\d+)?$")
_UNIT_IN_HEADER = re.compile(r"^(?P<base>.*?)\s*[\(/\[]\s*(?P<unit>[^)\]]+?)\s*[\)\]]?$")

# Thousands grouping, both conventions. Either one silently truncates a number
# if it is parsed with the wrong decimal mark, so it is detected, never guessed.
_GROUPED_POINT = re.compile(r"\d{1,3}(?:,\d{3})+\.\d")      # 1,234.5
_GROUPED_COMMA = re.compile(r"\d{1,3}(?:\.\d{3})+,\d")      # 1.234,5

# A header holding any of these is a setpoint, a limit or an auxiliary channel,
# never the measured quantity. A profile may still bind one by naming the
# column in full, which makes the choice explicit and reviewable.
EXCLUDE_SUBSTRINGS = ("control", "setpoint", "set point", "set-point",
                      "limit", "aux", "target", "nominal")

# Roles without which no electrochemical calculation is defined.
REQUIRED_ROLES = ("test_time_second", "current_ampere", "voltage_volt")

# Fraction of unreadable values in a numeric column above which the column is
# not trusted. Scattered instrument flags are normal; a majority is a mapping
# or an encoding mistake.
MAX_INVALID_FRACTION = 0.5

# The reader streams (P08f): memory follows rows times bound columns, not the size of the file, so
# this limit is a guard against a wrong file (a disk image, a video) rather than a memory bound.
MAX_BYTES = 2 * 1024 ** 3

# Streaming. None of these changes a result: the reference test reads the corpus with them set to
# a few bytes and a few rows as well.
BLOCK_BYTES = 4 * 1024 * 1024    # bytes read and decoded at a time
CHUNK_ROWS = 16384               # data rows parsed at a time
SNIFF_ROWS = 200                 # rows the decimal mark and the grouping are decided from
DAMAGE_CHARS = 20000             # decoded characters searched for U+FFFD (encoding damage)
NUL_BYTES = 65536                # bytes searched for NUL (binary content)

Progress = Callable[[int, int, int], None]
"""progress(rows_read, bytes_read, bytes_total), called once per chunk of rows. For a workbook,
bytes_read is estimated from the rows read and the sheets' declared dimensions."""


class ImportFailure(ValueError):
    """Typed failure. A reader never returns a partly-understood table."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass
class RawTable:
    """SI arrays plus the provenance of every decision taken to produce them."""

    source_name: str
    source_sha256: str
    profile: str
    n: int
    t: np.ndarray                      # s, test time
    i: np.ndarray                      # A, charge-positive after normalisation
    e: np.ndarray                      # V
    step_id: np.ndarray | None = None
    cycle: np.ndarray | None = None
    step_kind: list[str] | None = None  # cc_charge, cv_charge, rest, ...
    q_charge: np.ndarray | None = None  # Ah, as the instrument reported it
    q_discharge: np.ndarray | None = None
    dq: np.ndarray | None = None        # Ah per row, derived from the above
    temperature: np.ndarray | None = None  # degC, surface if present else ambient
    columns: tuple[str, ...] = ()
    report: dict = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)

    @property
    def warnings(self) -> list[dict]:
        return [f for f in self.findings if f["severity"] == "warn"]


def interleaved_columns(headers: list[str], rows: list[list[str]]) -> list[int]:
    """1-based positions of nameless header columns that hold a value in some rows but not all.

    A nameless column that is filled in every row is an index (a file re-saved by pandas); one
    that is empty in every row is padding. Filled in only some rows, it marks rows of another
    table written into the same file, which no column mapping can make right."""
    out = []
    for k, h in enumerate(headers):
        if h.strip():
            continue
        filled = sum(1 for r in rows if k < len(r) and r[k].strip())
        if 0 < filled < len(rows):
            out.append(k + 1)
    return out


# ------------------------------------------------------------------- sniffing
def _sniff_delimiter(line: str) -> str:
    counts = {d: line.count(d) for d in ("\t", ";", ",")}
    best = max(counts, key=lambda d: counts[d])
    if counts[best] == 0:
        raise ImportFailure("no_delimiter", "no tab, semicolon or comma found on the header line")
    return best


def _sniff_decimal(rows: list[list[str]]) -> str:
    """Decide the decimal mark from the data, including grouped numbers.

    '1.234,5' is a decimal comma with point grouping; '1,234.5' is the reverse.
    Both contain a comma and a point next to digits, so the plain test is not
    enough on its own.
    """
    sample = " ".join(c for r in rows[:200] for c in r)
    if _GROUPED_COMMA.search(sample):
        return ","
    if _GROUPED_POINT.search(sample):
        return "."
    comma = re.search(r"\d,\d", sample) is not None
    point = re.search(r"\d\.\d", sample) is not None
    return "," if comma and not point else "."


def _split_unit(header: str) -> tuple[str, str | None]:
    m = _UNIT_IN_HEADER.match(header.strip())
    if not m:
        return header.strip(), None
    unit = m.group("unit").strip()
    return (m.group("base").strip(), unit) if unit in UNIT_FACTOR else (header.strip(), None)


def _excluded(header: str, candidate: str) -> bool:
    """A setpoint column never satisfies a measurement role implicitly."""
    if header.strip() == candidate:          # named in full: an explicit choice
        return False
    low = header.lower()
    return any(s in low for s in EXCLUDE_SUBSTRINGS)


def _match(binding: Binding, headers: list[str]) -> tuple[list[int], str | None] | None:
    """Return (all matching column indices, unit) for the first candidate that hits.

    All indices, not the first: two columns with the same name is an ambiguity
    the caller must refuse rather than resolve by position.
    """
    for cand in binding.source:
        hits: list[int] = []
        unit: str | None = None
        if "{unit}" in cand:
            pat = re.compile("^" + re.escape(cand).replace(r"\{unit\}", r"(?P<unit>[^)\]]+)") + "$")
            for k, h in enumerate(headers):
                m = pat.match(h.strip())
                if m and m.group("unit") in UNIT_FACTOR and not _excluded(h, cand):
                    hits.append(k)
                    unit = unit or m.group("unit")
        else:
            cand_base, cand_unit = _split_unit(cand)
            for k, h in enumerate(headers):
                base, u = _split_unit(h)
                same = (h.strip() == cand or base == cand
                        # the same quantity exported in another unit: 'Current(mA)' bound, 'Current(A)' in
                        # the file. Instruments let the user pick units at export time; the header's
                        # own unit is taken (Arbin, Landt: P08e)
                        or (cand_unit is not None and u is not None and _same_name(base, cand_base)))
                if same and not _excluded(h, cand):
                    hits.append(k)
                    unit = unit or u
        if hits:
            return hits, unit
    return None


def _same_name(a: str, b: str) -> bool:
    """Equal column names up to case, spacing and punctuation ('Test_Time' is 'Test Time')."""
    return re.sub(r"[\W_]+", "", a).lower() == re.sub(r"[\W_]+", "", b).lower()


def _to_float(tokens: list[str], decimal: str, duration: bool = False) -> tuple[np.ndarray, int]:
    """Numbers from tokens; with duration=True, clock-format durations to seconds instead.

    The two are never mixed: a column declared 'hh:mm:ss' reads only clock durations
    (a bare number in it could be seconds or hours, so it is counted as invalid), and a
    numeric column never reads a clock."""
    out = np.full(len(tokens), np.nan)
    bad = 0
    if duration:
        for k, tok in enumerate(tokens):
            v = parse_duration(tok)
            if v is None:
                bad += 1
            else:
                out[k] = v
        return out, bad
    for k, tok in enumerate(tokens):
        s = tok.strip().replace("−", "-")      # unicode minus
        if decimal == ",":
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")                   # grouping only; see guard
        if s and _NUM.match(s):
            out[k] = float(s.replace("d", "e").replace("D", "E"))
        else:
            bad += 1
    return out, bad


_SEP = "\x00"
_ASCII_SPACE = (" ", "\t", "\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x1f")
_INNER_SPACE = re.compile(r"[^\s\x00]\s+[^\s\x00]")
_SPLIT_BELOW = 1024


def _numbers(tokens, decimal: str) -> tuple[np.ndarray, int]:
    """_to_float(tokens, decimal) for one numeric column, a chunk of rows at a time.

    The whole chunk is converted at once by float() in numpy's object-to-float64 cast, which is
    the conversion _to_float makes token by token. That is only done where it provably gives the
    same answer for every token (_numbers_fast). A chunk holding a token it cannot vouch for is
    split into pieces of _SPLIT_BELOW rows, and a piece that still cannot be vouched for is read
    token by token by _to_float itself, which also counts the unreadable tokens."""
    n = len(tokens)
    if n == 0:
        return np.full(0, np.nan), 0
    fast = _numbers_fast(tokens, decimal)
    if fast is not None:
        return fast, 0
    if n > _SPLIT_BELOW:
        parts = [_numbers(tokens[a:a + _SPLIT_BELOW], decimal) for a in range(0, n, _SPLIT_BELOW)]
        return np.concatenate([v for v, _ in parts]), sum(b for _, b in parts)
    return _to_float(list(tokens), decimal)


def _numbers_fast(tokens, decimal: str) -> np.ndarray | None:
    """The values of a chunk in which every token is a number _to_float accepts, else None.

    _to_float strips a token, applies the Unicode minus and decimal-mark replacements, requires
    the result to match _NUM (ASCII or Unicode digits, an e/E/d/D exponent) and converts it with
    float(). Here the replacements (and d/D to e/E) are made on the chunk joined by NUL, and float()
    is applied to the result. The two agree token by token when
    - no token has whitespace inside it (only around it): stripping then commutes with the
      replacements, and float() ignores the surrounding whitespace it accepts; the whitespace it
      does not accept (U+001C to U+001F) makes it fail, which sends the chunk to _to_float;
    - the text is ASCII after the replacements, so no Unicode digit or space is involved;
    - there is no 'n', 'N' or '_': float() also reads 'nan', 'inf', 'infinity' and '1_000',
      which _NUM refuses, and each of those contains one of the three.
    Under these conditions float() accepts exactly the strings _NUM accepts, so a chunk that
    converts without error is one in which _to_float would have accepted every token, with the
    same value. Any failure returns None, never a partial answer."""
    j = _SEP.join(tokens)
    if j.count(_SEP) != len(tokens) - 1:
        return None                                 # a token holds NUL itself
    if any(s in j for s in _ASCII_SPACE) and _INNER_SPACE.search(j):
        return None
    changed = False
    if "\u2212" in j:
        j, changed = j.replace("\u2212", "-"), True
    if decimal == ",":
        if "." in j:
            j, changed = j.replace(".", ""), True
        if "," in j:
            j, changed = j.replace(",", "."), True
    elif "," in j:
        j, changed = j.replace(",", ""), True
    if "d" in j or "D" in j:
        j, changed = j.replace("d", "e").replace("D", "E"), True
    if not j.isascii() or "n" in j or "N" in j or "_" in j:
        return None
    try:
        return np.array(j.split(_SEP) if changed else tokens, dtype=object).astype(np.float64)
    except ValueError:
        return None


# ------------------------------------------------------------------ the grid
class _Grid:
    """The data rows of one table, kept as the columns a binding can use, never as rows.

    Rows arrive a chunk at a time (add). The first SNIFF_ROWS rows (and the unit row, when the
    layout names one) are held until the decimal mark is decided and the columns to keep are
    known (_plan); every later chunk is converted on arrival. Which columns to keep is found by
    running the binding loop itself (_bind) against the header, once for each width the header
    can still take: whether nameless trailing header columns are dropped depends on the widest
    row, which is known only at the end (read, 'trailing_delimiter_in_header')."""

    def __init__(self, p: ImportProfile, headers: list[str], *, progress: Progress | None = None,
                 bytes_total: int = 0):
        self.p = p
        self.headers = headers
        self.L = len(headers)
        self.units: list[str] | None = None
        self.await_units = bool(p.layout.unit_row)
        self.n = 0
        self.lengths: Counter = Counter()
        self.longer = 0            # rows wider than the header with a value beyond it
        self.trimmed = 0           # rows wider than the header with only empty fields beyond it
        self.blank = [k for k, h in enumerate(headers) if not h.strip()]
        self.filled = dict.fromkeys(self.blank, 0)
        self.pending: list[list[str]] = []
        self.planned = False
        self.sample: list[list[str]] = []
        self.sample_text = ""
        self.decimal = "."
        self.wanted: set[tuple[int, str]] = set()
        self._num: dict[tuple[int, str], list[np.ndarray]] = {}
        self._bad: dict[tuple[int, str], int] = {}
        self._text: dict[int, list[str]] = {}
        self._vocab: dict[str, str] = {}
        self.progress = progress
        self.bytes_total = bytes_total
        self.sha256 = ""

    # -- feeding
    def set_units(self, row: list[str]) -> None:
        self.units = row
        self.await_units = False

    def add(self, rows: list[list[str]]) -> None:
        """Data rows, in file order, with the blank rows already left out."""
        if not rows:
            return
        if not self.planned:
            self.pending.extend(rows)
            if len(self.pending) < SNIFF_ROWS or self.await_units:
                return
            self._plan()
            rows, self.pending = self.pending, []
        self._take(rows)

    def finish(self) -> None:
        if not self.planned:
            self._plan()
            rows, self.pending = self.pending, []
            if rows:
                self._take(rows)
        for key, parts in self._num.items():
            self._num[key] = [np.concatenate(parts)] if len(parts) != 1 else parts

    def report(self, bytes_read: int) -> None:
        if self.progress is not None:
            self.progress(self.n + len(self.pending), int(bytes_read), int(self.bytes_total))

    # -- deciding what to keep
    def _plan(self) -> None:
        self.planned = True
        p = self.p
        self.sample = self.pending[:SNIFF_ROWS]
        self.decimal = _sniff_decimal(self.sample) if p.layout.decimal == "auto" else p.layout.decimal
        self.sample_text = " ".join(c for r in self.sample for c in r)
        if self.decimal == "," and _GROUPED_POINT.search(self.sample_text):
            return                                  # decimal_mark_conflict stops the import: read nothing
        trailing = 0
        while trailing < self.L and not self.headers[self.L - 1 - trailing].strip():
            trailing += 1
        for width in range(self.L - trailing, self.L + 1):
            _bind(p, self.headers[:width], self.units, Findings(), self._request)

    def _request(self, k: int, kind: str):
        self.wanted.add((k, kind))
        return None

    # -- converting
    def _take(self, rows: list[list[str]]) -> None:
        n = len(rows)
        lens = list(map(len, rows))
        self.lengths.update(lens)
        L = self.L
        if max(lens) > L:
            for r in rows:
                if len(r) > L:
                    if any(c.strip() for c in r[L:]):
                        self.longer += 1
                    else:
                        self.trimmed += 1
        cols = list(zip_longest(*rows, fillvalue=""))
        for k in self.blank:
            if k < len(cols):
                self.filled[k] += sum(1 for _ in filter(None, map(str.strip, cols[k])))
        empty = None
        for k, kind in self.wanted:
            if k < len(cols):
                col = cols[k]
            else:
                col = empty = empty or ("",) * n
            if kind == "text":
                vocab = self._vocab
                self._text.setdefault(k, []).extend([vocab.setdefault(s, s) for s in map(str.strip, col)])
                continue
            if kind == "dur":
                values, bad = _to_float(list(col), self.decimal, duration=True)
            else:
                values, bad = _numbers(col, self.decimal)
            self._num.setdefault((k, kind), []).append(values)
            self._bad[(k, kind)] = self._bad.get((k, kind), 0) + bad
        self.n += n

    # -- what read() asks
    def fetch(self, k: int, kind: str):
        """Column k as read for `kind`, handed over: the grid keeps no copy, so a column's raw values
        and its converted values are not both held (the binding loop asks for a column once)."""
        if kind == "text":
            return self._text.pop(k) if self.n else []
        return self._num.pop((k, kind))[0], self._bad[(k, kind)]

    def release(self) -> None:
        self._num.clear()
        self._text.clear()

    @property
    def widest(self) -> int:
        return max(self.lengths) if self.lengths else 0

    def shorter_than(self, width: int) -> int:
        return sum(c for length, c in self.lengths.items() if length < width)

    def interleaved(self, headers: list[str]) -> list[int]:
        """interleaved_columns(headers, rows) from the counts: headers is a prefix of self.headers."""
        return [k + 1 for k in self.blank if k < len(headers) and 0 < self.filled[k] < self.n]


def _check_layout(lay) -> None:
    """Row positions the streaming reader cannot honour as the whole-grid reader did: a header row
    below 1 or a negative unit row indexed the grid from its end, and a negative skip started the
    data above the header. None is a meaningful layout, so each is refused by name (P08f)."""
    bad = []
    if lay.header_row < 1 and not lay.header_contains:
        bad.append(f"header_row={lay.header_row}")
    if lay.unit_row is not None and lay.unit_row < 0:
        bad.append(f"unit_row={lay.unit_row}")
    if lay.skip_rows_after_header < 0:
        bad.append(f"skip_rows_after_header={lay.skip_rows_after_header}")
    if bad:
        raise ImportFailure("invalid_layout", f"the profile's layout cannot locate the table: {', '.join(bad)} "
                            "(rows are counted from 1, and skips cannot be negative)")


def _non_blank(chunk: list[list[str]]) -> list[list[str]]:
    """The rows of a chunk that hold anything but whitespace (any(c.strip() for c in r))."""
    return list(compress(chunk, map(str.strip, map("".join, chunk))))


def _read_grid(path: Path, p: ImportProfile, fnd: Findings, progress: Progress | None = None) -> _Grid:
    """The table's header and data, streamed into a _Grid, for either file kind."""
    _check_layout(p.layout)
    if p.layout.kind == "excel":
        return _read_excel_grid(path, p, fnd, progress)
    return _read_text_grid(path, p, fnd, progress)


class _Decoded:
    """A text file decoded a block at a time with an incremental decoder: the concatenated blocks
    are path.read_bytes().decode(encoding, errors='replace'). Counts the bytes read, keeps the
    first DAMAGE_CHARS characters, and feeds a hash when given one."""

    def __init__(self, path: Path, encoding: str, hasher=None):
        self.path, self.encoding, self.hasher = path, encoding, hasher
        self.bytes_read = 0
        self.prefix = ""

    def blocks(self):
        decoder = codecs.getincrementaldecoder(self.encoding)(errors="replace")
        with open(self.path, "rb") as fh:
            while True:
                b = fh.read(BLOCK_BYTES)
                if self.hasher is not None:
                    self.hasher.update(b)
                self.bytes_read += len(b)
                text = decoder.decode(b, final=not b)
                if len(self.prefix) < DAMAGE_CHARS:
                    self.prefix += text[:DAMAGE_CHARS - len(self.prefix)]
                yield text, not b
                if not b:
                    return


def _line_batches(blocks, comment: str | None):
    """The lines of raw.splitlines(), comment lines left out, in batches. A block is cut after its
    last line feed (or a carriage return that is not its last character, so CR LF is never split),
    and the rest is carried into the next block, which keeps every line break where splitlines
    puts it."""
    carry = ""
    for text, final in blocks:
        if carry:
            text = carry + text
        if final:
            lines, carry = text.splitlines(), ""
        else:
            cut = max(text.rfind("\n"), text.rfind("\r", 0, len(text) - 1))
            if cut < 0:
                carry = text
                continue
            lines, carry = text[:cut + 1].splitlines(), text[cut + 1:]
        if comment:
            lines = [ln for ln in lines if not ln.startswith(comment)]
        if lines:
            yield lines


def _csv_input(batches):
    """io.StringIO('\n'.join(lines)), batch by batch: every line but the last ends in a line feed."""
    held = None
    for batch in batches:
        if held is not None:
            yield io.StringIO("\n".join(held) + "\n")
        held = batch
    if held is not None:
        yield io.StringIO("\n".join(held))


def _locate_header(path: Path, encoding: str, lay) -> tuple[int, str]:
    """(1-based header line, the line itself), counted as in raw.splitlines() without comments."""
    stream = _Decoded(path, encoding)
    batches = _line_batches(stream.blocks(), lay.comment)
    count = 0
    try:
        for batch in batches:
            if lay.header_contains:
                for ln in batch:
                    count += 1
                    if all(m in ln for m in lay.header_contains):
                        return count, ln
            elif count + len(batch) >= lay.header_row:
                return lay.header_row, batch[lay.header_row - count - 1]
            else:
                count += len(batch)
    finally:
        batches.close()
    if lay.header_contains:
        raise ImportFailure("no_header", f"no line contains all of {list(lay.header_contains)}")
    raise ImportFailure("short_file", f"fewer than {lay.header_row} lines")


def _read_text_grid(path: Path, p: ImportProfile, fnd: Findings, progress: Progress | None) -> _Grid:
    lay = p.layout
    with open(path, "rb") as fh:
        head = fh.read(NUL_BYTES)
    encoding = lay.encoding
    # A byte-order mark is the file's own statement of its encoding, and it
    # outranks the profile's. Without this, a UTF-8 BOM decoded as cp1252
    # becomes three visible characters glued to the first column name, which
    # unbinds that column silently instead of failing.
    for mark, enc in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe\x00\x00", "utf-32"),
                      (b"\x00\x00\xfe\xff", "utf-32"), (b"\xff\xfe", "utf-16"),
                      (b"\xfe\xff", "utf-16")):
        if head.startswith(mark):
            if enc.rstrip("-sig") != encoding.rstrip("-sig"):
                fnd.note("byte_order_mark_overrides_profile",
                         f"the file begins with a {enc} byte-order mark, so it was decoded as "
                         f"{enc} rather than the declared {encoding}",
                         declared=encoding, used=enc)
            encoding = enc
            break
    # A text export never contains NUL. Finding one means either a binary file
    # was handed to the text reader, or the text is UTF-16/32 with the BOM
    # stripped. cp1252 maps NUL to a valid character, so decoding alone would
    # not notice and the failure would surface later as "missing column".
    if not encoding.startswith("utf-16") and not encoding.startswith("utf-32") \
            and b"\x00" in head[:NUL_BYTES]:
        fnd.refuse(
            "binary_content",
            f"the file contains NUL bytes, so it is not text in {encoding}. It is either a "
            "binary instrument file (an .mpr or .res, which needs the native reader) or a "
            "UTF-16/32 export whose byte-order mark has been removed.",
            encoding=encoding)
        fnd.raise_if_refused(path.name)
    codecs.lookup(encoding)                                 # an unknown name fails here, as decode() did
    header_row, head_line = _locate_header(path, encoding, lay)
    delim = lay.delimiter or _sniff_delimiter(head_line)

    hasher = hashlib.sha256()
    stream = _Decoded(path, encoding, hasher)
    rows = csv.reader(chain.from_iterable(_csv_input(_line_batches(stream.blocks(), lay.comment))),
                      delimiter=delim)
    unit_row = lay.unit_row or None
    start = header_row + lay.skip_rows_after_header
    headers = units = None
    j = 0
    for row in islice(rows, start):                         # the preamble, the header, the rows skipped
        if j == header_row - 1:
            headers = [h.lstrip("\ufeff") for h in row]
        if unit_row and j == unit_row - 1:
            units = row
        j += 1
    if headers is None:
        raise IndexError("list index out of range")         # fewer csv rows than header_row
    grid = _Grid(p, headers, progress=progress, bytes_total=path.stat().st_size)
    if units is not None:
        grid.set_units(units)
    while True:
        chunk = list(islice(rows, CHUNK_ROWS))
        if not chunk:
            break
        if grid.await_units and j <= unit_row - 1 < j + len(chunk):
            grid.set_units(chunk[unit_row - 1 - j])
        j += len(chunk)
        grid.add(_non_blank(chunk))
        grid.report(stream.bytes_read)
    if grid.await_units:
        raise IndexError("list index out of range")         # the unit row is beyond the last row
    if "\ufffd" in stream.prefix:
        fnd.refuse(
            "encoding_damage",
            f"the file does not decode cleanly as {encoding}. Characters were lost, so a column "
            "name may no longer match. Declare the correct encoding in the profile.",
            encoding=encoding)
    grid.finish()
    grid.sha256 = hasher.hexdigest()
    grid.report(stream.bytes_read)
    return grid


class _Span:
    """(first, last) readable value of one column over the rows given, as _time_span reported it:
    float(token.replace(',', '.')), None unless two values were readable."""

    def __init__(self, k: int | None):
        self.k = k
        self.first = self.last = None
        self.count = 0

    def _value(self, r):
        if self.k < len(r):
            try:
                return float(r[self.k].replace(",", "."))
            except ValueError:
                return None
        return None

    def update(self, rows: list[list[str]]) -> None:
        if self.k is None or not rows:
            return
        i1 = next((i for i, r in enumerate(rows) if self._value(r) is not None), None)
        if i1 is None:
            return
        v1 = self._value(rows[i1])
        i2 = next((i for i in range(len(rows) - 1, i1, -1) if self._value(rows[i]) is not None), None)
        if self.count == 0:
            self.first = v1
        self.last = self._value(rows[i2]) if i2 is not None else v1
        self.count = min(2, self.count + (2 if i2 is not None else 1))

    def result(self) -> tuple[float, float] | None:
        return (self.first, self.last) if self.count >= 2 and self.k is not None else None


def _read_excel_grid(path: Path, p: ImportProfile, fnd: Findings, progress: Progress | None = None) -> _Grid:
    wb = open_workbook(path)
    try:
        return _stream_workbook(wb, path, p, fnd, progress)
    finally:
        wb.close()


def _stream_workbook(wb, path: Path, p: ImportProfile, fnd: Findings, progress: Progress | None) -> _Grid:
    lay = p.layout
    names = list(lay.sheets) if lay.sheets else wb.sheetnames
    size = path.stat().st_size
    declared = sum((wb[n].max_row or 0) for n in names if n in wb.sheetnames) or 1
    seen = 0
    headers: list[str] | None = None
    grid: _Grid | None = None
    time_col: int | None = None
    used: list[str] = []
    skipped: list[str] = []
    headless: dict[str, list[list[str]]] = {}
    spans: list[tuple[str, tuple[float, float] | None]] = []
    for name in names:
        if name not in wb.sheetnames:
            raise ImportFailure("missing_sheet", f"sheet {name!r} is not in the workbook")
        ws = wb[name]
        it = ws.iter_rows(values_only=True)
        # the header is looked for in the first 100 rows, and a headerless sheet is judged by its
        # first 50, so a sheet that is not read is never walked further than that
        look = 100 if lay.header_contains else lay.header_row
        head = [[excel_cell_text(c) for c in r] for r in islice(it, max(look, 50))]
        seen += len(head)
        header_row = lay.header_row
        if lay.header_contains:
            # The header is located per sheet, as in a text file: a workbook whose first sheet is a
            # report (Arbin's Global_Info) or a summary (a Neware or Landt cycle sheet) is then read
            # from the sheet that actually holds the time series, whatever its name.
            found = next((k + 1 for k, r in enumerate(head[:100])
                          if all(any(m in c for c in r) for m in lay.header_contains)), None)
            if found is None:
                skipped.append(name)
                # a sheet with no header but rows of numbers may continue the record (Landt writes
                # its continuation sheets without a header row; P08 specification, trap 6)
                headless[name] = [r for r in head[:50] if any(c.strip() for c in r)]
                continue
            header_row = found
        if len(head) < header_row:
            continue
        sheet_headers = [h.lstrip("\ufeff") for h in head[header_row - 1]]
        first = headers is None
        if first:
            headers = sheet_headers
            grid = _Grid(p, headers, progress=progress, bytes_total=size)
            hit = _match(p.bindings["test_time_second"], [h.strip() for h in headers])
            time_col = hit[0][0] if hit is not None and len(hit[0]) == 1 else None
        elif sheet_headers != headers:
            skipped.append(name)
            continue
        used.append(name)
        start = header_row + lay.skip_rows_after_header
        unit_at = lay.unit_row - 1 if (first and lay.unit_row) else None
        span = _Span(time_col)
        rows = chain(head, ([excel_cell_text(c) for c in r] for r in it))
        j = 0
        while True:
            chunk = list(islice(rows, CHUNK_ROWS))
            if not chunk:
                break
            if unit_at is not None and j <= unit_at < j + len(chunk):
                grid.set_units(chunk[unit_at - j])
            data = _non_blank(chunk[max(0, start - j):])
            if j + len(chunk) > len(head):
                seen += j + len(chunk) - max(j, len(head))
            j += len(chunk)
            span.update(data)
            grid.add(data)
            grid.report(min(size, size * seen // declared))
        if unit_at is not None and grid.await_units:
            raise IndexError("list index out of range")     # the unit row is beyond the sheet
        spans.append((name, span.result()))
    if headers is None:
        raise ImportFailure("no_header", "no sheet carried a header row")
    if skipped:
        fnd.note("sheets_skipped",
                 f"sheet(s) {skipped} carry a different header and were not treated as time "
                 "series data", sheets=skipped)
    width = len([h for h in headers if h.strip()])
    looks_continued = [n for n, rs in headless.items() if rs and all(
        len([c for c in r if c.strip()]) == width
        and sum(bool(_NUM.match(c.strip())) for c in r if c.strip()) >= 0.5 * width for r in rs[:5])]
    if looks_continued:
        fnd.warn("headerless_sheet_not_read",
                 f"sheet(s) {looks_continued} have no header row but rows as wide as the table, as a "
                 "continuation of the record would. They were not read, so the data may end early; "
                 "check the workbook or export the record as one sheet or as text.",
                 sheets=looks_continued)
    if len(used) > 1:
        # Sheets with one header are a long record split by the export (Arbin, Neware) only if
        # the clock runs on from one to the next. A second sheet whose clock starts again is
        # another channel or another test in the same workbook, and reading the two as one cell
        # would give plausible wrong capacities, so the import stops (P08e).
        for (a, sa), (b, sb) in zip(spans, spans[1:]):
            if sa is not None and sb is not None and sb[0] < sa[1]:
                fnd.refuse("sheets_not_continuous",
                           f"sheet {b!r} starts its test clock at {sb[0]:g} while sheet {a!r} ends at {sa[1]:g}: "
                           "the workbook holds more than one channel or test with the same columns. Export "
                           "one channel per file, or keep only the sheet to analyse.",
                           sheets=[a, b], ends_at=sa[1], restarts_at=sb[0])
        fnd.note("sheets_concatenated",
                 f"{len(used)} sheets with an identical header were read in workbook order: "
                 f"{used}. Check that this is the intended order.", sheets=used)
    grid.finish()
    grid.sha256 = _sha256(path)
    grid.report(size)
    return grid


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(BLOCK_BYTES), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------- bindings
def _bind(p: ImportProfile, headers: list[str], unit_row, fnd: Findings, fetch):
    """Resolve every binding against the header and read the bound columns.

    fetch(k, kind) returns column k as read for that kind ('num', 'dur' for a clock-format
    duration, 'text' for the step type): (values, unreadable count), or the list of stripped
    strings. The grid also runs this loop before any row is read, with a fetch that records the
    request and returns None, to learn which columns to keep; nothing after a fetch runs then."""
    cols: dict[str, np.ndarray] = {}
    text_cols: dict[str, list[str]] = {}
    resolved: dict[str, dict] = {}
    invalid: dict[str, int] = {}
    claimed: dict[int, str] = {}

    for role, b in p.bindings.items():
        hit = _match(b, headers)
        if hit is None:
            if role in REQUIRED_ROLES:
                fnd.refuse("missing_column",
                           f"no column for {role}; tried {list(b.source)}; file has {headers}",
                           role=role, tried=list(b.source))
            continue
        idx, header_unit = hit
        if len(idx) > 1:
            fnd.refuse("ambiguous_column",
                       f"{len(idx)} columns match {role}: "
                       f"{[headers[k] for k in idx]}. Name the intended one in full in the "
                       "profile rather than letting position decide.",
                       role=role, columns=[headers[k] for k in idx])
            continue
        k = idx[0]
        if k in claimed:
            fnd.refuse("column_claimed_twice",
                       f"column {headers[k]!r} is bound to both {claimed[k]} and {role}",
                       column=headers[k], roles=[claimed[k], role])
            continue
        claimed[k] = role

        if role == "step_type":
            got = fetch(k, "text")
            if got is None:
                continue
            text_cols[role] = got
            resolved[role] = {"column": headers[k], "assumed": b.assumed}
            continue

        row_unit = unit_row[k].strip() if unit_row and k < len(unit_row) else None
        if header_unit and b.source_unit and header_unit != b.source_unit:
            fnd.refuse("unit_conflict",
                       f"column {headers[k]!r} declares {header_unit!r} in its header but the "
                       f"profile declares {b.source_unit!r} for {role}. One of them is wrong.",
                       column=headers[k], header_unit=header_unit, profile_unit=b.source_unit)
            continue
        unit = header_unit or b.source_unit or row_unit
        if unit is None and role in ("record_index", "step_id", "step_count", "cycle_count"):
            unit = "1"
        if unit is None:
            fnd.refuse("unknown_unit",
                       f"column {headers[k]!r} for {role} carries no unit and the profile "
                       "declares none", column=headers[k], role=role)
            continue
        if unit not in UNIT_FACTOR:
            fnd.refuse("unknown_unit", f"unit {unit!r} on column {headers[k]!r} is not in the "
                       "unit registry; add it there rather than guessing a factor",
                       column=headers[k], unit=unit)
            continue
        want = role_dimension(role)
        if UNIT_DIMENSION[unit] != want:
            fnd.refuse("unit_dimension_mismatch",
                       f"column {headers[k]!r} is in {unit!r} ({UNIT_DIMENSION[unit]}) but "
                       f"{role} must be a {want}. This binding is wrong, not merely "
                       "unconverted.",
                       column=headers[k], unit=unit, role=role,
                       got=UNIT_DIMENSION[unit], expected=want)
            continue

        got = fetch(k, "dur" if unit == "hh:mm:ss" else "num")
        if got is None:
            continue
        values, bad = got
        values = values * (UNIT_FACTOR[unit] * b.scale) + b.offset
        if b.reverse_sign:
            values = -values
        cols[role] = values
        if bad:
            invalid[headers[k]] = bad
            frac = bad / len(values)
            if frac > MAX_INVALID_FRACTION:
                fnd.refuse("column_mostly_unreadable",
                           f"{frac:.0%} of {headers[k]!r} ({role}) could not be read as a number. "
                           "The decimal mark, the encoding or the column choice is wrong.",
                           column=headers[k], role=role, fraction=frac)
            else:
                fnd.note("invalid_tokens",
                         f"{bad} value(s) in {headers[k]!r} are missing or non-numeric and "
                         "become NaN; rows carrying them are not integrated",
                         column=headers[k], rows=bad)
        check_plausible(fnd, role, values, headers[k])
        resolved[role] = {"column": headers[k], "unit": unit, "scale": b.scale,
                          "reverse_sign": b.reverse_sign, "assumed": b.assumed}
    return cols, text_cols, resolved, invalid, claimed


# -------------------------------------------------------------------- read
def read(path: str | Path, p: ImportProfile, progress: Progress | None = None) -> RawTable:
    """Read one export with one profile. progress(rows_read, bytes_read, bytes_total), when given,
    is called once per chunk of rows while the file is read."""
    path = Path(path)
    fnd = Findings()

    size = path.stat().st_size
    if size == 0:
        raise ImportFailure("empty_file", "the file is empty")
    if size > MAX_BYTES:
        raise ImportFailure("file_too_large",
                            f"{size / 2**20:.0f} MiB exceeds the {MAX_BYTES / 2**20:.0f} MiB limit")

    grid = _read_grid(path, p, fnd, progress)
    fnd.raise_if_refused(path.name)
    if not grid.n:
        raise ImportFailure("no_data", "the file has a header but no data rows")

    # --- shape of the grid -------------------------------------------------
    # A trailing delimiter on the header line alone invents a nameless column.
    # EC-Lab does this on every .mpt. Drop it only while every data row is
    # narrower than the header, so a genuinely empty last column is kept.
    headers = list(grid.headers)
    widest = grid.widest
    phantom = 0
    while len(headers) > widest and headers and not headers[-1].strip():
        headers.pop()
        phantom += 1
    if phantom:
        fnd.note("trailing_delimiter_in_header",
                 f"the header line ends with {phantom} delimiter(s) and no column name; the "
                 "nameless column(s) were dropped", count=phantom)

    width = len(headers)
    # The opposite habit: a delimiter after the last value of every data row but not after the
    # last header name (Maccor's export with the 12-line header block, cellpy maccor_002.txt).
    # Empty fields beyond the header carry nothing and are dropped; a value there still refuses.
    # (The grid counted both kinds of wide row against the header as written. When nameless
    # columns were dropped above, no row is wider than what remains, so the counts are still
    # those of rows wider than `width`: none.)
    trimmed = grid.trimmed
    if trimmed:
        fnd.note("trailing_delimiter_in_rows",
                 f"{trimmed} data row(s) end with empty field(s) beyond the {width} header names; "
                 "the empty fields were dropped", rows=trimmed, width=width)
    long_rows = grid.longer
    short_rows = grid.shorter_than(width)
    if long_rows:
        # Fields beyond the header have no name, so they would be dropped with
        # no trace. That is the one shape problem worth stopping for.
        fnd.refuse("rows_wider_than_header",
                   f"{long_rows} row(s) carry more fields than the {width} header names, so "
                   "those values have no column to belong to. The delimiter is appearing inside "
                   "a value, or the header is the wrong line.", rows=long_rows, width=width)
    if short_rows:
        fnd.warn("rows_narrower_than_header",
                 f"{short_rows} row(s) have fewer fields than the {width} header names. The "
                 "missing trailing fields are read as NaN and the rows carrying them are not "
                 "integrated.", rows=short_rows, width=width)
    mixed = grid.interleaved(headers)
    if mixed:
        fnd.refuse("interleaved_tables",
                   f"some rows, not all, carry values under the nameless column(s) {mixed} of the header, "
                   "so those rows belong to a different table interleaved with this one (Neware's "
                   "hierarchical export writes cycle, step and record rows into one file this way). "
                   "Reading them as records would put cycle totals among the measurements. Export "
                   "the record level only.", columns=mixed)
    dupes = sorted({h for h in headers if headers.count(h) > 1 and h.strip()})
    if dupes:
        fnd.note("duplicate_header_names", f"these column names occur more than once: {dupes}",
                 columns=dupes)

    # --- decimal mark and grouping (decided by the grid from the first SNIFF_ROWS rows) --------
    decimal = grid.decimal
    sample = grid.sample_text
    if decimal == "." and _GROUPED_POINT.search(sample):
        fnd.note("thousands_grouping", "values use ',' as a thousands separator; it is removed "
                 "before parsing")
    if decimal == "," and _GROUPED_POINT.search(sample):
        fnd.refuse("decimal_mark_conflict",
                   "the profile declares a decimal comma but the data contains numbers grouped "
                   "as 1,234.5. Parsing either way would truncate values.")
    fnd.raise_if_refused(path.name)

    # --- resolve every binding --------------------------------------------
    cols, text_cols, resolved, invalid, claimed = _bind(p, headers, grid.units, fnd, grid.fetch)
    grid.release()
    fnd.raise_if_refused(path.name)

    n = grid.n
    t, i, e = cols["test_time_second"], cols["current_ampere"], cols["voltage_volt"]
    check_time(fnd, t, resolved["test_time_second"]["column"], cols.get("step_id"))
    check_single_channel(fnd, cols, tuple(headers))
    fnd.raise_if_refused(path.name)

    # --- normalise direction to charge-positive, once, at the boundary ---
    c = p.conventions
    step_kind = None
    if "step_type" in text_cols:
        unmapped = sorted({s for s in text_cols["step_type"] if s and s not in c.step_type_map})
        if unmapped and c.direction_source == "step_type":
            raise ImportFailure(
                "unmapped_step_type",
                f"step types not in the profile's step_type_map: {unmapped}. A step type the "
                "profile does not know would silently land in the wrong branch, so the import "
                "stops. Add it to step_type_map.")
        step_kind = [c.step_type_map.get(s, "other") for s in text_cols["step_type"]]

    sign_decision = c.current_sign
    if c.current_sign == "detect":
        has_negative = bool(np.any(i[np.isfinite(i)] < 0))
        if has_negative:
            sign_decision = "charge_positive"
        elif step_kind and any(k != "rest" and s for k, s in zip(step_kind, text_cols["step_type"])):
            sign_decision = "unsigned"
        else:
            raise ImportFailure(
                "ambiguous_sign",
                "no negative current and no usable step type: the file cannot "
                "establish charge from discharge, so the import stops")
        fnd.note("current_sign_detected", f"detection concluded {sign_decision}",
                 decided=sign_decision, had_negative_current=has_negative)

    if sign_decision == "discharge_positive":
        i = -i
    elif sign_decision == "unsigned":
        if not step_kind or len(step_kind) != n:
            raise ImportFailure("no_direction", "unsigned current needs a step type on every row")
        missing_kind = np.array([not s for s in text_cols["step_type"]])
        if any(k == "other" and not m for k, m in zip(step_kind, missing_kind)):
            raise ImportFailure(
                "no_direction",
                "unsigned current and a step type that states no direction: "
                "every step type must map to charge, discharge, rest or ocv")
        # "cc_discharge" also ends in "charge": test for discharge first.
        sign = np.array([0.0 if k in ("rest", "ocv") else (-1.0 if "discharge" in k else 1.0)
                         for k in step_kind])
        i = np.abs(i) * sign
        # an empty step-type cell is a missing value, not a step type: that row has no direction,
        # so its current is not used (a cut-off last line, as in cellpy's maccor_two.txt)
        if missing_kind.any():
            i = np.where(missing_kind, np.nan, i)
            fnd.warn("step_type_missing",
                     f"{int(missing_kind.sum())} row(s) have no step type, and with an unsigned current "
                     "the step type is the only statement of direction; their current is not used",
                     rows=int(missing_kind.sum()))
    elif sign_decision == "charge_positive" and step_kind:
        _cross_check_sign_against_step_type(fnd, i, step_kind, cols.get("step_id"))

    # --- the declared capacity semantics are a claim: measure them ---
    consistent = _consistent_capacity_semantics(cols, cols.get("step_id"), cols.get("cycle_count"))
    measured = (next(s for s in _SEMANTICS_ORDER if s in consistent) if consistent else None)
    cumulative_family = ("step_cumulative", "cycle_cumulative", "test_cumulative")
    if (c.verify_capacity_semantics and consistent is not None
            and c.capacity_semantics in cumulative_family
            and c.capacity_semantics not in consistent):
        raise ImportFailure(
            "capacity_semantics_mismatch",
            f"the profile declares {c.capacity_semantics} but the counter in this file "
            f"behaves as {measured or 'none of the cumulative kinds'}. Arbin's reset behaviour "
            "depends on the schedule, so this is checked per file rather than assumed. Correct "
            "the profile or set verify_capacity_semantics=False after deciding which is right.")

    dq = _increments(cols, c.capacity_semantics, cols.get("step_id"), cols.get("cycle_count"), n, i)
    cross = check_counter_against_integral(fnd, dq, t, i, cols.get("step_id"))
    sign_vs_voltage = check_sign_against_voltage(fnd, i, e, cols.get("step_id"))
    if cols.get("cycle_count") is not None:
        _check_cycle_numbering(fnd, cols["cycle_count"], c.cycle_base)
    fnd.raise_if_refused(path.name)

    report = {
        "profile": p.name,
        "instrument": p.instrument,
        "rows": n,
        "decimal": decimal,
        "columns_resolved": resolved,
        "columns_unresolved": [r for r in p.bindings if r not in resolved],
        "columns_unused": [h for k, h in enumerate(headers) if k not in claimed and h.strip()],
        "invalid_tokens": invalid,
        "assumed_bindings": [r for r, d in resolved.items() if d.get("assumed")],
        "current_sign_declared": c.current_sign,
        "current_sign_applied": "charge_positive",
        "capacity_semantics": c.capacity_semantics,
        "instrument_increment_available": dq is not None,
        "capacity_semantics_measured": measured,
        "capacity_semantics_consistent": sorted(consistent) if consistent is not None else None,
        "capacity_semantics_verified": bool(consistent is not None and consistent == {c.capacity_semantics}),
        "counter_vs_integral": cross,
        "sign_vs_voltage": sign_vs_voltage,
        "warnings": len(fnd.warnings),
    }
    return RawTable(
        source_name=path.name,
        source_sha256=grid.sha256,
        profile=p.name,
        n=n, t=t, i=i, e=e,
        step_id=cols.get("step_id"),
        cycle=cols.get("cycle_count"),
        step_kind=step_kind,
        q_charge=cols.get("charging_capacity_ah"),
        q_discharge=cols.get("discharging_capacity_ah"),
        dq=dq,
        temperature=cols.get("surface_temperature_celsius", cols.get("ambient_temperature_celsius")),
        columns=tuple(headers),
        report=report,
        findings=fnd.as_list(),
    )


# ----------------------------------------------------------- cross-checks
def _cross_check_sign_against_step_type(fnd: Findings, i: np.ndarray, step_kind: list[str],
                                        step_id: np.ndarray | None) -> None:
    """A signed current file that also states step types has two independent
    statements of direction. When they disagree the profile's sign convention
    is backwards, which is the single most damaging import error there is."""
    kinds = np.array(step_kind)
    disagree = 0
    total = 0
    for want, mask in (("charge", np.char.find(kinds, "discharge") < 0),
                       ("discharge", np.char.find(kinds, "discharge") >= 0)):
        m = mask & (kinds != "rest") & (kinds != "ocv") & (kinds != "other") & np.isfinite(i)
        if not m.any():
            continue
        total += int(m.sum())
        net = float(np.nanmean(i[m]))
        if (want == "charge" and net < 0) or (want == "discharge" and net > 0):
            disagree += int(m.sum())
    if total and disagree:
        fnd.refuse(
            "sign_contradicts_step_type",
            f"the signed current disagrees with the step type on {disagree} of {total} rows. "
            "Either current_sign is declared backwards or step_type_map is. Both statements of "
            "direction must agree before any capacity is computed.",
            rows_disagreeing=disagree, rows_checked=total)


def _check_cycle_numbering(fnd: Findings, cycle: np.ndarray, base: int) -> None:
    finite = cycle[np.isfinite(cycle)]
    if finite.size == 0:
        return
    first = float(finite[0])
    if first != base:
        fnd.warn("cycle_base_mismatch",
                 f"the profile declares cycle numbering from {base} but the first cycle number "
                 f"in the file is {first:g}. Cycle labels in the results would be off by "
                 f"{first - base:g}.", declared=base, observed=first)
    if np.any(np.diff(finite) < 0):
        fnd.warn("cycle_counter_decreases",
                 "the cycle counter decreases somewhere in the file, which usually means two "
                 "runs were concatenated. Cycles must be re-indexed before pairing.")


_SEMANTICS_ORDER = ("test_cumulative", "cycle_cumulative", "step_cumulative")


def _consistent_capacity_semantics(cols, step_id, cycle) -> set[str] | None:
    """Every counter behaviour the file does not contradict.

    Evidence comes from the counter at boundaries, nothing else:
    - a drop anywhere rules out test_cumulative, and a drop that is not at a step
      (or cycle) boundary rules out resetting there;
    - a non-zero value carried unchanged or increased across a step boundary rules
      out step_cumulative, and across a cycle boundary rules out cycle_cumulative.

    A file can leave several behaviours open: a counter that never decreases in a
    single-cycle file is test- or cycle-cumulative, and nothing in it decides
    between the two. The declaration is then accepted as consistent, not as
    verified. Every non-negative counter bound is examined and the conclusions
    intersected; a signed net counter falls during discharge without resetting,
    so it says nothing here. Returns None when no counter can be examined.
    """
    open_ = set(_SEMANTICS_ORDER)
    seen = False
    for role in ("charging_capacity_ah", "discharging_capacity_ah",
                 "step_cumulative_capacity_ah", "cycle_cumulative_capacity_ah"):
        q = cols.get(role)
        if q is None or q.size < 3 or not np.any(np.isfinite(q)):
            continue
        seen = True
        scale = float(np.nanmax(np.abs(q))) or 1.0
        tol = 1e-9 * scale
        prev, cur = q[:-1], q[1:]
        ok = np.isfinite(prev) & np.isfinite(cur)
        drop = ok & (cur < prev - tol)
        carried = ok & (prev > tol) & (cur >= prev - tol)
        if drop.any():
            open_.discard("test_cumulative")
        for name, group in (("step_cumulative", step_id), ("cycle_cumulative", cycle)):
            if group is None or group.size != q.size:
                open_.discard(name)
                continue
            boundary = group[1:] != group[:-1]
            if np.any(drop & ~boundary) or np.any(carried & boundary):
                open_.discard(name)
    return open_ if seen else None


def _measure_capacity_semantics(cols, step_id, cycle) -> str | None:
    """Decide from the data how the instrument's counter actually behaves.

    The simplest behaviour the file does not contradict (test- before cycle-
    before step-cumulative), from _consistent_capacity_semantics. This is
    measured rather than assumed because the published descriptions disagree
    and the behaviour is configurable: in the real files read for P08d, Arbin's
    counters reset at each cycle (battery-data-toolkit and battetl exports),
    Neware's and Maccor's at each step, and Arbin schedules can issue explicit
    capacity resets. Returns None when the file cannot say.
    """
    consistent = _consistent_capacity_semantics(cols, step_id, cycle)
    if not consistent:
        return None
    return next(s for s in _SEMANTICS_ORDER if s in consistent)


def _increments(cols, semantics, step_id, cycle, n, i=None) -> np.ndarray | None:
    """Convert whatever capacity counter exists into signed Ah per row.

    Charge-positive. Returns None when the file carries no usable counter, in
    which case the engine integrates the sampled current and says so.

    A throughput counter (BDF step_cumulative_capacity_ah or
    cycle_cumulative_capacity_ah: one unsigned accumulator that resets at each
    step or cycle, as Maccor's single Amp-hr column does) states how much charge
    passed but not which way. The direction of each increment is taken from the
    charge-positive current of the row it belongs to, which the reader has
    already normalised; an increment on a row carrying no current is not
    counted, and the counter-against-integral check reports any charge lost so.
    """
    if semantics == "none":
        return None
    qc, qd = cols.get("charging_capacity_ah"), cols.get("discharging_capacity_ah")
    net = cols.get("net_capacity_ah")
    throughput = next((cols[r] for r in ("step_cumulative_capacity_ah", "cycle_cumulative_capacity_ah")
                       if r in cols), None)
    if semantics == "per_row_increment":
        if net is not None:
            return net
        if qc is not None or qd is not None:
            return (qc if qc is not None else 0) - (qd if qd is not None else 0)
        return None

    def undo_cumulative(series: np.ndarray, group: np.ndarray | None) -> np.ndarray:
        d = np.diff(series, prepend=series[0])
        if group is not None:
            starts = np.flatnonzero(np.diff(group, prepend=group[0]) != 0)
            d[starts] = series[starts]
        d[0] = 0.0
        return np.where(d < 0, 0.0, d)   # a reset mid-group is not negative charge

    group = {"step_cumulative": step_id, "cycle_cumulative": cycle,
             "test_cumulative": None}[semantics]
    if net is not None:
        return np.diff(net, prepend=net[0])
    if throughput is not None and qc is None and qd is None:
        if i is None:
            return None
        mag = undo_cumulative(throughput, group)
        # the increment on row k belongs to row k's step, so its direction is row k's current;
        # where that reads exactly zero (the last point of a decaying tail) the previous row's
        direction = np.sign(np.nan_to_num(i))
        prev = np.concatenate(([0.0], direction[:-1]))
        direction = np.where(direction == 0, prev, direction)
        return mag * direction
    parts = []
    if qc is not None:
        parts.append(undo_cumulative(qc, group))
    if qd is not None:
        parts.append(-undo_cumulative(qd, group))
    if not parts:
        return None
    return np.sum(parts, axis=0)
