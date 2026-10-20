"""One test per named failure mode.

The register in P08 lists every way a wrong number could leave this layer. Each
entry has a test here, and each test asserts the specific behaviour promised:
refuse, warn, or handle. A failure mode without a test is a claim, not a
property, so this file is the evidence for the robustness register.

Grouped by what the guard protects against:

  A. file and grid shape
  B. text, encoding and number formats
  C. column mapping
  D. physical and structural sanity
  E. the universal path for an instrument with no profile
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tests import reader_fixtures as fixtures
from electrochem.readers import propose
from electrochem.readers.profile import Binding, Conventions, ImportProfile, Layout
from electrochem.readers.builtin import ARBIN_CSV, MACCOR_TXT, NEWARE_XLSX
from electrochem.readers.reader import ImportFailure, read


@pytest.fixture(scope="module")
def files(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("rob")
    return {
        "arbin": fixtures.write_arbin_like(d / "cell_arbin.csv"),
        "neware": fixtures.write_neware_like(d / "cell_neware.xlsx"),
        "maccor": fixtures.write_maccor_like(d / "cell_maccor.txt"),
    }


def codes(exc) -> set[str]:
    return {ln.split(":")[0].split("] ")[-1].strip()
            for ln in str(exc.value).splitlines() if "] " in ln} | {exc.value.code}


def edit_csv(src: Path, dst: Path, header=None, rows=None) -> Path:
    head, *body = src.read_text().splitlines()
    head = header(head) if header else head
    body = [rows(r) for r in body] if rows else body
    dst.write_text("\n".join([head] + [r for r in body if r is not None]) + "\n")
    return dst


def col(src: Path, name: str) -> int:
    return src.read_text().splitlines()[0].split(",").index(name)


def map_column(src: Path, dst: Path, name: str, fn) -> Path:
    """Apply fn to one named column in every data row."""
    k = col(src, name)
    return edit_csv(src, dst, rows=lambda r: ",".join(
        fn(c) if j == k else c for j, c in enumerate(r.split(","))))


# =============================================== A. file and grid shape
def test_an_empty_file_is_refused(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_bytes(b"")
    with pytest.raises(ImportFailure, match="empty_file"):
        read(p, ARBIN_CSV)


def test_a_header_with_no_data_rows_is_refused(files, tmp_path):
    p = tmp_path / "headeronly.csv"
    p.write_text(files["arbin"].read_text().splitlines()[0] + "\n")
    with pytest.raises(ImportFailure, match="no_data"):
        read(p, ARBIN_CSV)


def test_a_row_with_extra_fields_is_refused_because_values_would_vanish(files, tmp_path):
    """Fields beyond the last header name have no column to belong to, so they
    would be dropped with no trace. That is the one shape fault worth stopping."""
    dst = edit_csv(files["arbin"], tmp_path / "wide.csv",
                   rows=lambda r: r + ",99999" if r.startswith("5,") else r)
    with pytest.raises(ImportFailure) as e:
        read(dst, ARBIN_CSV)
    assert "rows_wider_than_header" in codes(e)


def test_a_truncated_final_line_warns_but_still_imports(files, tmp_path):
    """An interrupted run leaves a short last line. The missing fields become
    NaN and the row is not integrated; throwing the file away would be worse."""
    lines = files["arbin"].read_text().splitlines()
    dst = tmp_path / "truncated.csv"
    dst.write_text("\n".join(lines[:-1] + [",".join(lines[-1].split(",")[:4])]) + "\n")
    tab = read(dst, ARBIN_CSV)
    assert any(f["code"] == "rows_narrower_than_header" for f in tab.warnings)
    assert tab.n == len(lines) - 1


def test_a_trailing_delimiter_in_the_header_is_not_a_column(files, tmp_path):
    """EC-Lab ends every .mpt header line with a tab. The nameless column it
    invents must not make every data row look one field short."""
    dst = edit_csv(files["arbin"], tmp_path / "trailing.csv", header=lambda h: h + ",")
    tab = read(dst, ARBIN_CSV)
    assert any(f["code"] == "trailing_delimiter_in_header" for f in tab.findings)
    assert np.allclose(tab.i, read(files["arbin"], ARBIN_CSV).i, atol=1e-15)


def test_an_oversized_file_is_refused_before_it_is_read(files, tmp_path, monkeypatch):
    from electrochem.readers import reader
    monkeypatch.setattr(reader, "MAX_BYTES", 10)
    with pytest.raises(ImportFailure, match="file_too_large"):
        read(files["arbin"], ARBIN_CSV)


# ================================== B. text, encoding and number formats
def test_a_byte_order_mark_overrides_the_declared_encoding(files, tmp_path):
    """A BOM is the file's own statement of its encoding and outranks the
    profile's guess. Without this a UTF-8 BOM read as cp1252 becomes three
    visible characters glued to the first column name, which unbinds that
    column silently rather than failing."""
    dst = tmp_path / "utf16.csv"
    dst.write_bytes(files["arbin"].read_text().encode("utf-16"))   # writes a BOM
    tab = read(dst, ARBIN_CSV)                                     # profile says cp1252
    assert any(f["code"] == "byte_order_mark_overrides_profile" for f in tab.findings)
    assert np.allclose(tab.i, read(files["arbin"], ARBIN_CSV).i, atol=1e-15)


def test_a_bom_in_front_of_a_cp1252_profile_does_not_corrupt_the_first_column(files, tmp_path):
    dst = tmp_path / "bom_cp1252.csv"
    dst.write_bytes(b"\xef\xbb\xbf" + files["arbin"].read_bytes())
    tab = read(dst, ARBIN_CSV)
    assert tab.columns[0] == "Data_Point"
    assert tab.step_id is not None, "the first column must still bind"


def test_a_file_that_does_not_decode_as_declared_is_refused(files, tmp_path):
    """No BOM to go on, and the bytes are not text in the declared encoding."""
    dst = tmp_path / "binary.csv"
    dst.write_bytes(files["arbin"].read_text().encode("utf-16-le"))   # no BOM
    with pytest.raises(ImportFailure) as e:
        read(dst, ARBIN_CSV)
    assert {"encoding_damage", "binary_content"} & codes(e)


def test_a_utf8_bom_does_not_break_the_first_column_name(files, tmp_path):
    dst = tmp_path / "bom.csv"
    dst.write_bytes(b"\xef\xbb\xbf" + files["arbin"].read_bytes())
    p = ARBIN_CSV.model_copy(
        update={"layout": ARBIN_CSV.layout.model_copy(update={"encoding": "utf-8-sig"})})
    assert read(dst, p).n == read(files["arbin"], ARBIN_CSV).n


def test_a_unicode_minus_is_read_as_a_negative_number(files, tmp_path):
    dst = edit_csv(files["arbin"], tmp_path / "uminus.csv",
                   rows=lambda r: r.replace(",-", ",−"))
    assert np.allclose(read(dst, ARBIN_CSV).i, read(files["arbin"], ARBIN_CSV).i, atol=1e-15)


def test_a_fortran_d_exponent_is_read(tmp_path):
    from electrochem.readers.reader import _to_float
    v, bad = _to_float(["1.5D-03", "2.0d+00"], ".")
    assert bad == 0 and v[0] == pytest.approx(1.5e-3) and v[1] == pytest.approx(2.0)


def test_european_grouping_is_read_as_a_decimal_comma(tmp_path):
    from electrochem.readers.reader import _sniff_decimal, _to_float
    assert _sniff_decimal([["1.234,5", "6,7"]]) == ","
    v, bad = _to_float(["1.234,5"], ",")
    assert bad == 0 and v[0] == pytest.approx(1234.5)


def test_grouping_that_contradicts_the_declared_decimal_mark_is_refused(tmp_path):
    """'1,234.5' parsed with a decimal comma silently becomes 1.2345. Refuse."""
    p = tmp_path / "grouped.csv"
    p.write_text("Test_Time(s);Current(A);Voltage(V)\n"
                 "0;0.001;3.5\n1,234.5;0.001;3.6\n2,500.0;0.001;3.7\n")
    prof = ARBIN_CSV.model_copy(
        update={"layout": ARBIN_CSV.layout.model_copy(
            update={"delimiter": ";", "decimal": ","})})
    with pytest.raises(ImportFailure) as e:
        read(p, prof)
    assert "decimal_mark_conflict" in codes(e)


def test_a_column_that_is_mostly_unreadable_is_refused(files, tmp_path):
    dst = map_column(files["arbin"], tmp_path / "junk.csv", "Current(A)", lambda c: "XXX")
    with pytest.raises(ImportFailure) as e:
        read(dst, ARBIN_CSV)
    assert {"column_mostly_unreadable", "column_all_invalid"} & codes(e)


def test_scattered_instrument_flags_become_nan_and_are_counted(files, tmp_path):
    n = [0]
    k = col(files["arbin"], "Current(A)")

    def one_row_only(r):
        n[0] += 1
        f = r.split(",")
        if n[0] == 10:
            f[k] = "OVERFLOW"
        return ",".join(f)

    dst = edit_csv(files["arbin"], tmp_path / "flagged.csv", rows=one_row_only)
    tab = read(dst, ARBIN_CSV)
    assert sum(tab.report["invalid_tokens"].values()) == 1
    assert np.isnan(tab.i).sum() == 1


# ========================================================= C. column mapping
def test_two_columns_with_the_same_name_are_refused_not_resolved_by_position(files, tmp_path):
    dst = edit_csv(files["arbin"], tmp_path / "dupe.csv",
                   header=lambda h: h + ",Current(A)",
                   rows=lambda r: r + ",0.0")
    with pytest.raises(ImportFailure) as e:
        read(dst, ARBIN_CSV)
    assert "ambiguous_column" in codes(e)


def test_a_unit_of_the_wrong_dimension_is_refused(files, tmp_path):
    """'Current(V)' is not a current in volts; it is a wrong binding. The unit
    registry knows the dimension of every unit, so this cannot pass."""
    dst = edit_csv(files["arbin"], tmp_path / "dim.csv",
                   header=lambda h: h.replace("Current(A)", "Current(mV)"))
    with pytest.raises(ImportFailure) as e:
        read(dst, ARBIN_CSV)
    assert "unit_dimension_mismatch" in codes(e)


def test_a_header_unit_that_contradicts_the_profile_is_refused(tmp_path):
    p = tmp_path / "conflict.csv"
    p.write_text("Test_Time(s),Current(mA),Voltage(V)\n0,1.0,3.0\n60,1.0,3.1\n")
    prof = ImportProfile(
        name="x", instrument="x",
        layout=Layout(kind="delimited", delimiter=","),
        conventions=Conventions(current_sign="charge_positive",
                                direction_source="current_sign",
                                capacity_semantics="none", cycle_base=1,
                                evidence="constructed for this test only"),
        bindings={"test_time_second": Binding(source=("Test_Time",), source_unit="s"),
                  "current_ampere": Binding(source=("Current",), source_unit="A"),
                  "voltage_volt": Binding(source=("Voltage",), source_unit="V")})
    with pytest.raises(ImportFailure) as e:
        read(p, prof)
    assert "unit_conflict" in codes(e)


def test_an_unreadable_unit_is_refused_rather_than_assumed(files, tmp_path):
    dst = edit_csv(files["arbin"], tmp_path / "furlong.csv",
                   header=lambda h: h.replace("Test_Time(s)", "Test_Time(furlongs)"))
    with pytest.raises(ImportFailure):
        read(dst, ARBIN_CSV)


def test_every_problem_is_reported_in_one_run(files, tmp_path):
    """Three faults at once must produce three findings, not the first one."""
    dst = edit_csv(files["arbin"], tmp_path / "many.csv",
                   header=lambda h: h.replace("Current(A)", "Current(mV)")
                                     .replace("Voltage(V)", "Voltage(furlongs)"))
    with pytest.raises(ImportFailure) as e:
        read(dst, ARBIN_CSV)
    assert len(codes(e)) >= 2, str(e.value)
    assert "problem(s)" in str(e.value)


# ============================================ D. physical and structural sanity
def test_a_step_clock_mapped_as_the_test_clock_is_refused(tmp_path):
    """The most damaging quiet error available: a per-step time column read as
    the cumulative clock shortens every branch, and the result still looks like
    a battery."""
    rows = []
    for step in (1, 2, 3, 4):
        for k in range(6):
            rows.append(f"{step},{k * 60},{0.001 if step % 2 else -0.001},3.5")
    p = tmp_path / "steptime.csv"
    p.write_text("Step_Index,Test_Time(s),Current(A),Voltage(V)\n" + "\n".join(rows) + "\n")
    prof = ImportProfile(
        name="x", instrument="x", layout=Layout(kind="delimited", delimiter=","),
        conventions=Conventions(current_sign="charge_positive",
                                direction_source="current_sign",
                                capacity_semantics="none", cycle_base=1,
                                evidence="constructed for this test only"),
        bindings={"test_time_second": Binding(source=("Test_Time",)),
                  "current_ampere": Binding(source=("Current",)),
                  "voltage_volt": Binding(source=("Voltage",)),
                  "step_id": Binding(source=("Step_Index",), source_unit="1")})
    with pytest.raises(ImportFailure) as e:
        read(p, prof)
    assert "time_resets_at_every_step" in codes(e)


def test_a_signed_current_that_contradicts_the_step_type_is_refused(tmp_path):
    """Two independent statements of direction. When they disagree one of the
    two declarations is backwards, which would swap charge and discharge."""
    rows = [f"1,{k * 60},0.001,3.5,CC_DChg" for k in range(6)]
    p = tmp_path / "contradict.csv"
    p.write_text("Step_Index,Test_Time(s),Current(A),Voltage(V),Status\n" + "\n".join(rows) + "\n")
    prof = ImportProfile(
        name="x", instrument="x", layout=Layout(kind="delimited", delimiter=","),
        conventions=Conventions(current_sign="charge_positive",
                                direction_source="current_sign",
                                capacity_semantics="none", cycle_base=1,
                                step_type_map={"CC_DChg": "cc_discharge", "CC_Chg": "cc_charge"},
                                evidence="constructed for this test only"),
        bindings={"test_time_second": Binding(source=("Test_Time",)),
                  "current_ampere": Binding(source=("Current",)),
                  "voltage_volt": Binding(source=("Voltage",)),
                  "step_id": Binding(source=("Step_Index",), source_unit="1"),
                  "step_type": Binding(source=("Status",))})
    with pytest.raises(ImportFailure) as e:
        read(p, prof)
    assert "sign_contradicts_step_type" in codes(e)


def test_a_current_a_thousand_times_too_large_is_flagged(files, tmp_path):
    """A mislabelled unit is the commonest real cause. It cannot be corrected
    automatically, so it is reported rather than silently accepted."""
    dst = map_column(files["arbin"], tmp_path / "huge.csv", "Current(A)",
                     lambda c: f"{float(c) * 1e7:.6f}")
    tab = read(dst, ARBIN_CSV)
    assert any(f["code"] == "implausible_magnitude" for f in tab.warnings)


def test_the_instrument_counter_and_the_integral_are_compared(files):
    """The in-field oracle: on a correctly mapped file the instrument's own
    charge counter and our integral of the sampled current must agree."""
    tab = read(files["arbin"], ARBIN_CSV)
    x = tab.report["counter_vs_integral"]
    assert x is not None and x["worst_relative_difference"] < 0.02
    assert x["charge"]["instrument_counter_Ah"] == pytest.approx(
        fixtures.TRUE_Q_CHARGE_AH, rel=1e-9)


def test_a_cycle_counter_that_starts_at_the_wrong_number_is_flagged(files):
    wrong = ARBIN_CSV.model_copy(
        update={"conventions": ARBIN_CSV.conventions.model_copy(update={"cycle_base": 0})})
    tab = read(files["arbin"], wrong)
    assert any(f["code"] == "cycle_base_mismatch" for f in tab.warnings)


def test_two_concatenated_runs_are_flagged_but_not_mistaken_for_a_step_clock(tmp_path):
    """One backwards jump is two runs appended, not a per-step clock. The two
    need different remedies, so the check distinguishes them by how many of the
    step boundaries reset rather than by whether any does."""
    body = [f"1,{k * 60},0.001,3.5" for k in range(8)]
    p = tmp_path / "twice.csv"
    p.write_text("Step_Index,Test_Time(s),Current(A),Voltage(V)\n"
                 + "\n".join(body + [r.replace("1,", "2,", 1) for r in body]) + "\n")
    prof = ImportProfile(
        name="x", instrument="x", layout=Layout(kind="delimited", delimiter=","),
        conventions=Conventions(current_sign="charge_positive",
                                direction_source="current_sign",
                                capacity_semantics="none", cycle_base=1,
                                evidence="constructed for this test only"),
        bindings={"test_time_second": Binding(source=("Test_Time",)),
                  "current_ampere": Binding(source=("Current",)),
                  "voltage_volt": Binding(source=("Voltage",)),
                  "step_id": Binding(source=("Step_Index",), source_unit="1")})
    tab = read(p, prof)
    assert any(f["code"] == "time_goes_backwards" for f in tab.warnings)
    assert not any(f["code"] == "time_resets_at_every_step" for f in tab.findings)


def test_the_report_names_the_columns_that_were_not_used(files):
    tab = read(files["arbin"], ARBIN_CSV)
    assert isinstance(tab.report["columns_unused"], list)
    assert all(c in tab.columns for c in tab.report["columns_unused"])


# ================================ E. the universal path: no profile exists
def test_a_setpoint_column_is_never_taken_for_the_measurement(tmp_path):
    p = tmp_path / "control.csv"
    p.write_text("Test_Time(s),Control_Current(A),Current(A),Voltage(V)\n"
                 "0,0.002,0.001,3.5\n60,0.002,0.001,3.6\n")
    pr = propose.propose(p)
    assert pr.chosen["current_ampere"].column == "Current(A)"


def test_an_impedance_spectrum_is_refused_as_a_cycling_file(tmp_path):
    p = tmp_path / "eis.txt"
    p.write_text("freq/Hz\tRe(Z)/Ohm\t-Im(Z)/Ohm\ttime/s\n"
                 "1000\t12.0\t3.0\t0\n100\t13.0\t4.0\t1\n")
    pr = propose.propose(p)
    assert any("impedance spectrum" in b for b in pr.blocking)
    assert not pr.ready


def test_an_impedance_column_cannot_be_matched_to_the_current(tmp_path):
    """'-Im(Z)' reads like a current by name. The dimension of its unit is what
    rules it out, which is a property of the registry, not of the name list."""
    assert propose.score_column("current_ampere", "-Im(Z)/Ohm") is None
    assert propose.score_column("current_ampere", "I/mA") is not None


def test_the_header_is_found_whatever_the_preamble_length(tmp_path):
    for preamble in (0, 1, 3, 12, 92):
        p = tmp_path / f"pre{preamble}.txt"
        p.write_text("\n".join(f"some preamble line {k}" for k in range(preamble))
                     + ("\n" if preamble else "")
                     + "time/s\tI/mA\tEwe/V\n0\t1.0\t3.0\n1\t1.0\t3.1\n2\t1.0\t3.2\n")
        pr = propose.propose(p)
        assert pr.layout.header_row == preamble + 1, preamble
        assert pr.chosen["current_ampere"].column == "I/mA"


def test_an_unsigned_file_with_no_status_column_blocks_rather_than_guessing(tmp_path):
    p = tmp_path / "flat.csv"
    p.write_text("Test_Time(s),Current(A),Voltage(V)\n0,0.001,3.5\n60,0.001,3.6\n")
    pr = propose.propose(p)
    assert not pr.ready
    assert any("distinguishes charge from discharge" in b for b in pr.blocking)


def test_a_signed_file_still_asks_which_sign_means_charge(tmp_path):
    p = tmp_path / "signed.csv"
    p.write_text("Test_Time(s),Current(A),Voltage(V)\n0,0.001,3.5\n60,-0.001,3.6\n")
    pr = propose.propose(p)
    assert pr.ready                                   # nothing blocks
    assert any("positive means charge" in q for q in pr.questions)


@pytest.mark.parametrize("dialect", ["arbin", "neware", "maccor"])
def test_the_proposed_profile_reproduces_the_hand_written_one(files, dialect):
    """The strongest claim this layer makes: for a file we *do* have a curated
    profile for, the automatic proposal plus the answers a person would give
    produces the identical table. The universal path is not a lesser path."""
    curated = {"arbin": ARBIN_CSV, "neware": NEWARE_XLSX, "maccor": MACCOR_TXT}[dialect]
    pr = propose.propose(files[dialect])
    # the one answer the file cannot give: Maccor's TestTime states no unit (it is minutes)
    for role, col in pr.unit_unknown.items():
        if role in curated.bindings:
            pr.bindings[role] = Binding(source=(col,), source_unit=curated.bindings[role].source_unit, assumed=True)
    auto = pr.to_profile(f"auto-{dialect}", f"proposed from {dialect}", curated.conventions)
    a, b = read(files[dialect], auto), read(files[dialect], curated)
    assert a.n == b.n
    assert np.allclose(a.t, b.t, atol=1e-9, equal_nan=True)
    assert np.allclose(a.i, b.i, atol=1e-15, equal_nan=True)
    assert np.allclose(a.e, b.e, atol=1e-12, equal_nan=True)


def test_every_proposed_binding_is_marked_assumed(files):
    pr = propose.propose(files["arbin"])
    assert pr.bindings and all(b.assumed for b in pr.bindings.values())
    prof = pr.to_profile("auto", "proposed", ARBIN_CSV.conventions)
    tab = read(files["arbin"], prof)
    assert set(tab.report["assumed_bindings"]) == set(prof.bindings)


# ============================== F. learning an instrument the tool has not met
def test_an_unknown_instrument_is_learned_once_and_then_recognised(files, tmp_path):
    """The universal path end to end: an unrecognised file, a proposal, the
    answers a person supplies, and then automatic recognition of the next file
    from the same instrument."""
    from electrochem.readers.registry import Registry, confirm

    reg = Registry(tmp_path / "profiles")
    with pytest.raises(LookupError, match="no profile recognises"):
        reg.identify(files["arbin"])

    pr = propose.propose(files["arbin"])
    assert pr.ready, pr.blocking
    learned = confirm(pr, name="my-cycler", instrument="the one in our lab",
                      conventions=ARBIN_CSV.conventions, registry=reg)

    again = reg.identify(files["arbin"])
    assert again.name == "my-cycler"
    a, b = read(files["arbin"], again), read(files["arbin"], ARBIN_CSV)
    assert np.allclose(a.i, b.i, atol=1e-15) and np.allclose(a.t, b.t, atol=1e-9)
    assert learned.bindings


def test_a_fingerprint_survives_reordered_columns_and_different_units(files, tmp_path):
    """Firmware reorders columns and the export dialog changes units; neither
    changes which instrument wrote the file."""
    from electrochem.readers.registry import fingerprint

    head = files["arbin"].read_text().splitlines()[0].split(",")
    assert fingerprint(head) == fingerprint(list(reversed(head)))
    assert fingerprint(head) == fingerprint(
        [h.replace("(A)", "(mA)").replace("(Ah)", "(mAh)") for h in head])


def test_a_proposal_with_open_questions_cannot_be_saved(files, tmp_path):
    """Saving a guess would apply it to every future file from that instrument."""
    from electrochem.readers.registry import Registry, confirm

    pr = propose.propose(files["maccor"])          # unsigned, and a time column with no unit: blocking
    assert not pr.ready
    with pytest.raises(ValueError, match="blocking"):
        confirm(pr, name="x", instrument="x", conventions=MACCOR_TXT.conventions,
                registry=Registry(tmp_path / "p"))


# ===================== G. the remaining named refusals and warnings
def _tiny(tmp_path, name, text, **binding_extra):
    p = tmp_path / name
    p.write_text(text)
    return p


def _simple_profile(**over):
    base = dict(
        name="x", instrument="x", layout=Layout(kind="delimited", delimiter=","),
        conventions=Conventions(current_sign="charge_positive",
                                direction_source="current_sign",
                                capacity_semantics="none", cycle_base=1,
                                evidence="constructed for this test only"),
        bindings={"test_time_second": Binding(source=("Test_Time",)),
                  "current_ampere": Binding(source=("Current",)),
                  "voltage_volt": Binding(source=("Voltage",))})
    base.update(over)
    return ImportProfile(**base)


def test_one_column_bound_to_two_roles_is_refused(tmp_path):
    p = _tiny(tmp_path, "twice.csv", "Test_Time(s),Current(A),Voltage(V)\n0,1,3\n1,1,3\n")
    prof = _simple_profile(bindings={
        "test_time_second": Binding(source=("Test_Time",)),
        "current_ampere": Binding(source=("Current",)),
        "voltage_volt": Binding(source=("Voltage",)),
        "power_watt": Binding(source=("Current",), source_unit="W")})
    with pytest.raises(ImportFailure) as e:
        read(p, prof)
    assert {"column_claimed_twice", "unit_conflict"} & codes(e)


def test_a_file_with_no_delimiter_on_the_header_line_is_refused(tmp_path):
    p = _tiny(tmp_path, "plain.txt", "just one column name\n1\n2\n")
    prof = _simple_profile(layout=Layout(kind="delimited", delimiter=None))
    with pytest.raises(ImportFailure, match="no_delimiter|missing_column"):
        read(p, prof)


def test_a_header_marker_that_is_absent_is_refused(tmp_path):
    p = _tiny(tmp_path, "nohdr.csv", "a,b,c\n1,2,3\n")
    prof = _simple_profile(
        layout=Layout(kind="delimited", delimiter=",", header_contains=("Voltage(V)",)))
    with pytest.raises(ImportFailure, match="no_header"):
        read(p, prof)


def test_a_file_shorter_than_the_declared_header_row_is_refused(tmp_path):
    p = _tiny(tmp_path, "tiny.csv", "a,b,c\n")
    prof = _simple_profile(layout=Layout(kind="delimited", delimiter=",", header_row=9))
    with pytest.raises(ImportFailure, match="short_file"):
        read(p, prof)


def test_a_named_sheet_that_is_absent_is_refused(files):
    p = NEWARE_XLSX.model_copy(
        update={"layout": NEWARE_XLSX.layout.model_copy(update={"sheets": ("Nope",)})})
    with pytest.raises(ImportFailure, match="missing_sheet"):
        read(files["neware"], p)


def test_an_unsigned_file_whose_step_type_states_no_direction_is_refused(tmp_path):
    p = _tiny(tmp_path, "nodir.csv",
              "Test_Time(s),Current(A),Voltage(V),Status\n0,1,3,Weird\n1,1,3,Weird\n")
    prof = _simple_profile(
        conventions=Conventions(current_sign="unsigned", direction_source="step_type",
                                capacity_semantics="none", cycle_base=1,
                                step_type_map={"Weird": "other"},
                                evidence="constructed for this test only"),
        bindings={"test_time_second": Binding(source=("Test_Time",)),
                  "current_ampere": Binding(source=("Current",)),
                  "voltage_volt": Binding(source=("Voltage",)),
                  "step_type": Binding(source=("Status",))})
    with pytest.raises(ImportFailure, match="no_direction"):
        read(p, prof)


def test_a_voltage_far_outside_the_plausible_band_is_flagged(files, tmp_path):
    dst = map_column(files["arbin"], tmp_path / "hv.csv", "Voltage(V)",
                     lambda c: f"{float(c) * 1000:.3f}")
    tab = read(dst, ARBIN_CSV)
    assert any(f["code"] == "implausible_range" for f in tab.warnings)


def test_rows_with_no_readable_time_are_counted_not_silently_dropped(files, tmp_path):
    n = [0]
    k = col(files["arbin"], "Test_Time(s)")

    def blank_one(r):
        n[0] += 1
        f = r.split(",")
        if n[0] == 5:
            f[k] = ""
        return ",".join(f)

    tab = read(edit_csv(files["arbin"], tmp_path / "notime.csv", rows=blank_one), ARBIN_CSV)
    assert any(f["code"] == "time_not_finite" for f in tab.warnings)


def test_a_file_with_fewer_than_two_readable_times_is_refused(tmp_path):
    p = _tiny(tmp_path, "one.csv", "Test_Time(s),Current(A),Voltage(V)\n0,1,3\n,1,3\n")
    with pytest.raises(ImportFailure) as e:
        read(p, _simple_profile())
    assert {"time_too_short", "column_mostly_unreadable"} & codes(e)


def test_a_counter_that_disagrees_with_the_integral_is_flagged(files, tmp_path):
    """Halve the instrument's charge counter: the integral of the current no
    longer matches it, and the cross-check must say so."""
    dst = map_column(files["arbin"], tmp_path / "badq.csv", "Charge_Capacity(Ah)",
                     lambda c: f"{float(c) * 0.5:.12f}")
    tab = read(dst, ARBIN_CSV)
    assert any(f["code"] == "counter_disagrees_with_integral" for f in tab.warnings)


def test_a_repeated_column_name_is_reported(files, tmp_path):
    dst = edit_csv(files["arbin"], tmp_path / "dup2.csv",
                   header=lambda h: h + ",Notes,Notes", rows=lambda r: r + ",a,b")
    tab = read(dst, ARBIN_CSV)
    assert any(f["code"] == "duplicate_header_names" for f in tab.findings)


def test_a_channel_column_is_reported_so_a_multi_cell_file_is_not_averaged(files, tmp_path):
    dst = edit_csv(files["arbin"], tmp_path / "chan.csv",
                   header=lambda h: h + ",Channel", rows=lambda r: r + ",7")
    tab = read(dst, ARBIN_CSV)
    assert any(f["code"] == "channel_column_present" for f in tab.findings)


def test_detection_records_the_conclusion_it_reached(files):
    tab = read(files["maccor"], MACCOR_TXT)
    rec = [f for f in tab.findings if f["code"] == "current_sign_detected"]
    assert rec and rec[0]["detail"]["decided"] == "unsigned"


def test_a_second_sheet_with_a_different_header_is_reported_as_skipped(files):
    tab = read(files["neware"], NEWARE_XLSX)
    assert any(f["code"] in ("sheets_skipped", "sheets_concatenated") for f in tab.findings)


# ============================ H. behaviours found on real instrument files (P08d)
def test_a_clock_duration_is_read_only_from_a_column_declared_so(tmp_path):
    """'hh:mm:ss' parses Maccor's '0d 00:00:5.05', Neware's '00:01:00' and PEC's unbounded hours;
    a bare number in such a column is invalid (seconds or hours?), and a numeric column never
    reads a clock."""
    from electrochem.readers.cells import parse_duration
    assert parse_duration("  0d 00:00:5.05000019073486") == pytest.approx(5.05000019073486)
    assert parse_duration("1d 02:00:00") == 93600.0 and parse_duration("123:45:06.5") == 445506.5
    assert parse_duration("12.5") is None and parse_duration("01:00.5") is None and parse_duration("1:61:00") is None
    p = tmp_path / "clock.csv"
    p.write_text("Test_Time,Current(A),Voltage(V)\n00:00:00,0.001,3.5\n00:01:00,0.001,3.6\n61,0.001,3.7\n")
    prof = _simple_profile(bindings={"test_time_second": Binding(source=("Test_Time",), source_unit="hh:mm:ss"),
                                     "current_ampere": Binding(source=("Current",)),
                                     "voltage_volt": Binding(source=("Voltage",))})
    tab = read(p, prof)
    assert tab.t[:2].tolist() == [0.0, 60.0] and np.isnan(tab.t[2])
    secs = _simple_profile(bindings={"test_time_second": Binding(source=("Test_Time",), source_unit="s"),
                                     "current_ampere": Binding(source=("Current",)),
                                     "voltage_volt": Binding(source=("Voltage",))})
    with pytest.raises(ImportFailure, match="column_mostly_unreadable"):
        read(p, secs)


def test_excel_time_cells_past_one_day_are_elapsed_seconds(tmp_path):
    """openpyxl returns a time-formatted cell as a time of day, a time span, or a 1900 date
    depending on its format and size; all three are the same elapsed time. Excel's fictitious
    29 February 1900 makes 59 to 61 days ambiguous, so such a cell is invalid, not a day out."""
    import datetime as dt
    from electrochem.readers.cells import excel_cell_text, parse_duration
    assert parse_duration(excel_cell_text(dt.time(3, 51, 50))) == 13910.0
    assert parse_duration(excel_cell_text(dt.datetime(1900, 1, 1, 0, 0, 0, 900000))) == pytest.approx(86400.9)
    assert parse_duration(excel_cell_text(dt.timedelta(days=2, seconds=5))) == 172805.0
    assert parse_duration(excel_cell_text(dt.datetime(1900, 2, 28, 12))) is None
    assert excel_cell_text(dt.datetime(2024, 2, 29, 9, 20, 29)) == "2024-02-29 09:20:29"


def test_interleaved_tables_are_refused_by_the_reader_and_the_proposer(tmp_path):
    """Neware's hierarchical CSV writes cycle, step and record rows into one table; a record header
    with nameless leading columns that only some rows fill gives it away."""
    p = tmp_path / "hier.csv"
    p.write_text("Cycle Index,Chg. Cap.(Ah),DChg. Cap.(Ah),Chg. Energy(Wh),DChg. Energy(Wh)\n"
                 ",Step Index,Step Number,Step Type,Step Time,Capacity(Ah),Energy(Wh)\n"
                 ",,Test_Time,Current,Voltage,Capacity(Ah),Energy(Wh)\n"
                 "1,0.02,0.01,0.07,0.03\n"
                 ",1,1,Rest,00:00:20,0.0,0.0\n"
                 ",,0,0.0,3.5,0.0,0.0\n,,10,0.0,3.5,0.0,0.0\n"
                 ",2,2,CC Chg,00:02:51,0.02,0.07\n"
                 ",,20,0.5,3.6,0.001,0.004\n,,30,0.5,3.7,0.002,0.008\n,,40,0.5,3.8,0.003,0.011\n")
    prof = _simple_profile(layout=Layout(kind="delimited", delimiter=",", header_contains=("Test_Time",)))
    with pytest.raises(ImportFailure, match="interleaved_tables"):
        read(p, prof)
    pr = propose.propose(p)
    assert not pr.ready and any("interleaves several tables" in b for b in pr.blocking)


def test_empty_fields_after_the_last_header_name_are_dropped_but_values_there_refuse(tmp_path):
    p = tmp_path / "trail.csv"
    p.write_text("Test_Time,Current,Voltage\n0,0.001,3.5,\n60,0.001,3.6,\n")
    prof = _simple_profile(bindings={"test_time_second": Binding(source=("Test_Time",), source_unit="s"),
                                     "current_ampere": Binding(source=("Current",), source_unit="A"),
                                     "voltage_volt": Binding(source=("Voltage",), source_unit="V")})
    tab = read(p, prof)
    assert tab.n == 2 and any(f["code"] == "trailing_delimiter_in_rows" for f in tab.findings)
    p.write_text("Test_Time,Current,Voltage\n0,0.001,3.5,9\n60,0.001,3.6,\n")
    with pytest.raises(ImportFailure, match="rows_wider_than_header"):
        read(p, prof)


def test_a_vocabulary_that_names_no_cv_stage_builds_no_mode_array(files):
    """Maccor's State gives direction only: no CC/CV split may be reported for it (the engine would
    otherwise report 0 % constant voltage for a charge ending in a hold)."""
    from electrochem.readers import to_table
    tab = to_table(read(files["maccor"], MACCOR_TXT), MACCOR_TXT)
    assert tab.mode is None
    with_cv = MACCOR_TXT.model_copy(update={"conventions": MACCOR_TXT.conventions.model_copy(
        update={"step_type_map": {**MACCOR_TXT.conventions.step_type_map, "CV": "cv_charge"}})})
    assert to_table(read(files["maccor"], with_cv), with_cv).mode is not None


def test_the_voltage_trend_flags_a_sign_declared_backwards(files):
    """Declaring discharge-positive on a charge-positive file makes the voltage fall under 'charge'
    in every step; the import warns."""
    flipped = ARBIN_CSV.model_copy(update={"conventions": ARBIN_CSV.conventions.model_copy(
        update={"current_sign": "discharge_positive"})})
    tab = read(files["arbin"], flipped)
    assert any(f["code"] == "current_sign_contradicts_voltage" for f in tab.warnings)
    assert read(files["arbin"], ARBIN_CSV).report["sign_vs_voltage"]["disagree"] == 0


def test_the_counter_is_not_compared_where_no_current_flows(tmp_path):
    p = tmp_path / "ocv.csv"
    p.write_text("Test_Time(s),Step_Index,Current(A),Voltage(V),Charge_Capacity(Ah),Discharge_Capacity(Ah)\n"
                 + "".join(f"{k * 60},1,{-1e-6 if k == 3 else 0.0},3.5,0,{1e-6 * k}\n" for k in range(10)))
    prof = _simple_profile(
        conventions=Conventions(current_sign="charge_positive", direction_source="current_sign",
                                capacity_semantics="test_cumulative", cycle_base=1, evidence="constructed for this test only"),
        bindings={"test_time_second": Binding(source=("Test_Time",)), "step_id": Binding(source=("Step_Index",)),
                  "current_ampere": Binding(source=("Current",)), "voltage_volt": Binding(source=("Voltage",)),
                  "charging_capacity_ah": Binding(source=("Charge_Capacity",)),
                  "discharging_capacity_ah": Binding(source=("Discharge_Capacity",))})
    tab = read(p, prof)
    codes = {f["code"] for f in tab.findings}
    assert "counter_not_compared" in codes and "counter_disagrees_with_integral" not in codes


def test_a_cycle_cumulative_declaration_is_consistent_with_one_cycle_and_refused_when_contradicted(files, tmp_path):
    """A counter that never falls in a one-cycle file is consistent with cycle-cumulative; a counter
    that carries a non-zero value across a cycle boundary is not."""
    tab = read(files["arbin"], ARBIN_CSV)
    assert tab.report["capacity_semantics_consistent"] == ["cycle_cumulative", "test_cumulative"]
    assert not tab.report["capacity_semantics_verified"]
    # make the last two steps cycle 2 without resetting the counters: contradicts cycle-cumulative
    k = col(files["arbin"], "Cycle_Index")
    s = col(files["arbin"], "Step_Index")
    dst = edit_csv(files["arbin"], tmp_path / "two_cycles.csv", rows=lambda r: ",".join(
        ("2" if (j == k and int(r.split(",")[s]) >= 3) else c) for j, c in enumerate(r.split(","))))
    with pytest.raises(ImportFailure, match="capacity_semantics_mismatch"):
        read(dst, ARBIN_CSV)


def test_a_maccor_throughput_counter_takes_its_direction_from_the_current(files):
    """One unsigned counter for both directions: charge on charge rows, discharge on discharge rows,
    and the totals equal the known answer."""
    tab = read(files["maccor"], MACCOR_TXT)
    assert tab.report["capacity_semantics_verified"]
    assert float(tab.dq[tab.dq > 0].sum()) == pytest.approx(fixtures.TRUE_Q_CHARGE_AH, rel=1e-9)
    assert float(-tab.dq[tab.dq < 0].sum()) == pytest.approx(fixtures.TRUE_Q_DISCHARGE_AH, rel=1e-9)
    assert np.all(np.sign(tab.dq[tab.dq != 0]) == np.sign(tab.i[tab.dq != 0]))


def test_a_headerless_sheet_that_looks_like_more_records_is_warned_about(tmp_path):
    """Landt writes continuation sheets without a header row (P08 trap 6). Without a real
    multi-sheet Landt file the rows are not appended on a guess; the import warns instead."""
    from openpyxl import Workbook
    from electrochem.readers.builtin import LANDT_XLSX
    wb = Workbook()
    ws = wb.active
    ws.title = "Record"
    ws.append(["Index", "TestTime/h", "StepTime/h", "Voltage/V", "Current/mA", "Capacity/mAh", "State"])
    for k in range(1, 11):
        ws.append([k, k * 0.01, k * 0.01, 3.0 + 0.01 * k, 0.1, 0.001 * k, "C_CC"])
    more = wb.create_sheet("Record1")
    for k in range(11, 21):
        more.append([k, k * 0.01, k * 0.01, 3.0 + 0.01 * k, 0.1, 0.001 * k, "C_CC"])
    p = tmp_path / "landt.xlsx"
    wb.save(p)
    tab = read(p, LANDT_XLSX)
    assert tab.n == 10
    assert any(f["code"] == "headerless_sheet_not_read" for f in tab.warnings)
