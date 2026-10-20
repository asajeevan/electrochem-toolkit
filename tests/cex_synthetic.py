"""Synthetic LANHE .cex files whose every number is known by construction.

Not a measurement and not derived from any real file: the bytes are written from the format description
in electrochem/readers/lanhe_cex.py, and the tests compare what the reader decodes with what was written.

A protocol is a list of Step. Time runs in whole centiseconds. Each step starts on the tester's side when
the step before it wrote its last record; its first record follows GAP later (the first step's at t = 0), and
then one record every `every` seconds, the last at the step's end after a partial interval when the
duration is not a whole number of intervals, as a tester logs. The tester's counters behave as the reader
expects of a real file: zero at a step's first record (or the step before's last values when `carry`), and
from the second record on, the charge (Ah) and the energy (Wh) since the step started on the tester's side,
so the first increment includes the gap.

Currents of constant-current steps are whole counts, so the decoded current equals the written one
exactly; the voltage is linear in time within a step and is rounded to counts, as a tester does.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

import numpy as np

MAGIC = b"\x10\x11\x09\x88"
LAYOUT = b"\x07\x00\x04\x00"
FULL = 0x7E00
START = 1_700_000_000                 # Unix seconds of the synthetic test start
GAP = 0.20                            # s between a step's last record and the next step's first
BLOCK, BLOCK_END, CTRL, CTRL_STEP = 0xFFFFAAAA, 0xFFFFBBBB, 0xFFFFCCCC, 0xFFFFCCCD
TYPE = {"rest": 0x70, "cc_charge": 0x03, "cc_discharge": 0x02, "cv_charge": 0x05}
SIGN = {"rest": 0, "cc_charge": 1, "cc_discharge": -1, "cv_charge": 1}


@dataclass
class Step:
    kind: str
    duration: float                   # s, from the step's first record to its last
    every: float = 10.0               # s between records
    counts: int = 0                   # constant current: magnitude in counts; constant voltage: current at its start
    v0: float = 3.5                   # V at the step's start on the tester's side
    v1: float | None = None           # V at its last record (linear between); None: constant
    tau: float = 600.0                # s, current decay of a constant-voltage step
    carry: bool = False               # counters carried from the step before
    type_code: int | None = None      # override the step type code (unknown types)


@dataclass
class Truth:
    t: list = field(default_factory=list)            # s
    v: list = field(default_factory=list)            # V as written (rounded to counts)
    i: list = field(default_factory=list)            # A as written
    step: list = field(default_factory=list)         # 1-based
    q_end: list = field(default_factory=list)        # Ah, counter at each step's last record
    w_end: list = field(default_factory=list)        # Wh
    charge: list = field(default_factory=list)       # Ah passed in each step, gap included (the counter's view)
    charge_records: list = field(default_factory=list)   # Ah passed between each step's first and last record
    energy: list = field(default_factory=list)       # Wh passed in each step, gap included


def u(w0, w1, w2, w3) -> bytes:
    return struct.pack("<4I", w0 & 0xFFFFFFFF, w1 & 0xFFFFFFFF, w2 & 0xFFFFFFFF, w3 & 0xFFFFFFFF)


def header(start=START, v_code=0xE005, i_code=0xC00A, mass_g=0.0, layout=LAYOUT) -> bytes:
    h = bytearray(64)
    h[0:4] = MAGIC
    h[4:8] = layout
    struct.pack_into("<I", h, 16, start)
    struct.pack_into("<HH", h, 24, v_code, i_code)
    struct.pack_into("<f", h, 28, mass_g)
    return bytes(h)


def block(typ: int, payload: bytes) -> bytes:
    assert len(payload) % 16 == 0
    w1 = typ | (len(payload) << 16)
    return u(BLOCK, w1, 0, 0) + payload + u(BLOCK_END, w1, 0, 0)


def control(kind: int, w2=0, w3=0, hi=0, sig=CTRL) -> bytes:
    return u(sig, kind | (hi << 16), w2, w3)


def record(t_cs: int, v: int, i: int, q: float, w: float) -> bytes:
    return struct.pack("<Ihhff", t_cs, v, i, q, w)


def preamble() -> bytes:
    plan = bytearray(3104)
    plan[0:4] = b"\x22\x11\x09\x88"
    return (block(0xAA, bytes(64)) + control(0x88, 0x00060002, 2) + block(0x55, bytes(16))
            + block(0x78, bytes(384)) + block(0x13, bytes(plan)))


def write(steps: list[Step], *, v_fs=5.0, i_fs=1e-3, v_code=0xE005, i_code=0xC00A, mass_g=0.0,
          end_event=True, start=START, time_unit=0.01) -> tuple[bytes, Truth]:
    """The file and its truth. v_fs and i_fs set the scales the counts are written with; the header states
    v_code and i_code, so a header can be made to disagree with its data. time_unit is the unit the
    record time is written in (the tester's is 0.01 s). The truth holds the physical values written."""
    sv, si = v_fs / FULL, i_fs / FULL
    out = bytearray(header(start, v_code, i_code, mass_g))
    out += preamble()
    out += control(0x33, 0x0201, start)
    tr = Truth()
    t_prev = None                                    # last record time of the step before, s
    q_prev = w_prev = 0.0
    direction_prev = None
    cycle = 0
    for k, st in enumerate(steps):
        sgn = SIGN[st.kind]
        if sgn and sgn != direction_prev:
            if direction_prev is not None and sgn == 1:
                cycle += 1
            out += control(0x44, 1 if sgn < 0 else 0, (cycle << 16) | 0x8000 | (k + 1))
            direction_prev = sgn
        t_start = 0.0 if t_prev is None else t_prev                  # the step starts on the tester's side
        t_first = 0.0 if t_prev is None else t_prev + GAP
        times = [t_first + j * st.every for j in range(int(math.floor(st.duration / st.every + 1e-9)) + 1)]
        if times[-1] < t_first + st.duration - 1e-9:
            times.append(t_first + st.duration)
        times = [round(x * 100) / 100 for x in times]
        wall = start + int(math.floor(t_start + (0 if t_prev is None else GAP)))
        typ = st.type_code if st.type_code is not None else TYPE[st.kind]
        setpoint = (st.counts if st.kind.startswith("cc") else
                    round(st.v0 / sv) if st.kind == "cv_charge" else 0)
        out += control(0x22, (setpoint << 16) | (0x85 if st.carry else 0x05) << 8 | typ, wall, hi=0x8000 | (k + 1),
                       sig=CTRL_STEP)
        v1 = st.v0 if st.v1 is None else st.v1
        span = times[-1] - t_start

        def volt(x):                                  # x: s since the step started on the tester's side
            return st.v0 + (v1 - st.v0) * (x / span if span else 0.0)

        def amps(x):
            if st.kind == "cv_charge":
                return st.counts * si * math.exp(-x / st.tau)
            return sgn * st.counts * si

        def charge(x):                                # Ah since the tester's start of the step
            if st.kind == "cv_charge":
                return st.counts * si * st.tau * (1 - math.exp(-x / st.tau)) / 3600
            return st.counts * si * x / 3600

        def energy(x):                                # Wh: integral of V |I| dt
            if st.kind == "cv_charge":
                return st.v0 * charge(x)
            a, b = st.v0, (v1 - st.v0) / span if span else 0.0
            return st.counts * si * (a * x + b * x * x / 2) / 3600

        q_base = q_prev if st.carry else 0.0
        w_base = w_prev if st.carry else 0.0
        for j, tt in enumerate(times):
            x = tt - t_start
            v_counts = int(round(volt(x) / sv))
            i_true = amps(x)
            i_counts = int(round(i_true / si)) if sgn else 0
            if sgn == 0 or j == 0:
                q, w = q_base, w_base
            else:
                q, w = q_base + charge(x), w_base + energy(x)
            q32 = struct.unpack("<f", struct.pack("<f", q))[0]
            w32 = struct.unpack("<f", struct.pack("<f", w))[0]
            out += record(int(round(tt / time_unit)), v_counts, i_counts, q32, w32)
            tr.t.append(tt); tr.v.append(v_counts * sv); tr.i.append(i_counts * si); tr.step.append(k + 1)
        x_end = times[-1] - t_start
        tr.q_end.append(q32); tr.w_end.append(w32)
        tr.charge.append(charge(x_end) if sgn else 0.0)
        tr.charge_records.append((charge(x_end) - charge(times[0] - t_start)) if sgn else 0.0)
        tr.energy.append(energy(x_end) if sgn else 0.0)
        t_prev = times[-1]
        q_prev, w_prev = (q32, w32) if sgn else (q_prev, w_prev)
    if end_event:
        out += control(0x33, 0x0101, start + int(math.floor(t_prev)))
    return bytes(out), tr


def two_cycles(**kw) -> list[Step]:
    """Rest; constant-current charge to 4.1 V then a constant-voltage hold carrying the counters; rest;
    discharge; rest; a second charge and discharge; a closing rest, so both cycles are complete."""
    return [
        Step("rest", 0.0, v0=3.20),
        Step("cc_charge", 3600.0, counts=16128, v0=3.30, v1=4.10, **kw),           # 0.5 mA
        Step("cv_charge", 1800.0, counts=16128, v0=4.10, tau=400.0, carry=True, **kw),
        Step("rest", 600.0, v0=4.05, every=60.0),
        Step("cc_discharge", 3000.0, counts=16128, v0=4.00, v1=2.90, **kw),
        Step("rest", 600.0, v0=3.10, every=60.0),
        Step("cc_charge", 3200.0, counts=8064, v0=3.30, v1=4.05, **kw),              # 0.25 mA
        Step("cc_discharge", 6000.0, counts=8064, v0=4.00, v1=2.85, **kw),
        Step("rest", 300.0, v0=3.05, every=60.0),
    ]


def records_of(blob: bytes) -> np.ndarray:
    """Byte offsets of the data records (units whose first word is below 0xFFFF0000 and that lie outside
    blocks), for tests that edit one record."""
    out, k = [], 64
    while k + 16 <= len(blob):
        w0, w1 = struct.unpack_from("<II", blob, k)
        if w0 == BLOCK:
            k += 16 + (w1 >> 16) + 16
            continue
        if w0 < 0xFFFF0000:
            out.append(k)
        k += 16
    return np.array(out)
