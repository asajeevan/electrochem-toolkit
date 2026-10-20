"""Cycling engine against the frozen P02 references and a public formation file."""
import json
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]

from electrochem.cycling import integrate, analyse, Settings, theoretical_capacity_mAh_g
from electrochem.segment import segment, edges, REST
from electrochem.table import load, Table, UnsupportedTechnique

FIXTURES = sorted((ROOT / "reference/fixtures").glob("S[0-9][0-9].json"))
FORMATION_MPT = ROOT / "data/public/mpt/020-formation_CB5.mpt"
FORMATION_MPR = ROOT / "data/public/mpr/020-formation_CB5.mpr"


def _fixture_arrays(case):
    rows = case["rows"]
    t = np.array([float(Fraction(r[0])) for r in rows])
    i = np.array([float(Fraction(r[1])) if r[1] is not None else np.nan for r in rows]) * case["current_multiplier"]
    u = np.array([float(Fraction(r[2])) if r[2] is not None else np.nan for r in rows])
    sup = np.zeros(len(rows) - 1, bool)
    for k in case["supported_edges"]:
        sup[k] = True
    return t, i, u, sup


class ReferenceIntegration(unittest.TestCase):
    """Every S-case: signed charge and energy over the fixture's supported edges."""

    def test_all_cases(self):
        self.assertEqual(len(FIXTURES), 21)
        for path in FIXTURES:
            case = json.loads(path.read_text())
            t, i, u, sup = _fixture_arrays(case)
            exp = case["expected"]
            with self.subTest(case=case["id"]):
                q, w, dur = integrate(t, i, u if case["potential_role"] == "terminal" else None, sup)
                self.assertAlmostEqual(dur, float(Fraction(exp["supported_duration_s"])), places=12)
                if exp["signed_charge_C"] is None:
                    self.assertEqual(dur, 0.0)
                    continue
                self.assertAlmostEqual(q, float(Fraction(exp["signed_charge_C"])), delta=1e-12 * max(1, abs(q)))
                if exp["signed_energy_J"] is not None and w is not None:
                    self.assertAlmostEqual(w, float(Fraction(exp["signed_energy_J"])), delta=1e-12 * max(1, abs(w)))

    def test_s02_energy_is_38_over_3(self):
        case = json.loads((ROOT / "reference/fixtures/S02.json").read_text())
        t, i, u, sup = _fixture_arrays(case)
        _, w, _ = integrate(t, i, u, sup)
        self.assertAlmostEqual(w, 38 / 3, places=12)

    def test_instrument_dq_path(self):
        t = np.array([0.0, 1.0, 2.0]); i = np.array([1.0, 1.0, 1.0]); u = np.array([3.0, 3.0, 3.0])
        dq = np.array([np.nan, 0.9, 0.9])          # increments disagree with the samples on purpose
        q, w, _ = integrate(t, i, u, np.ones(2, bool), dq)
        self.assertAlmostEqual(q, 1.8); self.assertAlmostEqual(w, 5.4)
        q2, _, _ = integrate(t, i, None, np.ones(2, bool))
        self.assertAlmostEqual(q2, 2.0)


def _synthetic_table(t, i, ns=None, mode=None, e=None):
    n = len(t)
    return Table("synthetic", "0" * 64, "mpt", ("time/s", "I/A"), np.array(t, float), np.array(i, float),
                 None if e is None else np.array(e, float), None if ns is None else np.array(ns, float),
                 None if mode is None else np.array(mode, float), None, None, None, None, None, None)


class SegmentationRules(unittest.TestCase):
    def test_time_reset_and_duplicate_are_unsupported(self):
        tab = _synthetic_table([0, 1, 0, 1, 1, 2], [1, 1, 1, 1, 1, 1])
        seg = segment(tab, charge="positive", rest_current_a=0.0)
        self.assertEqual(set(seg.edges.reason), {1, 3})
        self.assertIn("reset", seg.edges.reason[1]); self.assertIn("zero-duration", seg.edges.reason[3])

    def test_missing_current_is_not_zero(self):
        tab = _synthetic_table([0, 1, 2], [1, np.nan, 1])
        seg = segment(tab, charge="positive")
        self.assertEqual(sorted(seg.edges.reason), [0, 1])
        br = analyse(tab, seg, Settings(charge="positive")).branches
        self.assertTrue(all(r.charge_mAh == 0.0 for r in br))

    def test_sign_change_across_step_boundary_is_unsupported(self):
        tab = _synthetic_table([0, 1, 2, 3], [1, 1, -1, -1], ns=[0, 0, 1, 1], mode=[1, 1, 1, 1])
        seg = segment(tab, charge="positive")
        self.assertIn(1, seg.edges.reason)
        self.assertEqual([b.direction for b in seg.branches], ["charge", "discharge"])

    def test_cc_cv_same_direction_is_one_branch(self):
        tab = _synthetic_table([0, 1, 2, 3, 4, 5], [2, 2, 2, 1, 0.5, 0], ns=[0, 0, 0, 1, 1, 1], mode=[1, 1, 1, 2, 2, 2],
                               e=[3, 3.5, 4, 4, 4, 4])
        seg = segment(tab, charge="positive")
        self.assertEqual(len(seg.branches), 1)
        self.assertEqual(seg.branches[0].modes, ("constant_current", "constant_voltage"))
        self.assertFalse(seg.branches[0].complete)   # runs to end of data
        an = analyse(tab, seg, Settings(charge="positive", terminal_voltage=True))
        br, cy = an.branches, an.cycles
        self.assertAlmostEqual(br[0].charge_cv_mAh, (1.5 + 0.75 + 0.25) / 3.6)
        self.assertEqual(cy[0].coulombic_efficiency_pct, None)
        self.assertEqual(an.summary.complete_cycles, 0)

    def test_first_branch_discharge_stays_unpaired_in_charge_first_order(self):
        tab = _synthetic_table([0, 1, 2, 3, 4, 5], [-1, -1, -1, 1, 1, 1], ns=[0, 0, 0, 1, 1, 1], mode=[1] * 6)
        seg = segment(tab, charge="positive", order="charge-first")
        self.assertEqual([p.note for p in seg.pairs][0], "unpaired discharge branch")
        seg2 = segment(tab, charge="positive", order="discharge-first")
        self.assertEqual(len(seg2.pairs), 1)
        self.assertEqual(seg2.pairs[0].note, "")

    def test_no_convention_means_no_efficiency(self):
        tab = _synthetic_table([0, 1, 2, 3], [1, 1, -1, -1], ns=[0, 0, 1, 1], mode=[1] * 4)
        seg = segment(tab)
        self.assertEqual([b.direction for b in seg.branches], ["positive", "negative"])
        self.assertEqual(seg.pairs, [])

    def test_normalisation_requires_positive_mass(self):
        tab = _synthetic_table([0, 3600], [0.001, 0.001], mode=[1, 1])
        seg = segment(tab, charge="positive")
        br = analyse(tab, seg, Settings(charge="positive", active_mass_mg=10)).branches
        self.assertAlmostEqual(br[0].specific_capacity_mAh_g, 100.0)
        for bad in (0, -1, None):
            br = analyse(tab, seg, Settings(charge="positive", active_mass_mg=bad)).branches
            self.assertIsNone(br[0].specific_capacity_mAh_g)

    def test_c_rate_delta_x_and_energy_gating(self):
        tab = _synthetic_table([0, 3600], [0.001, 0.001], mode=[1, 1], e=[3.0, 3.0])
        seg = segment(tab, charge="positive")
        s = Settings(charge="positive", active_mass_mg=10, molar_mass_g_mol=100, electrons=1, reference="Li/Li+")
        r = analyse(tab, seg, s).branches[0]
        self.assertAlmostEqual(s.theoretical_capacity_mAh_g, 268.01, delta=0.01)
        self.assertAlmostEqual(r.c_rate, 100 / 268.01, places=3)     # 100 mA/g against 268 mAh/g
        self.assertAlmostEqual(r.delta_x, 3.6 * 100 / (96485.33212 * 0.01), places=9)
        self.assertAlmostEqual(r.average_voltage_V, 3.0)
        self.assertAlmostEqual(r.specific_energy_Wh_kg, 300.0)
        r0 = analyse(tab, seg, Settings(charge="positive")).branches[0]
        self.assertIsNone(r0.energy_mWh)

    def test_theoretical_capacity(self):
        self.assertAlmostEqual(theoretical_capacity_mAh_g(1, 97.87), 273.8, delta=0.1)  # LiCoO2 one-electron
        with self.assertRaises(ValueError):
            theoretical_capacity_mAh_g(1, 0)


@unittest.skipUnless(FORMATION_MPT.exists(), "public corpus missing")
class PublicFormationFile(unittest.TestCase):
    def setUp(self):
        self.s = Settings(charge="ox", terminal_voltage=True)

    def _run(self, path):
        tab = load(path)
        seg = segment(tab, charge="ox")
        an = analyse(tab, seg, self.s)
        return tab, seg, (an.branches, an.cycles)

    def test_segmentation_and_instrument_agreement(self):
        tab, seg, (br, cy) = self._run(FORMATION_MPT)
        self.assertEqual([b.direction for b in seg.branches], ["charge", "discharge", "charge", "discharge"])
        self.assertEqual(seg.branches[0].modes, ("constant_current", "constant_voltage"))
        self.assertTrue(all(b.complete for b in seg.branches))
        for r in br:
            self.assertEqual(r.charge_method, "instrument dq increments")
            self.assertLess(abs(r.instrument_relative_difference), 1e-12)
        # Sampled-current trapezoid agrees on CC, deviates only on the sparse CV tail
        self.assertLess(abs(br[1].charge_trapezoid_mAh - br[1].charge_mAh) / br[1].charge_mAh, 5e-5)
        self.assertGreater(br[0].charge_trapezoid_mAh, br[0].charge_mAh)
        self.assertEqual(len(cy), 2)
        self.assertAlmostEqual(cy[0].coulombic_efficiency_pct, 81.994, places=2)
        self.assertAlmostEqual(cy[1].capacity_retention_pct, 97.637, places=2)

    @unittest.skipUnless(FORMATION_MPR.exists(), "public MPR missing")
    def test_native_and_text_give_same_numbers(self):
        try:
            _, _, (br_n, cy_n) = self._run(FORMATION_MPR)
        except Exception as exc:   # optional reader absent
            self.skipTest(f"native reader unavailable: {exc}")
        _, _, (br_t, cy_t) = self._run(FORMATION_MPT)
        for a, b in zip(br_n, br_t):
            self.assertAlmostEqual(a.charge_mAh, b.charge_mAh, delta=1e-6)
            self.assertAlmostEqual(a.energy_mWh, b.energy_mWh, delta=1e-4)

    def test_cli_writes_tables_and_figures(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = [sys.executable, "-m", "electrochem.analyze", str(FORMATION_MPT), "--charge", "ox",
                   "--terminal-voltage", "--cycles", "1,2", "--formats", "pdf,png", "--no-prompt", "--out", d]
            res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            names = {p.name for p in Path(d).iterdir()}
            for f in ("branches.csv", "cycles.csv", "rests.csv", "summary.json", "metadata.json", "settings.json",
                      "curves_potential_capacity.csv", "dqde_curves.csv", "dqde_peaks.csv",
                      "fig1_potential_capacity.pdf", "fig2_capacity_efficiency.png", "fig3_dqde.pdf",
                      "fig4_average_voltage.pdf", "fig5_overview_time.pdf", "fig_summary.pdf"):
                self.assertIn(f, names)
            for f in ("cycles.csv", "curves_potential_capacity_wide.csv", "dqde_wide.csv", "build_origin_project.py"):
                self.assertIn(f, {p.name for p in (Path(d) / "origin").iterdir()})
            head = (Path(d) / "origin/cycles.csv").read_text(encoding="utf-8-sig").splitlines()[:3]
            self.assertTrue(head[0].startswith("Cycle,") and head[2].startswith("cycle,"))
            meta = json.loads((Path(d) / "metadata.json").read_text())["declared_in_header"]
            self.assertEqual(meta["cycle_definition"], "Charge/Discharge alternance")
            summary = json.loads((Path(d) / "summary.json").read_text())
            self.assertEqual(summary["complete_cycles"], 2)
            rec = json.loads((Path(d) / "settings.json").read_text())
            self.assertEqual(rec["complete_cycles"], 2)
            self.assertEqual(rec["settings"]["charge"], "ox")


if __name__ == "__main__":
    unittest.main()


class RobustLoading(unittest.TestCase):
    def test_non_cycling_files_are_rejected_with_a_clear_message(self):
        for name, key in (("mpt/EIS_latin1.mpt", "impedance"), ("mpt/CV_C01.mpt", "no galvanostatic step"),
                          ("mpt/bio_logic6.mpt", "Staircase Voltammetry")):
            with self.assertRaises(UnsupportedTechnique) as cm:
                load(ROOT / "data/public" / name)
            self.assertIn(key, str(cm.exception))

    def test_decimal_comma_is_detected(self):
        tab = load(ROOT / "data/public/mpt/CV_C01.mpt", check=False)
        self.assertEqual(tab.invalid_rows, {})
        self.assertGreater(tab.n, 1000)

    def test_current_derived_from_dq_when_missing(self):
        try:
            tab = load(ROOT / "data/public/mpr/bio_logic1.mpr", check=False)
        except Exception as exc:
            self.skipTest(f"native reader unavailable: {exc}")
        self.assertEqual(tab.labels["current"], "derived: dq/dt")
        self.assertTrue(np.isnan(tab.i[0]) and np.isfinite(tab.i[1:]).any())
