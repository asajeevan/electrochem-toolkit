"""Findings: every check the import makes, with a severity and a reason.

Two rules shape this module.

1. **Collect, then decide.** A reader gathers every finding before it raises, so
   the user sees all the problems at once instead of fixing them one per run.
2. **Refuse rather than repair.** A check that cannot be sure does not correct
   the data silently. It either refuses the import or records a warning that
   travels with the results into settings.json and the report.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np

Severity = Literal["refuse", "warn", "note"]


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    detail: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.severity}] {self.code}: {self.message}"


class Findings:
    def __init__(self) -> None:
        self.items: list[Finding] = []

    def add(self, code: str, severity: Severity, message: str, **detail) -> None:
        self.items.append(Finding(code, severity, message, detail))

    def refuse(self, code: str, message: str, **detail) -> None:
        self.add(code, "refuse", message, **detail)

    def warn(self, code: str, message: str, **detail) -> None:
        self.add(code, "warn", message, **detail)

    def note(self, code: str, message: str, **detail) -> None:
        self.add(code, "note", message, **detail)

    @property
    def refusals(self) -> list[Finding]:
        return [f for f in self.items if f.severity == "refuse"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.items if f.severity == "warn"]

    def as_list(self) -> list[dict]:
        return [asdict(f) for f in self.items]

    def raise_if_refused(self, source: str) -> None:
        if not self.refusals:
            return
        from .reader import ImportFailure

        lines = "\n  ".join(str(f) for f in self.refusals)
        raise ImportFailure(
            self.refusals[0].code,
            f"{source} was not imported. {len(self.refusals)} problem(s):\n  {lines}",
        )


# --------------------------------------------------------------- plausibility
# Wide enough to pass any real battery or electrolyte measurement, narrow enough
# that a unit mistake of three orders of magnitude cannot pass unremarked. These
# are warnings, not physics: a value outside the band is reported, not corrected.
PLAUSIBLE = {
    "current_ampere": (1e-15, 1e3),        # 1 fA to 1 kA in magnitude
    "voltage_volt": (-20.0, 100.0),
    "ambient_temperature_celsius": (-100.0, 400.0),
    "surface_temperature_celsius": (-100.0, 400.0),
}


def check_plausible(findings: Findings, role: str, values: np.ndarray, column: str) -> None:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        findings.refuse("column_all_invalid",
                        f"every value in {column!r} (mapped to {role}) is missing or unreadable",
                        column=column, role=role)
        return
    if role not in PLAUSIBLE:
        return
    lo, hi = PLAUSIBLE[role]
    if role == "current_ampere":
        nonzero = np.abs(finite[finite != 0])
        if nonzero.size and (nonzero.max() > hi or nonzero.min() < lo):
            findings.warn(
                "implausible_magnitude",
                f"{column!r} spans {nonzero.min():.3g} to {nonzero.max():.3g} A after unit "
                f"conversion, outside {lo:g} to {hi:g} A. Check the unit on this column: an "
                "instrument that labels mAh but writes Ah has been reported in the field.",
                column=column, role=role, min=float(nonzero.min()), max=float(nonzero.max()))
    elif finite.min() < lo or finite.max() > hi:
        findings.warn(
            "implausible_range",
            f"{column!r} spans {finite.min():.4g} to {finite.max():.4g} after unit conversion, "
            f"outside the plausible band {lo:g} to {hi:g}. Check the declared unit.",
            column=column, role=role, min=float(finite.min()), max=float(finite.max()))


# ------------------------------------------------------------------ structure
def check_time(findings: Findings, t: np.ndarray, column: str, step: np.ndarray | None) -> None:
    """Time must be finite and must not reset. A reset usually means a step-time
    column was mapped to test time, which silently shortens every branch."""
    bad = int(np.sum(~np.isfinite(t)))
    if bad:
        findings.warn("time_not_finite", f"{bad} row(s) have no readable time in {column!r}",
                      column=column, rows=bad)
    finite = t[np.isfinite(t)]
    if finite.size < 2:
        findings.refuse("time_too_short", f"fewer than two readable times in {column!r}",
                        column=column)
        return
    d = np.diff(finite)
    backwards = int(np.sum(d < 0))
    if backwards:
        # A per-step clock restarts at essentially *every* step boundary. One or
        # two restarts at a boundary mean two runs were concatenated, which is a
        # different fault with a different remedy, so the two are distinguished
        # by how many of the boundaries reset, not by whether any does.
        per_step_clock = False
        if step is not None and step.size == t.size:
            idx = np.flatnonzero(np.diff(t) < 0) + 1
            transitions = int(np.sum(step[1:] != step[:-1]))
            at_boundary = int(np.sum(step[idx] != step[idx - 1])) if idx.size else 0
            per_step_clock = (at_boundary == idx.size and at_boundary >= 2
                              and transitions > 0 and at_boundary >= 0.5 * transitions)
        if per_step_clock:
            findings.refuse(
                "time_resets_at_every_step",
                f"{column!r} restarts at step boundaries, so it is a step time, not the "
                "cumulative test time. Mapping it to test_time_second would shorten every "
                "branch. Bind the cumulative column, or reconstruct it from step time.",
                column=column, resets=backwards)
        else:
            findings.warn(
                "time_goes_backwards",
                f"{column!r} decreases at {backwards} row(s). Edges across a reversal are not "
                "integrated; the engine reports them as unsupported.",
                column=column, rows=backwards)
    if int(np.sum(d == 0)):
        findings.note("duplicate_timestamps",
                      f"{int(np.sum(d == 0))} consecutive row(s) share a timestamp in {column!r}",
                      column=column, rows=int(np.sum(d == 0)))


def check_single_channel(findings: Findings, cols: dict, headers: tuple[str, ...]) -> None:
    """One file, one cell. A multi-channel export silently averages nothing but
    interleaves two cells, which no downstream rule can detect."""
    for name in headers:
        low = name.strip().lower()
        if low in ("channel", "channel_id", "channel index", "cell", "cell_id", "test_id"):
            findings.note("channel_column_present",
                          f"{name!r} is present; if this file holds more than one channel it must "
                          "be split before analysis", column=name)


def check_counter_against_integral(findings: Findings, dq: np.ndarray | None, t: np.ndarray,
                                   i: np.ndarray, step: np.ndarray | None,
                                   tol: float = 0.05) -> dict | None:
    """The in-field oracle: the instrument's own charge against ours.

    Agreement to a few parts per million means the columns, units and signs were
    read as the instrument meant them. This is the check that a wrong mapping
    cannot survive, and it needs no knowledge of the true capacity.
    """
    if dq is None:
        return None
    m = np.isfinite(t) & np.isfinite(i)
    if m.sum() < 3:
        return None
    # Only a file that carries current can show a wrong column, unit or sign. At open circuit
    # the instrument's counter accumulates leakage below the logged current's resolution (a PEC
    # idle file: 0.02 mAh counted while the log shows 0 or 1 uA), and the two then differ by any
    # ratio at all; the comparison is not made and the report says why.
    if not _sustained_current(i, step, rows=3):
        findings.note("counter_not_compared",
                      "no step carries current of one sign over three or more rows, so the "
                      "instrument counter is not compared with the integral")
        return {"tolerance": tol, "compared": False}
    h = np.diff(t)
    edge = np.isfinite(h) & (h > 0) & np.isfinite(i[:-1]) & np.isfinite(i[1:])
    if step is not None and step.size == t.size:
        edge &= step[:-1] == step[1:]
    trap = np.where(edge, h * (i[:-1] + i[1:]) / 2.0 / 3600.0, 0.0)
    q = np.where(np.isfinite(dq), dq, 0.0)

    # Charge and discharge separately. A net comparison can be passed by two
    # compensating errors, which is exactly the case a reversed sign produces.
    # Each direction is compared relative to its own size, but never to less than
    # a tenth of the throughput of both: a direction that carries almost nothing
    # (one boundary increment of 2e-5 Ah in a file that otherwise only charges,
    # seen in a real Arbin export) cannot then raise the warning on its own, while
    # a swapped sign, which moves most of the throughput, still does.
    result: dict = {"tolerance": tol}
    worst = 0.0
    totals = {}
    for label, sel_q, sel_t in (("charge", q > 0, trap > 0), ("discharge", q < 0, trap < 0)):
        totals[label] = (float(np.abs(q[sel_q]).sum()), float(np.abs(trap[sel_t]).sum()))
    floor = 0.1 * sum(max(c, s) for c, s in totals.values())
    for label, (counter, integral) in totals.items():
        scale = max(counter, integral, floor)
        if max(counter, integral) == 0:
            continue
        rel = (integral - counter) / scale
        worst = max(worst, abs(rel))
        result[label] = {"instrument_counter_Ah": counter, "trapezoid_Ah": integral,
                         "relative_difference": rel}
    if len(result) == 1:
        return None
    result["worst_relative_difference"] = worst
    if worst > tol:
        findings.warn(
            "counter_disagrees_with_integral",
            f"the instrument's own charge counter and the integral of the sampled current "
            f"differ by up to {worst * 100:.2f} %. On a sparsely sampled constant-voltage tail a "
            "difference of this size is expected and the counter is the better value. The same "
            "difference on constant-current data instead means a wrong column, unit or sign.",
            **result)
    else:
        findings.note("counter_agrees_with_integral",
                      f"instrument counter and integral agree to {worst * 100:.4f} % on both "
                      "charge and discharge", **result)
    return result


def _runs(i: np.ndarray, step: np.ndarray | None):
    """(start, end) of each programmed step, or of each run of one current sign without steps."""
    if step is None or step.size != i.size:
        sgn = np.sign(np.nan_to_num(i))
        step = np.cumsum(np.concatenate(([0], sgn[1:] != sgn[:-1])))
    starts = np.flatnonzero(np.concatenate(([True], step[1:] != step[:-1])))
    return zip(starts, np.concatenate((starts[1:], [i.size])))


def _sustained_current(i: np.ndarray, step: np.ndarray | None, rows: int) -> bool:
    for a, b in _runs(i, step):
        ii = i[a:b]
        ii = ii[np.isfinite(ii)]
        if ii.size >= rows and (np.all(ii > 0) or np.all(ii < 0)):
            return True
    return False


def check_sign_against_voltage(findings: Findings, i: np.ndarray, e: np.ndarray,
                               step: np.ndarray | None, min_rows: int = 5,
                               min_dv: float = 1e-3) -> dict | None:
    """A physical statement of the sign convention that needs no label in the file.

    Current into the positive terminal raises the terminal voltage, whatever the
    chemistry, because the differential capacitance of a stable cell is positive.
    So over a programmed step that carries current of one sign, the voltage should
    end higher than it started when the current is charge-positive and positive.
    Rows of the step that carry no current are left out of the comparison.
    Each such step (or, in a file without step numbers, each run of one current
    sign) with at least `min_rows` rows and a voltage change above
    `min_dv` volts votes; constant-voltage holds (no change) and short steps
    abstain. This is applied to the charge-positive current after normalisation,
    so disagreement means the declared or detected convention is backwards.

    It is a warning, not a refusal: a symmetric or blocking-electrode cell can
    polarise against the current over a long step, and a step whose voltage swings
    through a maximum votes by its end points only. The counts travel with the
    import report either way.
    """
    if e is None or e.size != i.size:
        return None
    agree = disagree = 0
    # without programmed steps in the file (a Landt record sheet) runs of one current sign vote
    for a, b in _runs(i, step):
        if b - a < min_rows:
            continue
        ii, ee = i[a:b], e[a:b]
        # rows without current inside a step (the first point, logged before the source switched
        # on, in Novonix's and Arbin's exports) abstain; the rest must share one sign
        ok = np.isfinite(ii) & np.isfinite(ee) & (ii != 0)
        if ok.sum() < min_rows:
            continue
        ii, ee = ii[ok], ee[ok]
        if np.all(ii > 0):
            s = 1.0
        elif np.all(ii < 0):
            s = -1.0
        else:
            continue
        dv = float(ee[-1] - ee[0])
        if abs(dv) < min_dv:
            continue
        if np.sign(dv) == s:
            agree += 1
        else:
            disagree += 1
    result = {"steps_voting": agree + disagree, "agree": agree, "disagree": disagree}
    if agree + disagree == 0:
        return result
    if disagree > agree:
        findings.warn(
            "current_sign_contradicts_voltage",
            f"in {disagree} of {agree + disagree} current-carrying steps the voltage moved against "
            "the charge-positive current. Charging raises the terminal voltage, so the sign "
            "convention is probably declared backwards; check it before using any capacity.",
            **result)
    else:
        findings.note(
            "current_sign_agrees_with_voltage",
            f"in {agree} of {agree + disagree} current-carrying steps the voltage moved in the "
            "direction of the charge-positive current", **result)
    return result
