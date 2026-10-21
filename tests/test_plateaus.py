"""dQ/dE peaks, pairing, charge under each peak, presence across cycles and the evolution grid.

The main cell (tests/plateau_cell.py) is synthetic with every answer known by
construction: three reversible plateaus with a 60 mV hysteresis, one plateau in
the first charge only, one small plateau from cycle 3 on, sampled as an
instrument records a galvanostatic test and read through the EC-Lab text path.
The pure functions are also checked on hand-made inputs whose answers follow
from arithmetic, not from the implementation.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from electrochem import differential, workflow
from electrochem.cycling import Settings
from electrochem.differential import DqdvCurve, DqdvPeak
from tests import plateau_cell as pc

ROOT = Path(__file__).resolve().parents[1]
BIN_V = 0.010
DEMO = ROOT / "data" / "demo" / "cyclara_demo_synthetic.mpt"
FORMATION = ROOT / "data" / "public" / "mpt" / "020-formation_CB5.mpt"


@pytest.fixture(scope="module")
def cell(tmp_path_factory):
    return pc.write(tmp_path_factory.mktemp("plateau") / "plateau_cell.mpt")


@pytest.fixture(scope="module")
def run(cell):
    return workflow.analyse_file(workflow.open_file(cell), Settings(charge="ox", reference="Li/Li+"), cycles="1:-1")


@pytest.fixture(scope="module")
def report(run):
    return run.plateaus()


def rows_of(report, cycle, direction):
    return sorted((r for r in report.peaks if r.cycle == cycle and r.direction == direction), key=lambda r: r.voltage_V)


def near(rows, e, tol=BIN_V):
    hit = [r for r in rows if abs(r.voltage_V - e) <= tol]
    assert len(hit) == 1, f"expected one peak within {tol * 1000:g} mV of {e:.4f} V, found {[r.voltage_V for r in hit]}"
    return hit[0]


# ------------------------------------------------------------------ the synthetic cell

def test_the_cell_is_read_as_constructed(run):
    assert [p.index for p in run.seg.pairs] == list(range(1, pc.N_CYCLES + 1))
    for c in run.an.cycles:
        assert c.charge_capacity_mAh == pytest.approx(pc.branch_capacity(c.cycle, "charge"), rel=1e-9)
        assert c.discharge_capacity_mAh == pytest.approx(pc.branch_capacity(c.cycle, "discharge"), rel=1e-9)


def test_one_peak_per_plateau_within_one_bin(report):
    for n in range(1, pc.N_CYCLES + 1):
        for d in ("charge", "discharge"):
            rows = rows_of(report, n, d)
            truth = pc.plateaus(n, d)
            assert len(rows) == len(truth), (n, d)
            for r, (e, _) in zip(rows, truth):
                assert abs(r.voltage_V - e) <= BIN_V, (n, d, r.voltage_V, e)


def test_pairs_have_the_constructed_separation_and_mid_point(report):
    for n in range(1, pc.N_CYCLES + 1):
        pairs = [p for p in report.pairs if p.cycle == n]
        centres = sorted([e for e, _ in pc.REVERSIBLE] + ([pc.LATE[0]] if n >= pc.LATE_FROM else []))
        assert len(pairs) == len(centres)
        for p, e in zip(sorted(pairs, key=lambda p: p.midpoint_V), centres):
            assert abs(p.separation_mV - pc.HYST * 1000) <= BIN_V * 1000
            assert p.separation_mV == pytest.approx((p.charge_voltage_V - p.discharge_voltage_V) * 1000)
            assert abs(p.midpoint_V - e) <= BIN_V              # the construction's centre, by symmetry


def test_the_first_charge_only_plateau_is_reported_as_what_the_data_show(report):
    r = near(rows_of(report, 1, "charge"), pc.IRREVERSIBLE[0])
    assert r.pairing == "unpaired" and r.partner_voltage_V is None and r.separation_mV is None
    assert r.pairing_note == "no counterpart within 200 mV in the discharge of the same cycle"
    assert r.evolution == "first cycle only" and r.cycles_seen == "1"
    assert all(abs(x.voltage_V - pc.IRREVERSIBLE[0]) > 0.1 for x in report.peaks if x.cycle > 1 and x.direction == "charge")
    assert not any("irreversible" in str(v).lower() for row in report.peak_rows() for v in row.values())


def test_the_late_plateau_appears_from_cycle_3(report):
    for d, shift in (("charge", +1), ("discharge", -1)):
        e = pc.LATE[0] + shift * pc.HYST / 2
        assert not [r for r in report.peaks if r.cycle < pc.LATE_FROM and r.direction == d and abs(r.voltage_V - e) < 0.1]
        for n in range(pc.LATE_FROM, pc.N_CYCLES + 1):
            r = near(rows_of(report, n, d), e)
            assert r.evolution == "appears from cycle 3" and r.cycles_seen == "3-5"
            assert r.pairing == "paired" and abs(r.separation_mV - 60) <= 10


def test_reversible_plateaus_are_seen_in_every_cycle(report):
    for e0, _ in pc.REVERSIBLE:
        for d, shift in (("charge", 1), ("discharge", -1)):
            for n in range(1, pc.N_CYCLES + 1):
                r = near(rows_of(report, n, d), e0 + shift * pc.HYST / 2)
                assert r.evolution == "seen in cycles 1-5" and r.pairing == "paired"


def test_charge_under_each_peak_is_the_plateau_capacity(report):
    """Known by construction: plateau capacity Q_i plus the linear background inside the peak's window."""
    for n in range(1, pc.N_CYCLES + 1):
        for d in ("charge", "discharge"):
            rows = rows_of(report, n, d)
            for r, (e, q) in zip(rows, pc.plateaus(n, d)):
                expected = q + pc.C_BG * (r.window_high_V - r.window_low_V)
                assert r.charge == pytest.approx(expected, rel=0.01), (n, d, e)
                if q >= 0.2:                                   # the three main plateaus: within 3 % of Q_i itself
                    assert abs(r.charge - q) <= 0.03 * q
                assert r.window_low_V <= r.voltage_V <= r.window_high_V
            total = pc.branch_capacity(n, d)
            assert rows[0].curve_capacity == pytest.approx(total, rel=1e-3)     # no constant-voltage stage here
            shares = sum(r.share_of_branch_pct for r in rows)
            assert shares == pytest.approx(100 * sum(r.charge for r in rows) / rows[0].curve_capacity)
            assert 98.0 < shares <= 100.0 + 1e-9
            for a, b in zip(rows, rows[1:]):                   # windows tile: a shared valley, no overlap or gap
                assert a.window_high_V == b.window_low_V


def test_branch_mean_potential_is_the_capacity_weighted_mean_of_the_plateaus(run, report):
    """The branch mean (energy / charge) is unchanged; with several plateaus it is sum Q_i E_i / sum Q_i."""
    for c in run.an.cycles:
        for d, mean in (("charge", c.average_charge_voltage_V), ("discharge", c.average_discharge_voltage_V)):
            assert mean == pytest.approx(pc.mean_potential(c.cycle, d), abs=2e-4)      # exact by construction
            assert abs(mean - pc.plateau_mean(c.cycle, d)) < 3e-3                      # background shifts < 3 mV
            rows = rows_of(report, c.cycle, d)
            recon = sum(r.charge * r.voltage_V for r in rows) / sum(r.charge for r in rows)
            assert abs(recon - mean) < 3e-3          # the reported descriptors reproduce it


def test_a_window_below_the_hysteresis_pairs_nothing_and_says_so(cell, run):
    narrow = workflow.analyse_file(workflow.open_file(cell), Settings(charge="ox", reference="Li/Li+"), cycles="1:-1",
                                   peak_pair_window_mV=50)
    assert narrow.settings.peak_pair_window_mV == 50 and run.settings.peak_pair_window_mV == 200
    rep = narrow.plateaus()
    assert rep.pairs == []
    assert "no charge peak has a discharge peak within 50 mV in any analysed cycle" in rep.notes
    assert all(r.pairing == "unpaired" and "within 50 mV" in r.pairing_note for r in rep.peaks)
    assert rep.summary(1)["pairs"] == 0 and rep.summary(1)["notes"]
    wide = differential.plateau_analysis(narrow.dqde_curves(narrow.all_cycles), window_mV=70)
    assert len(wide.pairs) == len(run.plateaus().pairs)


def test_capping_the_peak_count_is_stated(run):
    rep = differential.plateau_analysis(run.dqde_curves(run.all_cycles), max_peaks=2)
    rows = rows_of(rep, 3, "charge")                          # four plateaus in this branch
    assert len(rows) == 2 and all(r.capped and r.peaks_found == 4 and r.peaks_reported == 2 for r in rows)
    assert "4 peaks found; the 2 most prominent are reported (max_peaks = 2)" == rows[0].peaks_note
    assert sorted(round(r.voltage_V, 1) for r in rows) == [3.4, 3.8]          # the two largest plateaus
    assert any("capped at 2 per branch" in n for n in rep.notes)
    assert rep.summary(3)["capped_branches"] == ["cycle 3 charge", "cycle 3 discharge"]


def test_export_writes_the_tables_and_the_summary_block(run, tmp_path):
    rec = workflow.export(run, tmp_path, workflow.ExportOptions(formats=("png",), plots={"dqde_map"}))
    peaks = list(csv.DictReader(open(tmp_path / "dqde_peaks.csv")))
    assert list(peaks[0])[:10] == ["cycle", "branch", "direction", "peak", "voltage_V", "dqdv", "prominence", "width_V",
                                   "basis", "bin_mV"]                       # the columns of 0.7.0 come first
    for col in ("charge", "charge_unit", "share_of_branch_pct", "partner_voltage_V", "separation_mV", "midpoint_V",
                "pairing", "pairing_note", "cycles_seen", "evolution", "peaks_found", "capped"):
        assert col in peaks[0]
    assert {r["cycle"] for r in peaks} == {str(c) for c in range(1, 6)}     # every cycle, not only the plotted ones
    pairs = list(csv.DictReader(open(tmp_path / "dqde_pairs.csv")))
    assert len(pairs) == 3 + 3 + 4 + 4 + 4
    block = json.loads((tmp_path / "summary.json").read_text())["plateaus"]
    assert block["cycle"] == 1 and block["pairs"] == 3
    assert [(u["direction"], round(u["voltage_V"], 1)) for u in block["unpaired_peaks"]] == [("charge", 4.1)]
    assert [(u["direction"], u["cycle"], round(u["voltage_V"], 1)) for u in block["first_cycle_only_peaks"]] == \
        [("charge", 1, 4.1)]
    assert {r["no_curve_cycles"] for r in peaks} == {""}                     # every branch has its curve
    assert sorted((u["direction"], u["from_cycle"]) for u in block["peaks_appearing_later"]) == \
        [("charge", 3), ("discharge", 3)]
    assert rec["differential"]["peak_pair_window_mV"] == 200 and rec["settings"]["peak_pair_window_mV"] == 200
    assert "200 mV" in rec["methods"]["dqde_pairs"] and "capacity-weighted mean" in rec["methods"]["average_voltage"]
    head = (tmp_path / "origin" / "dqde_peaks.csv").read_text(encoding="utf-8-sig").splitlines()[:3]
    assert head[0].startswith("Cycle,") and head[2].startswith("cycle,branch,direction")
    assert (tmp_path / "origin" / "dqde_pairs.csv").exists()
    grid = list(csv.reader(open(tmp_path / "dqde_map.csv")))
    assert grid[0][:3] == ["cycle", "direction", "basis"] and len(grid) == 1 + 2 * pc.N_CYCLES
    volts = np.array([float(v) for v in grid[0][3:]])
    assert np.allclose(volts / BIN_V, np.round(volts / BIN_V), atol=1e-6)    # nodes at multiples of the bin
    assert (tmp_path / "fig6_dqde_map.png").exists()


def test_the_window_lives_in_the_settings():
    assert Settings().peak_pair_window_mV == differential.PEAK_PAIR_WINDOW_MV == 200.0
    with pytest.raises(ValueError):
        workflow.analyse_file(workflow.open_file(FORMATION), Settings(charge="ox", terminal_voltage=True),
                              peak_pair_window_mV=0)


# ------------------------------------------------------------------ pure functions on hand-made inputs

def _pk(direction, v, k=1):
    return DqdvPeak(1, 1, direction, k, v, 1.0, 1.0, 0.01, "mAh/V", 10.0)


def test_pairing_is_greedy_by_smallest_separation_and_uses_no_peak_twice():
    ch = [_pk("charge", 3.00), _pk("charge", 3.08)]
    di = [_pk("discharge", 3.06), _pk("discharge", 2.90)]
    got = [(a.voltage_V, b.voltage_V) for a, b in differential.pair_peaks(ch, di, 200)]
    assert got == [(3.00, 2.90), (3.08, 3.06)]          # 20 mV first, then 100 mV; 3.06 is not reused
    tie = differential.pair_peaks([_pk("charge", 3.00), _pk("charge", 3.10)], [_pk("discharge", 3.05)], 200)
    assert [(a.voltage_V, b.voltage_V) for a, b in tie] == [(3.00, 3.05)]   # equal separations: lower charge first
    edge = differential.pair_peaks([_pk("charge", 3.200)], [_pk("discharge", 3.000)], 200)
    assert len(edge) == 1                                                    # the window is inclusive
    assert differential.pair_peaks([_pk("charge", 3.2005)], [_pk("discharge", 3.000)], 200) == []


def test_peak_windows_split_at_the_valley_and_charges_are_the_peak_areas():
    v = np.round(np.arange(0, 1.0001, 0.001), 6)
    g = lambda m, s: np.exp(-0.5 * ((v - m) / s) ** 2) / (s * np.sqrt(2 * np.pi))
    y = 0.3 * g(0.3, 0.02) + 0.5 * g(0.7, 0.03)                   # areas 0.3 and 0.5, far apart
    q = np.concatenate(([0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(v))))
    cv = DqdvCurve(1, 1, "charge", v, y, "mAh/V", 1.0, q)
    found = differential.peaks(cv)
    assert [round(p.voltage_V, 3) for p in found] == [0.3, 0.7]
    (lo1, hi1), (lo2, hi2) = differential.peak_windows(cv, found)
    assert hi1 == lo2 and abs(v[hi1] - 0.5) < 0.05                # the valley between the peaks
    c1, c2 = (x[0] for x in differential.peak_charges(cv, found))
    assert c1 == pytest.approx(0.3, rel=1e-3) and c2 == pytest.approx(0.5, rel=1e-3)
    bare = DqdvCurve(1, 1, "charge", v, y, "mAh/V", 1.0)          # without the grid capacity: trapezoid of |dQ/dE|
    assert [x[0] for x in differential.peak_charges(bare, found)] == pytest.approx([c1, c2], rel=1e-9)


def test_peaks_are_followed_across_cycles_through_drift_and_gaps():
    found = {(1, "charge"): [_pk("charge", 3.00)], (2, "charge"): [_pk("charge", 3.03)],
             (3, "charge"): [_pk("charge", 3.06), _pk("charge", 3.20)], (4, "charge"): [_pk("charge", 3.09)],
             (5, "charge"): [_pk("charge", 3.12), _pk("charge", 3.24)]}
    tracks, member = differential.track_peaks(found, [1, 2, 3, 4, 5], 200)
    drift = member[id(found[(5, "charge")][0])]
    late = member[id(found[(5, "charge")][1])]
    assert drift.cycles == [1, 2, 3, 4, 5]                          # 30 mV per cycle stays one track
    assert late.cycles == [3, 5]                                    # a gap in cycle 4 does not end it
    assert differential.evolution_text(drift, [1, 2, 3, 4, 5]) == "seen in cycles 1-5"
    assert differential.evolution_text(late, [1, 2, 3, 4, 5]) == "appears from cycle 3"
    assert differential.cycle_ranges(late.cycles, [1, 2, 3, 4, 5]) == "3, 5"
    assert differential.cycle_ranges([1, 2, 5, 10], [1, 2, 5, 10, 20]) == "1-10"    # consecutive analysed cycles


# ------------------------------------------------------------------ the evolution grid

def _lin(cycle, direction, lo, n, step=0.01):
    v = lo + step * np.arange(n)
    return cycle, DqdvCurve(cycle, 1, direction, v, 2.0 * v, "mAh/V", step * 1000)


def test_evolution_grid_places_each_curve_on_common_nodes():
    """dQ/dE = 2 E is linear, so interpolation onto the nodes is exact: every value must be 2 x node."""
    curves = [_lin(1, "charge", 3.0034, 50), _lin(3, "charge", 3.1071, 40), _lin(2, "discharge", 2.9, 10)]
    g = differential.evolution_grid(curves, "charge")
    assert list(g.cycles) == [1, 3]
    assert np.allclose(g.voltage_V / 0.01, np.round(g.voltage_V / 0.01))
    assert g.voltage_V[0] == pytest.approx(3.01) and g.voltage_V[-1] == pytest.approx(3.49)
    for k, (lo, hi) in enumerate(((3.0034, 3.0034 + 0.49), (3.1071, 3.1071 + 0.39))):
        inside = (g.voltage_V >= lo) & (g.voltage_V <= hi)
        assert np.allclose(g.dqde[k, inside], 2.0 * g.voltage_V[inside], rtol=0, atol=1e-12)
        assert np.isnan(g.dqde[k, ~inside]).all()
    f = g.filled()
    assert list(f.cycles) == [1, 2, 3] and np.isnan(f.dqde[1]).all()
    assert f.value(3, 3.2049) == pytest.approx((3.20, 6.40))
    assert differential.evolution_grid(curves, "neither") is None
    with pytest.raises(ValueError):
        differential.evolution_grid([_lin(1, "charge", 3.0, 10), _lin(2, "charge", 3.0, 10, step=0.005)], "charge")
    rows = differential.grid_rows([g, differential.evolution_grid(curves, "discharge")])
    assert rows[0][:4] == ["cycle", "direction", "basis", "2.900"] and len(rows) == 4
    assert rows[1][:3] == [1, "charge", "mAh/V"] and rows[1][3] == ""      # 2.90 V: not measured in cycle 1


# ------------------------------------------------------------------ smoke tests on two other files

@pytest.mark.parametrize("path,settings", [
    (DEMO, Settings(charge="ox", reference="Li/Li+", active_mass_mg=5.0)),
    (FORMATION, Settings(charge="ox", terminal_voltage=True))], ids=["demo", "formation"])
def test_other_files_give_well_formed_tables(path, settings):
    r = workflow.analyse_file(workflow.open_file(path), settings)
    rep = r.plateaus()
    assert rep.peaks and rep.cycles == r.all_cycles
    for p in rep.peaks:
        assert p.pairing in ("paired", "unpaired") and p.evolution and p.cycles_seen
        assert p.charge >= 0 and 0 <= p.share_of_branch_pct <= 100 + 1e-9
        assert p.window_low_V <= p.voltage_V <= p.window_high_V
        assert (p.partner_voltage_V is None) == (p.pairing == "unpaired")
    for c in rep.cycles:
        for d in ("charge", "discharge"):
            assert sum(p.share_of_branch_pct for p in rep.peaks if p.cycle == c and p.direction == d) <= 100 + 1e-6
    for q in rep.pairs:
        assert q.separation_mV == pytest.approx((q.charge_voltage_V - q.discharge_voltage_V) * 1000)
        assert abs(q.separation_mV) <= rep.window_mV + 1e-6
    json.dumps(rep.summary(settings.reference_cycle))
    for g in r.evolution_grids():
        assert g.dqde.shape == (len(g.cycles), len(g.voltage_V))


# ------------------------------------------------------------------ a branch without a curve

def _interrupted(path, cycle, direction, back_s=100.0):
    """The plateau cell with the time going back once, halfway through one branch, as at a tester's restart
    (every later row is moved back_s earlier): that branch has no dQ/dE curve (M01 section 9.3, item 1)."""
    pc.write(path)
    lines = path.read_bytes().decode("cp1252").split("\r\n")
    n_head = int(lines[1].split(":")[1])
    cols = lines[n_head - 1].split("\t")
    ns_k, t_k, cyc_k = cols.index("Ns"), cols.index("time/s"), cols.index("cycle number")
    rows = [line.split("\t") for line in lines[n_head:] if line]
    want = 1 if direction == "charge" else 3
    idx = [k for k, r in enumerate(rows) if int(r[ns_k]) == want and int(r[cyc_k]) == cycle - 1]
    for r in rows[idx[len(idx) // 2]:]:
        r[t_k] = f"{float(r[t_k]) - back_s:.9E}"
    path.write_bytes(("\r\n".join(lines[:n_head] + ["\t".join(r) for r in rows]) + "\r\n").encode("cp1252"))
    return path


def _analysed(p):
    return workflow.analyse_file(workflow.open_file(p), Settings(charge="ox", reference="Li/Li+"), cycles="1:-1")


def test_a_peak_whose_partner_branch_has_no_curve_says_so(tmp_path):
    """Cycle 2's discharge is interrupted, so it has no curve: the charge peaks of cycle 2 are unpaired because
    that branch has no dQ/dE curve, not because the cycle has no discharge; the discharge peaks of the other
    cycles are seen in cycles 1 and 3 to 5, a range broken at cycle 2, which no_curve_cycles names."""
    run = _analysed(_interrupted(tmp_path / "cell.mpt", 2, "discharge"))
    assert [b.curve_breaks for b in run.seg.branches] == [0, 0, 0, 1, 0, 0, 0, 0, 0, 0]
    assert run.dqde_and_withheld(run.all_cycles)[1] == {(2, "discharge")}
    rep = run.plateaus()
    ch2 = rows_of(rep, 2, "charge")
    assert len(ch2) == 3 and {r.pairing for r in ch2} == {"unpaired"}
    assert {r.pairing_note for r in ch2} == {"the discharge branch of this cycle has no dQ/dE curve"}
    assert not rows_of(rep, 2, "discharge") and not [q for q in rep.pairs if q.cycle == 2]
    for e0, _ in pc.REVERSIBLE:
        r = near(rows_of(rep, 3, "discharge"), e0 - pc.HYST / 2)
        assert r.pairing == "paired" and r.evolution == "seen in cycles 1, 3-5" and r.cycles_seen == "1, 3-5"
        assert r.no_curve_cycles == "2"                  # why the range breaks at cycle 2
        assert near(rows_of(rep, 3, "charge"), e0 + pc.HYST / 2).no_curve_cycles == ""
    late = near(rows_of(rep, 3, "discharge"), pc.LATE[0] - pc.HYST / 2)
    assert late.evolution == "appears from cycle 3"
    assert differential.describe_peak(late).endswith("appears from cycle 3 (no discharge dQ/dE curve in cycle 2).")


def test_presence_is_judged_over_the_cycles_with_a_curve(tmp_path):
    """Cycle 1's charge is interrupted: the charge peaks of cycles 2 to 5 are seen in every cycle whose charge
    has a curve, not 'appearing from cycle 2' (the first charge is not known to lack them), and the
    first-charge-only plateau cannot be reported at all."""
    run = _analysed(_interrupted(tmp_path / "cell.mpt", 1, "charge"))
    rep = run.plateaus()
    assert not rows_of(rep, 1, "charge")
    for e0, _ in pc.REVERSIBLE:
        c = near(rows_of(rep, 2, "charge"), e0 + pc.HYST / 2)
        assert c.evolution == "seen in cycles 2-5" and c.cycles_seen == "2-5"
        d = near(rows_of(rep, 1, "discharge"), e0 - pc.HYST / 2)
        assert d.pairing_note == "the charge branch of this cycle has no dQ/dE curve"
        assert d.evolution == "seen in cycles 1-5"
    assert not [r for r in rep.peaks if abs(r.voltage_V - pc.IRREVERSIBLE[0]) < 0.02]
    assert rep.summary(1)["first_cycle_only_peaks"] == []


def _gauss(cycle, direction, centres, lo=2.8, hi=3.9, step=0.01, width=0.02):
    v = lo + step * np.arange(int(round((hi - lo) / step)) + 1)
    y = sum(np.exp(-0.5 * ((v - c) / width) ** 2) for c in centres)
    return cycle, DqdvCurve(cycle, 1, direction, v, y if direction == "charge" else -y, "mAh/V", step * 1000)


def test_a_first_cycle_only_peak_after_a_branch_without_a_curve_names_its_cycle():
    """Cycle 1's charge has no curve; a charge peak found in cycle 2 and no later cycle is 'first cycle only'
    over the cycles with a charge curve: the words, the summary and the methods window name cycle 2."""
    curves = [_gauss(1, "discharge", [3.0]), _gauss(2, "charge", [3.3, 3.6]), _gauss(2, "discharge", [3.0]),
              _gauss(3, "charge", [3.3]), _gauss(3, "discharge", [3.0])]
    rep = differential.plateau_analysis(curves, withheld={(1, "charge")})
    p = next(r for r in rep.peaks if r.direction == "charge" and abs(r.voltage_V - 3.6) < 0.011)
    assert p.evolution == "first cycle only" and p.no_curve_cycles == "1"
    assert differential.presence_words(p) == "present only in cycle 2, the first analysed cycle with a charge dQ/dE curve"
    assert differential.describe_peak(p).endswith("present only in cycle 2, the first analysed cycle with a charge "
                                                  "dQ/dE curve (no charge dQ/dE curve in cycle 1).")
    entry = rep.summary(1)["first_cycle_only_peaks"]
    assert [(u["direction"], u["cycle"], round(u["voltage_V"], 1)) for u in entry] == [("charge", 2, 3.6)]
    d1 = next(r for r in rep.peaks if r.cycle == 1)
    assert d1.pairing_note == "the charge branch of this cycle has no dQ/dE curve" and d1.evolution == "seen in cycles 1-3"
    from types import SimpleNamespace
    from electrochem import methods_text
    ctx = methods_text.Context(settings=Settings(charge="ox", reference="Li/Li+"), run=SimpleNamespace(plateaus=lambda: rep))
    line = next(x for x in methods_text.for_file("peaks", ctx) if x.startswith("Cycle 1:"))
    assert line.endswith("first cycle only: charge 3.600 V (cycle 2, the first with a charge dQ/dE curve).")
