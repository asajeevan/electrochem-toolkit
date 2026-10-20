"""Write a synthetic EC-Lab text export for demonstrations, screenshots and end-to-end tests.

    python scripts/make_demo_data.py [OUT_DIR]

The file, data/demo/cyclara_demo_synthetic.mpt, is NOT a measurement. Its header
says so in the Comments line, and its name says so. It imitates a galvanostatic
cycling test of a positive electrode against lithium metal:

- 50 cycles at C/5 between 2.30 and 3.80 V: constant-current charge, then a
  constant-voltage hold at 3.80 V until the current falls to C/20, 30-minute rests;
- an open-circuit potential with three regions (about 2.7, 3.05 and 3.5 V), so the
  differential capacity has distinct peaks;
- a coulombic efficiency of 87.8 % in the first cycle and 99.4 to 99.7 % afterwards, as
  recorded (the generator aims at 88 % and 99.6 to 99.9 %, but each discharge reaches
  the 2.30 V cut-off a little before its nominal charge); capacity fade of about 0.18 %
  per cycle and a slowly growing resistance, so the hysteresis widens.

Each row's dq/mA.h is the charge passed since the previous row, as EC-Lab records
it, and the per-cycle sums are written next to the file
(cyclara_demo_synthetic_truth.json): an end-to-end check with a known answer.
As an instrument does, a step's last point is recorded when its limit is reached,
after a partial interval, so capacities are not multiples of the sampling interval.
Deterministic: the small noise comes from a fixed seed.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

MASS_MG = 5.0
MOLAR_MASS = 214.4                 # g/mol: 1 x F / (3.6 x 214.4) = 125.0 mAh/g
Q_TH = 96485.33212 / (3.6 * MOLAR_MASS)
Q0 = Q_TH * MASS_MG * 1e-3 * 0.94  # first discharge, mAh
I_C5 = Q_TH * MASS_MG * 1e-3 / 5   # mA, C/5 on the theoretical capacity
E_MAX, E_MIN = 3.80, 2.30
DT = 90.0                          # s between rows while current flows
DT_REST = 120.0
N_CYCLES = 50
COLS = ["mode", "ox/red", "error", "control changes", "Ns changes", "counter inc.", "Ns", "time/s", "control/V/mA",
        "Ewe/V", "I/mA", "dq/mA.h", "(Q-Qo)/mA.h", "half cycle", "Q charge/discharge/mA.h", "cycle number"]


def crossing(g, lo=0.0, hi=1.0):
    """The fraction f in (lo, hi] of a sampling interval at which g(f) changes sign (bisection)."""
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if g(mid) >= 0:
            hi = mid
        else:
            lo = mid
    return hi


def ocv(x):
    """Open-circuit potential against Li+/Li at state of charge x (0 discharged, 1 charged)."""
    x = min(max(x, 1e-4), 1 - 1e-4)
    return (2.62 + 0.36 / (1 + math.exp(-(x - 0.27) / 0.022)) + 0.43 / (1 + math.exp(-(x - 0.66) / 0.026))
            + 0.10 * x + 0.035 * math.log(x / (1 - x)))


class Writer:
    def __init__(self):
        self.rows, self.t, self.q_total, self.half, self.ns = [], 0.0, 0.0, 0, None

    def row(self, mode, oxred, ns, i_mA, e, dq, q_branch, cycle, ctrl, dt):
        """One recorded point, dt after the previous one; dq is the charge passed in that interval."""
        self.t += dt
        changed = ns != self.ns
        self.ns = ns
        self.q_total += dq
        self.rows.append((mode, oxred, 0, int(changed), int(changed), 0, ns, self.t, ctrl, e, i_mA, dq, self.q_total,
                          self.half, abs(q_branch), cycle))


def main(out: Path):
    rng = np.random.default_rng(20261019)
    w = Writer()
    truth = []
    for k in range(16):                                    # initial rest, discharged
        w.row(3, 0, 0, 0.0, round(ocv(0.02) - 0.002 * math.exp(-k / 4), 6), 0.0, 0.0, 0, 0.0, 0.0 if k == 0 else DT_REST)
    for n in range(1, N_CYCLES + 1):
        qd = Q0 * (1 - 0.0018 * (n - 1)) * (1 + 0.002 * rng.standard_normal())
        ce = 0.88 if n == 1 else 0.996 + 0.003 * (1 - math.exp(-(n - 1) / 6)) + 0.0003 * rng.standard_normal()
        qc = qd / ce                                       # the charge this cycle passes for its discharge
        r_ohm = 220.0 * (1 + 0.006 * (n - 1))              # grows, so the hysteresis widens
        ir = I_C5 * r_ohm * 1e-3

        # ---- charge: constant current up to 3.80 V (the step's first point carries no charge yet)
        def e_ch(qq):
            u = qq / qc
            return ocv(u) + ir + 0.012 * math.log(1 / max(1 - u, 1e-3))
        q = 0.0
        dq = I_C5 * DT / 3600.0
        w.row(1, 1, 1, I_C5, round(ocv(0.0) + ir, 6), 0.0, 0.0, n - 1, I_C5, DT_REST)
        while True:
            if e_ch(q + dq) >= E_MAX or (q + dq) / qc >= 0.97:
                # the limit is reached inside this interval: the last point is recorded there
                f = crossing(lambda f: max(e_ch(q + f * dq) - E_MAX, (q + f * dq) / qc - 0.97))
                q += f * dq
                w.row(1, 1, 1, I_C5, round(e_ch(q), 6), f * dq, q, n - 1, I_C5, f * DT)
                break
            q += dq
            w.row(1, 1, 1, I_C5, round(e_ch(q), 6), dq, q, n - 1, I_C5, DT)
        # ---- constant voltage at 3.80 V: the current decays to C/20 and passes the rest of qc
        rest_q = max(qc - q, 1e-6)
        tau = rest_q * 3600.0 / (I_C5 * 0.75)              # I0 exp(-t/tau) down to I0/4 passes 0.75 I0 tau
        i = I_C5
        while q < qc - 1e-12:
            i_new = i * math.exp(-DT / tau)
            dq = (i - i_new) * tau / 3600.0                # exact charge over the interval
            if q + dq > qc:
                dq = qc - q
            q += dq
            w.row(2, 1, 2, i_new, round(E_MAX - 0.0002 * rng.random(), 6), dq, q, n - 1, E_MAX, DT)
            i = i_new
        q_charge = q
        # ---- rest after the charge: the potential relaxes towards the open-circuit value
        w.half += 1
        e_oc = ocv(0.985)
        for k in range(15):
            w.row(3, 1, 3, 0.0, round(e_oc + (E_MAX - e_oc) * math.exp(-(k + 1) * DT_REST / 360.0), 6), 0.0,
                  q_charge, n - 1, 0.0, DT_REST)
        # ---- discharge: constant current down to 2.30 V, the last point at the cut-off
        def e_dis(qq):
            u = qq / qd
            return ocv(1 - u) - ir - 0.012 * math.log(1 / max(1 - u, 1e-4))
        q = 0.0
        dq = I_C5 * DT / 3600.0                            # a full interval (the CV loop above changed dq)
        w.row(1, 0, 4, -I_C5, round(ocv(1.0) - ir, 6), 0.0, 0.0, n - 1, -I_C5, DT_REST)
        while True:
            if e_dis(q + dq) <= E_MIN or (q + dq) / qd >= 0.9995:
                f = crossing(lambda f: max(E_MIN - e_dis(q + f * dq), (q + f * dq) / qd - 0.9995))
                q += f * dq
                w.row(1, 0, 4, -I_C5, round(e_dis(q), 6), -f * dq, q, n - 1, -I_C5, f * DT)
                break
            q += dq
            w.row(1, 0, 4, -I_C5, round(e_dis(q), 6), -dq, q, n - 1, -I_C5, DT)
        q_discharge = q
        e_end = ocv(1 - q / qd) - ir
        # ---- rest after the discharge
        w.half += 1
        e_oc = ocv(0.03)
        for k in range(15):
            w.row(3, 0, 5, 0.0, round(e_oc + (e_end - e_oc) * math.exp(-(k + 1) * DT_REST / 360.0), 6), 0.0,
                  q_discharge, n, 0.0, DT_REST)
        truth.append({"cycle": n, "charge_mAh": q_charge, "discharge_mAh": q_discharge,
                      "coulombic_efficiency_pct": 100 * q_discharge / q_charge})

    header = [
        "EC-Lab ASCII FILE",
        "Nb header lines : 0",
        "",
        "Galvanostatic Cycling with Potential Limitation",
        "",
        "Run on channel : 1 (SN 00000)",
        "User : Cyclara demonstration",
        "Comments : SYNTHETIC DATA made by scripts/make_demo_data.py for demonstrations and tests. Not a measurement.",
        "Electrode connection : standard",
        "Potential control : Ewe",
        "Electrode material : synthetic positive electrode (three-region open-circuit potential)",
        "Initial state : discharged",
        "Electrolyte : none (synthetic)",
        f"Mass of active material : {MASS_MG:.3f} mg",
        " at x = 0.000",
        f"Molecular weight of active material (at x = 0) : {MOLAR_MASS:.3f} g/mol",
        "Atomic weight of intercalated ion : 6.941 g/mol",
        "Acquisition started at : xo = 0.000",
        "Number of e- transfered per intercalated ion : 1",
        "Electrode surface area : 1.131 cm2",
        "Cycle Definition : Charge/Discharge alternance",
        "\t".join(COLS),
    ]
    header[1] = f"Nb header lines : {len(header)}"
    fmt = lambda v: f"{v:.9E}" if isinstance(v, float) else str(v)
    lines = header + ["\t".join(fmt(v) for v in r) for r in w.rows]
    out.mkdir(parents=True, exist_ok=True)
    p = out / "cyclara_demo_synthetic.mpt"
    p.write_bytes(("\r\n".join(lines) + "\r\n").encode("cp1252"))
    (out / "cyclara_demo_synthetic_truth.json").write_text(json.dumps(
        {"note": "Per-cycle charges of the synthetic file: sums of its dq/mA.h column. Not a measurement.",
         "mass_mg": MASS_MG, "theoretical_capacity_mAh_g": Q_TH, "cycles": truth}, indent=1) + "\n")
    (out / "README.txt").write_text(
        "cyclara_demo_synthetic.mpt is SYNTHETIC: generated by scripts/make_demo_data.py, not measured.\n"
        "It is used for the screenshots, the handout and an end-to-end test against the exact per-cycle\n"
        "charges in cyclara_demo_synthetic_truth.json. Do not use it as evidence about any material.\n")
    print(p, f"{len(w.rows)} rows, {N_CYCLES} cycles, {p.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "data" / "demo")
