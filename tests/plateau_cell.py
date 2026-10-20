"""A synthetic cell whose dQ/dE peaks, pairs and plateau capacities are known by construction.

Not a measurement. The capacity of each branch as a function of potential is a
sum of logistic steps, one per plateau, plus a small linear background:

    Q(E) = sum_i Q_i / (1 + exp(-(E - E_i) / s)) + C_bg (E - E_min)        (minus Q(E_min))

so dQ/dE is a sum of symmetric peaks of area Q_i centred at E_i, and the
capacity-weighted mean potential of a branch, integral of E dQ over Q, is
sum_i Q_i E_i + C_bg (E_max^2 - E_min^2) / 2 over sum_i Q_i + C_bg (E_max - E_min)
up to the logistic tails beyond the cut-offs (below 1e-9 of Q_i here).

Plateaus: three reversible ones (about 3.0, 3.4, 3.8 V) with the charge plateau 30 mV
above and the discharge plateau 30 mV below, a 60 mV hysteresis; one at 4.10 V
in the first charge only; one small reversible plateau at 2.65 V from cycle 3 on. The
centres sit between the 10 mV grid nodes, so a peak found on a node is off by up to half a bin.

It is sampled as an instrument records a galvanostatic test: constant current,
a row every DT seconds, the last row of each branch at the cut-off after a
partial interval, dq/mA.h the charge passed since the previous row, rests
between branches. Written as an EC-Lab text export so the whole import and
analysis path is exercised.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

E_MIN, E_MAX = 2.40, 4.30
S = 0.012                           # V, logistic scale: full width at half maximum 3.53 S = 42 mV
HYST = 0.060                        # V, charge plateau minus discharge plateau
C_BG = 0.005                        # mAh/V, linear background
I_MA = 0.10
DT = 20.0
REVERSIBLE = [(3.0047, 0.20), (3.4021, 0.30), (3.8063, 0.25)]  # (centre V, capacity mAh), off the grid nodes
IRREVERSIBLE = (4.1036, 0.08)                                # first charge only
LATE = (2.6512, 0.04)                                        # from cycle LATE_FROM on, both directions
LATE_FROM = 3
N_CYCLES = 5

COLS = ["mode", "ox/red", "error", "control changes", "Ns changes", "counter inc.", "Ns", "time/s", "control/V/mA",
        "Ewe/V", "I/mA", "dq/mA.h", "(Q-Qo)/mA.h", "half cycle", "Q charge/discharge/mA.h", "cycle number"]


def plateaus(cycle: int, direction: str) -> list[tuple[float, float]]:
    """(potential of the plateau in this branch, capacity) for one branch."""
    shift = HYST / 2 if direction == "charge" else -HYST / 2
    out = [(e + shift, q) for e, q in REVERSIBLE]
    if cycle >= LATE_FROM:
        out.append((LATE[0] + shift, LATE[1]))
    if cycle == 1 and direction == "charge":
        out.append(IRREVERSIBLE)
    return sorted(out)


def q_of_e(e, plats):
    """Capacity accumulated from E_MIN up to e, mAh (charge sense)."""
    def raw(x):
        return sum(q / (1 + math.exp(-(x - c) / S)) for c, q in plats) + C_BG * (x - E_MIN)
    return raw(e) - raw(E_MIN)


def branch_capacity(cycle, direction):
    return q_of_e(E_MAX, plateaus(cycle, direction))


def mean_potential(cycle, direction):
    """integral of E dQ over the branch / branch capacity, by construction (logistic tails neglected)."""
    plats = plateaus(cycle, direction)
    num = sum(q * c for c, q in plats) + C_BG * (E_MAX ** 2 - E_MIN ** 2) / 2
    den = sum(q for _, q in plats) + C_BG * (E_MAX - E_MIN)
    return num / den


def plateau_mean(cycle, direction):
    """Capacity-weighted mean of the plateau potentials alone (no background)."""
    plats = plateaus(cycle, direction)
    return sum(q * c for c, q in plats) / sum(q for _, q in plats)


def _invert(q_target, plats):
    lo, hi = E_MIN, E_MAX
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if q_of_e(mid, plats) < q_target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def write(path: Path) -> Path:
    rows = []
    t = 0.0
    q_total = 0.0
    half = 0
    ns_prev = None

    def row(mode, oxred, ns, i_ma, e, dq, qb, cyc, dt):
        nonlocal t, q_total, ns_prev
        t += dt
        changed = int(ns != ns_prev)
        ns_prev = ns
        q_total += dq
        rows.append((mode, oxred, 0, changed, changed, 0, ns, t, i_ma, e, i_ma, dq, q_total, half, abs(qb), cyc))

    for k in range(5):
        row(3, 0, 0, 0.0, E_MIN, 0.0, 0.0, 0, 0.0 if k == 0 else 60.0)
    for n in range(1, N_CYCLES + 1):
        for direction, ns in (("charge", 1), ("discharge", 3)):
            plats = plateaus(n, direction)
            qb = q_of_e(E_MAX, plats)
            sign = 1 if direction == "charge" else -1
            dq_full = I_MA * DT / 3600.0

            def pot(q):          # discharge: from E_MAX down, the capacity counted from E_MAX
                return _invert(q, plats) if sign > 0 else _invert(qb - q, plats)
            q = 0.0
            row(1, int(sign > 0), ns, sign * I_MA, pot(0.0), 0.0, 0.0, n - 1, 60.0)
            while True:
                if q + dq_full >= qb:
                    f = (qb - q) / dq_full
                    q = qb
                    row(1, int(sign > 0), ns, sign * I_MA, E_MAX if sign > 0 else E_MIN, sign * f * dq_full, q, n - 1,
                        f * DT)
                    break
                q += dq_full
                row(1, int(sign > 0), ns, sign * I_MA, pot(q), sign * dq_full, q, n - 1, DT)
            half += 1
            e_end = E_MAX if sign > 0 else E_MIN
            for k in range(5):
                row(3, int(sign > 0), ns + 1, 0.0, e_end, 0.0, q, n - 1 if sign > 0 else n, 60.0)
    header = [
        "EC-Lab ASCII FILE",
        "Nb header lines : 0",
        "",
        "Galvanostatic Cycling with Potential Limitation",
        "",
        "Comments : SYNTHETIC DATA made by tests/plateau_cell.py for tests. Not a measurement.",
        "Electrode connection : standard",
        "Potential control : Ewe",
        "Cycle Definition : Charge/Discharge alternance",
        "\t".join(COLS),
    ]
    header[1] = f"Nb header lines : {len(header)}"
    fmt = lambda v: f"{v:.9E}" if isinstance(v, float) else str(v)
    lines = header + ["\t".join(fmt(v) for v in r) for r in rows]
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("cp1252"))
    return path
