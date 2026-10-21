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
    4   layout code: 07 00 04 00 and 05 00 04 00 are read (the same units and records, each verified on a
        real file); any other is refused
    16  test start, Unix seconds (uint32)
    24  voltage range code (uint16): 0xE005 is 5 V
    26  current range code (uint16): 0xC00A is 1 mA; any other 0xC0nn is taken as nn x 0.1 mA only when the
        file's own capacity counter confirms it
    28  active-material mass in g (float32), 0 when not set: seen set in one real file, not yet compared with
        what was entered in the tester's software, so it is offered and never applied

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
      0x33  status event. Word 2: the event code (low 16 bits) and a parameter (high 16). Word 3: Unix
            seconds for most codes. See STATUS_EVENTS: start, end, step change (listed, not checked); a pause,
            a stop after which the tester restored an earlier state, and the resume that ends either; and events
            after which the records were found to continue unchanged (_breaks checks each against the records).
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
READER_VERSION = "1.1.0"
INSTRUMENT = "LANHE (LAND) battery tester"

MAGIC = b"\x10\x11\x09\x88"
HEADER_BYTES = 64
UNIT_BYTES = 16
LAYOUTS = (b"\x07\x00\x04\x00", b"\x05\x00\x04\x00")   # 16-byte records with float32 counters, each verified
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
BLOCK_TYPES_SEEN = (0xAA, 0x55, 0x78, 0x13, 0xCC)       # 0x13 the step plan (written again when it is edited);
                                                         # 0xCC written at each pause

# step type code -> (name, engine mode: 1 constant current, 2 constant voltage, 3 rest; direction: +1 charge)
STEP_TYPES = {0x70: ("rest", 3, 0), 0x03: ("cc_charge", 1, 1), 0x02: ("cc_discharge", 1, -1),
              0x05: ("cv_charge", 2, 1)}
# status event codes (low 16 bits of word 2), each seen in a real file, with what the records around them showed
STATUS_EVENTS = {
    0x0201: "start", 0x0101: "end", 0x0401: "step change",
    0x0802: "pause",                  # records continue after the resume; the record time does not count the pause
    0x0803: "stop",                   # after which the tester restored an earlier state. Word 3: the clock of that
                                      # state; on resuming, the record
                                      # time and the counters go back to it (a power failure, for example)
    0x0203: "resume",                 # word 3: the clock of the resume; ends a pause or a stop
    0x1008: "resume detail", 0x1012: "resume detail", 0x100E: "resume detail",   # written with every resume
    0x1013: "periodic",               # at regular intervals on the tester's clock; meaning unknown
    0x0402: "step plan edited",       # followed by a new step-plan block
    0x0404: "status 0x0404", 0x2001: "status 0x2001", 0x2004: "status 0x2004",    # meaning unknown
}
PAUSE, STOP_RESTORED, RESUME, PERIODIC = 0x0802, 0x0803, 0x0203, 0x1013
RESUME_DETAILS = (0x1008, 0x1012, 0x100E)         # only ever written with a resume, at the same place
# events after which the records were found to continue unchanged. Each occurrence inside a step is checked again
# (_continues); at a step boundary, or before the first record or after the last, they are listed only; the resume
# details are checked for their place only (with a resume)
INERT_EVENTS = RESUME_DETAILS + (PERIODIC, 0x0402, 0x0404, 0x2001, 0x2004)

SCALE_TOLERANCE = 2e-3            # decoded current and power against the counters, constant-current steps
SCALE_TOLERANCE_CV = 1e-2         # the same when only constant-voltage steps carry enough intervals
SCALE_MIN_INTERVALS = 20          # intervals needed for the scale check to decide
CLOCK_SLOPE_TOLERANCE = 1e-2      # record time against the step-start clock, per interval of at least a minute
CLOCK_OFFSET_S = 2.0              # a step's first record this far from its start on the clock is reported
CLOCK_MIN_SPAN_S = 60.0           # the clock check's intervals: step starts at least this far apart
CLOCK_DRIFT = 1e-4                # allowance for the record time's drift against the clock (1e-5 seen)
ROLLBACK_MAX_S = 120.0            # a restored state at most this far back in record time

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
    def mode(self):
        return STEP_TYPES[self.type][1]            # 1 constant current, 2 constant voltage, 3 rest

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
            events.append({"offset": at, "unit": k, "kind": code, "parameter": int(np.int16(np.uint16(w2 >> 16))),
                           "code": f"{w2:#010x}", "event": STATUS_EVENTS[code], "unix": w3, "clock": _clock(w3)})
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
                   + ". What the records after an event of this kind mean has not been established (an alarm, for "
                   "example, may write one); export the run to Excel from the tester's software",
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


REMEDY = "; export the run to Excel from the tester's software"


def _continues(j, row_step, steps, t, q, typical) -> bool:
    """Whether the records continue across the place before record j, inside one step: the time advances by
    no more than twice the largest of the step's other intervals and the usual logging interval of steps of
    its type (typical: {step type: median interval}; a step of two intervals, one of them a short last one,
    would otherwise allow almost nothing), and the capacity counter does not fall. A step with no other
    interval has nothing to compare with and passes."""
    step = steps[int(row_step[j])]
    a, b = step.first, step.last + 1
    h = np.diff(t[a:b])
    others = np.delete(h, j - 1 - a) if h.size > 1 else h[:0]
    limit = 2.0 * max(float(others.max()), typical.get(step.type, 0.0)) if others.size else np.inf
    return bool(0 < t[j] - t[j - 1] <= limit and q[j] >= q[j - 1])


def _inside_curve(steps, k) -> bool:
    """Whether a place inside step k lies inside its branch's dQ/dE curve (M01 section 9.3): a constant-current
    step is part of the curve; a constant-voltage step only when steps of the same direction that carry
    constant-current records lie on both sides of it in the same branch (no rest or other direction between)."""
    step = steps[k]
    if step.mode != 2:
        return True

    def cc_on(order):
        for j in order:
            other = steps[j]
            if other.records <= 0:
                continue
            if other.direction != step.direction:
                return False
            if other.mode == 1:
                return True
        return False
    return cc_on(range(k - 1, -1, -1)) and cc_on(range(k + 1, len(steps)))


def _breaks(events, rec_units, row_step, steps, t, q, w, typical, fnd: Findings):
    """Pauses and restarts, from the status events, checked against the records around them.

    A pause (0x0802) is ended by a resume (0x0203) with no record between them; inside a step the records then
    continue (_continues), and the record time does not count the pause. A stop after which the tester
    restored an earlier state (0x0803, word 3 the clock of that state) is also ended by a resume; the first
    record after it goes back in record time, by more than 0 s and at most ROLLBACK_MAX_S, within the step,
    and its capacity and energy counters lie between those of the two records around the moment the tester
    went back to. A stop resumed before the first record or after the last cannot be checked so and is
    refused. The resume details (RESUME_DETAILS) must sit where a resume is. Every other event of INERT_EVENTS
    that lies inside a step must sit where the records continue; at a step boundary, or before the first record
    or after the last, it is only listed. Start, end and step-change events are listed, not checked. Anything
    else refuses the file. Returns (pauses, restarts, open_at_end): open_at_end is the pause or stop the file ends in without
    a resume, if any. Each event gets its record index (the number of records before it)."""
    n = t.size
    for ev in events:
        ev["record"] = int(np.searchsorted(rec_units, ev["unit"]))     # records before the event
    resumed_at = {ev["record"] for ev in events if ev["kind"] == RESUME}
    pauses, restarts, open_break = [], [], None
    for ev in events:
        j, kind = ev["record"], ev["kind"]
        if kind in (PAUSE, STOP_RESTORED):
            if open_break is not None:
                fnd.refuse("cex_event_break", f"a {ev['event']} event at byte {ev['offset']} comes before the "
                           f"{open_break['event']} at byte {open_break['offset']} was resumed" + REMEDY,
                           offset=ev["offset"])
            open_break = ev
        elif kind == RESUME:
            if open_break is None:
                fnd.refuse("cex_event_break", f"a resume event at byte {ev['offset']} follows no pause or stop" + REMEDY,
                           offset=ev["offset"])
                continue
            if open_break["record"] != j:
                fnd.refuse("cex_event_break", f"records lie between the {open_break['event']} event at byte "
                           f"{open_break['offset']} and the resume at byte {ev['offset']}" + REMEDY, offset=ev["offset"])
            else:
                where = "before the first record" if j == 0 else "after the last record" if j == n else None
                entry = {"step": steps[int(row_step[min(j, n - 1)])].seq, "record": j + 1, "where": where,
                         "from_clock": open_break["clock"], "resumed_clock": ev["clock"],
                         "clock_s": int(ev["unix"]) - int(open_break["unix"]), "from_unix": int(open_break["unix"]),
                         "resumed_unix": int(ev["unix"]), "resume_offset": ev["offset"]}
                if open_break["kind"] == PAUSE:
                    if where is None and row_step[j] == row_step[j - 1] and not _continues(j, row_step, steps, t, q,
                                                                                          typical):
                        fnd.refuse("cex_event_break", f"the records break at the pause resumed at byte {ev['offset']} "
                                   f"(record {j + 1}): after the pauses seen, the records continue" + REMEDY,
                                   offset=ev["offset"], record=j + 1)
                    pauses.append(entry)
                elif where is None:
                    restarts.append(entry)
                else:
                    fnd.refuse("cex_restart_unverified", f"the tester resumed after a stop {where} (resume at byte "
                               f"{ev['offset']}), so the records cannot show what it restored" + REMEDY,
                               offset=ev["offset"])
            open_break = None
        elif kind in RESUME_DETAILS:
            if j not in resumed_at:
                fnd.refuse("cex_event_break", f"a {ev['event']} event at byte {ev['offset']} is not where a resume "
                           "is, the only place it was seen" + REMEDY, offset=ev["offset"])
        elif kind in INERT_EVENTS and 0 < j < n and row_step[j] == row_step[j - 1]:
            if not _continues(j, row_step, steps, t, q, typical):
                fnd.refuse("cex_event_break", f"the records break at the {ev['event']} event at byte {ev['offset']} "
                           f"(record {j + 1}): what an event of this kind means where the records do not continue "
                           "has not been established" + REMEDY, offset=ev["offset"], record=j + 1)
    since = {}                                      # step -> first record after its latest restart
    for r in restarts:
        j = r["record"] - 1
        back = float(t[j - 1] - t[j])
        k = int(row_step[j])
        a = max(steps[k].first, since.get(k, 0))     # the records since the step began, or since its last restart
        went_to = int(np.searchsorted(t[a:j], t[j], side="right")) - 1 + a       # last record at or before it
        nxt = min(went_to + 1, j - 1)
        tol, tol_w = 1e-9 + 1e-7 * abs(float(q[j])), 1e-9 + 1e-7 * abs(float(w[j]))   # float32: a part in 1e7
        bracketed = (went_to >= a and q[went_to] - tol <= q[j] <= q[nxt] + tol            # the counters of that
                     and w[went_to] - tol_w <= w[j] <= w[nxt] + tol_w)                     # moment, both
        if row_step[j - 1] != row_step[j] or not 0 < back <= ROLLBACK_MAX_S or not bracketed:
            fnd.refuse("cex_restart_unverified", f"at record {j + 1} (step {r['step']}) the tester resumed after a "
                       "stop, but the records do not go back to an earlier state the way a restart was verified to "
                       f"(within one step, more than 0 s and at most {ROLLBACK_MAX_S:g} s back in record time, the "
                       "restored capacity and energy counters between those of the two records around the moment "
                       "restored)" + REMEDY,
                       record=j + 1, step=r["step"])
            continue
        r.update(rollback_s=back, rollback_records=int(j - 1 - went_to), counter_drop_Ah=float(q[j - 1] - q[j]),
                 last_record_s=float(t[j - 1]), restored_record_s=float(t[j]))
        since[k] = j
    if open_break is not None and open_break["record"] < n:
        fnd.refuse("cex_event_break", f"records follow the {open_break['event']} event at byte {open_break['offset']} "
                   "without a resume event" + REMEDY, offset=open_break["offset"])
    return pauses, restarts, open_break


def _counters(steps, q, w, fnd: Findings, restored=()) -> np.ndarray:
    """Charge increments (Ah per record, charge positive) from the capacity counter, step by step.

    A step's counter starts at zero (reset) or at the last value of the step before it when that step ran
    in the same direction (carried). Anything else is reported and read as a reset whose first increment is
    the counter's first value. The counter never decreases inside a step, except at a verified restart
    (restored: the first record after one), where the tester went back to an earlier state: that record's
    increment is not a charge and is set to 0 (the engine does not integrate across a restart, whose record
    time goes back), and the increments after it continue from the restored value. Any other decrease
    refuses the file."""
    dq = np.zeros(q.size)
    restored = np.asarray(sorted(restored), dtype=np.int64)
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
        inside = restored[(restored > a) & (restored < b)] - a           # restarts inside this step
        drop = np.setdiff1d(np.flatnonzero(np.diff(qq) < 0), inside - 1)
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
                     "neither zero nor the values the step before it ended with; read as a reset whose first "
                     "increment is that value", step=s.seq, capacity_Ah=float(qq[0]), energy_Wh=float(ww[0]))
        inc = np.diff(qq, prepend=base)
        inc[inside] = 0.0
        dq[a:b] = inc * s.direction
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


def _clock_check(steps, t, start_unix, breaks=()) -> dict:
    """Record time against the steps' start times on the tester's clock (whole seconds).

    The record time does not count a pause or the time a stopped test stood still, so the clock time of each
    (from its events: resume minus pause or restored state) is added back first, for the step starts written
    after its resume event. Then:

    - the time unit: the step starts are taken in consecutive intervals of at least CLOCK_MIN_SPAN_S of
      clock, and in each the record time must advance as the clock does, within CLOCK_SLOPE_TOLERANCE plus
      the clock's resolution (2 s over the interval). A wrong unit fails every interval; a change of the
      clock (a summer-time change, for example) or a pause the file does not mark fails only the interval it
      falls in, so the unit is refused only when fewer than half the intervals agree;
    - between consecutive step starts, how far the two disagree beyond CLOCK_OFFSET_S plus a drift of
      CLOCK_DRIFT of the time between them: reported, with the place of the largest;
    - the least-squares slope over the whole test, reported for the drift of the record time against the
      clock (it is not the test of the unit: one change of the clock moves it)."""
    pts = [(s.unix - start_unix, float(t[s.first]), HEADER_BYTES + s.unit * UNIT_BYTES, s.seq)
           for s in steps if s.records > 0]
    if not pts:
        return {"steps_compared": 0}
    wall = np.array([p[0] for p in pts], float)
    written = np.array([p[2] for p in pts])                                 # byte offset of each step start
    at = np.array([b["resume_offset"] for b in breaks], dtype=np.int64)
    dur = np.array([b["clock_s"] for b in breaks], float)
    not_counted = np.array([dur[at < f].sum() for f in written]) if at.size else np.zeros(len(pts))
    rec = np.array([p[1] for p in pts], float) + not_counted
    off = rec - wall
    span = float(wall.max() - wall.min())
    slope = float(np.polyfit(wall, rec, 1)[0]) if len(pts) >= 2 and span >= CLOCK_MIN_SPAN_S else None
    ratios, agreeing, anchor = [], 0, 0
    for k in range(1, len(pts)):
        dw = wall[k] - wall[anchor]
        if dw >= CLOCK_MIN_SPAN_S:
            r = (rec[k] - rec[anchor]) / dw
            ratios.append(float(r))
            agreeing += bool(abs(r - 1) <= CLOCK_SLOPE_TOLERANCE + 2.0 / dw)
            anchor = k
    out = {"steps_compared": len(pts), "span_s": span, "intervals": len(ratios), "intervals_agreeing": agreeing,
           "median_ratio": float(np.median(ratios)) if ratios else None, "slope": slope, "largest_offset_s": 0.0,
           "pauses_and_restarts": len(breaks), "time_not_counted_s": float(dur.sum()), "disagreement": None,
           "places_disagreeing": 0}
    if len(pts) >= 2:
        d = np.diff(off)
        excess = np.abs(d) - (CLOCK_OFFSET_S + CLOCK_DRIFT * np.diff(wall))
        k = int(np.argmax(np.abs(d)))
        out["largest_offset_s"] = float(d[k])
        out["places_disagreeing"] = int(np.sum(excess > 0))
        if excess.max() > 0:
            k = int(np.argmax(excess))
            out["disagreement"] = {"between_steps": [pts[k][3], pts[k + 1][3]], "seconds": float(d[k])}
    return out


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
    if layout not in LAYOUTS:
        raise ImportFailure("cex_layout", f"{path.name} is a .cex file of layout {layout.hex(' ')}; this version reads "
                            "layouts " + " and ".join(x.hex(" ") for x in LAYOUTS) + " only, each verified on a real "
                            "file. Export the run to Excel from the tester's software, which this version reads.")
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
    d_t = np.diff(t)
    within = (row_step[1:] == row_step[:-1]) & (d_t > 0)
    step_type = np.array([s.type for s in steps])[row_step[1:]]
    typical = {int(k): float(np.median(d_t[within & (step_type == k)])) for k in np.unique(step_type[within])}
    pauses, restarts, ends_open = _breaks(events, rec_units, row_step, steps, t, q, w, typical, fnd)
    restored = {r["record"] - 1 for r in restarts if "rollback_s" in r}     # first record after each restart
    back = np.flatnonzero(np.diff(t) < 0)
    unexplained = [int(k) for k in back if int(k) + 1 not in restored]
    if unexplained:
        fnd.refuse("cex_time_backwards", f"the record time decreases at {len(unexplained)} place(s) that the tester's "
                   f"events do not mark as a restart, first at record {unexplained[0] + 2}: a concatenated run, which "
                   "this version does not read", records=len(unexplained), first=unexplained[0] + 2)
    step_seq = row_step + 1
    time_findings = Findings()
    check_time(time_findings, t, "record time", step_seq.astype(float))
    for f in time_findings.items:                     # a decrease at a restart is reported below, with its cause
        if not (f.code == "time_goes_backwards" and not unexplained):
            fnd.add(f.code, f.severity, f.message, **f.detail)
    dq_ah = _counters(steps, q, w, fnd, restored=restored)
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

    # --- pauses, restarts and the other events, as the records showed them ---------------------------------
    for pz in pauses:
        at = f"before record {pz['record']}" if pz["where"] is None else pz["where"]
        steps[pz["step"] - 1].notes.append(f"paused {pz['clock_s']} s on the tester's clock ({pz['from_clock']} to "
                                           f"{pz['resumed_clock']}) {at}")
    if pauses:
        fnd.note("cex_pauses", f"{len(pauses)} pause(s), {sum(p['clock_s'] for p in pauses)} s in all on the tester's "
                 "clock (" + ", ".join(f"step {p['step']}: {p['clock_s']} s" for p in pauses[:12])
                 + ("..." if len(pauses) > 12 else "") + "): the record time does not count a pause, and inside a step "
                 "the records continue after each. A pause inside the dQ/dE curve of a charge or discharge branch (between its "
                 "first and last record outside constant-voltage stages) removes the branch's dQ/dE, because the "
                 "potential relaxes while the current is off; a pause leaves its capacities and efficiency as they are",
                 pauses=pauses[:100])
    for r in restarts:
        if "rollback_s" not in r:
            continue
        hours = r["clock_s"] / 3600.0
        step = steps[r["step"] - 1]
        step.notes.append(f"stopped after record {r['record'] - 1}; resumed at {r['resumed_clock']} on the tester's "
                          f"clock with its state of {r['from_clock']} ({hours:.2f} h earlier), {r['rollback_s']:.1f} s "
                          "back in record time")
        if step.direction:
            what = (f"The {r['rollback_records']} record(s) of those seconds are kept, and so is the charge the "
                    f"tester's counter left out by going back ({r['counter_drop_Ah'] * 1e6:.3g} µAh). The interval "
                    "across the restart is not integrated, so the branch it belongs to counts as partial (M01): its "
                    "cycle has no efficiency or retention (and no cycle has a retention when that cycle is the "
                    "reference cycle)"
                    + (", and the branch has no dQ/dE, the restart lying inside its dQ/dE curve"
                       if _inside_curve(steps, r["step"] - 1) else
                       "; the restart lies in a constant-voltage hold, outside the branch's dQ/dE curve (no "
                       "constant-current records of the same direction on both sides of it), so the branch keeps "
                       "its dQ/dE (M01 section 9.3)"))
        else:
            what = (f"The {r['rollback_records']} record(s) of those seconds are kept; the step is a rest, so no "
                    "charge is involved, and its duration in record time does not count the time the tester was "
                    "stopped")
        fnd.warn("cex_restart", f"step {r['step']}: the tester stopped after record {r['record'] - 1} and resumed at "
                 f"{r['resumed_clock']} on its clock, {hours:.1f} h after {r['from_clock']}, the moment whose state it "
                 f"restored; so at record {r['record']} the record time goes back {r['rollback_s']:.1f} s and the "
                 "capacity and energy counters return to their values of that moment. " + what, **r)
    if ends_open is not None:
        kind_ = "pause" if ends_open["kind"] == PAUSE else "stop"
        fnd.note("cex_ends_paused", f"the file ends in a {kind_} (event at byte {ends_open['offset']}) that it does not "
                 "show resumed: the test may have been paused or stopped when the file was copied",
                 offset=ends_open["offset"])
    inert, where_ = {}, {"inside_steps": {}, "elsewhere": {}, "with_resumes": {}}
    for ev in events:
        if ev["kind"] in INERT_EVENTS:
            key = ev["event"] if ev["event"].startswith("status") else f"{ev['event']} ({ev['kind']:#06x})"
            inert[key] = inert.get(key, 0) + 1
            j = ev["record"]
            if ev["kind"] in RESUME_DETAILS:
                place = "with_resumes"
            elif 0 < j < n and row_step[j] == row_step[j - 1]:
                place = "inside_steps"
                if ev["kind"] != PERIODIC:
                    steps[int(row_step[j])].notes.append(f"{key} event before record {j + 1}; the records continue")
            else:
                place = "elsewhere"
            where_[place][key] = where_[place].get(key, 0) + 1
    if inert:
        parts = [label + ", ".join(f"{k} x{v}" for k, v in where_[place].items()) for place, label in (
            ("inside_steps", "inside a step, where the records were checked to continue across each: "),
            ("elsewhere", "at a step boundary, before the first record or after the last, listed only: "),
            ("with_resumes", "written with each resume, where each was checked to sit: ")) if where_[place]]
        fnd.note("cex_other_events", "other status events, as the records showed them: " + "; ".join(parts),
                 events=inert, where=where_)

    # --- the time unit against the tester's clock, then the scales against its own counters ------------------
    clock = _clock_check(steps, t, start_unix, pauses + [r for r in restarts if "rollback_s" in r])
    if clock.get("intervals") and 2 * clock["intervals_agreeing"] < clock["intervals"]:
        fnd.refuse("cex_time_base", f"the record time runs at {clock['median_ratio']:.4f} times the tester's clock "
                   f"between step starts (the median over {clock['intervals']} interval(s), "
                   f"{clock['intervals_agreeing']} agreeing), so its unit is not the 0.01 s this reader knows",
                   **{k: v for k, v in clock.items() if k != "disagreement"})
    elif clock.get("disagreement"):
        dis = clock["disagreement"]
        more, less = ("tester's clock", "record time") if dis["seconds"] < 0 else ("record time", "tester's clock")
        why = ("a change of the clock, or a pause the file does not mark" if dis["seconds"] < 0
               else "a change of the clock")
        fnd.warn("cex_clock_offset", f"from the start of step {dis['between_steps'][0]} to that of step "
                 f"{dis['between_steps'][1]} the {more} advanced {abs(dis['seconds']):.1f} s more than the {less}, "
                 f"beyond the pauses and restarts the file marks ({why})"
                 + (f"; {clock['places_disagreeing']} places disagree in all" if clock["places_disagreeing"] > 1
                    else "") + ". The record time is used",
                 **{k: v for k, v in clock.items() if k != "disagreement"}, between_steps=dis["between_steps"])
    if not clock.get("intervals"):
        fnd.note("cex_clock_not_checked", "the record time could not be checked against the tester's clock, which "
                 f"needs two step starts at least {CLOCK_MIN_SPAN_S:g} s apart; the 0.01 s unit verified on a real "
                 "file was used", **clock)
    restart_steps = {r["step"] for r in restarts}
    scale = _scale_check([s for s in steps if s.seq not in restart_steps], t, i, e, q, w)
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
        left = (f", once its {len(restart_steps)} step(s) with a restart are left out (their record time goes back)"
                if restart_steps else "")
        fnd.note("cex_scale_not_checked", "too few intervals carry current for the scales to be checked against the "
                 f"tester's counters in this file{left}; the verified scales of its range codes were used")
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
        "layout": layout.hex(" "), "time_unit_s": TIME_UNIT_S, "full_scale_counts": FULL_SCALE_COUNTS,
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
            "bytes": len(blob), "layout": layout.hex(" "), "units": int(n_units), "records": n, "steps": len(steps),
            "step_types": kinds, "pauses": pauses, "restarts": restarts, "other_events": inert,
            "other_events_where": where_,
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
                "is checked again where it holds enough records: " + _scale_sentence(scale, bool(restart_steps)) + ".")
    meta = {"instrument": INSTRUMENT, "profile": READER, "profile_version": READER_VERSION,
            "profile_evidence": evidence, "import_report": report, "import_findings": fnd.as_list(),
            "import_profile": description, "header_source": None, "instrument_steps": rows}
    if ok_mass:
        meta["active_mass_declared"] = {"value": float(mass_g), "unit": "g",
                                        "source": "the .cex header (offset 28; seen set in a real file, not yet "
                                                  "compared with the value entered in the tester's software)"}
    raw = RawTable(source_name=path.name, source_sha256=hashlib.sha256(blob).hexdigest(), profile=READER, n=n,
                   t=t, i=i, e=e, step_id=step_seq.astype(float), cycle=None, step_kind=list(kind), dq=dq_ah,
                   columns=COLUMNS, report=report, findings=meta["import_findings"],
                   paused_rows=np.array([pz["record"] - 1 for pz in pauses if pz["where"] is None], dtype=np.int64))
    return raw, meta


def _scale_sentence(scale: dict, restarts_left_out: bool = False) -> str:
    if not scale.get("basis"):
        return ("this file carries too little current for the check"
                + (" outside its steps with a restart, which are left out" if restarts_left_out else ""))
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
