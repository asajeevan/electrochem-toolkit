"""LANHE (LAND) .cex files: the battery tester's own binary file, read natively.

LANHE publishes no description of the .cex format. This reader reads what has been established on a
real file and checks it again on each file it opens, wherever the file holds enough records for the check
(a note says when it does not). A layout, step type, status event or unit kind it has not seen, or a range
code the file's own counters cannot confirm, is refused with what it found, never read as a plausible
measurement; block types it has not seen are skipped with a note. docs/P08g_LANHE_cex_Reader.md gives the
evidence for each fact below, the checks, and what is still unverified.

Layout (little-endian, offsets in bytes)

  Header, 64 bytes
    0   magic 10 11 09 88
    4   layout code: 07 00 04 00 is the only one read
    16  test start, Unix seconds (uint32)
    24  voltage range code (uint16): 0xE005 is 5 V
    26  current range code (uint16): 0xC00A is 1 mA; any other 0xC0nn is taken as nn x 0.1 mA only when the
        file's own capacity counter confirms it
    28  active-material mass in g (float32), 0 when not set: described by another project, not yet seen
        set in a file read here, so it is offered and never applied

  then 16-byte units, told apart by their first word:
    FFFFAAAA  a block: type in the low 16 bits of word 1, payload length in bytes in the high 16; the
              payload follows, then an end unit FFFFBBBB repeating words 1 to 3. Type 0x13 holds the step
              plan. Blocks carry no measurement and are skipped.
    FFFFCCCC or FFFFCCCD  a control unit, its kind in the low 16 bits of word 1:
      0x22  step start. Word 1, high 16 bits: the tester's step number (bit 15 set). Word 2: the step type
            (low byte), a flag byte, and the setpoint in counts (high 16 bits: the current of a
            constant-current step, the voltage of a constant-voltage step). Word 3: start, Unix seconds.
      0x44  cycle marker. Word 2: a direction flag. Word 3: the tester's cycle number (high 16 bits, from 0)
            and step number (low 16).
      0x33  status event. Word 2: the event code. Word 3: Unix seconds.
      0x88  once, before the step plan.
    anything else  a data record: time (uint32, 0.01 s since the test start); voltage and current (int16
              counts, the range's full scale at 0x7E00 = 32256 counts, positive current charging); the
              tester's capacity counter (float32, Ah) and energy counter (float32, Wh).

Step types read: 0x70 rest, 0x03 constant-current charge, 0x02 constant-current discharge, 0x05
constant-voltage charge.

The counters restart at zero with each step, except that a step continuing the one before it in the same
direction carries them on (a constant-voltage step after the constant-current one). A step's first
increment includes the charge passed between the previous step's last record and its own first record,
so the counter is the tester's charge; the integral of the logged current misses that interval.
"""
from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .checks import Findings, check_counter_against_integral, check_sign_against_voltage, check_time
from .reader import MAX_BYTES, ImportFailure, RawTable

READER = "lanhe-cex"
READER_VERSION = "1.0.0"
INSTRUMENT = "LANHE (LAND) battery tester"

MAGIC = b"\x10\x11\x09\x88"
HEADER_BYTES = 64
UNIT_BYTES = 16
LAYOUT = b"\x07\x00\x04\x00"            # 16-byte records with float32 counters
TIME_UNIT_S = 0.01
FULL_SCALE_COUNTS = 0x7E00               # 32256 counts are the range's full scale
SATURATED = (32767, -32768)              # an int16 count at its limit: the reading is clipped

# Range codes whose scale was established on a real file. Another code of the same family is decoded by
# the family's rule (voltage 0xE0nn: nn V; current 0xC0nn: nn x 0.1 mA) only when the file's own counters
# confirm the scale it gives (SCALE_TOLERANCE); otherwise the file is refused.
VOLTAGE_VERIFIED_V = {0xE005: 5.0}
CURRENT_VERIFIED_A = {0xC00A: 1e-3}

BLOCK, BLOCK_END = 0xFFFFAAAA, 0xFFFFBBBB
CONTROL = (0xFFFFCCCC, 0xFFFFCCCD)
STEP_START, CYCLE_MARK, STATUS, OPENING = 0x22, 0x44, 0x33, 0x88
# kinds another project's decoder describes as retention references (a capacity and an energy kept for the
# tester's own retention figures); no measurement, skipped with a note. Not yet seen in a file read here.
RETENTION_REFERENCES = (0xB1, 0xB2)
BLOCK_TYPES_SEEN = (0xAA, 0x55, 0x78, 0x13)

# step type code -> (name, engine mode: 1 constant current, 2 constant voltage, 3 rest; direction: +1 charge)
STEP_TYPES = {0x70: ("rest", 3, 0), 0x03: ("cc_charge", 1, 1), 0x02: ("cc_discharge", 1, -1),
              0x05: ("cv_charge", 2, 1)}
# status event codes (low 16 bits of word 2) seen in complete runs
STATUS_EVENTS = {0x0201: "start", 0x0101: "end", 0x0401: "step change"}

SCALE_TOLERANCE = 2e-3            # decoded current and power against the counters, constant-current steps
SCALE_TOLERANCE_CV = 1e-2         # the same when only constant-voltage steps carry enough intervals
SCALE_MIN_INTERVALS = 20          # intervals needed for the scale check to decide
CLOCK_SLOPE_TOLERANCE = 1e-2      # record time against the step-start clock, over at least a minute
CLOCK_OFFSET_S = 2.0              # a step's first record this far from its start on the clock is reported
CLOCK_MIN_SPAN_S = 60.0           # the clock slope needs two step starts at least this far apart

RECORD = np.dtype([("t", "<u4"), ("v", "<i2"), ("i", "<i2"), ("q", "<f4"), ("w", "<f4")])
assert RECORD.itemsize == UNIT_BYTES

COLUMNS = ("time/0.01 s", "voltage/counts", "current/counts", "capacity counter/Ah", "energy counter/Wh")


def is_cex(path: str | Path) -> bool:
    """True for a file that begins with the .cex signature, whatever its extension."""
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == MAGIC
    except OSError:
        return False


@dataclass
class _Step:
    seq: int                       # 1-based, in the order the steps ran
    unit: int                      # index of the step-start unit among the units after the header
    code: int                      # the tester's step number with its flag bit
    type: int
    flags: int
    setpoint: int                  # counts
    unix: int
    signature: int
    marker: dict | None
    first: int = 0                 # first and last record (0-based, inclusive); last < first when none
    last: int = -1
    counter_start: str = ""
    notes: list = field(default_factory=list)

    @property
    def name(self):
        return STEP_TYPES[self.type][0]

    @property
    def direction(self):
        return STEP_TYPES[self.type][2]

    @property
    def records(self):
        return self.last - self.first + 1


def _clock(unix: int | None) -> str | None:
    """The tester's clock as a date and time. The file stores Unix-style seconds and no time zone, so none is
    written: the digits are those of the clock, whether it kept UTC or local time."""
    if unix is None:
        return None
    return datetime.fromtimestamp(unix, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _scales(v_code: int, i_code: int) -> tuple[float, float, bool, bool]:
    """(volts per count, amperes per count, voltage verified, current verified), or ImportFailure."""
    if v_code in VOLTAGE_VERIFIED_V:
        v_fs, v_ok = VOLTAGE_VERIFIED_V[v_code], True
    elif v_code & 0xFF00 == 0xE000 and v_code & 0xFF:
        v_fs, v_ok = float(v_code & 0xFF), False
    else:
        raise ImportFailure("cex_range_unverified", f"the voltage range code {v_code:#06x} is not one this reader "
                            "knows (0xE005, 5 V, is); export the run to Excel from the tester's software")
    if i_code in CURRENT_VERIFIED_A:
        i_fs, i_ok = CURRENT_VERIFIED_A[i_code], True
    elif i_code & 0xFF00 == 0xC000 and i_code & 0xFF:
        i_fs, i_ok = (i_code & 0xFF) * 1e-4, False
    else:
        raise ImportFailure("cex_range_unverified", f"the current range code {i_code:#06x} is not one this reader "
                            "knows (0xC00A, 1 mA, is); export the run to Excel from the tester's software")
    return v_fs / FULL_SCALE_COUNTS, i_fs / FULL_SCALE_COUNTS, v_ok, i_ok


def _walk(words: np.ndarray, fnd: Findings):
    """Blocks and control units among the 16-byte units; every other unit is a data record."""
    n = words.shape[0]
    is_record = np.ones(n, bool)
    blocks, controls = [], []
    special = np.flatnonzero(words[:, 0] >= 0xFFFF0000)
    inside = -1
    for k in special.tolist():
        if k <= inside:                                    # a word inside a block's payload or its end unit
            continue
        w0, w1, w2, w3 = (int(x) for x in words[k])
        if w0 == BLOCK:
            length = w1 >> 16
            end = k + 1 + length // UNIT_BYTES
            if length % UNIT_BYTES or end >= n or int(words[end, 0]) != BLOCK_END \
                    or tuple(int(x) for x in words[end, 1:]) != (w1, w2, w3):
                raise ImportFailure("cex_block", f"the block at byte {HEADER_BYTES + k * UNIT_BYTES} does not end "
                                    "where its length says: the file is damaged or of a layout this reader does "
                                    "not know")
            blocks.append({"offset": HEADER_BYTES + k * UNIT_BYTES, "type": w1 & 0xFFFF, "bytes": length})
            is_record[k:end + 1] = False
            inside = end
        elif w0 in CONTROL:
            controls.append((k, w0, w1, w2, w3))
            is_record[k] = False
        else:
            raise ImportFailure("cex_unit", f"the unit at byte {HEADER_BYTES + k * UNIT_BYTES} begins {w0:#010x}, "
                                "which is neither a record nor a unit this reader knows")
    unseen = sorted({b["type"] for b in blocks} - set(BLOCK_TYPES_SEEN))
    if unseen:
        fnd.note("cex_block_types", "blocks of types " + ", ".join(f"{x:#04x}" for x in unseen) + " were skipped "
                 "(not seen before; blocks carry no measurement)", types=unseen)
    return is_record, blocks, controls


def _controls(controls, fnd: Findings):
    steps, markers, events, opening, references = [], [], [], [], 0
    marker = None
    unknown_kinds, unknown_types, unknown_events = {}, {}, {}
    for k, w0, w1, w2, w3 in controls:
        kind, at = w1 & 0xFFFF, HEADER_BYTES + k * UNIT_BYTES
        if kind == STEP_START:
            typ = w2 & 0xFF
            if typ not in STEP_TYPES:
                unknown_types.setdefault(typ, at)
                continue
            steps.append(_Step(seq=len(steps) + 1, unit=k, code=w1 >> 16, type=typ, flags=(w2 >> 8) & 0xFF,
                               setpoint=w2 >> 16, unix=w3, signature=w0, marker=marker))
        elif kind == CYCLE_MARK:
            marker = {"offset": at, "direction_flag": w2, "cycle": w3 >> 16, "step": (w3 & 0xFFFF) & 0x7FFF}
            markers.append(marker)
        elif kind == STATUS:
            code = w2 & 0xFFFF
            if code not in STATUS_EVENTS:
                unknown_events.setdefault(w2, at)
                continue
            events.append({"offset": at, "code": f"{w2:#010x}", "event": STATUS_EVENTS[code], "unix": w3,
                           "clock": _clock(w3)})
        elif kind == OPENING:
            opening.append({"offset": at, "words": [f"{w2:#010x}", f"{w3:#010x}"]})
        elif kind in RETENTION_REFERENCES:
            references += 1
        else:
            unknown_kinds.setdefault(kind, at)
    if unknown_types:
        fnd.refuse("cex_step_unverified", "step types this reader has not been verified on: "
                   + ", ".join(f"{t:#04x} (first at byte {a})" for t, a in unknown_types.items())
                   + ". Rest, constant-current charge and discharge, and constant-voltage charge are read; export "
                   "the run to Excel from the tester's software", types=sorted(unknown_types))
    if unknown_events:
        fnd.refuse("cex_event_unverified", "status events this reader has not been verified on: "
                   + ", ".join(f"{c:#010x} (first at byte {a})" for c, a in unknown_events.items())
                   + ". A pause, a resume or an alarm writes events of this kind, and what the records after one "
                   "mean has not been established; export the run to Excel from the tester's software",
                   codes=[f"{c:#010x}" for c in unknown_events])
    if unknown_kinds:
        fnd.refuse("cex_control_unverified", "control units of kinds this reader does not know: "
                   + ", ".join(f"{c:#04x} (first at byte {a})" for c, a in unknown_kinds.items())
                   + "; export the run to Excel from the tester's software", kinds=sorted(unknown_kinds))
    if references:
        fnd.note("cex_retention_references", f"{references} retention-reference unit(s) of the tester were "
                 "skipped (they hold the tester's own reference for retention, not a measurement)", units=references)
    return steps, markers, events, opening


def _assign(steps: list[_Step], rec_units: np.ndarray, n_records: int) -> np.ndarray:
    """Step (0-based) of every record: the last step start before it."""
    starts = np.array([s.unit for s in steps], dtype=np.int64)
    row_step = np.searchsorted(starts, rec_units, side="right") - 1
    if row_step.size and row_step[0] < 0:
        before = int(np.sum(row_step < 0))
        raise ImportFailure("cex_records_before_step", f"{before} record(s) come before the first step start, so "
                            "their step type, and with it their direction, is unknown")
    for k, s in enumerate(steps):
        s.first = int(np.searchsorted(row_step, k, side="left"))
        s.last = int(np.searchsorted(row_step, k, side="right")) - 1
    return row_step


def _counters(steps, q, w, fnd: Findings) -> np.ndarray:
    """Charge increments (Ah per record, charge positive) from the capacity counter, step by step.

    A step's counter starts at zero (reset) or at the last value of the step before it when that step ran
    in the same direction (carried). Anything else is reported and read as a reset whose first increment is
    the counter's first value. The counter never decreases inside a step: a decrease refuses the file."""
    dq = np.zeros(q.size)
    last = None                                            # (direction, capacity, energy) of the last active step
    for s in steps:
        a, b = s.first, s.last + 1
        if b <= a:
            continue
        qq, ww = q[a:b], w[a:b]
        if not (np.all(np.isfinite(qq)) and np.all(np.isfinite(ww))):
            fnd.refuse("cex_counter_invalid", f"step {s.seq}: the capacity or energy counter holds a value that is "
                       "not a number", step=s.seq)
            continue
        drop = np.flatnonzero(np.diff(qq) < 0)
        if drop.size:
            fnd.refuse("cex_counter_decreases", f"step {s.seq}: the capacity counter decreases at record "
                       f"{a + int(drop[0]) + 2} of the file, which no step of a complete run does", step=s.seq,
                       record=a + int(drop[0]) + 2)
            continue
        if s.direction == 0:
            s.counter_start = "rest"
            if np.any(qq != 0):
                s.notes.append("the capacity counter is not zero during this rest")
            continue
        if qq[0] == 0.0 and ww[0] == 0.0:
            s.counter_start, base = "reset", 0.0
        elif last is not None and last[0] == s.direction and qq[0] == last[1] and ww[0] == last[2]:
            s.counter_start, base = "carried", float(qq[0])
        else:
            s.counter_start, base = "other", 0.0
            fnd.warn("cex_counter_start", f"step {s.seq}: the counters start at {qq[0]:.6g} Ah and {ww[0]:.6g} Wh, "
                     "neither zero nor the values the step before it ended with; read as a restart whose first "
                     "increment is that value", step=s.seq, capacity_Ah=float(qq[0]), energy_Wh=float(ww[0]))
        dq[a:b] = np.diff(qq, prepend=base) * s.direction
        last = (s.direction, float(qq[-1]), float(ww[-1]))
    return dq


def _signs(steps, i_counts, fnd: Findings) -> None:
    """The current must flow the way the step type says: the reader's two statements of direction agree."""
    against = []
    for s in steps:
        a, b = s.first, s.last + 1
        if b <= a:
            continue
        ii = i_counts[a:b]
        if s.direction == 0:
            moving = int(np.count_nonzero(ii))
            if moving:
                s.notes.append(f"{moving} record(s) of this rest carry current")
            continue
        opposite = int(np.count_nonzero(np.sign(ii) == -s.direction))
        if int(ii.sum()) * s.direction < 0:
            fnd.refuse("sign_contradicts_step_type", f"step {s.seq} is a {s.name.replace('_', ' ')} step but its "
                       "current flows the other way; the file does not follow the layout this reader knows",
                       step=s.seq)
        elif opposite:
            s.notes.append(f"{opposite} record(s) carry current against the step's direction")
            if s.type != 0x05:
                against.append(s.seq)
    if against:
        fnd.warn("cex_current_against_step", "constant-current steps with records whose current flows against "
                 "the step type: " + ", ".join(map(str, against[:12])) + ("..." if len(against) > 12 else ""),
                 steps=against[:100])


def _interval_sums(t, i, e, q, w, a, b):
    """Sums over the intervals of one step after its first: counter charge and integrated current (C),
    and, when the voltage stays positive, counter energy and integrated power (J)."""
    if b - a < 3:
        return None
    tt, ii, qq, ww, ee = t[a:b], np.abs(i[a:b]), q[a:b], w[a:b], e[a:b]
    h = tt[2:] - tt[1:-1]
    trap_q = float(np.sum(h * (ii[1:-1] + ii[2:]) / 2.0))
    count_q = float(qq[-1] - qq[1]) * 3600.0
    out = {"intervals": int(h.size), "counter_q": count_q, "trap_q": trap_q}
    if np.all(ee > 0):
        p = ee * ii
        out.update(counter_w=float(ww[-1] - ww[1]) * 3600.0, trap_w=float(np.sum(h * (p[1:-1] + p[2:]) / 2.0)))
    return out


def _scale_check(steps, t, i, e, q, w) -> dict:
    """The decoded current against the tester's own capacity counter, and the decoded power against its energy
    counter: two statements in physical units (Ah, Wh) that the scales must reproduce. Intervals inside
    current-carrying steps after each step's first; constant-current steps decide when they carry at least
    SCALE_MIN_INTERVALS intervals, else constant-voltage steps with the wider tolerance."""
    tot = {1: [0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0], 2: [0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0]}
    for s in steps:
        if s.direction == 0:
            continue
        r = _interval_sums(t, i, e, q, w, s.first, s.last + 1)
        if r is None:
            continue
        if r["counter_q"] > 0:
            s.notes.append(f"integrated current / counter = {r['trap_q'] / r['counter_q']:.6f} over "
                           f"{r['intervals']} intervals")
        acc = tot[STEP_TYPES[s.type][1]]
        acc[0] += r["intervals"]; acc[1] += r["counter_q"]; acc[2] += r["trap_q"]
        if "counter_w" in r:
            acc[3] += r["intervals"]; acc[4] += r["counter_q"]; acc[5] += r["trap_q"]
            acc[6] += r["counter_w"]; acc[7] += r["trap_w"]
    for mode, basis, tol in ((1, "constant-current steps", SCALE_TOLERANCE),
                             (2, "constant-voltage steps", SCALE_TOLERANCE_CV)):
        n, cq, tq, ne, cqe, tqe, cw, tw = tot[mode]
        if n >= SCALE_MIN_INTERVALS and cq > 0:
            out = {"basis": basis, "intervals": n, "tolerance": tol, "counter_C": cq, "integral_C": tq,
                   "current_ratio": tq / cq, "voltage_ratio": None}
            if ne >= SCALE_MIN_INTERVALS and cqe > 0 and cw > 0 and tqe > 0:
                out.update(energy_counter_J=cw, energy_integral_J=tw, voltage_ratio=(tw / cw) / (tqe / cqe))
            out["current_passed"] = abs(out["current_ratio"] - 1) <= tol
            out["voltage_passed"] = None if out["voltage_ratio"] is None else abs(out["voltage_ratio"] - 1) <= tol
            return out
    return {"basis": None, "intervals": int(tot[1][0] + tot[2][0]), "current_passed": None, "voltage_passed": None}


def _clock_check(steps, t, start_unix) -> dict:
    """Record time against the steps' start times on the tester's clock (whole seconds)."""
    pts = [(s.unix - start_unix, float(t[s.first])) for s in steps if s.records > 0]
    if not pts:
        return {"steps_compared": 0}
    wall = np.array([p[0] for p in pts], float)
    rec = np.array([p[1] for p in pts], float)
    off = rec - wall
    span = float(wall.max() - wall.min())
    slope = float(np.polyfit(wall, rec, 1)[0]) if len(pts) >= 2 and span >= CLOCK_MIN_SPAN_S else None
    return {"steps_compared": len(pts), "span_s": span, "slope": slope,
            "largest_offset_s": float(off[np.argmax(np.abs(off))])}


def read(path: str | Path, progress=None) -> tuple[RawTable, dict]:
    """Read one .cex file: a RawTable (SI, charge-positive current, a step type on every row, the counter's
    charge increments in Ah) and the metadata the app and the exports carry. bridge.native_table makes the
    engine's Table from it; a reader never builds one itself.

    progress is accepted for the workflow's signature and not called: decoding is one vectorised pass."""
    path = Path(path)
    size = path.stat().st_size
    if size == 0:
        raise ImportFailure("empty_file", "the file is empty")
    if size > MAX_BYTES:
        raise ImportFailure("file_too_large", f"{size / 2**20:.0f} MiB exceeds the {MAX_BYTES / 2**20:.0f} MiB limit")
    blob = path.read_bytes()
    if len(blob) < HEADER_BYTES or blob[:4] != MAGIC:
        raise ImportFailure("cex_signature", f"{path.name} does not begin with the LANHE (LAND) .cex signature, so it "
                            "is not a .cex file this version can read. Export the run as .csv, .txt or .xlsx from the "
                            "cycler's software.")
    layout = blob[4:8]
    if layout != LAYOUT:
        raise ImportFailure("cex_layout", f"{path.name} is a .cex file of layout {layout.hex(' ')}; this version reads "
                            f"layout {LAYOUT.hex(' ')} only, the one verified on a real file. Export the run to Excel "
                            "from the tester's software, which this version reads.")
    fnd = Findings()
    start_unix = struct.unpack_from("<I", blob, 16)[0]
    v_code, i_code = struct.unpack_from("<HH", blob, 24)
    mass_g = struct.unpack_from("<f", blob, 28)[0]
    try:
        sv, si, v_ok, i_ok = _scales(v_code, i_code)
    except ImportFailure as exc:
        raise ImportFailure(exc.code, f"{path.name}: {str(exc).split(': ', 1)[1]}") from None

    tail = (len(blob) - HEADER_BYTES) % UNIT_BYTES
    n_units = (len(blob) - HEADER_BYTES) // UNIT_BYTES
    if tail:
        fnd.warn("cex_truncated_tail", f"the file ends {tail} byte(s) into a unit, as a file copied while the test "
                 "was still being written does; the incomplete unit was not read", bytes=tail)
    words = np.frombuffer(blob, dtype="<u4", count=4 * n_units, offset=HEADER_BYTES).reshape(n_units, 4)
    is_record, blocks, controls = _walk(words, fnd)
    steps, markers, events, opening = _controls(controls, fnd)
    fnd.raise_if_refused(path.name)
    rec_units = np.flatnonzero(is_record)
    if rec_units.size == 0:
        raise ImportFailure("no_data", f"{path.name} holds the test's settings but no data records")
    if not steps:
        raise ImportFailure("cex_records_before_step", f"{path.name}: data records but no step start")
    rec = np.frombuffer(blob, dtype=RECORD, count=n_units, offset=HEADER_BYTES)[rec_units]
    try:
        row_step = _assign(steps, rec_units, rec.size)
    except ImportFailure as exc:
        raise ImportFailure(exc.code, f"{path.name}: {str(exc).split(': ', 1)[1]}") from None
    n = int(rec.size)

    t = rec["t"].astype(np.float64) * TIME_UNIT_S
    v_counts = rec["v"].astype(np.int64)
    i_counts = rec["i"].astype(np.int64)
    e = v_counts * sv
    i = i_counts * si
    q = rec["q"].astype(np.float64)
    w = rec["w"].astype(np.float64)

    # --- structure ------------------------------------------------------------------------------------------
    dt = np.diff(t)
    back = np.flatnonzero(dt < 0)
    if back.size:
        fnd.refuse("cex_time_backwards", f"the record time decreases at {back.size} place(s), first at record "
                   f"{int(back[0]) + 2}: a resumed or concatenated run, which this version does not read",
                   records=int(back.size), first=int(back[0]) + 2)
    step_seq = row_step + 1
    check_time(fnd, t, "record time", step_seq.astype(float))
    dq_ah = _counters(steps, q, w, fnd)
    _signs(steps, i_counts, fnd)
    fnd.raise_if_refused(path.name)
    for name, counts in (("voltage", v_counts), ("current", i_counts)):
        clipped = int(np.isin(counts, SATURATED).sum())
        if clipped:
            fnd.warn("cex_saturated", f"{clipped} {name} reading(s) sit at the end of the tester's range, so the "
                     "true value may be larger", quantity=name, records=clipped)
    empty = [s.seq for s in steps if s.records == 0]
    if empty:
        fnd.note("cex_empty_steps", f"{len(empty)} step(s) hold no record: " + ", ".join(map(str, empty[:12])),
                 steps=empty[:100])

    # --- the time unit against the tester's clock, then the scales against its own counters ------------------
    clock = _clock_check(steps, t, start_unix)
    if clock.get("slope") is not None and abs(clock["slope"] - 1) > CLOCK_SLOPE_TOLERANCE:
        fnd.refuse("cex_time_base", f"the record time runs at {clock['slope']:.4f} times the tester's clock between "
                   "step starts, so its unit is not the 0.01 s this reader knows", **clock)
    elif clock.get("steps_compared") and abs(clock["largest_offset_s"]) > CLOCK_OFFSET_S:
        fnd.warn("cex_clock_offset", f"a step's first record lies {clock['largest_offset_s']:.1f} s from the step's "
                 "start on the tester's clock (a clock change, or a pause the file does not mark)", **clock)
    if clock.get("slope") is None:
        fnd.note("cex_clock_not_checked", "the record time could not be checked against the tester's clock, which "
                 f"needs two step starts at least {CLOCK_MIN_SPAN_S:g} s apart; the 0.01 s unit verified on a real "
                 "file was used", **clock)
    scale = _scale_check(steps, t, i, e, q, w)
    scale.update(voltage_range_verified=v_ok, current_range_verified=i_ok)
    if scale["current_passed"] is False or scale["voltage_passed"] is False:
        what = " and ".join(x for x, ok in (("current", scale["current_passed"]), ("voltage", scale["voltage_passed"]))
                            if ok is False)
        fnd.refuse("cex_scale_check", f"the decoded {what} {'do' if ' and ' in what else 'does'} not reproduce the "
                   "tester's own counters "
                   f"(current ratio {scale['current_ratio']:.5f}"
                   + (f", voltage ratio {scale['voltage_ratio']:.5f}" if scale.get("voltage_ratio") else "")
                   + f", tolerance {scale['tolerance']:g}): the file does not follow the scales this reader knows",
                   **{k: v for k, v in scale.items() if isinstance(v, (int, float, str, bool)) or v is None})
    unverified = [x for x, ok in (("voltage", v_ok), ("current", i_ok)) if not ok]
    if unverified:
        if not all(scale.get(f"{x}_passed") for x in unverified):
            fnd.refuse("cex_range_unverified", f"the {' and '.join(unverified)} range code ("
                       + ", ".join(f"{c:#06x}" for x, c in (("voltage", v_code), ("current", i_code)) if x in unverified)
                       + ") has not been verified on a real file, and this file does not let the scale it would give "
                       "be confirmed against the tester's own counters; export the run to Excel from the tester's "
                       "software")
        else:
            fnd.note("cex_range_confirmed", f"the {' and '.join(unverified)} range code has not been verified on "
                     "another file; the scale it gives reproduces this file's own counters (see scale_check)")
    elif scale["current_passed"] is None:
        fnd.note("cex_scale_not_checked", "too few intervals carry current for the scales to be checked against the "
                 "tester's counters in this file; the verified scales of its range codes were used")
    elif scale["voltage_passed"] is None:
        fnd.note("cex_voltage_not_checked", "the decoded voltage could not be checked against the tester's energy "
                 f"counter, which needs {SCALE_MIN_INTERVALS} intervals with a positive voltage in current-carrying "
                 "steps; the verified scale of its range code was used")
    fnd.raise_if_refused(path.name)
    if steps[0].unix != start_unix:
        fnd.note("cex_start_time", "the header's start time and the first step's start differ by "
                 f"{steps[0].unix - start_unix} s", header=start_unix, first_step=steps[0].unix)
    if not any(ev["event"] == "end" for ev in events):
        fnd.note("cex_no_end_event", "the file has no end-of-test event: the test may still have been running when "
                 "it was copied, and its last branch is then incomplete")

    # --- the rows, for bridge.native_table ------------------------------------------------------------------
    kind = np.array([s.name for s in steps], dtype=object)[row_step]
    cross = check_counter_against_integral(fnd, dq_ah, t, i, step_seq.astype(float))
    sign_vs_voltage = check_sign_against_voltage(fnd, i, e, step_seq.astype(float))
    fnd.raise_if_refused(path.name)
    i_fs = si * FULL_SCALE_COUNTS
    labels = {"time": "record time (0.01 s)", "current": f"current counts ({i_fs * 1e3:g} mA range)",
              "potential": f"voltage counts ({sv * FULL_SCALE_COUNTS:g} V range)", "step": "step-start units",
              "mode": "step types", "dq": "the tester's capacity counter (Ah), reset or carried per step"}

    # --- what the reader concluded, for the app, the exports and a later reader ------------------------------
    starts = {k: sum(1 for s in steps if s.counter_start == k) for k in ("reset", "carried", "other")}
    kinds = {}
    for s in steps:
        kinds[s.name] = kinds.get(s.name, 0) + 1
    rows = _step_rows(steps, t, e, q, w, sv, si)
    ok_mass = math.isfinite(mass_g) and mass_g > 0
    description = {
        "name": READER, "kind": "native binary reader", "version": READER_VERSION, "instrument": INSTRUMENT,
        "layout": LAYOUT.hex(" "), "time_unit_s": TIME_UNIT_S, "full_scale_counts": FULL_SCALE_COUNTS,
        "voltage_range_code": f"{v_code:#06x}", "voltage_full_scale_V": sv * FULL_SCALE_COUNTS,
        "voltage_range_verified": v_ok, "current_range_code": f"{i_code:#06x}", "current_full_scale_A": i_fs,
        "current_range_verified": i_ok, "step_types": {f"{k:#04x}": v[0] for k, v in STEP_TYPES.items()},
        "conventions": {"current_sign": "charge_positive",
                        "direction_source": "step type, cross-checked with the sign of the current",
                        "capacity_semantics": "the tester's counter, reset or carried per step",
                        "cycle_base": "cycles numbered by Cyclara from 1; the tester's cycle markers are listed per step"},
        "specification": "docs/P08g_LANHE_cex_Reader.md",
    }
    report = {
        "profile": READER, "instrument": INSTRUMENT, "rows": n,
        "current_sign_declared": "charge_positive", "current_sign_applied": "charge_positive",
        "direction_from_step_types": True,       # every step's type names its direction; the current agrees (_signs)
        "capacity_semantics": "reset_or_carried_per_step", "capacity_semantics_verified": starts["other"] == 0,
        "instrument_increment_available": True, "counter_vs_integral": cross, "sign_vs_voltage": sign_vs_voltage,
        "warnings": len(fnd.warnings), "labels": labels, "potential_name": "Voltage/V",
        "cex": {
            "bytes": len(blob), "units": int(n_units), "records": n, "steps": len(steps), "step_types": kinds,
            "counter_starts": starts, "blocks": blocks, "cycle_markers": len(markers), "status_events": events,
            "opening_units": opening, "start_unix_s": start_unix, "start_clock": _clock(start_unix),
            "clock": "seconds on the tester's clock, written as a date and time without a time zone: whether that "
                     "clock kept UTC or local time is not recorded in the file",
            "active_mass_g_in_header": float(mass_g) if math.isfinite(mass_g) else None,
            "scale_check": scale, "time_check": clock, "truncated_tail_bytes": tail,
        },
    }
    evidence = ("Read natively. The record layout, the 0.01 s time unit and the voltage and current scales were "
                "established on a real LANHE file from its own statements in physical units (the step-start times, "
                "the capacity counter in Ah, the energy counter in Wh and the programmed setpoints), and each file "
                "is checked again where it holds enough records: " + _scale_sentence(scale) + ".")
    meta = {"instrument": INSTRUMENT, "profile": READER, "profile_version": READER_VERSION,
            "profile_evidence": evidence, "import_report": report, "import_findings": fnd.as_list(),
            "import_profile": description, "header_source": None, "instrument_steps": rows}
    if ok_mass:
        meta["active_mass_declared"] = {"value": float(mass_g), "unit": "g",
                                        "source": "the .cex header (offset 28; not yet verified on a file with a "
                                                  "mass set)"}
    raw = RawTable(source_name=path.name, source_sha256=hashlib.sha256(blob).hexdigest(), profile=READER, n=n,
                   t=t, i=i, e=e, step_id=step_seq.astype(float), cycle=None, step_kind=list(kind), dq=dq_ah,
                   columns=COLUMNS, report=report, findings=meta["import_findings"])
    return raw, meta


def _scale_sentence(scale: dict) -> str:
    if not scale.get("basis"):
        return "this file carries too little current for the check"
    parts = [f"the decoded current integrates to the tester's capacity counter within "
             f"{_pct(scale['current_ratio'])}"]
    if scale.get("voltage_ratio") is not None:
        parts.append(f"the decoded voltage reproduces the mean voltage of its energy and capacity counters within "
                     f"{_pct(scale['voltage_ratio'])}")
    return " and ".join(parts) + f" over {scale['intervals']} intervals of {scale['basis']}"


def _pct(ratio: float) -> str:
    """|ratio - 1| as a percentage with two significant figures (for example 0.0012 %), never rounded to zero."""
    return f"{abs(ratio - 1) * 100:.2g} %"


def _step_rows(steps, t, e, q, w, sv, si) -> list[dict]:
    """One row per step, as the tester ran them: the tester's step table rebuilt from the file."""
    out = []
    for s in steps:
        has = s.records > 0
        a, b = s.first, s.last
        unit = {1: "A", 2: "V", 3: ""}[STEP_TYPES[s.type][1]]
        setpoint = s.setpoint * (si if unit == "A" else sv) if unit else None
        if unit == "A" and setpoint is not None:
            setpoint *= s.direction                         # charge positive, as the current column
        out.append({
            "step": s.seq, "tester_step": s.code & 0x7FFF, "type": s.name, "type_code": f"{s.type:#04x}",
            "setpoint": setpoint, "setpoint_unit": unit, "start_unix_s": s.unix, "start_clock": _clock(s.unix),
            "cycle_marker": s.marker["cycle"] if s.marker else None,
            "first_record": a + 1 if has else None, "last_record": b + 1 if has else None, "records": s.records,
            "t_start_s": float(t[a]) if has else None, "t_end_s": float(t[b]) if has else None,
            "voltage_start_V": float(e[a]) if has else None, "voltage_end_V": float(e[b]) if has else None,
            "counter_start": s.counter_start, "capacity_end_Ah": float(q[b]) if has else None,
            "energy_end_Wh": float(w[b]) if has else None, "notes": "; ".join(s.notes),
        })
    return out
