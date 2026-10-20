"""The LANHE (LAND) .cex reader (electrochem/readers/lanhe_cex.py) on synthetic files whose every number is
known by construction (tests/cex_synthetic.py). No real file is used: the real file the format was
established on is private, and its regression check lives beside it, outside the repository."""
import json
import struct
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import cex_synthetic as cs  # noqa: E402

from electrochem import workflow  # noqa: E402
from electrochem.cycling import Settings  # noqa: E402
from electrochem.readers import ImportFailure, is_cex, lanhe_cex, native_table  # noqa: E402


def read(path):
    """The reader's RawTable made into the engine's Table by the bridge, as workflow.open_file does."""
    raw, meta = lanhe_cex.read(path)
    assert raw.profile == "lanhe-cex" and raw.n == len(raw.t) and len(raw.step_kind) == raw.n
    return native_table(raw), meta


def write(tmp_path, steps=None, name="run.cex", **kw):
    blob, truth = cs.write(steps if steps is not None else cs.two_cycles(), **kw)
    p = tmp_path / name
    p.write_bytes(blob)
    return p, truth


def refused(path, code):
    with pytest.raises(ImportFailure) as info:
        lanhe_cex.read(path)
    assert info.value.code == code, str(info.value)
    return str(info.value)


def codes(meta, severity=None):
    return {f["code"] for f in meta["import_findings"] if severity is None or f["severity"] == severity}


# ------------------------------------------------------------------------------------------------ decoding
def test_every_record_decodes_to_what_was_written(tmp_path):
    p, tr = write(tmp_path)
    tab, meta = read(p)
    assert tab.n == len(tr.t) == 1794
    assert np.allclose(tab.t, tr.t, rtol=0, atol=1e-9)
    assert np.array_equal(tab.e, np.array(tr.v)) and np.array_equal(tab.i, np.array(tr.i))
    assert np.array_equal(tab.ns, np.array(tr.step, float))
    kinds = [s.kind for s in cs.two_cycles()]
    want_mode = {"rest": 3, "cc_charge": 1, "cc_discharge": 1, "cv_charge": 2}
    assert [int(tab.mode[tab.ns == k][0]) for k in range(1, 10)] == [want_mode[k] for k in kinds]
    assert tab.format == "lanhe-cex" and tab.source_sha256 and tab.cycle is None and tab.q_instrument is None
    rep = meta["import_report"]["cex"]
    assert rep["counter_starts"] == {"reset": 4, "carried": 1, "other": 0}
    assert rep["step_types"] == {"rest": 4, "cc_charge": 2, "cv_charge": 1, "cc_discharge": 2}
    assert [e["event"] for e in rep["status_events"]] == ["start", "end"]
    assert [b["type"] for b in rep["blocks"]] == [0xAA, 0x55, 0x78, 0x13]
    assert meta["import_profile"]["voltage_full_scale_V"] == 5.0
    assert meta["import_profile"]["current_full_scale_A"] == pytest.approx(1e-3, rel=1e-15)
    assert meta["import_profile"]["voltage_range_verified"] and meta["import_profile"]["current_range_verified"]
    assert not codes(meta, "warn")
    # constant current and a voltage linear in time: over the intervals after each step's first, the integrals of
    # the decoded current and power equal the counters to float32 precision (the first interval holds the gap)
    sc = rep["scale_check"]
    assert abs(sc["current_ratio"] - 1) < 1e-6 and abs(sc["voltage_ratio"] - 1) < 1e-5


def test_the_scales_are_the_ranges_over_32256_counts(tmp_path):
    """One count is a 32256th of the range: 5 V and 1 mA for the verified codes. A step at 16128 counts runs at
    half the current range, 0.5 mA, and its charge over an hour follows."""
    p, tr = write(tmp_path)
    tab, _ = read(p)
    cc = tab.ns == 2
    assert np.all(tab.i[cc] == 0.5e-3)
    assert tab.e[cc][-1] == pytest.approx(4.10, abs=0.5 * 5 / 32256)


def test_the_counters_give_the_charge_each_step_passed_gap_included(tmp_path):
    """Per step, the increments sum to the charge since the step started on the tester's side: the first
    increment of a step carries the interval between the previous step's last record and its first."""
    p, tr = write(tmp_path)
    tab, _ = read(p)
    signs = [cs.SIGN[s.kind] for s in cs.two_cycles()]
    for k, (q, sgn) in enumerate(zip(tr.charge, signs), start=1):
        assert np.sum(tab.dq[tab.ns == k]) / 3600 == pytest.approx(sgn * q, rel=1e-6, abs=1e-15)
    # the interval before the first record is in the counter and not in the records: GAP at 0.5 mA
    assert tr.charge[1] - tr.charge_records[1] == pytest.approx(0.5e-3 * cs.GAP / 3600, rel=1e-9)


def test_a_constant_voltage_step_carries_the_counters_on(tmp_path):
    p, tr = write(tmp_path)
    tab, meta = read(p)
    steps = meta["instrument_steps"]
    assert [s["counter_start"] for s in steps][:3] == ["rest", "reset", "carried"]
    first_cv = int(np.flatnonzero(tab.ns == 3)[0])
    assert tab.dq[first_cv] == 0.0                         # carried: no increment across the boundary
    assert steps[2]["capacity_end_Ah"] == pytest.approx(tr.charge[1] + tr.charge[2], rel=1e-6)
    assert steps[2]["type"] == "cv_charge" and steps[2]["setpoint_unit"] == "V"
    assert steps[2]["setpoint"] == pytest.approx(4.10, abs=0.5 * 5 / 32256)
    assert steps[1]["setpoint"] == pytest.approx(0.5e-3) and steps[4]["setpoint"] == pytest.approx(-0.5e-3)


def test_the_tester_step_table_is_rebuilt(tmp_path):
    p, tr = write(tmp_path)
    _, meta = read(p)
    rows = meta["instrument_steps"]
    assert [r["step"] for r in rows] == list(range(1, 10)) and [r["tester_step"] for r in rows] == list(range(1, 10))
    assert [r["records"] for r in rows] == [tr.step.count(k) for k in range(1, 10)]
    assert rows[0]["start_unix_s"] == cs.START and rows[0]["start_clock"] == "2023-11-14 22:13:20"
    assert rows[4]["capacity_end_Ah"] == pytest.approx(tr.q_end[4], rel=0, abs=0)


# ------------------------------------------------------------------------------------- the whole workflow
def test_cyclara_capacities_equal_the_constructed_ones(tmp_path):
    p, tr = write(tmp_path)
    loaded = workflow.open_file(p)
    assert loaded.meta["profile"] == "lanhe-cex" and loaded.proposal is None
    run = workflow.analyse_file(loaded, Settings(charge="ox", terminal_voltage=True))
    br = run.an.branches
    assert [b.direction for b in br] == ["charge", "discharge", "charge", "discharge"]
    want = [tr.charge[1] + tr.charge[2], tr.charge[4], tr.charge[6], tr.charge[7]]
    for b, q in zip(br, want):
        assert b.charge_mAh == pytest.approx(q * 1e3, rel=1e-6)
    assert br[0].charge_cv_mAh == pytest.approx(tr.charge[2] * 1e3, rel=1e-6)
    cyc = run.an.cycles
    assert [c.complete for c in cyc] == [True, True]
    assert cyc[0].coulombic_efficiency_pct == pytest.approx(100 * tr.charge[4] / (tr.charge[1] + tr.charge[2]), rel=1e-6)
    assert br[1].energy_mWh == pytest.approx(tr.energy[4] * 1e3, rel=2e-4)     # mean edge voltage times dq


def test_the_export_carries_the_reader_and_the_step_table(tmp_path):
    p, tr = write(tmp_path)
    loaded = workflow.open_file(p)
    run = workflow.analyse_file(loaded, Settings(charge="ox", terminal_voltage=True))
    out = tmp_path / "out"
    rec = workflow.export(run, out, workflow.ExportOptions(plots=set(), origin=False))
    assert rec["import"]["profile"]["name"] == "lanhe-cex"
    assert rec["import"]["steps_table"] == "instrument_steps.csv"
    assert rec["import"]["report"]["cex"]["scale_check"]["current_passed"] is True
    lines = (out / "instrument_steps.csv").read_text().splitlines()
    assert len(lines) == 1 + 9 and lines[0].startswith("step,tester_step,type,")
    meta = json.loads((out / "metadata.json").read_text())["declared_in_header"]
    assert "instrument_steps" not in meta and meta["profile"] == "lanhe-cex"


def test_a_declared_mass_is_offered_not_applied(tmp_path):
    p, _ = write(tmp_path, mass_g=0.0123)
    loaded = workflow.open_file(p)
    assert loaded.declared_mass_mg == pytest.approx(12.3, rel=1e-6)
    run = workflow.analyse_file(loaded, Settings(charge="ox", terminal_voltage=True))
    assert run.settings.active_mass_mg is None and run.an.branches[0].specific_capacity_mAh_g is None
    p0, _ = write(tmp_path, name="nomass.cex")
    assert workflow.open_file(p0).declared_mass_mg is None


def test_the_signature_decides_not_the_extension(tmp_path):
    p, _ = write(tmp_path, name="run.bin")
    assert is_cex(p) and workflow.open_file(p).meta["profile"] == "lanhe-cex"
    other = tmp_path / "other.cex"
    other.write_bytes(b"\x01\x02\x03\x04" + bytes(200))
    with pytest.raises(ImportFailure) as info:
        workflow.open_file(other)
    assert info.value.code == "cex_signature" and "Export the run as .csv, .txt or .xlsx" in str(info.value)
    empty = tmp_path / "empty.cex"
    empty.write_bytes(b"")
    with pytest.raises(ImportFailure) as info:
        workflow.open_file(empty)
    assert info.value.code == "empty_file"


# ------------------------------------------------------------------------- the scales checked on every file
def test_a_header_whose_range_disagrees_with_its_data_is_refused(tmp_path):
    """Counts written for a 1 mA range under a header that says 2 mA (0xC014): the decoded current is twice the
    tester's own counter, and the reader says so instead of reading it."""
    p, _ = write(tmp_path, i_code=0xC014)
    msg = refused(p, "cex_scale_check")
    assert "current ratio 2.0000" in msg and "voltage ratio 1.0000" in msg      # the voltage is still right
    p, _ = write(tmp_path, name="v.cex", v_code=0xE00A)
    msg = refused(p, "cex_scale_check")
    assert "voltage ratio 2.0000" in msg


def test_an_unverified_range_confirmed_by_the_counters_is_read(tmp_path):
    p, tr = write(tmp_path, i_fs=2e-3, i_code=0xC014)
    tab, meta = read(p)
    assert np.array_equal(tab.i, np.array(tr.i)) and tab.i.max() == pytest.approx(1e-3)    # 16128 counts of 2 mA
    sc = meta["import_report"]["cex"]["scale_check"]
    assert sc["current_passed"] and not sc["current_range_verified"]
    assert "cex_range_confirmed" in codes(meta, "note")


def test_a_check_that_cannot_be_made_is_said(tmp_path):
    short = [cs.Step("rest", 0.0), cs.Step("cc_charge", 25.0, every=1.0, counts=8064, v0=3.30, v1=3.50),
             cs.Step("cc_discharge", 25.0, every=1.0, counts=8064, v0=3.50, v1=3.30), cs.Step("rest", 2.0, every=1.0)]
    p, _ = write(tmp_path, short, name="short.cex")              # every step start within a minute: no clock slope
    _, meta = read(p)
    notes = codes(meta, "note")
    assert "cex_clock_not_checked" in notes and "cex_voltage_not_checked" not in notes
    assert meta["import_report"]["cex"]["scale_check"]["current_passed"] is True
    below = [cs.Step("rest", 0.0, v0=-0.30), cs.Step("cc_charge", 3600.0, counts=8064, v0=-0.50, v1=-0.10),
             cs.Step("cc_discharge", 3000.0, counts=8064, v0=-0.10, v1=-0.60), cs.Step("rest", 600.0, every=60.0,
                                                                                      v0=-0.40)]
    p, _ = write(tmp_path, below, name="below.cex")              # no positive voltage: no energy check
    _, meta = read(p)
    notes = codes(meta, "note")
    assert "cex_voltage_not_checked" in notes and "cex_clock_not_checked" not in notes
    sc = meta["import_report"]["cex"]["scale_check"]
    assert sc["current_passed"] is True and sc["voltage_passed"] is None


def test_an_unverified_range_without_current_to_confirm_it_is_refused(tmp_path):
    rest_only = [cs.Step("rest", 0.0), cs.Step("rest", 600.0, every=60.0)]
    p, _ = write(tmp_path, rest_only, i_fs=2e-3, i_code=0xC014)
    refused(p, "cex_range_unverified")
    p, _ = write(tmp_path, rest_only, name="known.cex")                     # verified codes: read, and said
    _, meta = read(p)
    assert "cex_scale_not_checked" in codes(meta, "note")


@pytest.mark.parametrize("v_code,i_code", [(0xD005, 0xC00A), (0xE005, 0xA00A), (0xE000, 0xC00A)])
def test_a_range_code_of_no_known_family_is_refused(tmp_path, v_code, i_code):
    p, _ = write(tmp_path, v_code=v_code, i_code=i_code)
    refused(p, "cex_range_unverified")


def test_a_record_time_in_another_unit_is_refused(tmp_path):
    """Written in milliseconds, the record time runs ten times faster than the step-start clock."""
    p, _ = write(tmp_path, time_unit=0.001)
    assert "times the tester's clock" in refused(p, "cex_time_base")


# --------------------------------------------------------------------------- what has not been seen: refused
def test_another_layout_is_refused(tmp_path):
    blob, _ = cs.write(cs.two_cycles())
    for layout in (b"\x01\x00\x04\x00", b"\x02\x01\x01\x00"):
        p = tmp_path / f"l{layout[0]}.cex"
        p.write_bytes(blob[:4] + layout + blob[8:])
        assert "07 00 04 00" in refused(p, "cex_layout")


def test_an_unknown_step_type_is_refused(tmp_path):
    steps = cs.two_cycles()
    steps[4] = replace(steps[4], type_code=0x04)
    p, _ = write(tmp_path, steps)
    assert "0x04" in refused(p, "cex_step_unverified")


def test_a_pause_or_alarm_event_is_refused(tmp_path):
    blob, _ = cs.write(cs.two_cycles())
    at = int(cs.records_of(blob)[100])
    blob = blob[:at] + cs.control(0x33, 0x0203, cs.START + 500) + blob[at:]
    p = tmp_path / "paused.cex"
    p.write_bytes(blob)
    assert "pause" in refused(p, "cex_event_unverified")


def test_an_unknown_control_unit_is_refused_and_retention_units_are_skipped(tmp_path):
    blob, _ = cs.write(cs.two_cycles())
    at = int(cs.records_of(blob)[50])
    p = tmp_path / "unknown.cex"
    p.write_bytes(blob[:at] + cs.control(0x23) + blob[at:])
    refused(p, "cex_control_unverified")
    p = tmp_path / "references.cex"
    p.write_bytes(blob[:at] + cs.control(0xB1, 1, 2) + cs.control(0xB2, 3, 4) + blob[at:])
    tab, meta = read(p)
    assert tab.n == 1794 and "cex_retention_references" in codes(meta, "note")


def test_a_damaged_block_or_unit_is_refused(tmp_path):
    blob, _ = cs.write(cs.two_cycles())
    bad = bytearray(blob)
    struct.pack_into("<I", bad, 64 + 16 + 64, 0)                # the first block's end unit
    p = tmp_path / "block.cex"
    p.write_bytes(bytes(bad))
    refused(p, "cex_block")
    at = int(cs.records_of(blob)[10])
    bad = bytearray(blob)
    struct.pack_into("<I", bad, at, 0xFFFF1234)
    p = tmp_path / "unit.cex"
    p.write_bytes(bytes(bad))
    refused(p, "cex_unit")


def edit_record(tmp_path, name, k, **fields):
    blob, _ = cs.write(cs.two_cycles())
    at = int(cs.records_of(blob)[k])
    t, v, i, q, w = struct.unpack_from("<Ihhff", blob, at)
    vals = {"t": t, "v": v, "i": i, "q": q, "w": w}
    vals.update(fields)
    bad = bytearray(blob)
    struct.pack_into("<Ihhff", bad, at, vals["t"], vals["v"], vals["i"], vals["q"], vals["w"])
    p = tmp_path / name
    p.write_bytes(bytes(bad))
    return p, vals, (t, v, i, q, w)


def test_time_going_backwards_is_refused(tmp_path):
    p, _, _ = edit_record(tmp_path, "back.cex", 200, t=10)
    refused(p, "cex_time_backwards")


def test_a_decreasing_counter_is_refused(tmp_path):
    p, _, old = edit_record(tmp_path, "drop.cex", 200, q=0.0)
    assert old[3] > 0
    refused(p, "cex_counter_decreases")


def test_current_against_its_step_type_is_refused(tmp_path):
    blob, _ = cs.write(cs.two_cycles())
    bad = bytearray(blob)
    for at in cs.records_of(blob):
        t, v, i, q, w = struct.unpack_from("<Ihhff", bad, int(at))
        if 0 < t < 360000 and i > 0:                            # the first charge: current reversed
            struct.pack_into("<Ihhff", bad, int(at), t, v, -i, q, w)
    p = tmp_path / "reversed.cex"
    p.write_bytes(bytes(bad))
    refused(p, "sign_contradicts_step_type")


def test_records_before_the_first_step_and_no_records_are_refused(tmp_path):
    blob, _ = cs.write(cs.two_cycles())
    pre = cs.header() + cs.preamble()
    p = tmp_path / "early.cex"
    p.write_bytes(pre + cs.record(0, 20000, 0, 0.0, 0.0) + blob[len(pre):])
    refused(p, "cex_records_before_step")
    p = tmp_path / "settings_only.cex"
    p.write_bytes(pre + cs.control(0x33, 0x0201, cs.START))
    refused(p, "no_data")


# ------------------------------------------------------------------------------------ reported, then read
def test_a_file_copied_mid_test_is_read_with_a_warning(tmp_path):
    blob, tr = cs.write(cs.two_cycles(), end_event=False)
    p = tmp_path / "running.cex"
    p.write_bytes(blob + b"\x01\x02\x03\x04\x05")
    tab, meta = read(p)
    assert tab.n == len(tr.t)
    assert "cex_truncated_tail" in codes(meta, "warn") and "cex_no_end_event" in codes(meta, "note")


def test_a_clipped_reading_and_an_odd_counter_start_are_warned(tmp_path):
    p, _, _ = edit_record(tmp_path, "clipped.cex", 300, v=32767)
    _, meta = read(p)
    assert "cex_saturated" in codes(meta, "warn")
    blob, tr = cs.write(cs.two_cycles())
    first_discharge = int(cs.records_of(blob)[tr.step.index(5)])
    t, v, i, q, w = struct.unpack_from("<Ihhff", blob, first_discharge)
    assert q == 0.0
    bad = bytearray(blob)
    struct.pack_into("<Ihhff", bad, first_discharge, t, v, i, 1e-9, w)
    p = tmp_path / "start.cex"
    p.write_bytes(bytes(bad))
    _, meta = read(p)
    assert "cex_counter_start" in codes(meta, "warn")
    assert meta["instrument_steps"][4]["counter_start"] == "other"


def test_the_refusals_are_shown_in_the_app_as_written(tmp_path):
    pytest.importorskip("PySide6")
    from electrochem.studio.worker import friendly
    p, _ = write(tmp_path, i_code=0xC014)
    with pytest.raises(ImportFailure) as info:
        workflow.open_file(p)
    assert friendly(info.value) == str(info.value)
