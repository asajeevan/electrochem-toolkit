"""Differential capacity dQ/dE, its peaks, peak pairing and plateau descriptors.

Method: within one branch, the cumulative capacity Q is interpolated onto a
uniform potential grid of spacing `bin_mV` (after sorting by potential), and
dQ/dE is the central finite difference on that grid. The bin width is the
only smoothing and is recorded with every output. Constant-voltage stages are
excluded because dE is zero there. Sign convention: charge branches positive,
discharge branches negative.

Peaks are located with scipy.signal.find_peaks on |dQ/dE| with a prominence
threshold expressed as a fraction of the branch maximum. Peak potentials are
descriptors of the measured curve at the applied rate, not equilibrium redox
potentials; they shift with rate, temperature and electrode polarisation.

Plateau descriptors (section "dQ/dE peaks, pairing and plateau descriptors" of
M01) are pure functions of the curves and peaks above:

- charge under a peak: the capacity between the two grid points that bound the
  peak (`peak_windows`), on the branch's capacity basis;
- pairing: each charge peak with the nearest discharge peak of the same cycle
  within `window_mV`, greedy by smallest separation, no peak used twice
  (`pair_peaks`); the mid-point of a pair is an apparent descriptor, not a
  formal potential;
- presence across cycles: peaks of one direction are linked from cycle to cycle
  (`track_peaks`), and each peak is described by the cycles its track covers.

Nothing here concludes that a process is reversible or irreversible. The words
used in the tables state what the curve shows: "no counterpart within 200 mV in
the discharge of the same cycle", "present in the first cycle only".

The evolution grid (`evolution_grid`) resamples each branch's dQ/dE onto one
potential grid shared by all cycles, for the colour map, the 3D surface, the
app's Evolution view and dqde_map.csv. Peak tables never use it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.signal import find_peaks

from .cycling import capacity_basis, cumulative_charge

PEAK_PAIR_WINDOW_MV = 200.0          # default pairing and tracking window
MIN_PROMINENCE_FRACTION = 0.05       # of the branch maximum of |dQ/dE|
MAX_PEAKS = 6                        # per branch, the most prominent kept

CAPACITY_UNIT_OF_BASIS = {"mAh/V": "mAh", "mAh/(g V)": "mAh/g", "mAh/(cm2 V)": "mAh/cm2"}


@dataclass
class DqdvCurve:
    cycle: int
    branch: int
    direction: str
    voltage_V: np.ndarray
    dqdv: np.ndarray              # mAh/V, or per g / per cm2 depending on `basis`
    basis: str
    bin_mV: float
    capacity: np.ndarray | None = None
    """Capacity interpolated on the grid (the function differentiated), on the capacity basis of `basis`."""

    @property
    def capacity_unit(self) -> str:
        return CAPACITY_UNIT_OF_BASIS.get(self.basis, self.basis.replace("/V", "").replace(" V)", ")"))

    def grid_capacity(self) -> np.ndarray:
        """Capacity on the grid, zero at the lowest potential. When the curve was built without it, the
        cumulative trapezoid of |dQ/dE| stands in (exact for a curve given only as dQ/dE)."""
        if self.capacity is not None and len(self.capacity) == len(self.voltage_V):
            return np.asarray(self.capacity, float)
        y = np.abs(np.asarray(self.dqdv, float))
        v = np.asarray(self.voltage_V, float)
        return np.concatenate(([0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(v))))


@dataclass
class DqdvPeak:
    cycle: int
    branch: int
    direction: str
    peak: int
    voltage_V: float
    dqdv: float
    prominence: float
    width_V: float
    basis: str
    bin_mV: float


def curve(tab, seg, s, branch, cycle, bin_mV=10.0) -> DqdvCurve | None:
    """The branch's dQ/dE on a grid of bin_mV (M01 section 9.3), or None. A branch with a curve break (an
    interval where the time goes back, as at a tester's restart, or the current is missing, or the instrument
    flagged an error: segment.CURVE_BREAKS) or a pause the instrument marked inside it has none: its potential
    after the break need not continue the curve before it (a cell left without current relaxes), and the
    sorted, interpolated Q(E) then folds back on itself and shows false peaks. A zero-duration interval (a time
    printed coarsely, or a programmed discontinuity) loses no time and does not count; nor does reaching the
    end of the data."""
    if getattr(branch, "curve_breaks", 0) or getattr(branch, "pauses", 0):
        return None
    q = cumulative_charge(tab, seg, branch, s.use_instrument_dq) / 3.6   # mAh
    basis = "mAh/V"
    kind = capacity_basis(s)                  # the same decision as every other capacity
    if kind == "specific":
        q = q / (s.active_mass_mg * 1e-3); basis = "mAh/(g V)"
    elif kind == "areal":
        q = q / s.area_cm2; basis = "mAh/(cm2 V)"
    e = tab.e[branch.rows]
    if tab.mode is not None:
        keep = tab.mode[branch.rows] != 2
        q, e = q[keep], e[keep]
    keep = np.isfinite(e)
    q, e = q[keep], e[keep]
    if len(e) < 4:
        return None
    step = bin_mV / 1000.0
    # the grid stays inside the measured range: a point beyond the last measured
    # potential would hold a clamped (flat) capacity and a fabricated dQ/dE near zero
    lo, hi = float(np.min(e)), float(np.max(e))
    grid = lo + step * np.arange(int(np.floor((hi - lo) / step + 1e-9)) + 1)
    if grid.size < 3:
        return None
    order = np.argsort(e, kind="stable")
    qi = np.interp(grid, e[order], q[order])
    d = np.gradient(qi, grid)
    return DqdvCurve(cycle, branch.index, branch.direction, grid, d, basis, bin_mV, qi)


def _find(c: DqdvCurve, min_prominence_fraction):
    y = np.abs(c.dqdv)
    if y.size < 5 or not np.isfinite(y).any() or np.nanmax(y) <= 0:
        return np.array([], int), {"prominences": np.array([]), "widths": np.array([])}
    return find_peaks(y, prominence=min_prominence_fraction * np.nanmax(y), width=1)


def peak_search(c: DqdvCurve, min_prominence_fraction=MIN_PROMINENCE_FRACTION, max_peaks=MAX_PEAKS):
    """(peaks, number found before the cap): the `max_peaks` most prominent of the peaks found, in order of
    potential. The number found tells a table whether the cap removed any."""
    idx, props = _find(c, min_prominence_fraction)
    order = np.argsort(props["prominences"])[::-1][:max_peaks]
    out = []
    dv = c.voltage_V[1] - c.voltage_V[0] if len(c.voltage_V) > 1 else 0.0
    for rank, k in enumerate(sorted(order, key=lambda j: c.voltage_V[idx[j]])):
        out.append(DqdvPeak(c.cycle, c.branch, c.direction, rank + 1, float(c.voltage_V[idx[k]]),
                            float(c.dqdv[idx[k]]), float(props["prominences"][k]),
                            float(props["widths"][k] * dv), c.basis, c.bin_mV))
    return out, int(len(idx))


def peaks(c: DqdvCurve, min_prominence_fraction=0.05, max_peaks=6) -> list[DqdvPeak]:
    return peak_search(c, min_prominence_fraction, max_peaks)[0]


# ------------------------------------------------------------------ charge under a peak

def _argmin(y, a, b, prefer_last):
    """Index of the smallest y on [a, b]; ties go to the first index, or the last with prefer_last."""
    seg = y[a:b + 1]
    if prefer_last:
        return a + (len(seg) - 1 - int(np.argmin(seg[::-1])))
    return a + int(np.argmin(seg))


def peak_windows(c: DqdvCurve, found: list[DqdvPeak]) -> list[tuple[int, int]]:
    """Grid-index bounds (lo, hi) of the charge window of each peak, peaks in order of potential.

    Boundary rule: between two neighbouring reported peaks, the grid point of lowest |dQ/dE| between them
    (the first such point when several are equal), shared by both peaks so the windows neither overlap nor
    leave a gap; outside the outermost peaks, the grid point of lowest |dQ/dE| between the peak and the curve
    end (the one nearest the peak when several are equal). Capacity outside every window, before the first
    boundary or after the last, belongs to no peak and is not reported as one.
    """
    if not found:
        return []
    y = np.abs(np.asarray(c.dqdv, float))
    v = np.asarray(c.voltage_V, float)
    idx = [int(np.argmin(np.abs(v - p.voltage_V))) for p in sorted(found, key=lambda p: p.voltage_V)]
    valleys = [_argmin(y, idx[k], idx[k + 1], False) for k in range(len(idx) - 1)]
    out = []
    for k, p in enumerate(idx):
        lo = valleys[k - 1] if k > 0 else _argmin(y, 0, p, True)
        hi = valleys[k] if k < len(idx) - 1 else _argmin(y, p, len(y) - 1, False)
        out.append((lo, hi))
    return out


def peak_charges(c: DqdvCurve, found: list[DqdvPeak]) -> list[tuple[float, float, float]]:
    """(charge, window low V, window high V) for each peak in order of potential.

    charge = |Q(E_hi) - Q(E_lo)|, with Q the capacity interpolated on the grid, on the curve's capacity basis
    (mAh, mAh/g or mAh/cm2)."""
    q = c.grid_capacity()
    v = np.asarray(c.voltage_V, float)
    return [(float(abs(q[hi] - q[lo])), float(v[lo]), float(v[hi])) for lo, hi in peak_windows(c, found)]


def curve_capacity(c: DqdvCurve) -> float:
    """Capacity spanned by the dQ/dE curve: the branch capacity with constant-voltage stages excluded."""
    q = c.grid_capacity()
    return float(abs(q[-1] - q[0])) if len(q) else 0.0


# ------------------------------------------------------------------ pairing within a cycle

def pair_peaks(charge: list[DqdvPeak], discharge: list[DqdvPeak],
               window_mV: float = PEAK_PAIR_WINDOW_MV) -> list[tuple[DqdvPeak, DqdvPeak]]:
    """Pairs (charge peak, discharge peak) of one cycle.

    All combinations with |E_charge - E_discharge| <= window are taken in order of increasing separation
    (ties: lower charge potential first, then lower discharge potential); a combination is kept when neither
    peak is already used. A convention of proximity: it does not establish that two peaks belong to one
    process."""
    w = window_mV / 1000.0 + 1e-9
    cand = sorted((abs(c.voltage_V - d.voltage_V), c.voltage_V, d.voltage_V, i, j)
                  for i, c in enumerate(charge) for j, d in enumerate(discharge)
                  if abs(c.voltage_V - d.voltage_V) <= w)
    used_c, used_d, out = set(), set(), []
    for _, _, _, i, j in cand:
        if i in used_c or j in used_d:
            continue
        used_c.add(i); used_d.add(j)
        out.append((charge[i], discharge[j]))
    return sorted(out, key=lambda p: p[0].voltage_V)


# ------------------------------------------------------------------ presence across cycles

@dataclass
class Track:
    direction: str
    track: int
    cycles: list = field(default_factory=list)
    voltages_V: list = field(default_factory=list)


def track_peaks(peaks_by_cycle: dict, cycles: list[int], window_mV: float = PEAK_PAIR_WINDOW_MV):
    """Link peaks of one direction from cycle to cycle.

    peaks_by_cycle: {(cycle, direction): [DqdvPeak]}. Cycles are visited in increasing order. A peak joins
    the track whose most recent potential is nearest, within the window, greedy by smallest shift, one peak
    per track per cycle; a peak that joins none starts a new track. Tracks survive cycles in which they have
    no peak. Returns (tracks, {id(peak): track}).
    """
    w = window_mV / 1000.0 + 1e-9
    tracks: list[Track] = []
    member = {}
    present = {d for _, d in peaks_by_cycle}
    for direction in [d for d in ("charge", "discharge") if d in present] + sorted(present - {"charge", "discharge"}):
        mine: list[Track] = []
        for c in sorted(cycles):
            pk = peaks_by_cycle.get((c, direction), [])
            cand = sorted((abs(p.voltage_V - t.voltages_V[-1]), p.voltage_V, ti, pi)
                          for pi, p in enumerate(pk) for ti, t in enumerate(mine)
                          if abs(p.voltage_V - t.voltages_V[-1]) <= w)
            used_t, used_p = set(), set()
            for _, _, ti, pi in cand:
                if ti in used_t or pi in used_p:
                    continue
                used_t.add(ti); used_p.add(pi)
                mine[ti].cycles.append(c); mine[ti].voltages_V.append(pk[pi].voltage_V)
                member[id(pk[pi])] = mine[ti]
            for pi, p in enumerate(pk):
                if pi not in used_p:
                    t = Track(direction, len(tracks) + len(mine) + 1, [c], [p.voltage_V])
                    mine.append(t)
                    member[id(p)] = t
        tracks.extend(mine)
    for k, t in enumerate(sorted(tracks, key=lambda t: (t.direction != "charge", t.cycles[0], t.voltages_V[0]))):
        t.track = k + 1
    return tracks, member


def cycle_ranges(cycles, analysed) -> str:
    """'1-5, 7, 9-10' over the analysed cycles: a range runs through consecutive analysed cycles."""
    pos = {c: k for k, c in enumerate(sorted(analysed))}
    ks = sorted(pos[c] for c in cycles if c in pos)
    order = sorted(analysed)
    parts, start = [], None
    for k in ks:
        if start is None:
            start = prev = k
        elif k == prev + 1:
            prev = k
        else:
            parts.append((start, prev)); start = prev = k
    if start is not None:
        parts.append((start, prev))
    return ", ".join(str(order[a]) if a == b else f"{order[a]}-{order[b]}" for a, b in parts)


def evolution_text(t: Track, analysed: list[int]) -> str:
    first = min(analysed)
    if len(analysed) < 2:
        return "one cycle analysed"
    if t.cycles == [first]:
        return "first cycle only"
    if t.cycles[0] > first:
        return f"appears from cycle {t.cycles[0]}"
    return f"seen in cycles {cycle_ranges(t.cycles, analysed)}"


# ------------------------------------------------------------------ the report

@dataclass
class PlateauPeak:
    """One row of dqde_peaks.csv. The first ten columns are those of DqdvPeak."""
    cycle: int
    branch: int
    direction: str
    peak: int
    voltage_V: float
    dqdv: float
    prominence: float
    width_V: float
    basis: str
    bin_mV: float
    charge: float                    # capacity under the peak, on charge_unit
    charge_unit: str
    share_of_branch_pct: float       # of curve_capacity
    curve_capacity: float            # branch capacity spanned by the dQ/dE curve (constant-voltage stages excluded)
    window_low_V: float
    window_high_V: float
    partner_voltage_V: float | None
    separation_mV: float | None      # charge minus discharge
    midpoint_V: float | None         # apparent mid-point of the pair, not a formal potential
    pairing: str                     # "paired" or "unpaired"
    pairing_note: str
    pair_window_mV: float
    track: int
    cycles_seen: str
    evolution: str                   # "seen in cycles a-b", "first cycle only", "appears from cycle k"
    peaks_found: int                 # in this branch, before the cap
    peaks_reported: int
    capped: bool
    peaks_note: str
    no_curve_cycles: str = ""        # cycles of this direction whose branch has no dQ/dE curve (the ranges run through them)


@dataclass
class PeakPair:
    """One row of dqde_pairs.csv."""
    cycle: int
    pair: int
    charge_peak: int
    discharge_peak: int
    charge_voltage_V: float
    discharge_voltage_V: float
    separation_mV: float             # charge minus discharge
    midpoint_V: float                # apparent mid-point, not a formal potential
    charge_capacity: float           # under the charge peak
    discharge_capacity: float        # under the discharge peak
    capacity_unit: str
    pair_window_mV: float
    bin_mV: float


@dataclass
class PlateauReport:
    peaks: list
    pairs: list
    cycles: list
    window_mV: float
    min_prominence_fraction: float
    max_peaks: int
    bin_mV: float | None
    notes: list = field(default_factory=list)

    def peak_rows(self) -> list[dict]:
        return [asdict(p) for p in self.peaks]

    def pair_rows(self) -> list[dict]:
        return [asdict(p) for p in self.pairs]

    def summary(self, reference_cycle: int = 1) -> dict:
        """The short `plateaus` block of summary.json, for the reference cycle (or the first analysed cycle
        when the reference cycle has no dQ/dE curve)."""
        if not self.cycles:
            return {"cycle": None, "note": "no dQ/dE curve: no peaks"}
        cyc = reference_cycle if reference_cycle in self.cycles else min(self.cycles)
        mine = [p for p in self.peaks if p.cycle == cyc]
        pairs = [p for p in self.pairs if p.cycle == cyc]
        out = {
            "cycle": cyc,
            "pair_window_mV": self.window_mV, "bin_mV": self.bin_mV,
            "pairs": len(pairs),
            "pair_potentials_V": [{"charge": round(p.charge_voltage_V, 6), "discharge": round(p.discharge_voltage_V, 6),
                                   "separation_mV": round(p.separation_mV, 3), "midpoint": round(p.midpoint_V, 6)}
                                  for p in pairs],
            "unpaired_peaks": [{"direction": p.direction, "voltage_V": round(p.voltage_V, 6), "note": p.pairing_note}
                               for p in mine if p.pairing == "unpaired"],
            # in the first analysed cycle of its direction only (a direction whose first branch has no curve
            # starts later, so each entry names its cycle)
            "first_cycle_only_peaks": [{"direction": p.direction, "cycle": p.cycle, "voltage_V": round(p.voltage_V, 6)}
                                       for p in self.peaks if p.evolution == "first cycle only"],
            # each track that starts after the first analysed cycle, at the cycle it appears
            "peaks_appearing_later": [{"direction": p.direction, "from_cycle": p.cycle, "voltage_V": round(p.voltage_V, 6)}
                                      for p in self.peaks if p.evolution == f"appears from cycle {p.cycle}"],
            "capped_branches": sorted({f"cycle {p.cycle} {p.direction}" for p in mine if p.capped}),
            "note": ("Peak potentials, separations and mid-points describe the measured curve at the applied rate; "
                     "pairing by proximity is a convention and does not establish that two peaks are one process."),
        }
        if self.notes:
            out["notes"] = list(self.notes)
        if cyc != reference_cycle:
            out["note"] = f"reference cycle {reference_cycle} has no dQ/dE curve; cycle {cyc} is shown. " + out["note"]
        return out


OPPOSITE = {"charge": "discharge", "discharge": "charge"}


def plateau_analysis(curves, window_mV: float = PEAK_PAIR_WINDOW_MV,
                     min_prominence_fraction: float = MIN_PROMINENCE_FRACTION,
                     max_peaks: int = MAX_PEAKS, withheld=frozenset()) -> PlateauReport:
    """Peaks, charge under each peak, pairs and presence across cycles for (cycle, DqdvCurve) items.

    Only branches named charge or discharge take part in pairing and tracking (a file whose charging
    direction is not stated has no cycles, so no curves reach here). withheld: (cycle, direction) of the
    branches that exist but have no curve (Run.dqde_curves leaves them out), so that a peak without a
    partner says so rather than that the branch is absent. Presence across cycles is judged, for each
    direction, over the cycles in which that direction has a curve."""
    window_mV = float(window_mV)
    by_branch = {}
    found = {}
    for c, cv in curves:
        pk, n = peak_search(cv, min_prominence_fraction, max_peaks)
        by_branch[(c, cv.direction)] = (cv, pk, n)
        found[(c, cv.direction)] = pk
    cycles = sorted({c for c, _ in curves})
    analysed = {}                                      # direction -> the cycles in which it has a curve
    for c, d in by_branch:
        analysed.setdefault(d, []).append(c)
    analysed = {d: sorted(v) for d, v in analysed.items()}
    known = sorted(set(cycles) | {c for c, _ in withheld})
    gaps = {d: cycle_ranges(sorted(c for c, dd in withheld if dd == d), known) for d in analysed}
    tracks, member = track_peaks(found, cycles, window_mV)
    rows, pair_rows = [], []
    for c in cycles:
        ch = by_branch.get((c, "charge"))
        di = by_branch.get((c, "discharge"))
        pairs = pair_peaks(ch[1] if ch else [], di[1] if di else [], window_mV)
        partner = {}
        for k, (a, b) in enumerate(pairs):
            partner[id(a)] = b; partner[id(b)] = a
        charges = {}
        for key in ((c, "charge"), (c, "discharge")):
            if key in by_branch:
                cv, pk, _ = by_branch[key]
                for p, (q, lo, hi) in zip(sorted(pk, key=lambda p: p.voltage_V), peak_charges(cv, pk)):
                    charges[id(p)] = (q, lo, hi)
        for k, (a, b) in enumerate(pairs):
            pair_rows.append(PeakPair(
                cycle=c, pair=k + 1, charge_peak=a.peak, discharge_peak=b.peak,
                charge_voltage_V=a.voltage_V, discharge_voltage_V=b.voltage_V,
                separation_mV=(a.voltage_V - b.voltage_V) * 1000.0, midpoint_V=(a.voltage_V + b.voltage_V) / 2.0,
                charge_capacity=charges[id(a)][0], discharge_capacity=charges[id(b)][0],
                capacity_unit=by_branch[(c, "charge")][0].capacity_unit, pair_window_mV=window_mV,
                bin_mV=by_branch[(c, "charge")][0].bin_mV))
        for key in ((c, "charge"), (c, "discharge")):
            if key not in by_branch:
                continue
            cv, pk, n = by_branch[key]
            total = curve_capacity(cv)
            other = OPPOSITE.get(cv.direction, "other")
            has_other = (c, other) in by_branch
            note = (f"{n} peaks found; the {max_peaks} most prominent are reported (max_peaks = {max_peaks})"
                    if n > len(pk) else "")
            for p in pk:
                q, lo, hi = charges[id(p)]
                b = partner.get(id(p))
                if b is not None:
                    sep = (p.voltage_V - b.voltage_V) if cv.direction == "charge" else (b.voltage_V - p.voltage_V)
                    status, why = "paired", f"paired with the {other} peak at {b.voltage_V:.4f} V"
                else:
                    sep = None
                    status = "unpaired"
                    why = (f"no counterpart within {window_mV:g} mV in the {other} of the same cycle" if has_other
                           else f"the {other} branch of this cycle has no dQ/dE curve" if (c, other) in withheld
                           else f"no {other} branch in this cycle")
                t = member[id(p)]
                rows.append(PlateauPeak(
                    cycle=c, branch=p.branch, direction=p.direction, peak=p.peak, voltage_V=p.voltage_V, dqdv=p.dqdv,
                    prominence=p.prominence, width_V=p.width_V, basis=p.basis, bin_mV=p.bin_mV,
                    charge=q, charge_unit=cv.capacity_unit, share_of_branch_pct=100.0 * q / total if total > 0 else float("nan"),
                    curve_capacity=total, window_low_V=lo, window_high_V=hi,
                    partner_voltage_V=b.voltage_V if b is not None else None,
                    separation_mV=sep * 1000.0 if sep is not None else None,
                    midpoint_V=(p.voltage_V + b.voltage_V) / 2.0 if b is not None else None,
                    pairing=status, pairing_note=why, pair_window_mV=window_mV, track=t.track,
                    cycles_seen=cycle_ranges(t.cycles, analysed[cv.direction]),
                    evolution=evolution_text(t, analysed[cv.direction]),
                    peaks_found=n, peaks_reported=len(pk), capped=n > len(pk), peaks_note=note,
                    no_curve_cycles=gaps[cv.direction]))
    notes = []
    if cycles and not pair_rows and any(by_branch.get((c, "charge")) and by_branch.get((c, "discharge")) for c in cycles):
        notes.append(f"no charge peak has a discharge peak within {window_mV:g} mV in any analysed cycle")
    capped = sorted({f"{r.cycle} {r.direction}" for r in rows if r.capped})
    if capped:
        notes.append(f"peaks were capped at {max_peaks} per branch in {len(capped)} branch"
                     f"{'es' if len(capped) != 1 else ''}")
    bins = {cv.bin_mV for _, cv in curves}
    return PlateauReport(rows, pair_rows, cycles, window_mV, min_prominence_fraction, max_peaks,
                         bins.pop() if len(bins) == 1 else None, notes)


def describe_peak(p: PlateauPeak) -> str:
    """One factual sentence for the inspector or a tooltip."""
    s = f"Cycle {p.cycle} {p.direction} peak at {p.voltage_V:.4f} V: {p.charge:.4g} {p.charge_unit} under the peak " \
        f"({p.share_of_branch_pct:.1f} % of the branch capacity outside constant-voltage stages); {p.pairing_note}"
    if p.separation_mV is not None:
        s += f", separation {p.separation_mV:.0f} mV, apparent mid-point {p.midpoint_V:.4f} V"
    ev = p.evolution
    s += "; " + ("present in the first cycle only" if ev == "first cycle only" else ev)
    if p.no_curve_cycles:
        s += f" (no {p.direction} dQ/dE curve in cycle{'s' if any(x in p.no_curve_cycles for x in ',-') else ''} " \
             f"{p.no_curve_cycles})"
    return s + "."


# ------------------------------------------------------------------ evolution grid (map, surface, view)

@dataclass
class DqdeGrid:
    """dQ/dE of one direction on one potential grid shared by all cycles.

    dqde[k, j] is the value of cycle cycles[k] at voltage_V[j], signed (charge positive, discharge negative),
    in real units of `basis`; NaN outside that branch's measured range or for a cycle without the branch."""
    direction: str
    cycles: np.ndarray
    voltage_V: np.ndarray
    dqde: np.ndarray
    basis: str
    bin_mV: float

    def filled(self, first: int | None = None, last: int | None = None) -> "DqdeGrid":
        """Every integer cycle from the first to the last, NaN rows where a cycle has no curve: rows then sit at
        their cycle numbers, so a missing or unselected cycle shows as a gap, never as a neighbour's data.
        first and last widen the range (never narrow it), so two directions can share one set of rows."""
        if len(self.cycles) == 0:
            return self
        lo, hi = int(self.cycles.min()), int(self.cycles.max())
        lo = lo if first is None else min(lo, int(first))
        hi = hi if last is None else max(hi, int(last))
        full = np.arange(lo, hi + 1)
        z = np.full((len(full), len(self.voltage_V)), np.nan)
        z[np.searchsorted(full, self.cycles)] = self.dqde
        return DqdeGrid(self.direction, full, self.voltage_V, z, self.basis, self.bin_mV)

    def value(self, cycle: int, voltage: float):
        """(grid voltage, dQ/dE) of the node nearest `voltage` in `cycle`, or None."""
        k = np.flatnonzero(self.cycles == cycle)
        if not k.size or not len(self.voltage_V):
            return None
        j = int(np.argmin(np.abs(self.voltage_V - voltage)))
        return float(self.voltage_V[j]), float(self.dqde[k[0], j])


def evolution_grid(curves, direction: str) -> DqdeGrid | None:
    """Resample the dQ/dE curves of one direction onto a common grid.

    Nodes are integer multiples of the bin width (E_j = j x bin), from the lowest to the highest potential of
    any curve; each curve is linearly interpolated onto the nodes inside its own measured range and is NaN
    outside it. A curve's own nodes start at its lowest measured potential, so a common grid moves each value
    by less than one bin; that is the only change, and the peak tables, computed on each branch's own grid, do
    not use this grid. One row per cycle, in increasing cycle order."""
    mine = sorted(((c, cv) for c, cv in curves if cv.direction == direction), key=lambda x: x[0])
    if not mine:
        return None
    bins = {cv.bin_mV for _, cv in mine}
    if len(bins) != 1:
        raise ValueError("the curves use different bin widths; one grid cannot hold them")
    step = bins.pop() / 1000.0
    lo = min(float(cv.voltage_V[0]) for _, cv in mine)
    hi = max(float(cv.voltage_V[-1]) for _, cv in mine)
    j0, j1 = int(np.ceil(lo / step - 1e-9)), int(np.floor(hi / step + 1e-9))
    grid = np.round(np.arange(j0, j1 + 1) * step, 12)
    z = np.full((len(mine), len(grid)), np.nan)
    for k, (_, cv) in enumerate(mine):
        v = np.asarray(cv.voltage_V, float)
        inside = (grid >= v[0] - 1e-12) & (grid <= v[-1] + 1e-12)
        z[k, inside] = np.interp(grid[inside], v, np.asarray(cv.dqdv, float))
    return DqdeGrid(direction, np.array([c for c, _ in mine], int), grid, z, mine[0][1].basis, mine[0][1].bin_mV)


def grid_rows(grids) -> list[list]:
    """dqde_map.csv: a header row (cycle, direction, basis, then one column per potential in V) and one row per
    cycle and direction, signed real units, empty where the branch was not measured."""
    grids = [g for g in grids if g is not None]
    if not grids:
        return []
    volts = sorted({round(float(v), 9) for g in grids for v in g.voltage_V})
    col = {v: k for k, v in enumerate(volts)}
    nd = max(0, -int(np.floor(np.log10(min(g.bin_mV for g in grids) / 1000.0))) + 1)
    out = [["cycle", "direction", "basis"] + [f"{v:.{nd}f}" for v in volts]]
    for g in grids:
        for k, c in enumerate(g.cycles):
            row = [""] * len(volts)
            for v, d in zip(g.voltage_V, g.dqde[k]):
                if np.isfinite(d):
                    row[col[round(float(v), 9)]] = repr(float(d))
            out.append([int(c), g.direction, g.basis] + row)
    return out
