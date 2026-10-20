"""The explanations behind Help > How the numbers are calculated are tied to the code they describe."""
import inspect
import re
from dataclasses import fields

import numpy as np
import pytest

from electrochem import citation, cycling, differential, methods_text, workflow
from electrochem.cycling import BranchResult, CycleResult, RestResult, Settings, Summary

TOPICS = {t.key: t for t in methods_text.TOPICS}


def test_the_figures_quoted_in_the_text_are_the_code_defaults():
    sig = inspect.signature(differential.peaks)
    assert methods_text.PROMINENCE_FRACTION == sig.parameters["min_prominence_fraction"].default
    assert methods_text.MAX_PEAKS == sig.parameters["max_peaks"].default
    assert methods_text.PEAK_PAIR_WINDOW_MV == Settings().peak_pair_window_mV == differential.PEAK_PAIR_WINDOW_MV
    assert f"{methods_text.PEAK_PAIR_WINDOW_MV:g} mV" in TOPICS["peaks"].short
    assert str(cycling.F) in TOPICS["rate"].detail
    assert inspect.signature(workflow.analyse_file).parameters["dqde_mv"].default == methods_text.Context().dqde_mv


def test_every_topic_is_complete_and_in_the_house_style():
    for t in methods_text.TOPICS:
        for part in ("short", "detail", "outputs", "spec"):
            assert getattr(t, part).strip(), (t.key, part)
        text = t.short + t.detail + t.outputs + t.spec
        assert "—" not in text, t.key                         # no em dashes
        assert not re.search(r"normaliz|analyz|behavior\b|color\b", text), t.key   # British spelling
        assert "cathode" not in text and "anode" not in text, t.key  # positive/negative electrode wording
        assert "<p" in t.short and "Not produced when" in t.detail or t.key in ("evolution", "limits"), t.key
    assert [t.key for t in methods_text.TOPICS][:2] == ["segmentation", "charge"]


def test_the_columns_named_in_the_cycling_topics_exist():
    known = {f.name for cls in (BranchResult, CycleResult, RestResult, Summary, Settings,
                                differential.PlateauPeak, differential.PeakPair) for f in fields(cls)}
    known |= {"settings_json", "active_mass_mg", "area_cm2", "capacity_basis", "native_cycle",
              "fig6_dqde_map", "fig7_dqde_surface", "dqde_map", "dqde_peaks", "dqde_pairs", "dqde_curves"}
    for key in ("segmentation", "charge", "energy", "midpoint", "efficiency", "rate", "basis", "rests", "peaks",
                "evolution"):
        for tok in re.findall(r"\b[a-z0-9]+(?:_[A-Za-z0-9]+)+\b", TOPICS[key].outputs):
            if tok.endswith(("_mAh", "_mAh_g", "_V", "_pct", "_s", "_mWh", "_Wh_kg", "_mA", "_mA_g", "_mA_cm2", "_x",
                             "_cm2", "_mg", "_g", "_cycle", "_cycles", "_label", "_method", "_difference",
                             "_branch", "_by", "_mol", "_mV", "_unit", "_note", "_seen", "_found", "_reported",
                             "_capacity", "_peak", "_map", "_surface", "_peaks", "_pairs", "_curves")) or tok in known:
                assert tok in known, (key, tok)


def test_the_multi_plateau_claim_holds_in_the_engine():
    """The text says the branch average potential is the capacity-weighted mean of the plateau potentials and
    quotes 3.373 V for 40, 80 and 30 mAh/g at 3.0, 3.4 and 3.8 V. The engine's integral must say the same."""
    q = np.array([40.0, 80.0, 30.0]); e = np.array([3.0, 3.4, 3.8])
    expect = float(np.sum(q * e) / np.sum(q))
    assert f"{expect:.3f}" in TOPICS["energy"].short                 # 3.373
    n = 30001
    t = np.linspace(0.0, 150.0 * 3.6, n)                              # 1 A for 540 s passes 150 mAh
    i = np.ones(n)
    frac = np.cumsum(q) / np.sum(q)
    x = np.linspace(0.0, 1.0, n)
    pot = np.where(x < frac[0], e[0], np.where(x < frac[1], e[1], e[2]))
    Q, W, _ = cycling.integrate(t, i, pot, np.ones(n - 1, bool))
    assert W / Q == pytest.approx(expect, abs=1e-3)
    assert abs(Q / 3.6 - 150.0) < 1e-9


def test_the_peaks_lines_report_the_pairs_and_the_unpaired_peaks_of_the_reference_cycle(tmp_path):
    """On the synthetic multi-plateau cell: three pairs, one unpaired first-charge peak, in the file's own words."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    import plateau_cell
    p = plateau_cell.write(tmp_path / "plateaus.mpt")
    run = workflow.analyse_file(workflow.open_file(p), Settings(charge="ox", terminal_voltage=True, active_mass_mg=5.0))
    lines = methods_text.for_file("peaks", methods_text.Context(settings=run.settings, run=run))
    assert any("200 mV" in l for l in lines)
    last = lines[-1]
    assert "3 pairs" in last and "1 unpaired peak" in last and "charge 4.100 V" in last and "first cycle only" in last
    assert "irreversible" not in " ".join(lines)


def test_for_file_lines_reflect_the_settings():
    assert methods_text.for_file("charge", methods_text.Context()) == []
    s = Settings(charge="red", terminal_voltage=False, reference="Li/Li+", active_mass_mg=4.5, molar_mass_g_mol=72.0,
                 electrons=1.0, reference_cycle=2)
    ctx = methods_text.Context(settings=s, file_name="cell.mpt", profile_name="arbin-xlsx")
    seg = methods_text.for_file("segmentation", ctx)
    assert any("negative (reduction) current" in l for l in seg) and any("arbin-xlsx" in l for l in seg)
    assert any("4.5 mg" in l for l in methods_text.for_file("basis", ctx))
    assert any("Li/Li+" in l for l in methods_text.for_file("energy", ctx))
    assert any("Reference cycle for retention: 2" in l for l in methods_text.for_file("efficiency", ctx))
    rate = methods_text.for_file("rate", ctx)
    assert any(f"{s.theoretical_capacity_mAh_g:.4g}" in l for l in rate)
    no_rate = methods_text.for_file("rate", methods_text.Context(settings=Settings()))
    assert any("not produced" in l for l in no_rate)


def test_the_methods_paragraph_is_written_from_the_settings_and_ends_with_the_reference():
    s = Settings(charge="ox", terminal_voltage=True, active_mass_mg=10.0, reference_cycle=1)
    p = methods_text.paragraph(methods_text.Context(settings=s, dqde_mv=5.0))
    assert p.endswith(citation.plain()) and "Reference:" in p
    assert "10 mg" in p and "cycle 1" in p and "5 mV" in p and "cell voltage" in p
    assert "trapezoidal integration" in p and "charge increments" not in p.split("Reference:")[0].split(".")[2]
    half = methods_text.paragraph(methods_text.Context(settings=Settings(charge="red", reference="Li/Li+")))
    assert "against Li/Li+" in half and "active material" in half
    assert "—" not in p and "—" not in half
