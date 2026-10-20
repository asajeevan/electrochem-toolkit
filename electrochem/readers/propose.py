"""The universal path: reading a file from a cycler nobody wrote a profile for.

Every cycler on the market exports delimited text or Excel. So the honest claim
is not "we support every instrument" but "every instrument's text export can be
read, and the reader tells you exactly what it assumed."

This module does the part that can be automated (find the table, score each
column against a synonym register, measure the conventions the data can
reveal) and then stops. The conventions a file cannot state about itself are returned
as questions, not guesses. A Proposal is deliberately not an ImportProfile: it
cannot be used to compute anything until a person has answered them.

A large file is not read whole to make a proposal (P08f). The table is found in the first
DETECT_BYTES of a text file (whole lines) or the first DETECT_SHEET_ROWS rows of each worksheet,
which is also all the registry needs to recognise a file; the conventions are then measured on the
first MEASURE_ROWS data rows, and the proposal says so (measured['rows_measured'] and
['rows_total_estimate'], and a question). A file within those limits gives exactly the proposal it
gave when it was read whole.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path

import numpy as np

from .cells import excel_cell_text, parse_duration
from .profile import (UNIT_DIMENSION, UNIT_FACTOR, Binding, Conventions, ImportProfile,
                     Layout, role_dimension)
from .workbook import open_workbook

# A file carrying any of these is not a cycling time series, whatever else it
# contains. Treating a spectrum as a time series produces capacities from
# impedance, which is the worst available failure: plausible and wrong.
NOT_A_TIME_SERIES = {
    "freq": "an impedance spectrum (frequency-domain)",
    "frequency": "an impedance spectrum (frequency-domain)",
    "re z": "an impedance spectrum (frequency-domain)",
    "im z": "an impedance spectrum (frequency-domain)",
}

# ---------------------------------------------------------------- synonyms
# Tier 1 names are unambiguous; tier 2 need the vetoes below to stay honest.
# Sources: BDF canonical names, plus header names observed in the public corpus
# and in vendor documentation. Each entry is a normalised header, not a regex.
SYNONYMS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    #                     tier 1 (specific)                          tier 2 (generic)
    "test_time_second": (("test time", "total time", "run time", "elapsed time",
                          "absolute time", "time stamp", "cumulative time"), ("time", "t")),
    "step_time_second": (("step time", "time in step", "current step time"), ()),
    "current_ampere": (("current", "amps", "amperage", "i meas", "measured current"),
                       ("i", "im", "cur")),
    "voltage_volt": (("voltage", "volts", "cell voltage", "potential", "ewe", "ecell",
                      "terminal voltage", "working electrode potential"), ("v", "u", "e")),
    "charging_capacity_ah": (("charge capacity", "chg cap", "chg capacity", "cap chg",
                              "charging capacity", "capacity charge"), ()),
    "discharging_capacity_ah": (("discharge capacity", "dchg cap", "dchg capacity", "cap dchg",
                                 "discharging capacity", "capacity discharge"), ()),
    "net_capacity_ah": (("dq", "q q0", "net capacity", "charge passed", "ah"), ("capacity", "q")),
    # one unsigned counter restarting at every step: Maccor's Amp-hr (TRI, Birmingham) and Cap.
    # [Ah] (KIT), measured in P08d. Proposed as such, never as a signed net counter
    "step_cumulative_capacity_ah": (("amp hr", "amp hrs", "amphr", "step capacity"), ("cap",)),
    "step_id": (("step index", "step number", "step id", "ns", "step no"), ("step",)),
    "step_count": (("step count",), ()),
    "cycle_count": (("cycle index", "cycle number", "cycle id", "cycle no", "cyc index",
                     "loop counter"), ("cycle", "cyc", "loop")),
    "step_type": (("step type", "state", "status", "step name", "md", "work mode",
                   "operation", "control type"), ("mode",)),
    "ambient_temperature_celsius": (("ambient temperature", "chamber temperature"), ()),
    "surface_temperature_celsius": (("surface temperature", "cell temperature",
                                     "temperature", "temp"), ()),
    "power_watt": (("power",), ()),
    "record_index": (("record index", "data point", "record no", "rec", "index",
                      "point number"), ()),
}

# A header containing one of these never satisfies the role, whatever it scores.
# This is what stops a step-time column becoming the test clock and a control
# setpoint becoming the measured current: two mistakes that produce plausible
# numbers rather than obvious ones.
VETO: dict[str, tuple[str, ...]] = {
    "test_time_second": ("step", "cycle", "relative", "remain"),
    "current_ampere": ("control", "setpoint", "set point", "limit", "target", "nominal",
                       "density", "aux", "integral", "rate"),
    "voltage_volt": ("control", "setpoint", "set point", "limit", "target", "nominal",
                     "aux", "average", "delta", "drop", "ir", "ocv at", "max", "min"),
    "charging_capacity_ah": ("density", "specific", "retention", "efficiency", "spec"),
    "discharging_capacity_ah": ("density", "specific", "retention", "efficiency", "spec"),
    "net_capacity_ah": ("density", "specific", "retention", "efficiency", "spec", "energy"),
    "step_cumulative_capacity_ah": ("density", "specific", "retention", "efficiency", "spec", "energy"),
    "cycle_count": ("time", "capacity", "energy", "efficiency"),
    "step_id": ("time", "capacity", "energy", "type", "name", "mode"),
    "surface_temperature_celsius": ("ambient", "chamber", "set"),
}

_NUMERIC = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][+-]?\d+)?$")

# How much of a file the proposer reads (P08f): enough to find any table whose header lies in its
# first 200 rows (_find_header looks no further), and to measure the conventions on many cycles.
DETECT_BYTES = 8 * 1024 * 1024       # text: the head searched for the table, cut after a line feed
DETECT_SHEET_ROWS = 2000             # workbook: rows of each sheet searched; larger sheets are sized
                                     # from the dimension the sheet declares
MEASURE_ROWS = 200_000               # data rows the conventions are measured on

# Column names that state their own unit. Maccor writes 'Amps' and 'Volts' with
# no parenthetical, and refusing those would make the common case need a manual
# answer. Keyed on the normalised name, so the match is exact, never a guess.
IMPLIED_UNIT: dict[str, str] = {
    "amps": "A", "amperage": "A", "milliamps": "mA", "ma": "mA", "amperes": "A",
    "volts": "V", "millivolts": "mV", "mv": "mV",
    "amp hr": "Ah", "amp hrs": "Ah", "amphr": "Ah", "ah": "Ah", "mah": "mAh",
    "watts": "W",
}


def normalise(header: str) -> str:
    """'DChg. Cap.(mAh)' -> 'dchg cap'; 'Ewe/V' -> 'ewe'; 'TestTime(s)' -> 'test time'.

    CamelCase is split before lowering, because several instruments run words
    together ('TestTime', 'StepIndex') where others separate them.
    """
    s = header.strip().lstrip("﻿")
    s = re.split(r"[(\[/]", s, maxsplit=1)[0]
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    s = re.sub(r"[\W_]+", " ", s).lower()            # \W keeps letters of every script
    return " ".join(s.split())


@dataclass
class Candidate:
    role: str
    column: str
    index: int
    score: int
    reason: str
    unit: str | None


@dataclass
class Proposal:
    """A draft, with every uncertainty named. Not usable until answered."""

    path: Path
    layout: Layout
    headers: list[str]
    bindings: dict[str, Binding]
    chosen: dict[str, Candidate]
    rejected: dict[str, list[Candidate]] = field(default_factory=dict)
    unit_unknown: dict[str, str] = field(default_factory=dict)
    unmapped_columns: list[str] = field(default_factory=list)
    measured: dict = field(default_factory=dict)
    questions: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    preview: list[list[str]] = field(default_factory=list)
    """The first data rows as written, for a review screen to show beside the proposed mapping."""
    prior: object = None
    """A saved ImportProfile whose columns overlap this file's (the same instrument, another export
    layout), from which a review screen pre-fills the conventions. The conventions are still
    confirmed by the person; nothing is computed from the prior alone."""
    prior_shared: list[str] = field(default_factory=list)
    """The column names the prior and this file share."""

    @property
    def ready(self) -> bool:
        return not self.blocking

    def summary(self) -> str:
        lines = [f"{self.path.name}: {self.layout.kind}, {len(self.headers)} columns",
                 "", "Proposed mapping (all marked assumed until confirmed):"]
        for role, c in sorted(self.chosen.items()):
            alt = self.rejected.get(role, [])
            tail = f"   [also considered: {', '.join(a.column for a in alt[:3])}]" if alt else ""
            lines.append(f"  {role:<30} <- {c.column!r} ({c.reason}){tail}")
        missing = [r for r in ("test_time_second", "current_ampere", "voltage_volt")
                   if r not in self.chosen]
        if missing:
            lines += ["", f"No column found for: {', '.join(missing)}"]
        if self.unmapped_columns:
            lines += ["", f"Not mapped ({len(self.unmapped_columns)}): "
                          + ", ".join(self.unmapped_columns)]
        if self.measured:
            lines += ["", "Measured from the data:"]
            lines += [f"  {k}: {v}" for k, v in self.measured.items()]
        if self.questions:
            lines += ["", "Confirm before any result is computed:"]
            lines += [f"  - {q}" for q in self.questions]
        if self.blocking:
            lines += ["", "Cannot proceed until answered:"]
            lines += [f"  ! {q}" for q in self.blocking]
        return "\n".join(lines)

    def to_profile(self, name: str, instrument: str, conventions: Conventions) -> ImportProfile:
        """Build a real profile once a person has supplied the conventions.

        The bindings stay marked assumed, so every result carries the fact that
        this mapping was proposed by software and not verified against a
        reference measurement.
        """
        return ImportProfile(name=name, instrument=instrument, layout=self.layout,
                             conventions=conventions, bindings=self.bindings)


# ------------------------------------------------------------ layout finding
def _numeric_fraction(row: list[str]) -> float:
    vals = [c.strip() for c in row if c.strip()]
    if not vals:
        return 0.0
    return sum(1 for v in vals if _NUMERIC.match(v.replace(",", "."))) / len(vals)


def _find_header(grid: list[list[str]]) -> int | None:
    """The header is the last mostly-textual row above a run of mostly-numeric
    rows of the same width. Works for any preamble length, which matters because
    Maccor writes 1, 2, 3 or 12 preamble lines depending on the export dialog
    and EC-Lab's preamble length depends on the technique."""
    best = None
    for k, row in enumerate(grid[:200]):
        if len([c for c in row if c.strip()]) < 3:
            continue
        if _numeric_fraction(row) > 0.4:
            continue
        follow = [r for r in grid[k + 1:k + 6] if any(c.strip() for c in r)]
        if not follow:
            continue
        same_width = [r for r in follow if len(r) in (len(row), len(row) - 1, len(row) + 1)]
        if len(same_width) >= min(2, len(follow)) and _numeric_fraction(same_width[0]) >= 0.5:
            best = k
    return best


@dataclass
class _Detected:
    """What layout detection found, and how much of the file it saw."""
    layout: Layout
    header: list[str]
    rows: list[list[str]]
    complete: bool              # rows holds every data row of the table
    header_index: int           # 0-based row of the header in the grid (text) or in each sheet
    sheets: dict = field(default_factory=dict)  # workbook: sheet name -> declared max_row, for the
                                                # sheets whose header row matches


def detect_layout(path: Path) -> tuple[Layout, list[str], list[list[str]]]:
    """(layout, header row, data rows) of the table in this file. The rows are those found in the
    part of the file searched (all of them when the file is within DETECT_BYTES, or its sheets
    within DETECT_SHEET_ROWS rows)."""
    d = _detect(Path(path))
    return d.layout, d.header, d.rows


def _detect(path: Path) -> _Detected:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        wb = open_workbook(path)
        try:
            sheet_names = list(wb.sheetnames)
            sheets, read_whole, declared = [], [], []
            for n in sheet_names:
                ws = wb[n]
                g = [[excel_cell_text(c) for c in r]
                     for r in islice(ws.iter_rows(values_only=True), DETECT_SHEET_ROWS + 1)]
                read_whole.append(len(g) <= DETECT_SHEET_ROWS)
                sheets.append(g[:DETECT_SHEET_ROWS])
                declared.append(ws.max_row)
        finally:
            wb.close()
        # The time series is the largest table in the workbook. The first sheet with a header is
        # often a report or a summary instead: Arbin writes Global_Info first, Landt and Neware
        # write cycle and step statistics beside the record sheet. A sheet longer than the rows
        # searched is sized by the dimension it declares.
        found = []
        for k, g in enumerate(sheets):
            h = _find_header(g)
            if h is not None:
                size = sum(1 for r in g[h + 1:] if any(c.strip() for c in r))
                if not read_whole[k]:
                    size = max(size, (declared[k] or 0) - (h + 1))
                found.append((size, k, h))
        if not found:
            raise ValueError("no header row found in any worksheet")
        _, k_big, h = max(found, key=lambda f: (f[0], -f[1]))
        header = sheets[k_big][h]
        # Neware and others split a long run across several sheets, the later
        # ones repeating the same header. Reading only the largest would silently
        # truncate the experiment, so every sheet with the identical header is
        # included, in workbook order.
        rows = []
        matching = {}
        for name, g, whole, dim in zip(sheet_names, sheets, read_whole, declared):
            if len(g) > h and g[h] == header:
                rows += [r for r in g[h + 1:] if any(c.strip() for c in r)]
                matching[name] = dim if not whole else len(g)
        complete = all(whole for name, whole in zip(sheet_names, read_whole) if name in matching)
        # The layout finds that table again by its column names, not by sheet name or position,
        # so a later file from the same instrument with more (or differently named) record sheets
        # is read whole and its statistics sheets are still passed over.
        names = tuple(dict.fromkeys(c.strip() for c in header if c.strip()))[:4]
        return _Detected(Layout(kind="excel", header_row=h + 1, header_contains=names), header, rows,
                         complete, h, matching)

    size = path.stat().st_size
    with open(path, "rb") as fh:
        blob = fh.read(DETECT_BYTES)
    complete = len(blob) >= size
    if not complete and b"\n" in blob:
        blob = blob[:blob.rfind(b"\n") + 1]               # whole lines only
    encoding = next((e for e in ("utf-8-sig", "utf-8", "cp1252", "latin-1")
                     if _decodes(blob, e)), "latin-1")
    text = blob.decode(encoding, errors="replace")
    best: tuple[int, str, int, list[list[str]]] | None = None
    for delim in ("\t", ";", ",", "|"):
        grid = list(csv.reader(io.StringIO(text), delimiter=delim))
        h = _find_header(grid)
        if h is None:
            continue
        width = len(grid[h])
        if width < 3:
            continue
        consistent = sum(1 for r in grid[h + 1:] if len(r) == width)
        if best is None or consistent > best[0]:
            best = (consistent, delim, h, grid)
    if best is None:
        raise ValueError("could not find a delimited table in this file")
    _, delim, h, grid = best
    return _Detected(Layout(kind="delimited", encoding=encoding, delimiter=delim, header_row=h + 1),
                     grid[h], [r for r in grid[h + 1:] if any(c.strip() for c in r)], complete, h)


def _sample(path: Path, d: _Detected, limit: int = MEASURE_ROWS) -> tuple[list[list[str]], bool]:
    """The first `limit` data rows of the detected table, read on from the start of the file the way
    detect_layout reads its head (text: csv over the decoded text split at line feeds only;
    workbook: every sheet whose header row matches, in workbook order), and whether that was all."""
    rows: list[list[str]] = []
    if d.layout.kind == "excel":
        wb = open_workbook(path)
        try:
            for name in wb.sheetnames:
                it = wb[name].iter_rows(values_only=True)
                head = [[excel_cell_text(c) for c in r] for r in islice(it, d.header_index + 1)]
                if len(head) <= d.header_index or head[d.header_index] != d.header:
                    continue
                for r in it:
                    r = [excel_cell_text(c) for c in r]
                    if any(c.strip() for c in r):
                        if len(rows) == limit:
                            return rows, False
                        rows.append(r)
        finally:
            wb.close()
        return rows, True
    with open(path, "rb") as fh:
        text = io.TextIOWrapper(fh, encoding=d.layout.encoding, errors="replace", newline="\n")
        rdr = csv.reader(text, delimiter=d.layout.delimiter)
        for _ in islice(rdr, d.header_index + 1):
            pass
        for r in rdr:
            if any(c.strip() for c in r):
                if len(rows) == limit:
                    return rows, False
                rows.append(r)
    return rows, True


def _estimate_rows(path: Path, d: _Detected, measured: int) -> int:
    """About how many data rows the table holds: the lines after the header (blank ones included) of
    a text file, or the rows its matching sheets declare after their header row."""
    if d.layout.kind == "excel":
        total = sum(max(0, (dim or 0) - (d.header_index + 1)) for dim in d.sheets.values())
        return max(total, measured)
    lines, last = 0, b""
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(16 * 1024 * 1024), b""):
            lines += block.count(b"\n")
            last = block[-1:]
    lines += 1 if last not in (b"", b"\n") else 0
    return max(lines - (d.header_index + 1), measured)


def looks_tabular(path: str | Path, limit: int = 65536) -> bool:
    """A cheap screen for folder opening: does the first stretch of this file hold a delimited
    table (a header row of three or more names followed by numeric rows)? Spreadsheets are
    always candidates. A notes file, a log or a settings dump returns False and is left alone;
    a file the user picks by hand is never screened."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return True
    try:
        with open(path, "rb") as fh:
            blob = fh.read(limit)
    except OSError:
        return False
    if not blob or b"\x00" in blob[:4096]:
        return False
    encoding = next((e for e in ("utf-8-sig", "utf-8", "cp1252", "latin-1") if _decodes(blob, e)), "latin-1")
    text = blob.decode(encoding, errors="replace")
    for delim in ("\t", ";", ",", "|"):
        grid = list(csv.reader(io.StringIO(text), delimiter=delim))
        h = _find_header(grid)
        if h is not None and len(grid[h]) >= 3:
            return True
    return False


def _decodes(blob: bytes, encoding: str) -> bool:
    try:
        blob[:200000].decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return False
    return True


# ------------------------------------------------------------------ scoring
def _stated_unit(header: str) -> str | None:
    """The unit the reader itself will read from this header (reader._split_unit), or None."""
    from .reader import _split_unit
    return _split_unit(header)[1]


def _unit_of(header: str) -> str | None:
    m = re.search(r"[(\[/]\s*([^)\]]+?)\s*[)\]]?$", header.strip())
    if m and m.group(1).strip() in UNIT_FACTOR:
        return m.group(1).strip()
    return IMPLIED_UNIT.get(normalise(header))


def _raw_unit_token(header: str) -> str | None:
    """The unit as written, whether or not it is a unit we know."""
    m = re.search(r"[(\[/]\s*([^)\]]+?)\s*[)\]]?$", header.strip())
    return m.group(1).strip() if m else None


def score_column(role: str, header: str) -> tuple[int, str] | None:
    n = normalise(header)
    if not n:
        return None
    for veto in VETO.get(role, ()):
        if veto in n:
            return None
    # A declared unit of the wrong dimension disqualifies the column outright,
    # whatever its name suggests. This is what stops '-Im(Z)/Ohm' becoming the
    # current on an impedance file, where the name alone is convincing.
    raw = _raw_unit_token(header)
    if raw is not None:
        if raw not in UNIT_DIMENSION:
            return None
        if UNIT_DIMENSION[raw] != role_dimension(role):
            return None
    tier1, tier2 = SYNONYMS[role]
    if n in tier1:
        return 100, "exact name"
    if n in tier2:
        return 80, "generic name"
    for s in tier1:
        if n.startswith(s + " ") or n.endswith(" " + s) or f" {s} " in f" {n} ":
            return 70, f"contains {s!r}"
    for s in tier2:
        if n.split() and n.split()[0] == s:
            return 50, f"begins with {s!r}"
    return None


def propose(path: str | Path, registry=None) -> Proposal:
    """A mapping proposal for a file no profile claims. With a registry, the saved profile whose
    bound columns overlap this file's most (an instrument exported with other columns or units)
    is attached as `prior`, so the review step starts from its conventions."""
    path = Path(path)
    d = _detect(path)
    rows, sampled = d.rows, None
    if not d.complete:
        rows, whole = _sample(path, d)
        if not whole:
            sampled = (len(rows), _estimate_rows(path, d, len(rows)))
    headers = [h.strip() for h in d.header]
    prop = _propose(path, d.layout, headers, rows, sampled)
    if registry is not None:
        try:
            near = registry.nearest(headers, d.layout.kind)
        except Exception:                                   # a corrupt saved profile never blocks a proposal
            near = None
        if near is not None:
            prop.prior, prop.prior_shared = near
            prop.questions.insert(0, f"The saved profile {prop.prior.name!r} ({prop.prior.instrument}) binds "
                                     f"{len(prop.prior_shared)} of these columns; its conventions are offered "
                                     "as the starting point. Confirm them for this layout.")
    return prop


def _propose(path: Path, layout, headers: list[str], rows, sampled: tuple[int, int] | None = None) -> Proposal:

    all_scored: dict[str, list[Candidate]] = {}
    for role in SYNONYMS:
        hits = []
        for k, h in enumerate(headers):
            got = score_column(role, h)
            if got:
                hits.append(Candidate(role, h, k, got[0], got[1], _unit_of(h)))
        if hits:
            all_scored[role] = sorted(hits, key=lambda c: -c.score)

    # One column serves one role: resolve collisions by score, highest first.
    chosen: dict[str, Candidate] = {}
    taken: dict[int, str] = {}
    for role, hits in sorted(all_scored.items(),
                             key=lambda kv: -max(c.score for c in kv[1])):
        for c in hits:
            if c.index not in taken:
                chosen[role] = c
                taken[c.index] = role
                break
    # A generically named 'Capacity' beside explicit charge and discharge counters is a throughput
    # column (Neware's Capacity(mAh), PEC's), not a signed net counter: it is not proposed as one.
    if ("net_capacity_ah" in chosen and chosen["net_capacity_ah"].score < 100
            and "charging_capacity_ah" in chosen and "discharging_capacity_ah" in chosen):
        del taken[chosen.pop("net_capacity_ah").index]
    rejected = {r: [c for c in hits if r not in chosen or c.index != chosen[r].index]
                for r, hits in all_scored.items()}

    bindings: dict[str, Binding] = {}
    unit_unknown: dict[str, str] = {}
    for role, c in chosen.items():
        unit = c.unit
        if role == "step_type":
            bindings[role] = Binding(source=(c.column,), assumed=True)
            continue
        if unit is None and role_dimension(role) == "time" and _clock_column(rows, c.index):
            unit = "hh:mm:ss"          # a three-field clock states its own unit
        if unit is None:
            if role in ("record_index", "step_id", "step_count", "cycle_count"):
                unit = "1"
            else:
                unit_unknown[role] = c.column
                continue
        # A unit written in the header ('Current(mA)') is read from the header at import time and not
        # frozen into the profile, so a later export of the same instrument in another unit
        # ('Current(A)') is read right (P08e). A unit the name only implies ('Amps'), or a clock
        # format, is declared, because the reader cannot read it from the header.
        stated = _stated_unit(c.column)
        bindings[role] = Binding(source=(c.column,), source_unit=None if stated == unit else unit, assumed=True)

    prop = Proposal(path=path, layout=layout, headers=headers, bindings=bindings,
                    chosen=chosen, rejected=rejected, unit_unknown=unit_unknown,
                    unmapped_columns=[h for k, h in enumerate(headers)
                                      if k not in taken and h.strip()],
                    preview=[list(r) for r in rows[:60]])
    _measure(prop, rows, sampled)
    _ask(prop)
    return prop


def _clock_column(rows: list[list[str]], index: int) -> bool:
    """True when nearly every value of the column is a clock-format duration (cells.py)."""
    vals = [r[index].strip() for r in rows[:500] if index < len(r) and r[index].strip()]
    return bool(vals) and sum(parse_duration(v) is not None for v in vals) >= 0.9 * len(vals)


def _column(rows: list[list[str]], index: int) -> np.ndarray:
    out = np.full(len(rows), np.nan)
    for j, r in enumerate(rows):
        if index < len(r):
            s = r[index].strip().replace("−", "-")
            if _NUMERIC.match(s):
                out[j] = float(s.replace("d", "e").replace("D", "E"))
            elif _NUMERIC.match(s.replace(".", "").replace(",", ".")):
                out[j] = float(s.replace(".", "").replace(",", "."))
    return out


def _measure(prop: Proposal, rows: list[list[str]], sampled: tuple[int, int] | None = None) -> None:
    """Everything the data can state about itself, stated. The rest is a question.

    sampled=(rows measured, rows estimated in the file) when rows are only the first MEASURE_ROWS
    data rows of a larger file: 'rows' is then the estimate, and the two numbers are recorded."""
    prop.measured["rows"] = len(rows) if sampled is None else sampled[1]
    if sampled is not None:
        prop.measured["rows_measured"] = sampled[0]
        prop.measured["rows_total_estimate"] = sampled[1]
    from .reader import interleaved_columns
    mixed = interleaved_columns(prop.headers, rows)
    if mixed:
        prop.measured["interleaved_columns"] = mixed
    if "current_ampere" in prop.chosen:
        i = _column(rows, prop.chosen["current_ampere"].index)
        finite = i[np.isfinite(i)]
        neg = bool(np.any(finite < 0))
        prop.measured["current_has_negative_values"] = neg
        prop.measured["current_range_in_file_units"] = (
            f"{finite.min():.6g} to {finite.max():.6g}" if finite.size else "none readable")
    if "step_type" in prop.chosen:
        k = prop.chosen["step_type"].index
        seen = sorted({r[k].strip() for r in rows if k < len(r) and r[k].strip()})
        prop.measured["step_type_values"] = seen[:40]
    if "cycle_count" in prop.chosen:
        c = _column(rows, prop.chosen["cycle_count"].index)
        f = c[np.isfinite(c)]
        if f.size:
            prop.measured["first_cycle_number"] = float(f[0])
    if "test_time_second" in prop.chosen:
        k = prop.chosen["test_time_second"].index
        t = _column(rows, k)
        if _clock_column(rows, k):
            t = np.array([parse_duration(r[k]) if k < len(r) and parse_duration(r[k]) is not None
                          else np.nan for r in rows])
        f = t[np.isfinite(t)]
        if f.size > 1:
            prop.measured["time_is_monotonic"] = bool(np.all(np.diff(f) >= 0))
            prop.measured["time_span_in_file_units"] = f"{f.min():.6g} to {f.max():.6g}"
    for role in ("charging_capacity_ah", "discharging_capacity_ah", "net_capacity_ah",
                 "step_cumulative_capacity_ah"):
        if role in prop.chosen:
            q = _column(rows, prop.chosen[role].index)
            f = q[np.isfinite(q)]
            if f.size > 2:
                prop.measured[f"{role}_ever_decreases"] = bool(np.any(np.diff(f) < 0))


STEP_KINDS = ("cc_charge", "cc_discharge", "cv_charge", "cv_discharge", "rest", "ocv", "other")

STEP_KIND_TEXT = {"cc_charge": "charge (constant current)", "cc_discharge": "discharge (constant current)",
                  "cv_charge": "charge (constant voltage)", "cv_discharge": "discharge (constant voltage)",
                  "rest": "rest", "ocv": "open circuit", "other": "other (states no direction)"}


def guess_step_kind(value: str) -> str:
    """A proposal for one step-type value, from its wording; shown as proposed, confirmed by a person.

    'CC_DChg' and 'D' are discharges, 'CC_Chg' and 'C' charges, 'Rest', 'R' and 'Pause' rests; a value
    naming no direction stays 'other', which an unsigned-current file then refuses rather than guesses."""
    v = value.strip().lower()
    if not v:
        return "other"
    if v in ("r", "rest", "pause", "idle", "relax", "relaxation", "stop"):
        return "rest"
    if v in ("o", "ocv", "open circuit", "open_circuit"):
        return "ocv"
    cv = "cv" in v.replace("ccv", "") or "constant voltage" in v or "const v" in v
    if v in ("d", "dchg", "dis", "discharge") or "dchg" in v or "discharg" in v or "dis" in v.split("_") \
            or v.endswith("_d") or v.startswith("d_"):
        return "cv_discharge" if cv else "cc_discharge"
    if v in ("c", "chg", "charge") or "chg" in v or "charg" in v or v.endswith("_c") or v.startswith("c_"):
        return "cv_charge" if cv else "cc_charge"
    return "other"


def _ask(prop: Proposal) -> None:
    """Name what a person must decide. Blocking items stop the import outright."""
    if prop.measured.get("interleaved_columns"):
        prop.blocking.append(
            f"Some rows, not all, carry values under the nameless column(s) "
            f"{prop.measured['interleaved_columns']}: this file interleaves several tables (Neware's "
            "hierarchical export writes cycle, step and record rows together). Export the record "
            "level only; no mapping of these columns can separate them.")
    for h in prop.headers:
        n = normalise(h)
        for marker, what in NOT_A_TIME_SERIES.items():
            if n == marker or n.startswith(marker + " "):
                prop.blocking.append(
                    f"Column {h!r} means this file is {what}, not a cycling time series. "
                    "Cycling analysis does not apply to it; use the impedance workflow.")
                break

    for role in ("test_time_second", "current_ampere", "voltage_volt"):
        if role in prop.bindings:
            continue
        if role in prop.unit_unknown:
            prop.blocking.append(
                f"{role} was matched to {prop.unit_unknown[role]!r}, but neither its header nor "
                "its name states a unit. Give the unit; it will not be inferred from the "
                "magnitude of the values.")
        else:
            prop.blocking.append(
                f"No column could be matched to {role}. Name it, or confirm this file is not a "
                "time series.")
    for role, col in prop.unit_unknown.items():
        if role not in ("test_time_second", "current_ampere", "voltage_volt"):
            prop.questions.append(
                f"{role} was matched to {col!r} but carries no unit, so it was left unbound. "
                "Give the unit to use it.")

    neg = prop.measured.get("current_has_negative_values")
    steps = prop.measured.get("step_type_values")
    if neg is False and not steps:
        prop.blocking.append(
            "The current column has no negative values and there is no step-type column, so "
            "nothing in this file distinguishes charge from discharge. Supply the step-type "
            "column or a different export.")
    elif neg is False:
        prop.blocking.append(
            f"The current is unsigned. Map every step-type value to a direction: {steps}")
    elif neg is True:
        prop.questions.append(
            "The current is signed. Confirm whether positive means charge (most instruments) "
            "or discharge (some BioLogic and Maccor configurations). Getting this backwards "
            "swaps every charge and discharge capacity in the results.")

    if "time_is_monotonic" in prop.measured and not prop.measured["time_is_monotonic"]:
        prop.questions.append(
            "The proposed time column is not monotonic. Confirm it is the cumulative test time "
            "and not a per-step clock; a per-step clock would shorten every branch.")

    caps = [r for r in ("charging_capacity_ah", "discharging_capacity_ah", "net_capacity_ah",
                        "step_cumulative_capacity_ah") if r in prop.bindings]
    if caps:
        drops = any(prop.measured.get(f"{r}_ever_decreases") for r in caps)
        prop.questions.append(
            "Confirm what the capacity column accumulates: per row, per step, per cycle, or over "
            "the whole test. Measured behaviour: the counter "
            + ("does decrease somewhere, so it resets" if drops else "never decreases")
            + ". The reader re-measures this and refuses the import if the answer disagrees.")
    else:
        prop.questions.append(
            "No capacity column was matched, so capacity will be integrated from the sampled "
            "current. On sparsely sampled constant-voltage tails that underestimates the "
            "instrument's own value.")

    if "rows_measured" in prop.measured:
        prop.questions.append(
            f"This file holds about {prop.measured['rows_total_estimate']:,} rows; the measurements above "
            f"(sign and range of the current, counter behaviour, first cycle number, time span, step-type "
            f"values) come from its first {prop.measured['rows_measured']:,} rows only. Confirm they hold for "
            "the rest of the file. On import the reader checks every row again: it refuses a counter that "
            "behaves otherwise and, where the direction comes from the step type, a step type not mapped.")

    if "first_cycle_number" in prop.measured:
        prop.questions.append(
            f"The first cycle number in the file is "
            f"{prop.measured['first_cycle_number']:g}. Confirm whether this instrument numbers "
            "cycles from 0 or from 1.")

    for role, c in prop.chosen.items():
        if c.score < 70:
            prop.questions.append(
                f"{role} was matched to {c.column!r} only by a generic name ({c.reason}). "
                "Confirm it is the right column.")
