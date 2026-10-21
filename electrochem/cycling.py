"""Cycling quantities under the M01 contract.

Interpolation model: current and voltage vary linearly between consecutive
samples (M01 "point_linear"). Then, per supported edge of duration h with
end values (I0, I1) and (U0, U1):

    charge   dQ = h (I0 + I1) / 2                                  [C]
    energy   dW = h (2 I0 U0 + I0 U1 + I1 U0 + 2 I1 U1) / 6        [J]

The energy formula is the exact integral of the product of two linear
functions; it reproduces the 38/3 J reference of case S02.

Only supported edges contribute. Charge for a branch is the magnitude of the
signed sum.

When the file carries the instrument's per-row charge increment (dq/mA.h),
that increment is the primary charge: the instrument integrates at its full
acquisition rate, whereas exported rows are sparse samples. On constant-
voltage tails the sampled current is a poor description of the decay, and
trapezoidal integration over 300 s intervals can overstate the tail by tens
of percent. The trapezoidal value from sampled current is always reported
beside it as an independent check; on constant-current stages the two agree
to about 1e-6.

Energy needs a declared voltage: --terminal-voltage for a two-electrode cell
voltage, or --reference for a metal half-cell, where the measured potential
is the electrode potential against the metal counter electrode and includes
the counter electrode's polarisation. Energies from a half-cell are labelled
"vs. reference" and refer to the active material only, never to a packaged
cell.

Terminology used in the outputs:
    capacity                 charge passed in one branch, mAh
    specific capacity        capacity per gram of active material, mAh/g
    areal capacity           capacity per cm2 of electrode, mAh/cm2
    coulombic efficiency     100 x Q_discharge / Q_charge of the same cycle
    capacity retention       100 x Q_discharge(n) / Q_discharge(reference cycle)
    average voltage          energy / charge for one branch (charge-weighted mean potential)
    mid-capacity voltage     voltage at half of the branch capacity
    voltage hysteresis       average charge voltage minus average discharge voltage
    energy efficiency        100 x E_discharge / E_charge
    specific current         current per gram of active material, mA/g
    C-rate                   current / (theoretical capacity x mass); 1C = full theoretical capacity in 1 h
    degree of reaction, dx   charge / (n F m / M); the number of electrons (or ions) per formula unit exchanged
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .segment import Segmentation, Branch, Pair, CV, REST
from .table import Table

F = 96485.33212  # C/mol

# A branch of at most two rows (one recorded interval, or a single record) that carries less than this fraction
# of the charge of the branch it is paired with is a step that ended at once, for example a charge to a voltage
# limit started on a cell already beyond that limit. Found while checking a real file, where charge-first pairing
# put such a step with the full discharge after it and gave a coulombic efficiency of millions of per cent. The
# ratios of such a pair describe that step, not the cell: no efficiency, energy efficiency or hysteresis is given
# for it, and when the discharge is the branch that ended at once, no retention either (M01 section 6).
DEGENERATE_ROWS = 2
DEGENERATE_FRACTION = 1e-3
ENDED_AT_ONCE = "a step that ended at once"          # the words every such note carries


def degenerate(b: Branch, q_mAh: float | None, partner_q_mAh: float | None) -> bool:
    """True for a branch of at most DEGENERATE_ROWS rows carrying under DEGENERATE_FRACTION of its partner's charge."""
    if q_mAh is None or partner_q_mAh is None or not partner_q_mAh > 0:
        return False
    return (b.end - b.start + 1) <= DEGENERATE_ROWS and q_mAh < DEGENERATE_FRACTION * partner_q_mAh


def degenerate_note(b: Branch, r, partner) -> str:
    """The words for a degenerate branch b (result r) paired with or followed by `partner` (a result)."""
    span = ("is a single record" if b.end == b.start else
            f"spans one recorded interval ({r.duration_s:.3g} s)")
    return (f"the {r.direction} branch {r.branch} {span} and carries "
            f"{100 * r.charge_mAh / partner.charge_mAh:.2g} % of the charge of {partner.direction} branch "
            f"{partner.branch}: {ENDED_AT_ONCE}")


def integrate(t, i, e, supported, dq=None):
    """Signed charge (C) and signed energy (J) over supported edges.

    dq: optional instrument charge increments (C) per row; dq[k+1] belongs to
    edge k. When given, charge is the sum of increments and energy is the
    increment times the mean edge voltage. Otherwise both use the point-linear
    model. e may be None; energy is then None. Returns (Q, W, duration_s).
    """
    t = np.asarray(t, float); i = np.asarray(i, float)
    h = np.diff(t)
    m = np.asarray(supported, bool)
    dur = float(np.sum(h[m]))
    if dq is not None:
        inc = np.asarray(dq, float)[1:][m]
        if np.all(np.isfinite(inc)):
            q = np.sum(inc)
            if e is None:
                return float(q), None, dur
            e = np.asarray(e, float)
            u0, u1 = e[:-1][m], e[1:][m]
            if not np.all(np.isfinite(u0)) or not np.all(np.isfinite(u1)):
                return float(q), None, dur
            return float(q), float(np.sum(inc * (u0 + u1) / 2.0)), dur
    q = np.sum(h[m] * (i[:-1][m] + i[1:][m]) / 2.0)
    if e is None:
        return float(q), None, dur
    e = np.asarray(e, float)
    i0, i1, u0, u1 = i[:-1][m], i[1:][m], e[:-1][m], e[1:][m]
    if not np.all(np.isfinite(u0)) or not np.all(np.isfinite(u1)):
        return float(q), None, dur
    w = np.sum(h[m] * (2 * i0 * u0 + i0 * u1 + i1 * u0 + 2 * i1 * u1) / 6.0)
    return float(q), float(w), dur


def cumulative_charge(tab: Table, seg: Segmentation, b: Branch, use_dq: bool) -> np.ndarray:
    """Cumulative |charge| in C along a branch, zero at its first row."""
    sl = b.rows
    t, i = tab.t[sl], tab.i[sl]
    sup = seg.edges.supported[b.start:b.end]
    dq = tab.dq[sl] if (tab.dq is not None and use_dq) else None
    if dq is not None and np.all(np.isfinite(dq[1:])):
        inc = np.where(sup, dq[1:], 0.0)
    else:
        inc = np.where(sup, np.diff(t) * (i[:-1] + i[1:]) / 2.0, 0.0)
    return np.concatenate(([0.0], np.cumsum(np.abs(inc))))


@dataclass
class Settings:
    charge: str | None = None               # "ox"/"positive" or "red"/"negative"
    cycle_order: str = "charge-first"
    terminal_voltage: bool = False          # potential column is the two-electrode cell voltage
    reference: str | None = None            # e.g. "Li/Li+" for a metal half-cell
    active_mass_mg: float | None = None
    area_cm2: float | None = None
    molar_mass_g_mol: float | None = None   # for degree of reaction and theoretical capacity
    electrons: float | None = None          # electrons per formula unit for the theoretical capacity
    reference_cycle: int = 1
    rest_current_a: float = 0.0
    use_instrument_dq: bool = True
    peak_pair_window_mV: float = 200.0      # dQ/dE: pairs charge and discharge peaks of a cycle, follows peaks across cycles

    @property
    def energy_allowed(self) -> bool:
        return self.terminal_voltage or bool(self.reference)

    @property
    def potential_role(self) -> str | None:
        """Which potential column the answers call for: "cell" (terminal voltage), "working" (vs. a reference)."""
        return "cell" if self.terminal_voltage else ("working" if self.reference else None)

    @property
    def theoretical_capacity_mAh_g(self) -> float | None:
        if self.molar_mass_g_mol and self.electrons and self.molar_mass_g_mol > 0 and self.electrons > 0:
            return theoretical_capacity_mAh_g(self.electrons, self.molar_mass_g_mol)
        return None


@dataclass
class BranchResult:
    branch: int
    direction: str
    native_cycle: int | None
    native_half_cycle: int | None
    steps: str
    modes: str
    complete: bool
    terminated_by: str
    t_start_s: float
    t_end_s: float
    duration_s: float
    supported_duration_s: float
    charge_mAh: float
    charge_method: str
    charge_trapezoid_mAh: float
    charge_cc_mAh: float | None
    charge_cv_mAh: float | None
    cv_fraction_pct: float | None
    specific_capacity_mAh_g: float | None
    areal_capacity_mAh_cm2: float | None
    utilisation_pct: float | None           # 100 x specific capacity / theoretical capacity
    delta_x: float | None                   # electrons per formula unit exchanged in this branch
    mean_current_mA: float
    specific_current_mA_g: float | None
    current_density_mA_cm2: float | None
    c_rate: float | None
    c_rate_label: str | None
    voltage_start_V: float | None
    voltage_end_V: float | None
    mid_capacity_voltage_V: float | None
    average_voltage_V: float | None
    energy_mWh: float | None
    specific_energy_Wh_kg: float | None
    ocv_before_V: float | None              # potential at the end of the preceding rest
    rest_before_s: float | None
    ocv_after_V: float | None               # potential at the end of the following rest
    rest_after_s: float | None
    relaxation_after_V: float | None        # ocv_after minus voltage_end (IR drop plus relaxation)
    temperature_mean_C: float | None
    instrument_charge_mAh: float | None
    instrument_relative_difference: float | None
    notes: str


@dataclass
class CycleResult:
    cycle: int
    native_cycle: int | None
    complete: bool
    charge_branch: int | None
    discharge_branch: int | None
    charge_capacity_mAh: float | None
    discharge_capacity_mAh: float | None
    charge_specific_mAh_g: float | None
    discharge_specific_mAh_g: float | None
    coulombic_efficiency_pct: float | None
    coulombic_inefficiency_pct: float | None
    capacity_retention_pct: float | None
    charge_delta_x: float | None
    discharge_delta_x: float | None
    average_charge_voltage_V: float | None
    average_discharge_voltage_V: float | None
    average_voltage_hysteresis_V: float | None
    mid_capacity_charge_voltage_V: float | None
    mid_capacity_discharge_voltage_V: float | None
    mid_capacity_hysteresis_V: float | None
    charge_energy_mWh: float | None
    discharge_energy_mWh: float | None
    discharge_specific_energy_Wh_kg: float | None
    energy_efficiency_pct: float | None
    charge_c_rate: float | None
    discharge_c_rate: float | None
    charge_cv_fraction_pct: float | None
    ocv_before_charge_V: float | None
    ocv_after_discharge_V: float | None
    note: str


@dataclass
class RestResult:
    rest: int
    after_branch: int | None
    before_branch: int | None
    t_start_s: float
    duration_s: float
    voltage_start_V: float | None
    voltage_end_V: float | None
    relaxation_V: float | None
    steps: str


@dataclass
class Summary:
    complete_cycles: int
    reference_cycle: int
    first_cycle_charge_mAh: float | None
    first_cycle_discharge_mAh: float | None
    first_cycle_specific_discharge_mAh_g: float | None
    first_cycle_coulombic_efficiency_pct: float | None
    max_discharge_capacity_mAh: float | None
    max_discharge_cycle: int | None
    last_cycle: int | None
    last_discharge_capacity_mAh: float | None
    last_specific_discharge_mAh_g: float | None
    retention_at_last_cycle_pct: float | None
    cycle_reaching_80pct_retention: int | None
    capacity_fade_pct_per_cycle: float | None      # linear fit of retention from the reference cycle on
    capacity_fade_fit_cycles: str | None
    mean_coulombic_efficiency_pct: float | None    # cycles after the first, complete only
    mean_coulombic_efficiency_last10_pct: float | None
    mean_average_discharge_voltage_V: float | None
    mean_voltage_hysteresis_V: float | None
    theoretical_capacity_mAh_g: float | None
    first_cycle_utilisation_pct: float | None
    total_test_time_h: float
    notes: str


def _rate_label(c: float) -> str:
    if c >= 1:
        return f"{c:.3g}C"
    return f"C/{1 / c:.3g}"


def _mid_voltage(q: np.ndarray, e: np.ndarray | None) -> float | None:
    if e is None or q[-1] <= 0 or not np.all(np.isfinite(e)):
        return None
    return float(np.interp(q[-1] / 2.0, q, e))


def _rests(tab: Table, seg: Segmentation) -> list:
    if tab.mode is None:
        return []
    mode = tab.mode.astype(int)
    n = tab.n
    out = []
    starts = {b.start: b.index for b in seg.branches}
    ends = {b.end: b.index for b in seg.branches}
    k = 0
    while k < n:
        if mode[k] != REST:
            k += 1
            continue
        a = k
        while k + 1 < n and mode[k + 1] == REST:
            k += 1
        b = k
        e = tab.e
        v0 = float(e[a]) if e is not None and np.isfinite(e[a]) else None
        v1 = float(e[b]) if e is not None and np.isfinite(e[b]) else None
        steps = "+".join(str(int(x)) for x in dict.fromkeys(tab.ns[a:b + 1])) if tab.ns is not None else ""
        out.append(RestResult(
            rest=len(out) + 1, after_branch=ends.get(a - 1), before_branch=starts.get(b + 1),
            t_start_s=float(tab.t[a]), duration_s=float(tab.t[b] - tab.t[a]),
            voltage_start_V=v0, voltage_end_V=v1,
            relaxation_V=(v1 - v0) if (v0 is not None and v1 is not None) else None, steps=steps))
        k += 1
    return out


def _branch_result(tab, seg, b, s, rests_after, rests_before) -> BranchResult:
    sl = b.rows
    t, i = tab.t[sl], tab.i[sl]
    e = tab.e[sl] if tab.e is not None else None
    sup = seg.edges.supported[b.start:b.end]
    dq = tab.dq[sl] if (tab.dq is not None and s.use_instrument_dq) else None
    q, w, dur = integrate(t, i, e if s.energy_allowed else None, sup, dq)
    q_trap, _, _ = integrate(t, i, None, sup)
    method = "instrument dq increments" if dq is not None else "trapezoid of sampled current"
    q_mAh = abs(q) / 3.6
    q_cc = q_cv = cv_frac = None
    if tab.mode is not None:
        mode = tab.mode[sl]
        cv_edge = mode[1:] == CV      # an edge belongs to the stage its end row is recorded in
        qcv, _, _ = integrate(t, i, None, sup & cv_edge, dq)
        q_cv = abs(qcv) / 3.6
        q_cc = q_mAh - q_cv
        cv_frac = 100 * q_cv / q_mAh if q_mAh > 0 else None
    energy = abs(w) / 3.6 if w is not None else None          # mWh
    avg_v = (energy / q_mAh) if (energy is not None and q_mAh > 0) else None
    mass_g = s.active_mass_mg * 1e-3 if (s.active_mass_mg and s.active_mass_mg > 0) else None
    spec = q_mAh / mass_g if mass_g else None
    spec_e = (energy / mass_g) if (energy is not None and mass_g) else None  # mWh/g = Wh/kg
    areal = q_mAh / s.area_cm2 if (s.area_cm2 and s.area_cm2 > 0) else None
    mean_i_mA = float(np.nanmean(np.abs(i))) * 1e3
    spec_i = mean_i_mA / mass_g if mass_g else None
    j = mean_i_mA / s.area_cm2 if (s.area_cm2 and s.area_cm2 > 0) else None
    qth = s.theoretical_capacity_mAh_g
    util = 100 * spec / qth if (spec is not None and qth) else None
    c_rate = (spec_i / qth) if (spec_i is not None and qth) else None
    dx = (abs(q) * s.molar_mass_g_mol) / (F * mass_g) if (mass_g and s.molar_mass_g_mol) else None
    qcum = cumulative_charge(tab, seg, b, s.use_instrument_dq)
    mid = _mid_voltage(qcum, e)
    ra = rests_after.get(b.index); rb = rests_before.get(b.index)
    ocv_after = ra.voltage_end_V if ra else None
    inst = rel = None
    if tab.q_instrument is not None:
        qi = tab.q_instrument[sl]
        if np.isfinite(qi[0]) and np.isfinite(qi[-1]):
            inst = abs(qi[-1] - qi[0]) / 3.6
            rel = (q_mAh - inst) / inst if inst > 0 else None
    temp = None
    if getattr(tab, "temperature", None) is not None:
        tt = tab.temperature[sl]
        if np.any(np.isfinite(tt)):
            temp = float(np.nanmean(tt))
    notes = list(b.notes)
    if not s.energy_allowed:
        notes.append("energy not calculated: say whether the potential is the cell voltage or against a reference")
    elif s.reference and not s.terminal_voltage:
        notes.append(f"energy and voltages are vs. {s.reference} (half-cell); active-material basis only")
    return BranchResult(
        branch=b.index, direction=b.direction, native_cycle=b.native_cycle, native_half_cycle=b.native_half_cycle,
        steps="+".join(map(str, b.steps)), modes="+".join(m.replace("constant_", "") for m in b.modes),
        complete=b.complete, terminated_by=b.terminated_by,
        t_start_s=float(t[0]), t_end_s=float(t[-1]), duration_s=float(t[-1] - t[0]), supported_duration_s=dur,
        charge_mAh=q_mAh, charge_method=method, charge_trapezoid_mAh=abs(q_trap) / 3.6,
        charge_cc_mAh=q_cc, charge_cv_mAh=q_cv, cv_fraction_pct=cv_frac,
        specific_capacity_mAh_g=spec, areal_capacity_mAh_cm2=areal, utilisation_pct=util, delta_x=dx,
        mean_current_mA=mean_i_mA, specific_current_mA_g=spec_i, current_density_mA_cm2=j,
        c_rate=c_rate, c_rate_label=_rate_label(c_rate) if c_rate else None,
        voltage_start_V=float(e[0]) if e is not None else None, voltage_end_V=float(e[-1]) if e is not None else None,
        mid_capacity_voltage_V=mid, average_voltage_V=avg_v, energy_mWh=energy, specific_energy_Wh_kg=spec_e,
        ocv_before_V=rb.voltage_end_V if rb else None, rest_before_s=rb.duration_s if rb else None,
        ocv_after_V=ocv_after, rest_after_s=ra.duration_s if ra else None,
        relaxation_after_V=(ocv_after - float(e[-1])) if (ocv_after is not None and e is not None) else None,
        temperature_mean_C=temp, instrument_charge_mAh=inst, instrument_relative_difference=rel, notes="; ".join(notes),
    )


def ended_at_once(p: Pair, br: dict) -> str | None:
    """"charge" or "discharge" when that branch of the pair is a step that ended at once (degenerate against its
    partner), else None. Both cannot be: each would need under 0.1 % of the other's charge."""
    c = br.get(p.charge.index) if p.charge else None
    d = br.get(p.discharge.index) if p.discharge else None
    if c is None or d is None:
        return None
    if degenerate(p.discharge, d.charge_mAh, c.charge_mAh):
        return "discharge"
    if degenerate(p.charge, c.charge_mAh, d.charge_mAh):
        return "charge"
    return None


def _no_dqde(g) -> str:
    """Why a branch has no dQ/dE (differential.curve gives none for these), for the note of its pair."""
    why = [f"{reason} inside it" for reason in getattr(g, "breaks_why", ())]
    if getattr(g, "pauses", 0):
        why.append("paused partway, and the potential relaxes while the current is off")
    return f"the {g.direction} branch {g.index} has no dQ/dE ({'; '.join(why)})"


def _cycle_result(p: Pair, br: dict, reference) -> CycleResult:
    c = br.get(p.charge.index) if p.charge else None
    d = br.get(p.discharge.index) if p.discharge else None
    qc = c.charge_mAh if c else None
    qd = d.charge_mAh if d else None
    ok = p.complete
    ce = 100 * qd / qc if (ok and qc and qd is not None and qc > 0) else None
    ret = 100 * qd / reference if (ok and qd is not None and reference) else None
    ee = None
    if ok and c and d and c.energy_mWh and d.energy_mWh is not None and c.energy_mWh > 0:
        ee = 100 * d.energy_mWh / c.energy_mWh
    hyst = mid_h = None
    if c and d:
        if c.average_voltage_V is not None and d.average_voltage_V is not None:
            hyst = c.average_voltage_V - d.average_voltage_V
        if c.mid_capacity_voltage_V is not None and d.mid_capacity_voltage_V is not None:
            mid_h = c.mid_capacity_voltage_V - d.mid_capacity_voltage_V
    lead = ""
    ended = ended_at_once(p, br)
    if ended:
        ce = ee = hyst = mid_h = None
        if ended == "discharge":                     # not a measure of the cell's capacity: no retention either
            ret = None
            lead = degenerate_note(p.discharge, d, c) + ", so no efficiency, hysteresis or retention is given for this pair"
        else:
            lead = degenerate_note(p.charge, c, d) + ", so no efficiency or hysteresis is given for this pair"
    sides = [g for g in (p.charge, p.discharge) if g is not None]
    gaps = [g for g in sides if g.unsupported_edges]
    if not ok and not p.note and gaps:
        why = " and ".join(f"the {g.direction} branch {g.index} has "
                           + ("1 interval that is" if g.unsupported_edges == 1 else f"{g.unsupported_edges} intervals "
                              "that are") + " not integrated" for g in gaps)
        incomplete = (f"incomplete pair: {why} (settings.json lists each interval and why), so this pair has no "
                      "efficiency or retention")
    else:
        incomplete = "incomplete pair: efficiency and retention unavailable"
    no_curve = [_no_dqde(g) for g in sides if g.curve_breaks or getattr(g, "pauses", 0)]   # differential.curve
    note = "; ".join(x for x in (p.note or ("" if ok else incomplete), lead, *no_curve) if x)
    return CycleResult(
        cycle=p.index, native_cycle=p.native_cycle, complete=ok,
        charge_branch=c.branch if c else None, discharge_branch=d.branch if d else None,
        charge_capacity_mAh=qc, discharge_capacity_mAh=qd,
        charge_specific_mAh_g=c.specific_capacity_mAh_g if c else None,
        discharge_specific_mAh_g=d.specific_capacity_mAh_g if d else None,
        coulombic_efficiency_pct=ce, coulombic_inefficiency_pct=(100 - ce) if ce is not None else None,
        capacity_retention_pct=ret,
        charge_delta_x=c.delta_x if c else None, discharge_delta_x=d.delta_x if d else None,
        average_charge_voltage_V=c.average_voltage_V if c else None,
        average_discharge_voltage_V=d.average_voltage_V if d else None,
        average_voltage_hysteresis_V=hyst,
        mid_capacity_charge_voltage_V=c.mid_capacity_voltage_V if c else None,
        mid_capacity_discharge_voltage_V=d.mid_capacity_voltage_V if d else None,
        mid_capacity_hysteresis_V=mid_h,
        charge_energy_mWh=c.energy_mWh if c else None, discharge_energy_mWh=d.energy_mWh if d else None,
        discharge_specific_energy_Wh_kg=d.specific_energy_Wh_kg if d else None, energy_efficiency_pct=ee,
        charge_c_rate=c.c_rate if c else None, discharge_c_rate=d.c_rate if d else None,
        charge_cv_fraction_pct=c.cv_fraction_pct if c else None,
        ocv_before_charge_V=c.ocv_before_V if c else None, ocv_after_discharge_V=d.ocv_after_V if d else None,
        note=note,
    )


def _summary(cycles, s, tab, ended=None, reference_ended=False, reference_missing=False) -> Summary:
    """ended: {cycle: "charge" or "discharge"} for the pairs with a step that ended at once (ended_at_once);
    reference_ended: the reference cycle's discharge is such a step, so no retention is given at all;
    reference_missing: the reference cycle is not a complete cycle of the file, so no retention either."""
    ended = ended or {}
    ok = [c for c in cycles if c.complete]
    total_h = float((tab.t[-1] - tab.t[0]) / 3600)
    if not ok:
        return Summary(0, s.reference_cycle, *([None] * 19), total_h, "no complete cycle")
    first, last = ok[0], ok[-1]
    qd = np.array([c.discharge_capacity_mAh for c in ok]); n = np.array([c.cycle for c in ok])
    kmax = int(np.argmax(qd))
    ret = np.array([c.capacity_retention_pct if c.capacity_retention_pct is not None else np.nan for c in ok])
    fade = fit_cycles = None
    sel = (n >= s.reference_cycle) & np.isfinite(ret)
    if sel.sum() >= 3:
        slope, _ = np.polyfit(n[sel], ret[sel], 1)
        fade = float(-slope); fit_cycles = f"{int(n[sel].min())}-{int(n[sel].max())}"
    c80 = next((int(c.cycle) for c in ok if c.capacity_retention_pct is not None and c.capacity_retention_pct < 80), None)
    ces = [c.coulombic_efficiency_pct for c in ok[1:] if c.coulombic_efficiency_pct is not None]
    ce10 = [c.coulombic_efficiency_pct for c in ok[-10:] if c.coulombic_efficiency_pct is not None]
    av = [c.average_discharge_voltage_V for c in ok
          if c.average_discharge_voltage_V is not None and ended.get(c.cycle) != "discharge"]
    hy = [c.average_voltage_hysteresis_V for c in ok if c.average_voltage_hysteresis_V is not None]
    qth = s.theoretical_capacity_mAh_g
    util = (100 * first.discharge_specific_mAh_g / qth
            if (qth and first.discharge_specific_mAh_g and ended.get(first.cycle) != "discharge") else None)
    notes = []
    left_out = [c.cycle for c in cycles if not c.complete]          # wherever they are, not only the last
    if left_out:
        notes.append(f"cycle{'s' if len(left_out) > 1 else ''} {', '.join(map(str, left_out[:12]))}"
                     + (f"... ({len(left_out)} in all)" if len(left_out) > 12 else "")
                     + " incomplete and excluded from the summary")
    if reference_missing:
        notes.append(f"the reference cycle, {s.reference_cycle}, is not a complete cycle of this file, so no retention "
                     "is given; choose another reference cycle")
    odd = [c.cycle for c in ok if ended.get(c.cycle)]
    if odd:
        odd_d = [k for k in odd if ended[k] == "discharge"]
        notes.append(f"cycle{'s' if len(odd) > 1 else ''} {', '.join(map(str, odd[:12]))} pair{'' if len(odd) > 1 else 's'} "
                     "a branch that ended at once with a full one: no efficiency or hysteresis for "
                     f"{'them' if len(odd) > 1 else 'it'}"
                     + (f", and no retention for cycle{'s' if len(odd_d) > 1 else ''} {', '.join(map(str, odd_d[:12]))}, "
                        f"whose discharge it is" if odd_d else "")
                     + " (cycles.csv says which branch)")
    if reference_ended:
        notes.append(f"the discharge of reference cycle {s.reference_cycle} ended at once, so no retention is given; "
                     "choose another reference cycle")
    return Summary(
        complete_cycles=len(ok), reference_cycle=s.reference_cycle,
        first_cycle_charge_mAh=first.charge_capacity_mAh, first_cycle_discharge_mAh=first.discharge_capacity_mAh,
        first_cycle_specific_discharge_mAh_g=first.discharge_specific_mAh_g,
        first_cycle_coulombic_efficiency_pct=first.coulombic_efficiency_pct,
        max_discharge_capacity_mAh=float(qd[kmax]), max_discharge_cycle=int(n[kmax]),
        last_cycle=int(last.cycle), last_discharge_capacity_mAh=last.discharge_capacity_mAh,
        last_specific_discharge_mAh_g=last.discharge_specific_mAh_g,
        retention_at_last_cycle_pct=last.capacity_retention_pct, cycle_reaching_80pct_retention=c80,
        capacity_fade_pct_per_cycle=fade, capacity_fade_fit_cycles=fit_cycles,
        mean_coulombic_efficiency_pct=float(np.mean(ces)) if ces else None,
        mean_coulombic_efficiency_last10_pct=float(np.mean(ce10)) if ce10 else None,
        mean_average_discharge_voltage_V=float(np.mean(av)) if av else None,
        mean_voltage_hysteresis_V=float(np.mean(hy)) if hy else None,
        theoretical_capacity_mAh_g=qth, first_cycle_utilisation_pct=util,
        total_test_time_h=total_h, notes="; ".join(notes),
    )


@dataclass
class Analysis:
    branches: list
    cycles: list
    rests: list
    summary: Summary


def analyse(tab: Table, seg: Segmentation, s: Settings) -> Analysis:
    if tab.i is None:
        raise ValueError("No current column: charge cannot be calculated")
    rests = _rests(tab, seg)
    rests_after = {r.after_branch: r for r in rests if r.after_branch is not None}
    rests_before = {r.before_branch: r for r in rests if r.before_branch is not None}
    branch_results = [_branch_result(tab, seg, b, s, rests_after, rests_before) for b in seg.branches]
    by_index = {r.branch: r for r in branch_results}
    ended = {p.index: ended_at_once(p, by_index) for p in seg.pairs}
    ended = {k: v for k, v in ended.items() if v}
    reference = None
    reference_ended = False
    for p in seg.pairs:
        if p.index == s.reference_cycle and p.complete and p.discharge is not None:
            if ended.get(p.index) == "discharge":    # a discharge that ended at once is no reference capacity
                reference_ended = True
            else:
                reference = by_index[p.discharge.index].charge_mAh
    cycles = [_cycle_result(p, by_index, reference) for p in seg.pairs]
    missing = reference is None and not reference_ended
    return Analysis(branch_results, cycles, rests, _summary(cycles, s, tab, ended, reference_ended, missing))


def capacity_basis(s: Settings) -> str:
    """What capacities are reported per: "specific" (per gram of active material, when the mass is given),
    "areal" (per cm2 of electrode, when only the area is given) or "absolute" (mAh).

    Every label and every value comes from this one decision, so a label can never
    name a basis its numbers are not on (independent review, finding r01).
    """
    if s.active_mass_mg is not None and s.active_mass_mg > 0:
        return "specific"
    if s.area_cm2 is not None and s.area_cm2 > 0:
        return "areal"
    return "absolute"


CAPACITY_UNITS = {"specific": "mAh g⁻¹", "areal": "mAh cm⁻²", "absolute": "mAh"}


def on_basis(q_mAh: float | None, q_specific: float | None, s: Settings) -> float | None:
    """One capacity on the basis of capacity_basis(s), from its absolute and specific values."""
    b = capacity_basis(s)
    if b == "specific":
        return q_specific
    if q_mAh is None:
        return None
    return q_mAh / s.area_cm2 if b == "areal" else q_mAh


def cycle_capacity(c: CycleResult, side: str, s: Settings) -> float | None:
    """Charge or discharge capacity of one cycle on the basis of capacity_basis(s); side "charge" or "discharge"."""
    return on_basis(getattr(c, f"{side}_capacity_mAh"), getattr(c, f"{side}_specific_mAh_g"), s)


def theoretical_capacity_mAh_g(n_electrons: float, molar_mass_g_mol: float) -> float:
    """q_th = n F / (3.6 M) in mAh/g."""
    if molar_mass_g_mol <= 0 or n_electrons <= 0:
        raise ValueError("electron count and molar mass must be positive")
    return n_electrons * F / (3.6 * molar_mass_g_mol)


def rows(results) -> list[dict]:
    return [asdict(r) for r in results]
