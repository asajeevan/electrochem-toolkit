"""A branch with an interval that is not integrated (M01 sections 5.1 and 9.3, amended October 2026).

Time going back inside a branch (a tester that restarts from a saved state, for example) makes the edge across it
unsupported: the branch keeps its charge over the supported edges, counts as partial, and its cycle has no
efficiency or retention. It has no dQ/dE either, because its potential after the interval need not continue the
curve before it: sorted and interpolated, the two parts of Q(E) fold back on each other. A branch that is partial
only because it reaches the end of the data, or only because of zero-duration intervals (a time printed coarsely),
keeps its dQ/dE. Hand-made tables only.
"""
import numpy as np
import pytest

from electrochem import differential
from electrochem.cycling import Settings, analyse
from electrochem.segment import segment
from electrochem.table import Table


def table(rows):
    """rows: (t, I, E, step)."""
    t, i, e, ns = (np.array(c, float) for c in zip(*rows))
    mode = np.where(i == 0, 3.0, 1.0)
    return Table("synthetic", "0" * 64, "mpt", ("time/s", "I/A", "Ecell/V", "Ns"), t, i, e, ns, mode, None, None,
                 None, None, None, None, potentials={"Ecell/V": e})


def branch(t0, n, current, e0, slope, step):
    return [(t0 + k, current, e0 + slope * k, step) for k in range(n)]


def cycle_rows(restart_in=(), back=30, end_in_discharge=False):
    """A 1 mA charge of 1000 s from 3.0 V and a 1 mA discharge of 900 s from 4.0 V, rests between and after. For
    each branch named in restart_in ("charge", "discharge"), the time goes back `back` seconds halfway, as at a
    tester's restart, and the potential starts again 0.2 V nearer the rest potential after it (the cell relaxed
    while stopped)."""
    rows = [(0.0, 0.0, 3.0, 1)]
    for name, n, cur, e0, slope, step in (("charge", 1000, 1e-3, 3.0, 1e-3, 2), ("discharge", 900, -1e-3, 4.0, -1e-3, 4)):
        t0 = rows[-1][0] + 1
        part = branch(t0, n, cur, e0, slope, step)
        if name in restart_in:
            h = n // 2
            again = [(t - back, i, e - (0.2 if cur > 0 else -0.2), s) for t, i, e, s in part[h - back:]]
            part = part[:h] + again
        rows += part
        if name == "discharge" and end_in_discharge:
            return rows
        rows.append((rows[-1][0] + 1, 0.0, rows[-1][2], step + 1))
    return rows


def run(rows):
    tab = table(rows)
    s = Settings(charge="positive", terminal_voltage=True)
    seg = segment(tab, charge="positive")
    return tab, seg, s, analyse(tab, seg, s)


def curves(tab, seg, s):
    return {b.index: differential.curve(tab, seg, s, b, 1) for b in seg.branches}


def test_a_branch_whose_time_goes_back_keeps_its_charge_and_loses_its_ratios_and_dqde():
    tab, seg, s, an = run(cycle_rows(restart_in=("charge",)))
    assert [b.unsupported_edges for b in seg.branches] == [1, 0]
    assert [b.complete for b in an.branches] == [False, True]
    # 499 supported edges before the restart, 529 after it (from the restored moment to the end)
    assert an.branches[0].charge_mAh == pytest.approx(1e-3 * (499 + 529) / 3.6, rel=1e-12)
    c = an.cycles[0]
    assert not c.complete and c.coulombic_efficiency_pct is None and c.capacity_retention_pct is None
    assert c.charge_capacity_mAh == an.branches[0].charge_mAh and c.discharge_capacity_mAh is not None
    assert c.note == ("incomplete pair: the charge branch 1 has 1 interval that is not integrated (settings.json lists "
                      "each interval and why), so this pair has no efficiency or retention; the charge branch 1 has no "
                      "dQ/dE (time reset or invalid time inside it)")
    assert seg.branches[0].curve_breaks == 1 and seg.edges.reason == {500: "time reset or invalid time"}
    cv = curves(tab, seg, s)
    assert cv[1] is None and cv[2] is not None


def test_without_the_rule_the_folded_curve_would_show_a_false_peak():
    """What the rule prevents: the same branch's Q(E), sorted and interpolated as for any branch, puts a spike
    where the two parts overlap in potential; the branch without the restart has a flat dQ/dE."""
    tab, seg, s, _ = run(cycle_rows(restart_in=("charge",)))
    b = seg.branches[0]
    b.curve_breaks = 0                                           # the rule switched off for this one branch
    folded = differential.curve(tab, seg, s, b, 1)
    tab0, seg0, s0, _ = run(cycle_rows())
    plain = differential.curve(tab0, seg0, s0, seg0.branches[0], 1)
    inner = slice(5, -5)
    assert np.ptp(plain.dqdv[inner]) / np.median(plain.dqdv[inner]) < 1e-6        # constant current, linear E
    assert np.max(folded.dqdv[inner]) > 2 * np.median(plain.dqdv[inner])


def test_both_branches_with_gaps_are_named():
    _, seg, _, an = run(cycle_rows(restart_in=("charge", "discharge")))
    assert [b.unsupported_edges for b in seg.branches] == [1, 1]
    note = an.cycles[0].note
    assert "the charge branch 1 has 1 interval that is not integrated and the discharge branch 2 has 1 interval" in note
    assert note.endswith("; the charge branch 1 has no dQ/dE (time reset or invalid time inside it); the discharge "
                         "branch 2 has no dQ/dE (time reset or invalid time inside it)")


def test_a_time_printed_coarsely_does_not_stop_the_dqde():
    """Every second row shares its time with the row before (a time printed to two seconds): the zero-duration
    intervals lose no time, so the charge is the same over the positive intervals and the dQ/dE is kept; the
    branches are still partial, as M01 section 5.1 has it for any interval without advancing time."""
    rows = cycle_rows()
    coarse = [(2 * (t // 2) if st in (2, 4) else t, i, e, st) for t, i, e, st in rows]
    tab, seg, s, an = run(coarse)
    assert [b.curve_breaks for b in seg.branches] == [0, 0] and all(b.unsupported_edges > 400 for b in seg.branches)
    assert set(seg.edges.reason.values()) == {"zero-duration programmed discontinuity"}
    cv = curves(tab, seg, s)
    assert cv[1] is not None and cv[2] is not None
    assert an.cycles[0].note.endswith("so this pair has no efficiency or retention")


def test_a_branch_cut_off_by_the_end_of_the_data_keeps_its_dqde():
    tab, seg, s, an = run(cycle_rows(end_in_discharge=True))
    assert [b.unsupported_edges for b in seg.branches] == [0, 0]
    assert seg.branches[1].terminated_by == "end of data" and not an.branches[1].complete
    cv = curves(tab, seg, s)
    assert cv[1] is not None and cv[2] is not None
    assert an.cycles[0].note == "incomplete pair: efficiency and retention unavailable"


def test_the_summary_names_every_cycle_it_leaves_out():
    """An interrupted cycle in the middle of a run is left out of the summary like an unfinished last one, and
    the summary's note names both (it named only the last before October 2026)."""
    first = cycle_rows(restart_in=("charge",))
    later = [(t + first[-1][0] + 1, i, e, st + 5) for t, i, e, st in cycle_rows()]
    unfinished = [(t + later[-1][0] + 1, i, e, st + 10) for t, i, e, st in cycle_rows(end_in_discharge=True)][1:]
    _, _, _, an = run(first + later + unfinished)
    assert [c.complete for c in an.cycles] == [False, True, False]
    reference = ("the reference cycle, 1, is not a complete cycle of this file, so no retention is given; choose another "
                 "reference cycle")
    assert an.summary.complete_cycles == 1
    assert an.summary.notes == "cycles 1, 3 incomplete and excluded from the summary; " + reference
    assert all(c.capacity_retention_pct is None for c in an.cycles)
    _, _, _, an = run(first + later)
    assert an.summary.notes == "cycle 1 incomplete and excluded from the summary; " + reference
    # with a complete cycle as the reference, the retention returns and the note does not
    tab = table(first + later)
    s = Settings(charge="positive", terminal_voltage=True, reference_cycle=2)
    an = analyse(tab, segment(tab, charge="positive"), s)
    assert an.cycles[1].capacity_retention_pct == pytest.approx(100.0)
    assert an.summary.notes == "cycle 1 incomplete and excluded from the summary"


def test_a_long_list_of_left_out_cycles_says_how_many():
    rows = []
    for k in range(15):                                       # 14 interrupted cycles, then a complete one
        part = cycle_rows(restart_in=("charge",) if k < 14 else ())
        t0 = rows[-1][0] + 1 if rows else 0.0
        rows += [(t + t0, i, e, st + 10 * k) for t, i, e, st in part]
    s = Settings(charge="positive", terminal_voltage=True, reference_cycle=15)
    tab = table(rows)
    an = analyse(tab, segment(tab, charge="positive"), s)
    assert [c.complete for c in an.cycles] == [False] * 14 + [True]
    assert an.summary.notes == ("cycles 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12... (14 in all) incomplete and excluded "
                                "from the summary")
