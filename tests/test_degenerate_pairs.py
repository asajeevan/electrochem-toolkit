"""A step that ended at once, paired with a full branch (M01 section 6, amended 20 October 2026).

The case met in a real LANHE file: a charge to a voltage limit, started on a cell already above it, ran for one
recorded interval, and charge-first pairing put it with the long discharge after it, giving a coulombic
efficiency of millions of per cent. Such a pair keeps its capacities and its retention; its efficiency, energy
efficiency and hysteresis are not given, and the app asks which branch each cycle starts with. Synthetic data
only, with values of its own: hand-made tables for the rule's edges, and a synthetic .cex for the whole path.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import cex_synthetic as cs  # noqa: E402

from electrochem import workflow  # noqa: E402
from electrochem.cycling import DEGENERATE_FRACTION, DEGENERATE_ROWS, Settings, analyse  # noqa: E402
from electrochem.segment import segment  # noqa: E402
from electrochem.studio.model import Answers, degenerate_start, order_needed  # noqa: E402
from electrochem.table import Table  # noqa: E402


def table(rows):
    """rows: (t, I, E, step); a rest step between the two branches is not needed for the rule."""
    t, i, e, ns = (np.array(c, float) for c in zip(*rows))
    mode = np.where(i == 0, 3.0, 1.0)
    return Table("synthetic", "0" * 64, "mpt", ("time/s", "I/A", "Ecell/V", "Ns"), t, i, e, ns, mode, None, None,
                 None, None, None, None, potentials={"Ecell/V": e})


def first_cycle(rows, order="charge-first"):
    tab = table(rows)
    s = Settings(charge="positive", terminal_voltage=True, cycle_order=order)
    seg = segment(tab, charge="positive", order=order)
    return analyse(tab, seg, s)


def short_then_long(n_short, i_short, dt_short=0.1, n_long=200):
    """A charge of n_short rows at i_short (A), then a 1 mA discharge of n_long rows one second apart, then rest."""
    rows = [(k * dt_short, i_short, 4.0, 1) for k in range(n_short)]
    t0 = rows[-1][0] + 0.1
    rows += [(t0 + k, -1e-3, 3.5 - 0.001 * k, 2) for k in range(n_long)]
    rows += [(rows[-1][0] + 10, 0.0, 3.4, 3)]
    return rows


def test_a_two_row_branch_with_a_negligible_charge_gets_no_ratio():
    an = first_cycle(short_then_long(2, 1e-3))          # 0.1 s at 1 mA against 199 s at 1 mA: 0.05 %
    c = an.cycles[0]
    assert c.complete and c.discharge_capacity_mAh == pytest.approx(1e-3 * 199 / 3.6)
    assert c.charge_capacity_mAh == pytest.approx(1e-3 * 0.1 / 3.6)
    assert c.coulombic_efficiency_pct is None and c.coulombic_inefficiency_pct is None
    assert c.energy_efficiency_pct is None and c.average_voltage_hysteresis_V is None
    assert c.mid_capacity_hysteresis_V is None
    assert c.capacity_retention_pct == pytest.approx(100.0)
    assert "spans one recorded interval" in c.note and "a step that ended at once" in c.note
    assert an.summary.first_cycle_coulombic_efficiency_pct is None and "cycle 1 pairs a branch" in an.summary.notes


def test_the_rule_is_the_one_m01_states():
    assert DEGENERATE_ROWS == 2 and DEGENERATE_FRACTION == 1e-3


# The edges use the values M01 states, not the module's constants, so a changed constant fails here.
@pytest.mark.parametrize("n_short,i_short,why", [
    (3, 1e-4, "three rows (two intervals) at 0.01 % of the partner: the row condition alone keeps the ratio"),
    (2, 1e-3 * 199 * 1e-3 / 0.1 * 1.01, "two rows just above 0.1 % of the partner: the fraction condition keeps it"),
])
def test_the_rule_stops_at_its_stated_edges(n_short, i_short, why):
    c = first_cycle(short_then_long(n_short, i_short)).cycles[0]
    assert c.coulombic_efficiency_pct is not None, why
    assert "ended at once" not in c.note


def test_two_rows_just_below_the_fraction_are_withheld():
    i_short = 1e-3 * 199 * 1e-3 / 0.1 * 0.99
    assert first_cycle(short_then_long(2, i_short)).cycles[0].coulombic_efficiency_pct is None


def test_a_degenerate_discharge_is_treated_the_same_way():
    rows = [(k, 1e-3, 3.5 + 0.001 * k, 1) for k in range(200)]
    t0 = rows[-1][0] + 0.1
    rows += [(t0, -1e-3, 3.0, 2), (t0 + 0.1, -1e-3, 3.0, 2), (t0 + 10, 0.0, 3.4, 3)]
    c = first_cycle(rows).cycles[0]
    assert c.complete and c.coulombic_efficiency_pct is None and "discharge branch 2" in c.note


# ---------------------------------------------------------------------- the whole path, as in the real file
HOLD = [
    cs.Step("rest", 0.0, v0=3.50),
    cs.Step("cc_charge", 0.05, every=1.0, counts=8064, v0=4.40),                      # ended at once
    cs.Step("cc_discharge", 3000.0, every=10.0, counts=8064, v0=3.60, v1=2.80),
    cs.Step("cc_charge", 2500.0, every=10.0, counts=8064, v0=3.00, v1=4.00),
    cs.Step("cv_charge", 4000.0, every=10.0, counts=8064, v0=4.00, tau=1200.0, carry=True),
]


@pytest.fixture
def hold_file(tmp_path):
    blob, truth = cs.write(HOLD)
    p = tmp_path / "hold.cex"
    p.write_bytes(blob)
    return p, truth


def test_charge_first_keeps_the_capacities_and_withholds_the_ratio(hold_file):
    p, tr = hold_file
    run = workflow.analyse_file(workflow.open_file(p), Settings(charge="ox", terminal_voltage=True))
    c1, c2 = run.an.cycles
    assert c1.complete and c1.coulombic_efficiency_pct is None and "ended at once" in c1.note
    assert c1.discharge_capacity_mAh == pytest.approx(tr.charge[2] * 1e3, rel=1e-6)
    assert not c2.complete and c2.charge_capacity_mAh == pytest.approx((tr.charge[3] + tr.charge[4]) * 1e3, rel=1e-6)


def test_the_app_asks_which_branch_a_cycle_starts_with(hold_file):
    p, _ = hold_file
    run = workflow.analyse_file(workflow.open_file(p), Settings(charge="ox", terminal_voltage=True))
    lead = degenerate_start(run)
    assert lead and lead.startswith("the charge branch 1 spans one recorded interval (0.05 s)")
    assert order_needed(Answers(charge="ox"), run)
    assert not order_needed(Answers(), run)                       # the direction comes first


def test_an_ordinary_start_does_not_ask(tmp_path):
    blob, _ = cs.write(cs.two_cycles())
    p = tmp_path / "ordinary.cex"
    p.write_bytes(blob)
    run = workflow.analyse_file(workflow.open_file(p), Settings(charge="ox", terminal_voltage=True))
    assert degenerate_start(run) is None and not order_needed(Answers(charge="ox"), run)


def test_discharge_first_pairs_the_discharge_with_the_charge_after_it(hold_file):
    p, tr = hold_file
    run = workflow.analyse_file(workflow.open_file(p), Settings(charge="ox", terminal_voltage=True,
                                                                cycle_order="discharge-first"))
    c1, c2 = run.an.cycles
    assert c1.note == "unpaired charge branch" and c1.discharge_branch is None
    assert c2.discharge_capacity_mAh == pytest.approx(tr.charge[2] * 1e3, rel=1e-6)
    assert c2.charge_cv_fraction_pct == pytest.approx(100 * tr.charge[4] / (tr.charge[3] + tr.charge[4]), rel=1e-6)
    assert not c2.complete                                        # the file ends in the hold: M01's last-branch rule


# ------------------------------------------------------------------------------------------------- figures
def test_withheld_ratios_are_not_drawn_and_every_figure_still_passes(hold_file):
    plt = pytest.importorskip("matplotlib.pyplot")
    from electrochem import plotting
    p, _ = hold_file
    run = workflow.analyse_file(workflow.open_file(p), Settings(charge="ox", terminal_voltage=True))
    builders = workflow.figure_builders(run, workflow.ExportOptions())
    fig = builders["average_voltage"]()
    ax, ax2 = fig.axes[:2]
    squares = [ln for ln in ax2.lines if ln.get_marker() == "s"]
    assert squares and np.all(np.isnan(squares[0].get_ydata()))           # the cycle's hysteresis, withheld
    labels = [t.get_text() for t in fig.legends[0].get_texts()] if fig.legends else \
        [t.get_text() for a in fig.axes if a.get_legend() for t in a.get_legend().get_texts()]
    assert "Charge" in labels and not any("Hysteresis" in x for x in labels)
    plt.close(fig)
    fig = builders["capacity_efficiency"]()
    labels = [t.get_text() for a in fig.axes if a.get_legend() for t in a.get_legend().get_texts()]
    assert "Discharge" in labels and "Coulombic efficiency" not in labels
    plt.close(fig)
    for name, build in builders.items():
        fig = build()
        bad = [c for c in plotting.check_figure(fig) if c.status == "fail"]
        plt.close(fig)
        assert not bad, f"{name}: " + "; ".join(f"{c.name}: {c.detail}" for c in bad)


def test_the_map_panels_share_their_cycle_rows():
    """Charge curves in cycles 2 and 3, discharge in 1 and 2: both panels run from cycle 1 to 3, and the
    charge row of cycle 1 is not measured (grey). Before, each panel set the shared axis to its own cycles
    and the last one won, hiding the other's rows."""
    plt = pytest.importorskip("matplotlib.pyplot")
    from electrochem import differential, plotting
    v = np.round(3.0 + 0.01 * np.arange(40), 6)
    curves = [(c, differential.DqdvCurve(c, 2 * c, d, v, np.exp(-((v - 3.2) / 0.03) ** 2) * (1 if d == "charge" else -1),
                                         "mAh/V", 10.0))
              for c, d in ((2, "charge"), (3, "charge"), (1, "discharge"), (2, "discharge"))]
    fig = plotting.fig6_dqde_map(curves, Settings(reference="Li/Li+"))
    axes = [a for a in fig.axes if any(c.get_gid() == "dqde-map" for c in a.collections)]
    assert len(axes) == 2 and all(a.get_ylim() == pytest.approx((0.5, 3.5)) for a in axes)
    charge = next(c for c in axes[0].collections if c.get_gid() == "dqde-map")
    arr = np.ma.filled(np.ma.asarray(charge.get_array()).astype(float), np.nan).reshape(3, -1)
    assert np.all(np.isnan(arr[0])) and np.isfinite(arr[1]).any() and np.isfinite(arr[2]).any()
    plt.close(fig)


@pytest.mark.parametrize("figure", ["fig6_dqde_map", "fig7_dqde_surface"])
def test_one_cycle_is_labelled_with_a_whole_cycle_number(figure):
    plt = pytest.importorskip("matplotlib.pyplot")
    from electrochem import differential, plotting
    v = np.round(3.0 + 0.01 * np.arange(40), 6)
    curves = [(2, differential.DqdvCurve(2, 4, d, v, np.exp(-((v - 3.2) / 0.03) ** 2) * (1 if d == "charge" else -1),
                                         "mAh/V", 10.0)) for d in ("charge", "discharge")]
    fig = getattr(plotting, figure)(curves, Settings(reference="Li/Li+"))
    fig.canvas.draw()
    for ax in fig.axes[:2]:
        lo, hi = ax.get_ylim()
        ticks = [t for t in ax.yaxis.get_major_locator()() if lo <= t <= hi]
        assert ticks == [2.0], ticks
    plt.close(fig)
