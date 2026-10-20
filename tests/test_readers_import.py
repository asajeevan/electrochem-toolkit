"""The test battery that makes this safe to extend.

Three kinds of test, in increasing order of what they can catch:

1. Known-answer tests on one synthetic experiment whose capacity is exact.
2. Cross-dialect equivalence: the same experiment in three vendor dialects.
3. Metamorphic relations: transform the input in a way whose effect on the
   output is known exactly, without knowing the output itself. This is the
   standard answer to the oracle problem in scientific software, and it is what
   lets us test a reader for an instrument whose correct answer we do not know.
4. Refusal tests: wrong or incomplete declarations must fail loudly at load.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from tests import reader_fixtures as fixtures
from electrochem.readers.profile import Binding, Conventions, ImportProfile, Layout
from electrochem.readers.builtin import ARBIN_CSV, MACCOR_TXT, NEWARE_XLSX
from electrochem.readers.reader import ImportFailure, read

TOL = 1e-12


# ----------------------------------------------------------------- helpers
def capacities(tab) -> tuple[float, float, str]:
    """Charge and discharge capacity in Ah, and the method used.

    A miniature of the engine's rule: an edge is integrated only when both of
    its rows belong to the same programmed step. Integrating across a step
    boundary would attribute the switching interval to the branch. On this
    fixture that single mistake is worth 1.7 % of the charge capacity, which is
    why segmentation comes before integration.
    """
    if tab.dq is not None:
        return float(tab.dq[tab.dq > 0].sum()), float(-tab.dq[tab.dq < 0].sum()), "instrument counter"
    h = np.diff(tab.t)
    mid = h * (tab.i[:-1] + tab.i[1:]) / 2.0 / 3600.0
    if tab.step_id is not None:
        mid = np.where(tab.step_id[:-1] == tab.step_id[1:], mid, 0.0)
    return float(mid[mid > 0].sum()), float(-mid[mid < 0].sum()), "trapezoid of sampled current"


@pytest.fixture(scope="module")
def files(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("dialects")
    return {
        "arbin": fixtures.write_arbin_like(d / "cell_arbin.csv"),
        "neware": fixtures.write_neware_like(d / "cell_neware.xlsx"),
        "maccor": fixtures.write_maccor_like(d / "cell_maccor.txt"),
    }


PROFILES = {"arbin": ARBIN_CSV, "neware": NEWARE_XLSX, "maccor": MACCOR_TXT}


# ------------------------------------------------- 1. known-answer tests
@pytest.mark.parametrize("dialect", ["arbin", "neware", "maccor"])
def test_capacity_matches_the_constructed_truth(files, dialect):
    tab = read(files[dialect], PROFILES[dialect])
    qc, qd, _ = capacities(tab)
    assert qc == pytest.approx(fixtures.TRUE_Q_CHARGE_AH, rel=1e-9)
    assert qd == pytest.approx(fixtures.TRUE_Q_DISCHARGE_AH, rel=1e-9)


@pytest.mark.parametrize("dialect", ["arbin", "neware", "maccor"])
def test_current_is_charge_positive_whatever_the_file_said(files, dialect):
    tab = read(files[dialect], PROFILES[dialect])
    assert tab.i.max() > 0 and tab.i.min() < 0
    assert tab.report["current_sign_applied"] == "charge_positive"
    # the charge segment is the long positive one
    assert float(tab.i[tab.i > 0].mean()) == pytest.approx(1e-3, rel=1e-9)


# --------------------------------------------- 2. cross-dialect equivalence
def test_three_dialects_give_the_same_table(files):
    tabs = {k: read(files[k], PROFILES[k]) for k in PROFILES}
    ref = tabs["arbin"]
    for name, tab in tabs.items():
        assert tab.n == ref.n, name
        assert np.allclose(tab.t, ref.t, atol=1e-9), name
        assert np.allclose(tab.i, ref.i, atol=1e-15), name
        assert np.allclose(tab.e, ref.e, atol=1e-9), name


def test_dialects_agree_on_capacity_to_the_last_digit(files):
    vals = [capacities(read(files[k], PROFILES[k]))[:2] for k in PROFILES]
    for qc, qd in vals[1:]:
        assert qc == pytest.approx(vals[0][0], rel=1e-9)
        assert qd == pytest.approx(vals[0][1], rel=1e-9)


def test_excel_summary_sheet_is_not_concatenated(files):
    tab = read(files["neware"], NEWARE_XLSX)
    assert tab.n == len(fixtures.ground_truth())


# ------------------------------------------------- 3. metamorphic relations
def _rewrite(path: Path, fn, out: Path) -> Path:
    out.write_text("\n".join(fn(ln) for ln in path.read_text().splitlines()) + "\n")
    return out


def test_scaling_every_current_scales_every_capacity(files, tmp_path):
    """I -> kI must give Q -> kQ and leave the voltage untouched."""
    k = 7.0
    src = files["arbin"]
    head, *rows = src.read_text().splitlines()
    cols = head.split(",")
    ci, cqc, cqd = cols.index("Current(A)"), cols.index("Charge_Capacity(Ah)"), cols.index("Discharge_Capacity(Ah)")
    new = [head]
    for r in rows:
        f = r.split(",")
        for c in (ci, cqc, cqd):
            f[c] = f"{float(f[c]) * k:.12f}"
        new.append(",".join(f))
    scaled = tmp_path / "scaled.csv"
    scaled.write_text("\n".join(new) + "\n")

    base, scal = read(src, ARBIN_CSV), read(scaled, ARBIN_CSV)
    qc0, qd0, _ = capacities(base)
    qc1, qd1, _ = capacities(scal)
    assert qc1 == pytest.approx(k * qc0, rel=1e-9)
    assert qd1 == pytest.approx(k * qd0, rel=1e-9)
    assert np.allclose(scal.e, base.e, atol=1e-12)


def test_declaring_the_opposite_sign_convention_swaps_charge_and_discharge(files):
    """A profile that says discharge-positive on a charge-positive file must
    produce exactly the mirrored result. Catches a sign error in the reader."""
    flipped = ARBIN_CSV.model_copy(
        update={"conventions": ARBIN_CSV.conventions.model_copy(
            update={"current_sign": "discharge_positive"})}
    )
    a = read(files["arbin"], ARBIN_CSV)
    b = read(files["arbin"], flipped)
    assert np.allclose(b.i, -a.i, atol=1e-15)


def test_changing_the_unit_of_a_column_changes_nothing(files, tmp_path):
    """Current in mA with the header saying mA must equal current in A."""
    src = files["arbin"]
    head, *rows = src.read_text().splitlines()
    cols = head.split(",")
    ci = cols.index("Current(A)")
    cols[ci] = "Current(mA)"
    new = [",".join(cols)]
    for r in rows:
        f = r.split(",")
        f[ci] = f"{float(f[ci]) * 1e3:.12f}"
        new.append(",".join(f))
    in_ma = tmp_path / "ma.csv"
    in_ma.write_text("\n".join(new) + "\n")
    assert np.allclose(read(in_ma, ARBIN_CSV).i, read(src, ARBIN_CSV).i, atol=1e-15)


def test_changing_the_time_unit_changes_nothing(files, tmp_path):
    src = files["arbin"]
    head, *rows = src.read_text().splitlines()
    cols = head.split(",")
    ct = cols.index("Test_Time(s)")
    cols[ct] = "Test_Time(h)"
    new = [",".join(cols)]
    for r in rows:
        f = r.split(",")
        f[ct] = f"{float(f[ct]) / 3600.0:.12f}"
        new.append(",".join(f))
    in_h = tmp_path / "hours.csv"
    in_h.write_text("\n".join(new) + "\n")
    assert np.allclose(read(in_h, ARBIN_CSV).t, read(src, ARBIN_CSV).t, atol=1e-6)


def test_decimal_comma_is_read_the_same_as_decimal_point(files, tmp_path):
    src = files["arbin"]
    comma = tmp_path / "comma.csv"
    head, *rows = src.read_text().splitlines()
    comma.write_text(
        "\n".join([head] + [";".join(c.replace(".", ",") for c in r.split(",")) for r in rows]) + "\n"
    )
    p = ARBIN_CSV.model_copy(
        update={"layout": ARBIN_CSV.layout.model_copy(update={"delimiter": ";", "decimal": ","})}
    )
    head2 = ";".join(head.split(","))
    comma.write_text(
        "\n".join([head2] + [";".join(c.replace(".", ",") for c in r.split(",")) for r in rows]) + "\n"
    )
    assert np.allclose(read(comma, p).i, read(src, ARBIN_CSV).i, atol=1e-15)


def test_dropping_every_second_row_of_a_constant_current_step_is_harmless(files, tmp_path):
    """Resampling a constant-current branch must not change the integral.
    Catches an integration that depends on the sampling rather than the signal."""
    src = files["maccor"]
    # the counter is set aside, so the capacity is the integral of the sampled current
    integrate = MACCOR_TXT.model_copy(update={"conventions": MACCOR_TXT.conventions.model_copy(
        update={"capacity_semantics": "none"})})
    lines = src.read_text(encoding="cp1252").splitlines()
    k_head = next(k for k, ln in enumerate(lines) if ln.startswith("Rec\t"))
    head, body = lines[:k_head + 1], lines[k_head + 1:]
    # thin only the interior of the charge step: the first and last row of a
    # step carry the transition and dropping them would change the signal, not
    # merely the sampling of it
    step_col = head[k_head].split("\t").index("Step")
    charge_rows = [k for k, r in enumerate(body) if r.split("\t")[step_col:step_col + 1] == ["2"]]
    drop = set(charge_rows[1:-1:2])
    thinned = tmp_path / "thin.txt"
    thinned.write_text(
        "\n".join(head + [r for k, r in enumerate(body) if k not in drop]) + "\n",
        encoding="cp1252",
    )
    a = capacities(read(src, integrate))
    b = capacities(read(thinned, integrate))
    assert a[2] == b[2] == "trapezoid of sampled current"
    assert b[0] == pytest.approx(a[0], rel=1e-6)
    assert b[1] == pytest.approx(a[1], rel=1e-6)


# ------------------------------------------------------- 4. refusal tests
def test_unsigned_current_without_a_status_column_is_refused():
    with pytest.raises(ValidationError, match="direction_source"):
        Conventions(current_sign="unsigned", direction_source="current_sign",
                    capacity_semantics="none", cycle_base=1,
                    evidence="a profile that should not be allowed to exist")


def test_a_profile_without_evidence_is_refused():
    with pytest.raises(ValidationError):
        Conventions(current_sign="charge_positive", direction_source="current_sign",
                    capacity_semantics="none", cycle_base=1, evidence="")


def test_a_step_type_the_profile_does_not_know_is_refused(files, tmp_path):
    """New firmware writes a state code the profile has never seen. Where the
    direction comes from the state (Maccor's unsigned current), silently calling
    it 'other' would move charge into the wrong branch, so the import stops."""
    src = files["maccor"]
    lines = src.read_text(encoding="cp1252").splitlines()
    k = next(j for j, ln in enumerate(lines) if "\tD\t" in ln)
    lines[k] = lines[k].replace("\tD\t", "\tX\t")
    dst = tmp_path / "unknown_state.txt"
    dst.write_text("\n".join(lines) + "\n", encoding="cp1252")
    with pytest.raises(ImportFailure, match="unmapped_step_type"):
        read(dst, MACCOR_TXT)


def test_an_unknown_step_type_is_harmless_where_the_sign_gives_the_direction(files, tmp_path):
    """Neware's current is signed, so the step type only cross-checks the sign: a value the
    profile does not know is left out of the cross-check and changes no number."""
    from openpyxl import load_workbook
    src = files["neware"]
    dst = tmp_path / "unknown_status.xlsx"
    wb = load_workbook(src)
    ws = wb["record"]
    ws.cell(row=3, column=5, value="CCCV_DChg_new")
    wb.save(dst)
    a, b = read(src, NEWARE_XLSX), read(dst, NEWARE_XLSX)
    assert np.array_equal(a.i, b.i) and b.step_kind[1] == "other"


def test_a_missing_required_column_is_refused(files, tmp_path):
    src = files["arbin"]
    head, *rows = src.read_text().splitlines()
    cols = head.split(",")
    k = cols.index("Voltage(V)")
    dst = tmp_path / "no_voltage.csv"
    dst.write_text("\n".join(
        [",".join(c for j, c in enumerate(cols) if j != k)]
        + [",".join(c for j, c in enumerate(r.split(",")) if j != k) for r in rows]
    ) + "\n")
    with pytest.raises(ImportFailure, match="missing_column"):
        read(dst, ARBIN_CSV)


def test_an_unknown_unit_is_refused_rather_than_assumed(files, tmp_path):
    src = files["arbin"]
    head, *rows = src.read_text().splitlines()
    dst = tmp_path / "weird_unit.csv"
    dst.write_text("\n".join([head.replace("Current(A)", "Current(furlongs)")] + rows) + "\n")
    with pytest.raises(ImportFailure):
        read(dst, ARBIN_CSV)


def test_the_report_names_every_assumed_binding(files):
    assert not read(files["arbin"], ARBIN_CSV).report["assumed_bindings"]      # every binding was seen in a real file
    marked = ARBIN_CSV.model_copy(update={"bindings": {
        **ARBIN_CSV.bindings, "record_index": Binding(source=("Data_Point",), source_unit="1", assumed=True)}})
    tab = read(files["arbin"], marked)
    assert tab.report["assumed_bindings"] == ["record_index"]
    assert tab.report["capacity_semantics"] == "cycle_cumulative"
    assert tab.report["instrument_increment_available"] is True
    # Maccor's single unsigned counter is used too, its direction taken from the normalised current
    assert read(files["maccor"], MACCOR_TXT).report["instrument_increment_available"] is True


# ------------------------------- 5. conventions verified against the data
def test_the_declared_capacity_semantics_are_measured_not_trusted(files):
    """The profile's claim about the counter is checked against the counter."""
    from electrochem.readers.reader import _measure_capacity_semantics
    arbin = read(files["arbin"], ARBIN_CSV)
    neware = read(files["neware"], NEWARE_XLSX)
    assert _measure_capacity_semantics(
        {"charging_capacity_ah": arbin.q_charge}, arbin.step_id, arbin.cycle) == "test_cumulative"
    assert _measure_capacity_semantics(
        {"charging_capacity_ah": neware.q_charge}, neware.step_id, neware.cycle) == "step_cumulative"


def test_a_profile_that_misdeclares_the_counter_is_refused(files):
    """Arbin's reset behaviour depends on the schedule. Declaring the wrong one
    silently changes every capacity, so the file is checked and the import stops."""
    wrong = ARBIN_CSV.model_copy(
        update={"conventions": ARBIN_CSV.conventions.model_copy(
            update={"capacity_semantics": "step_cumulative"})}
    )
    with pytest.raises(ImportFailure, match="capacity_semantics_mismatch"):
        read(files["arbin"], wrong)


def test_maccor_sign_is_detected_from_the_file(files):
    """The fixture has an unsigned current and an Md column, so detection must
    conclude 'unsigned' and take the direction from Md; the one unsigned counter
    then gets its direction from the normalised current, and counter and
    integral both give the known answer."""
    tab = read(files["maccor"], MACCOR_TXT)
    assert [f["detail"]["decided"] for f in tab.findings if f["code"] == "current_sign_detected"] == ["unsigned"]
    qc, qd, method = capacities(tab)
    assert method == "instrument counter"
    assert qc == pytest.approx(fixtures.TRUE_Q_CHARGE_AH, rel=1e-9)
    assert qd == pytest.approx(fixtures.TRUE_Q_DISCHARGE_AH, rel=1e-9)
    no_counter = MACCOR_TXT.model_copy(update={"conventions": MACCOR_TXT.conventions.model_copy(
        update={"capacity_semantics": "none"})})
    qc2, qd2, method2 = capacities(read(files["maccor"], no_counter))
    assert method2 == "trapezoid of sampled current"
    assert qc2 == pytest.approx(qc, rel=1e-9) and qd2 == pytest.approx(qd, rel=1e-9)


def test_detection_refuses_when_the_file_cannot_say(tmp_path):
    """Unsigned current and nothing but rest steps: no evidence either way."""
    p = tmp_path / "flat.txt"
    p.write_text(
        "a\nb\nc\n" + "\t".join(["Rec", "Cycle P", "Cycle C", "Step", "TestTime", "Cap. [Ah]",
                                   "Current [A]", "Voltage [V]", "Md"]) + "\n"
        + "\n".join(f"{k}\t0\t1\t1\t{k},0\t0,0\t0,0\t3,0\tR" for k in range(5)) + "\n",
        encoding="cp1252",
    )
    with pytest.raises(ImportFailure, match="ambiguous_sign"):
        read(p, MACCOR_TXT)
