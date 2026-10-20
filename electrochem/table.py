"""Numeric measurement table built from an imported EC-Lab file.

The importers keep original tokens and bytes. This module turns one imported
file into NumPy arrays selected by column *name*, so the same call works for
an .mpt export and an .mpr binary of the same experiment. Nothing scientific
is decided here: current direction and potential meaning stay unresolved
until the analysis settings state them.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

import numpy as np

# Column names as EC-Lab and BT-Lab write them. Order = preference.
TIME_NAMES = ("time/s",)
CURRENT_NAMES = ("I/mA", "<I>/mA", "I/A", "<I>/A", "I/µA", "I/uA", "<I>/µA", "<I>/uA")
POTENTIAL_NAMES = ("Ecell/V", "Ewe/V", "<Ewe>/V", "Ewe-Ece/V", "<Ewe-Ece>/V", "Ece/V")
# What each potential column measures, for choosing between them once the researcher has said what the
# analysis needs (review finding r15): the working electrode against the reference, or the cell voltage.
# A two-electrode .mpr names its only potential column Ewe/V although it is then the cell voltage, and the
# text export of the same run may call it Ecell/V; when a file has one potential column, that column is used.
WORKING_NAMES = ("Ewe/V", "<Ewe>/V")
CELL_NAMES = ("Ecell/V", "Ewe-Ece/V", "<Ewe-Ece>/V")
STEP_NAMES = ("Ns",)
MODE_NAMES = ("mode",)
OXRED_NAMES = ("ox/red",)
ERROR_NAMES = ("error",)
HALF_CYCLE_NAMES = ("half cycle",)
CYCLE_NAMES = ("cycle number",)
INSTRUMENT_Q_NAMES = ("Q charge/discharge/mA.h", "(Q-Qo)/mA.h", "(Q-Qo)/C")
DQ_NAMES = ("dq/mA.h", "dQ/mA.h", "dq/C", "dQ/C")
STEP_TIME_NAMES = ("step time/s",)
TEMPERATURE_NAMES = ("Temperature/°C", "Temperature/C", "Temperature/\u00b0C")

UNIT_SCALE = {"A": 1.0, "mA": 1e-3, "µA": 1e-6, "uA": 1e-6, "V": 1.0, "mV": 1e-3, "s": 1.0,
              "mA.h": 3.6, "A.h": 3600.0, "C": 1.0}  # to SI (A, V, s, C)

MODE_LABELS = {1: "constant_current", 2: "constant_voltage", 3: "rest"}


@dataclass
class Table:
    source_name: str
    source_sha256: str
    format: str
    columns: tuple[str, ...]
    t: np.ndarray                      # s
    i: np.ndarray | None               # A, nan where missing/invalid
    e: np.ndarray | None               # V
    ns: np.ndarray | None              # native step index
    mode: np.ndarray | None            # 1 CC, 2 CV, 3 rest
    oxred: np.ndarray | None           # 1 oxidation (positive current), 0 reduction
    error: np.ndarray | None
    half_cycle: np.ndarray | None
    cycle: np.ndarray | None           # instrument cycle number
    q_instrument: np.ndarray | None    # C, instrument running charge
    dq: np.ndarray | None              # C, instrument charge increment since previous row
    temperature: np.ndarray | None = None  # degC
    invalid_rows: dict[str, int] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    header: tuple[str, ...] = ()
    potentials: dict[str, np.ndarray] = field(default_factory=dict)   # every potential column, V

    @property
    def n(self) -> int:
        return len(self.t)

    def header_value(self, key: str) -> str | None:
        for line in self.header:
            if line.startswith(key):
                rest = line[len(key):].strip()
                if rest.startswith(":"):
                    return rest[1:].strip()
        return None


def _unit_of(name: str) -> str:
    return name.rsplit("/", 1)[1] if "/" in name else ""


def _pick(columns, names):
    for name in names:
        if name in columns:
            return columns.index(name)
    return None


_NUM = re.compile(r"[+-]?(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)(?:[eE][+-]?[0-9]+)?")


def _floats(tokens, decimal="."):
    """Strict token conversion. Anything that is not a plain number becomes nan."""
    out = np.full(len(tokens), np.nan)
    bad = 0
    for k, tok in enumerate(tokens):
        s = tok.strip() if isinstance(tok, str) else ""
        if s and _NUM.fullmatch(s):
            out[k] = float(s.replace(decimal, "."))
        else:
            bad += 1
    return out, bad


def _column(rows, idx, decimal="."):
    if idx is None:
        return None, 0
    return _floats([r[idx] for r in rows], decimal)


def _build(source_name, sha, fmt, columns, rows, decimal, header=()):
    """A Table from rows of string tokens (the strict path: every token checked, invalid ones counted)."""
    return _assemble(source_name, sha, fmt, columns, lambda idx: _column(rows, idx, decimal), header)


def _assemble(source_name, sha, fmt, columns, column, header=()):
    """A Table from `column(idx) -> (float array, invalid count)`, whichever source feeds it."""
    columns = tuple(columns)
    picks = {
        "time": _pick(columns, TIME_NAMES),
        "current": _pick(columns, CURRENT_NAMES),
        "potential": _pick(columns, POTENTIAL_NAMES),
        "step": _pick(columns, STEP_NAMES),
        "mode": _pick(columns, MODE_NAMES),
        "oxred": _pick(columns, OXRED_NAMES),
        "error": _pick(columns, ERROR_NAMES),
        "half_cycle": _pick(columns, HALF_CYCLE_NAMES),
        "cycle": _pick(columns, CYCLE_NAMES),
        "q_instrument": _pick(columns, INSTRUMENT_Q_NAMES),
        "dq": _pick(columns, DQ_NAMES),
        "temperature": _pick(columns, TEMPERATURE_NAMES),
    }
    if picks["time"] is None:
        raise ValueError(f"No time/s column in {source_name}; columns: {columns}")
    arrays, invalid = {}, {}
    for key, idx in picks.items():
        arr, bad = column(idx) if idx is not None else (None, 0)
        if arr is not None:
            name = columns[idx]
            scale = UNIT_SCALE.get(_unit_of(name), 1.0) if key in ("current", "potential", "time", "q_instrument", "dq") else 1.0
            arrays[key] = arr * scale
            invalid[name] = bad
    labels = {k: columns[v] for k, v in picks.items() if v is not None}
    potentials = {}
    for name in POTENTIAL_NAMES:
        if name in columns:
            idx = columns.index(name)
            potentials[name] = arrays["potential"] if idx == picks["potential"] else \
                column(idx)[0] * UNIT_SCALE.get(_unit_of(name), 1.0)
    return Table(
        source_name=source_name, source_sha256=sha, format=fmt, columns=columns,
        t=arrays["time"], i=arrays.get("current"), e=arrays.get("potential"),
        ns=arrays.get("step"), mode=arrays.get("mode"), oxred=arrays.get("oxred"),
        error=arrays.get("error"), half_cycle=arrays.get("half_cycle"), cycle=arrays.get("cycle"),
        q_instrument=arrays.get("q_instrument"), dq=arrays.get("dq"), temperature=arrays.get("temperature"),
        invalid_rows={k: v for k, v in invalid.items() if v}, labels=labels, header=tuple(header),
        potentials=potentials,
    )


def with_potential(tab: Table, role: str | None) -> Table:
    """The table with the potential column that measures what the analysis needs.

    role "working": the working electrode against the reference (a half-cell answer);
    role "cell": the two-electrode cell voltage (a full-cell answer); None: unchanged.
    Only a file with both kinds of column (a three-electrode measurement) changes.
    """
    from dataclasses import replace
    if role not in ("working", "cell") or len(tab.potentials) < 2:
        return tab
    for name in (WORKING_NAMES if role == "working" else CELL_NAMES):
        if name in tab.potentials:
            if tab.labels.get("potential") == name:
                return tab
            return replace(tab, e=tab.potentials[name], labels={**tab.labels, "potential": name})
    if role == "cell" and "Ewe/V" in tab.potentials and "Ece/V" in tab.potentials:
        # three-electrode file without a cell-voltage column: EC-Lab defines Ecell = Ewe - Ece
        return replace(tab, e=tab.potentials["Ewe/V"] - tab.potentials["Ece/V"],
                       labels={**tab.labels, "potential": "derived: Ewe/V - Ece/V"})
    return tab


def from_text(parsed, decimal=".") -> Table:
    """Build a Table from eclab_import.text.parse() output."""
    columns = [c.original_name for c in parsed.source.columns]
    rows = [r.fields for r in parsed.rows]
    header = [line.text for line in parsed.header]
    return _build(parsed.source.original_name, parsed.source.sha256, "mpt", columns, rows, decimal, header)


def from_native(native) -> Table:
    """Build a Table from eclab_import.native.inspect_native() output."""
    fields = [f.backend_label for f in native.fields]
    flags = [f.backend_label for f in native.flags]
    columns = fields + flags
    flag_masks = [(f.mask, f.dtype) for f in native.flags]
    flag_col = fields.index("flags") if "flags" in fields else None
    rows = []
    for r in native.rows:
        vals = list(r.decoded_text)
        if flag_col is not None:
            raw = int(float(vals[flag_col]))
            for mask, _ in flag_masks:
                shift = (mask & -mask).bit_length() - 1
                vals.append(str((raw & mask) >> shift))
        else:
            vals.extend([""] * len(flag_masks))
        rows.append(vals)
    return _build(native.source.original_name, native.source.sha256, "mpr", columns, rows, ".")


# ---------------------------------------------------------------- fast paths for large files (P08f)
# The P03 importers in eclab_import keep every token of every row as a record, which is right for
# provenance and far too heavy for a million-row export (33 s and 2 GB for 1M rows of text; minutes
# for a large .mpr). The cycling workflow reads the same files through numpy instead: the text data
# block through numpy's C parser, the binary records straight from the decoded array. Both give the
# Table the strict builders give, which a test checks on every public file; whenever the fast path
# meets something it does not handle (a non-numeric token, an odd line ending, a short row) it steps
# aside and the strict path takes over, so no file is read by a looser rule.

_LINE_BREAK = re.compile(rb"\r\n|\n|\r")
TEXT_SIGNATURES = (b"EC-Lab ASCII FILE", b"BT-Lab ASCII FILE")
MAX_TEXT_BYTES = 2 * 1024 ** 3


def _text_header(data: bytes, encoding: str):
    """(header lines, column names, data block) of a signed EC-Lab export, or None when the file is not
    one the fast path reads (the strict parser then reports exactly what is wrong)."""
    if not data.startswith(TEXT_SIGNATURES):
        return None
    breaks = []
    for m in _LINE_BREAK.finditer(data, 0, min(len(data), 1 << 20)):
        breaks.append((m.start(), m.end()))
        if len(breaks) == 2:
            break
    if len(breaks) < 2:
        return None
    try:
        second = data[breaks[0][1]:breaks[1][0]].decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None
    m = re.fullmatch(r"Nb header lines\s*:\s*([0-9]+)\s*", second)
    if not m:
        return None
    count = int(m.group(1))
    if count < 3:
        return None
    ends = []
    for k, mm in enumerate(_LINE_BREAK.finditer(data)):
        ends.append((mm.start(), mm.end()))
        if len(ends) == count:
            break
    if len(ends) < count:
        return None
    try:
        text = data[:ends[-1][0]].decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return None
    lines = _LINE_BREAK.split(text.encode("utf-8"))      # the same breaks, line by line
    lines = [l.decode("utf-8") for l in lines]
    if len(lines) != count:
        return None
    return lines[:-1], lines[-1].split("\t"), data[ends[-1][1]:]


def _fast_text(data: bytes, name: str, encoding: str, decimal: str) -> Table | None:
    """The Table of a signed EC-Lab text export through numpy's C parser, or None for the strict path."""
    parts = _text_header(data, encoding)
    if parts is None:
        return None
    header, names, block = parts
    if not block.strip():
        return None
    columns = tuple(names)
    wanted = sorted({idx for idx in (
        _pick(columns, TIME_NAMES), _pick(columns, CURRENT_NAMES), _pick(columns, POTENTIAL_NAMES),
        _pick(columns, STEP_NAMES), _pick(columns, MODE_NAMES), _pick(columns, OXRED_NAMES),
        _pick(columns, ERROR_NAMES), _pick(columns, HALF_CYCLE_NAMES), _pick(columns, CYCLE_NAMES),
        _pick(columns, INSTRUMENT_Q_NAMES), _pick(columns, DQ_NAMES), _pick(columns, TEMPERATURE_NAMES),
        *(columns.index(n) for n in POTENTIAL_NAMES if n in columns)) if idx is not None})
    if not wanted:
        return None
    if re.search(rb"[a-dA-Df-wF-WyzYZ]", block):     # any letter but an exponent's e/E or EC-Lab's XXX: numpy
        return None                                   # would accept nan/inf; the strict path counts them invalid
    if block.count(b"\r") != block.count(b"\r\n"):
        return None                                   # bare carriage returns: the strict parser's business
    invalid = {}
    if b"XXX" in block:                               # EC-Lab's undefined value, usually in a technique's first row
        for m in re.finditer(rb"[^\r\n]*XXX[^\r\n]*", block):
            for k, tok in enumerate(m.group(0).split(b"\t")):
                if tok.strip() == b"XXX" and k in wanted:
                    invalid[k] = invalid.get(k, 0) + 1
        block = block.replace(b"XXX", b"nan")
    if decimal == ",":
        block = block.replace(b",", b".")
    import io
    try:
        arr = np.loadtxt(io.BytesIO(block), delimiter="\t", usecols=wanted, dtype=np.float64, ndmin=2,
                         encoding="latin1")
    except (ValueError, IndexError, TypeError):
        return None
    n_breaks = block.count(b"\n")
    expected = n_breaks if block.endswith(b"\n") else n_breaks + 1
    if arr.shape[0] != expected or arr.shape[1] != len(wanted):
        return None
    where = {idx: k for k, idx in enumerate(wanted)}
    return _assemble(name, hashlib.sha256(data).hexdigest(), "mpt", columns,
                     lambda idx: (arr[:, where[idx]].copy(), invalid.get(idx, 0)), header)


def _fast_native(data: bytes, name: str) -> Table:
    """The Table of an .mpr straight from the decoded record array (the same integrity checks as
    eclab_import.native.inspect_native, the same failure codes, no per-row records)."""
    import tempfile
    from pathlib import Path
    from eclab_import.native import ImportFailure, backend
    mod, _np = backend()
    if not data.startswith(mod.MPR_MAGIC):
        raise ImportFailure("native_signature", "Not a supported MPR signature")
    try:
        with tempfile.TemporaryDirectory(prefix="eclab-native-") as d:
            p = Path(d) / "source.mpr"
            p.write_bytes(data)
            obj = mod.MPRfile(str(p), error_on_unknown_column=True)
    except (ValueError, IOError, AssertionError, NotImplementedError, IndexError, UnboundLocalError, RuntimeError) as exc:
        raise ImportFailure("native_decode_failed", type(exc).__name__ + ": " + str(exc)) from exc
    array = obj.data
    if int(obj.npts.item()) != len(array):
        raise ImportFailure("native_record_count", "Declared record count differs from decoded count")
    previous_end = 0
    for m in obj.modules:
        off, length = int(m["offset"]), int(m["length"])
        if off < previous_end or off + length > len(data) or data[off:off + length] != m["data"]:
            raise ImportFailure("native_module_bounds", "Decoded module does not match original bytes")
        previous_end = off + length
    if previous_end != len(data):
        raise ImportFailure("native_trailing_data", "Not all input bytes belong to decoded modules")
    dm = [m for m in obj.modules if m["shortname"] == b"VMP data  "]
    if len(dm) != 1:
        raise ImportFailure("native_data_modules", "Exactly one data module required")
    offset = int(dm[0]["offset"]) + len(dm[0]["data"]) - array.nbytes
    if data[offset:offset + array.nbytes] != array.tobytes():
        raise ImportFailure("native_record_bytes", "Array does not reproduce source record bytes")
    fields = list(array.dtype.names)
    for label in fields:
        if array.dtype.fields[label][0].kind not in "fiub" or array.dtype.fields[label][0].shape:
            raise ImportFailure("native_dtype_unsupported", "Only contiguous scalar numerical fields are accepted")
    flags = [(n, int(mask)) for n, (mask, _dtype) in obj.flags_dict.items()]
    columns = fields + [n for n, _ in flags]
    raw_flags = array["flags"].astype(np.int64) if "flags" in fields else None

    def column(idx):
        if idx < len(fields):
            return array[fields[idx]].astype(np.float64), 0
        _n, mask = flags[idx - len(fields)]
        if raw_flags is None:
            return np.full(len(array), np.nan), len(array)
        shift = (mask & -mask).bit_length() - 1
        return ((raw_flags & mask) >> shift).astype(np.float64), 0

    return _assemble(name, hashlib.sha256(data).hexdigest(), "mpr", columns, column)


class UnsupportedTechnique(ValueError):
    """The file is not galvanostatic cycling data."""


CYCLING_TECHNIQUES = ("galvanostatic cycling", "gcpl", "modulo bat", "constant current", "battery capacity determination",
                      "cccv", "galvanostatic")
NON_CYCLING_COLUMNS = {"freq/Hz": "impedance spectroscopy (EIS)", "Re(Z)/Ohm": "impedance spectroscopy (EIS)"}


def check_technique(tab: Table):
    """Raise UnsupportedTechnique for CV, EIS, CA and similar files with a message the user can act on."""
    for col, what in NON_CYCLING_COLUMNS.items():
        if col in tab.columns:
            raise UnsupportedTechnique(f"{tab.source_name} is {what}. This version analyses galvanostatic cycling "
                                       "(GCPL, CC, CCCV) only; impedance and CV analysis are planned.")
    tech = tab.header[3].strip().lower() if len(tab.header) > 3 else ""
    if tech and not any(k in tech for k in CYCLING_TECHNIQUES):
        raise UnsupportedTechnique(f"{tab.source_name} was recorded with '{tab.header[3].strip()}'. This version analyses "
                                   "galvanostatic cycling (GCPL, CC, CCCV) only.")
    if tab.mode is not None and np.all(np.isfinite(tab.mode)) and not np.any(tab.mode == 1):
        raise UnsupportedTechnique(f"{tab.source_name} contains no galvanostatic step (EC-Lab mode 1): it looks like a "
                                   "potentiostatic technique (CV, CA, PITT). This version analyses galvanostatic cycling only.")
    if tab.i is None:
        raise UnsupportedTechnique(f"{tab.source_name} has no measured current column (columns: {', '.join(tab.columns)}); "
                                   "export the file from EC-Lab with I/mA included.")


def _sniff_decimal(data: bytes, encoding: str) -> str:
    """',' when the numeric fields of the first data rows use a decimal comma (French/German Windows exports)."""
    try:
        text = data[:200000].decode(encoding, errors="replace")
    except LookupError:
        return "."
    lines = text.splitlines()
    n = 0
    for k, line in enumerate(lines[:3]):
        if line.startswith("Nb header lines"):
            try:
                n = int(line.split(":")[1])
            except ValueError:
                n = 0
    sample = "\n".join(lines[n:n + 20])
    return "," if re.search(r"\d,\d+(?:[eE][+-]?\d+)?", sample) and not re.search(r"\d\.\d", sample) else "."


def load(path, *, native=False, encoding="cp1252", decimal=None, missing_terminal_empty_field=True, check=True,
         fast=True) -> Table:
    """Read one EC-Lab file from disk into a Table.

    decimal=None sniffs '.' or ',' from the data. check=True rejects files that are not cycling data.
    A missing measured current is derived from the instrument's dq increments (I = dq/dt) when those exist.
    fast=True reads through numpy (the fast paths above) and falls back to the P03 importers whenever a
    file needs their token-by-token care; fast=False is the strict path itself, for cross-checks.
    """
    from pathlib import Path
    from eclab_import.text import parse, Options

    data = Path(path).read_bytes()
    name = Path(path).name
    if native or name.lower().endswith(".mpr") or data.startswith(b"BIO-LOGIC MODULAR FILE"):
        tab = _fast_native(data, name) if fast else None
        if tab is None:
            from eclab_import.native import inspect_native
            tab = from_native(inspect_native(data, name))
    else:
        dec = decimal or _sniff_decimal(data, encoding)
        tab = _fast_text(data, name, encoding, dec) if fast else None
        if tab is None:
            if len(data) > MAX_TEXT_BYTES:
                raise ValueError(f"{name} is larger than 2 GiB")
            parsed = parse(data, name, Options(encoding=encoding, decimal=dec,
                                               missing_terminal_empty_field=missing_terminal_empty_field))
            tab = from_text(parsed, dec)
    if tab.i is None and tab.dq is not None:
        dt = np.diff(tab.t)
        with np.errstate(divide="ignore", invalid="ignore"):
            i = np.where(dt > 0, tab.dq[1:] / dt, np.nan)
        tab.i = np.concatenate(([np.nan], i))
        tab.labels["current"] = "derived: dq/dt"
    if check:
        check_technique(tab)
    return tab
