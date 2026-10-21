"""The LANHE (LAND) .cex reader (electrochem/readers/lanhe_cex.py) on synthetic files whose every number is
known by construction (tests/cex_synthetic.py). No real file is used: the real file the format was
established on is private, and its regression check lives beside it, outside the repository."""
import json
import re
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
    for layout in (b"\x01\x00\x04\x00", b"\x02\x01\x01\x00", b"\x06\x00\x04\x00"):
        p = tmp_path / f"l{layout[0]}.cex"
        p.write_bytes(blob[:4] + layout + blob[8:])
        msg = refused(p, "cex_layout")
        assert "07 00 04 00" in msg and "05 00 04 00" in msg


def test_an_unknown_step_type_is_refused(tmp_path):
    steps = cs.two_cycles()
    steps[4] = replace(steps[4], type_code=0x04)
    p, _ = write(tmp_path, steps)
    assert "0x04" in refused(p, "cex_step_unverified")


def test_an_unknown_status_event_is_refused(tmp_path):
    blob, _ = cs.write(cs.two_cycles())
    at = int(cs.records_of(blob)[100])
    p = tmp_path / "event.cex"
    p.write_bytes(blob[:at] + cs.status(0x0999, cs.START + 500, parameter=3) + blob[at:])
    assert "0x00030999" in refused(p, "cex_event_unverified")


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


# -------------------------------------------------------------- pauses, restarts and the other status events
LAYOUT_05 = b"\x05\x00\x04\x00"
DISCHARGE = 4                                       # index of the first discharge in cs.two_cycles()


def analysed(p):
    return workflow.analyse_file(workflow.open_file(p), Settings(charge="ox", terminal_voltage=True))


def with_step(k, **fields):
    steps = cs.two_cycles()
    steps[k] = replace(steps[k], **fields)
    return steps


def status_offsets(blob, code):
    """Byte offsets of the status events of one code, outside blocks."""
    out, k = [], 64
    while k + 16 <= len(blob):
        w0, w1, w2, _ = struct.unpack_from("<4I", blob, k)
        if w0 == cs.BLOCK:
            k += 16 + (w1 >> 16) + 16
            continue
        if w0 == cs.CTRL and w1 & 0xFFFF == 0x33 and w2 & 0xFFFF == code:
            out.append(k)
        k += 16
    return out


def test_the_second_layout_reads_as_the_first(tmp_path):
    """Layout 05 00 04 00 has the units and records of 07 00 04 00 (each verified on a real file): one run written
    under either code reads to the same table and findings, and only the layout reported differs."""
    p7, _ = write(tmp_path, name="l7.cex")
    p5, _ = write(tmp_path, name="l5.cex", layout=LAYOUT_05)
    (t7, m7), (t5, m5) = read(p7), read(p5)
    for name in ("t", "e", "i", "dq", "ns", "mode"):
        assert np.array_equal(getattr(t7, name), getattr(t5, name)), name
    assert m5["import_findings"] == m7["import_findings"]
    assert m5["import_report"]["cex"]["layout"] == m5["import_profile"]["layout"] == "05 00 04 00"
    assert m7["import_report"]["cex"]["layout"] == m7["import_profile"]["layout"] == "07 00 04 00"


def test_a_pause_is_read_and_the_clock_check_counts_it(tmp_path):
    """The record time does not count a pause, so the records are those of the same run without it; the clock
    check adds the pause back (resume minus pause, from the events) and then finds nothing to report."""
    steps = cs.two_cycles()
    steps[1] = replace(steps[1], pause=(1000.0, 5400))          # 1.5 h of clock inside the first charge
    steps[7] = replace(steps[7], pause=(2500.0, 600))
    edit = cs.status(0x0402, 0) + cs.block(0x13, bytes(64))      # a step plan edited during the second pause
    p, tr = write(tmp_path, steps, inserts={(7, 250): edit})
    p0, tr0 = write(tmp_path, name="plain.cex")
    (tab, meta), (tab0, meta0) = read(p), read(p0)
    assert tr.t == tr0.t and tab.n == tab0.n == 1794
    for name in ("t", "e", "i", "dq", "ns", "mode"):
        assert np.array_equal(getattr(tab, name), getattr(tab0, name)), name
    rep = meta["import_report"]["cex"]
    assert [(x["step"], x["clock_s"]) for x in rep["pauses"]] == [(2, 5400), (8, 600)] and rep["restarts"] == []
    tc = rep["time_check"]
    assert tc["pauses_and_restarts"] == 2 and tc["time_not_counted_s"] == 6000 and tc["disagreement"] is None
    assert abs(tc["slope"] - 1) < 1e-4
    assert not codes(meta, "warn") and {"cex_pauses", "cex_other_events"} <= codes(meta, "note")
    assert "paused 5400 s on the tester's clock" in meta["instrument_steps"][1]["notes"]
    assert "step plan edited (0x0402) event before record" in meta["instrument_steps"][7]["notes"]
    assert [b["type"] for b in rep["blocks"]].count(0xCC) == 2 and [b["type"] for b in rep["blocks"]].count(0x13) == 2
    assert rep["other_events"] == {"resume detail (0x1008)": 2, "resume detail (0x1012)": 2,
                                   "resume detail (0x100e)": 2, "step plan edited (0x0402)": 1}
    run, run0 = analysed(p), analysed(p0)
    assert [c.coulombic_efficiency_pct for c in run.an.cycles] == [c.coulombic_efficiency_pct for c in run0.an.cycles]
    assert [c.capacity_retention_pct for c in run.an.cycles] == [c.capacity_retention_pct for c in run0.an.cycles]
    assert [c.complete for c in run.an.cycles] == [True, True]
    # the potential relaxes during a pause: a branch paused partway has no dQ/dE, and its cycle's note says so
    assert list(tab.paused) == [k - 1 for k in (x["record"] for x in rep["pauses"])]
    assert [b.pauses for b in run.seg.branches] == [1, 0, 0, 1]
    assert [(c, cv.branch) for c, cv in run.dqde_curves([1, 2])] == [(1, 2), (2, 3)]
    assert [(c, cv.branch) for c, cv in run0.dqde_curves([1, 2])] == [(1, 1), (1, 2), (2, 3), (2, 4)]
    assert run.an.cycles[0].note == ("the charge branch 1 has no dQ/dE (paused partway, and the potential relaxes "
                                     "while the current is off)")
    from electrochem import methods_text
    text = methods_text.paragraph(methods_text.Context(settings=run.settings, run=run, profile_name="lanhe-cex"))
    assert ("2 branches were paused partway by the instrument; they keep their capacities and efficiencies, but no "
            "dQ/dE was calculated for them, because the potential relaxes while the current is off.") in text


def test_a_pause_the_file_does_not_mark_is_reported(tmp_path):
    """Without its events, a pause is still on the clock: the step starts after it are 5400 s later than the
    record time says, and the reader says between which steps."""
    blob, _ = cs.write(with_step(1, pause=(1000.0, 5400)))
    at = status_offsets(blob, 0x0802)[0]
    cut = 16 + (16 + 32 + 16) + 4 * 16                           # the pause, its block, the resume and its details
    assert struct.unpack_from("<I", blob, at + cut - 16 * 4 + 8)[0] & 0xFFFF == 0x0203
    p = tmp_path / "unmarked.cex"
    p.write_bytes(blob[:at] + blob[at + cut:])
    _, meta = read(p)
    warn = [f for f in meta["import_findings"] if f["code"] == "cex_clock_offset"]
    assert len(warn) == 1 and warn[0]["detail"]["between_steps"] == [2, 3]
    said = re.search(r"the tester's clock advanced ([0-9.]+) s more than the record time", warn[0]["message"])
    assert said and abs(float(said.group(1)) - 5400) <= 1.0          # the clock reads whole seconds


def test_periodic_events_are_noted_and_change_nothing(tmp_path):
    p, _ = write(tmp_path, periodic=1800)
    p0, _ = write(tmp_path, name="plain.cex")
    (tab, meta), (tab0, _) = read(p), read(p0)
    assert np.array_equal(tab.t, tab0.t) and np.array_equal(tab.dq, tab0.dq)
    n = meta["import_report"]["cex"]["other_events"]["periodic (0x1013)"]
    assert n == int(tab.t[-1] // 1800) and not codes(meta, "warn")


def test_a_restart_keeps_every_record_and_the_charge_the_counter_left_out(tmp_path):
    """Stopped 1490 s into the first discharge and resumed two hours later with the state of 30 s before: the
    record time and the counter go back 30 s, the three records of those seconds stay, and the charge they carry,
    which the tester's own counter left out, stays in the capacity. The branch is partial: no efficiency for its
    cycle, no dQ/dE for it; the second cycle is untouched."""
    p, tr = write(tmp_path, with_step(DISCHARGE, restart=(1495.0, 30.0, 7200)))
    tab, meta = read(p)
    assert tab.n == len(tr.t) == 1794 + 4                        # the stop's record and the three replayed
    warn = [f for f in meta["import_findings"] if f["code"] == "cex_restart"]
    assert len(warn) == 1 and warn[0]["severity"] == "warn"
    d = warn[0]["detail"]
    assert d["step"] == 5 and d["rollback_s"] == pytest.approx(30.0, abs=1e-6) and d["rollback_records"] == 3
    assert d["clock_s"] == 7230 and d["counter_drop_Ah"] == pytest.approx(tr.kept[DISCHARGE], rel=1e-6)
    assert "time_goes_backwards" not in codes(meta)              # reported once, with its cause
    tc = meta["import_report"]["cex"]["time_check"]
    assert tc["time_not_counted_s"] == 7230 and tc["disagreement"] is None
    k = d["record"] - 1                                          # the first record after the restart
    assert tab.t[k] == pytest.approx(tab.t[k - 1] - 30.0) and tab.dq[k] == 0.0
    assert np.sum(tab.dq[tab.ns == 5]) / 3600 == pytest.approx(-(tr.charge[DISCHARGE] + tr.kept[DISCHARGE]), rel=1e-6)

    run = analysed(p)
    br = run.an.branches
    assert [b.unsupported_edges for b in run.seg.branches] == [0, 1, 0, 0]
    assert [b.complete for b in br] == [True, False, True, True]
    assert br[1].charge_mAh == pytest.approx((tr.charge[DISCHARGE] + tr.kept[DISCHARGE]) * 1e3, rel=1e-6)
    c1, c2 = run.an.cycles
    assert not c1.complete and c1.coulombic_efficiency_pct is None and c1.discharge_capacity_mAh == br[1].charge_mAh
    assert c1.note == ("incomplete pair: the discharge branch 2 has 1 interval that is not integrated (settings.json "
                       "lists each interval and why), so this pair has no efficiency or retention; the discharge "
                       "branch 2 has no dQ/dE (time reset or invalid time inside it)")
    assert c2.complete and c2.coulombic_efficiency_pct == pytest.approx(100 * tr.charge[7] / tr.charge[6], rel=1e-6)
    # cycle 1 is the reference cycle by default: being incomplete, it gives no cycle a retention, and the summary says so
    assert c2.capacity_retention_pct is None and run.an.summary.retention_at_last_cycle_pct is None
    assert run.an.summary.notes == ("cycle 1 incomplete and excluded from the summary; the reference cycle, 1, is not a "
                                    "complete cycle of this file, so no retention is given; choose another reference "
                                    "cycle")
    run2 = workflow.analyse_file(workflow.open_file(p), Settings(charge="ox", terminal_voltage=True, reference_cycle=2))
    assert run2.an.cycles[1].capacity_retention_pct == pytest.approx(100.0)
    assert run2.an.summary.notes == "cycle 1 incomplete and excluded from the summary"
    assert [(c, cv.branch) for c, cv in run.dqde_curves([1, 2])] == [(1, 1), (2, 3), (2, 4)]
    assert "stopped after record" in meta["instrument_steps"][4]["notes"]
    from electrochem import methods_text
    text = methods_text.paragraph(methods_text.Context(settings=run.settings, run=run, profile_name="lanhe-cex"))
    assert ("1 branch contained an interval where the time went back, the current was missing or the instrument "
            "flagged an error; its capacity is given over the integrated intervals, but its cycle has no coulombic "
            "efficiency or retention and the branch no dQ/dE.") in text
    out = tmp_path / "out"
    rec = workflow.export(run, out, workflow.ExportOptions(plots=set(), origin=False))
    assert "none for a branch with a curve break" in rec["methods"]["dqde"]
    assert rec["import"]["report"]["cex"]["restarts"][0]["rollback_records"] == 3
    rows = (out / "cycles.csv").read_text().splitlines()
    assert "the discharge branch 2 has 1 interval that is not integrated" in rows[1]


@pytest.mark.parametrize("restarts,want,kept_s", [
    ([(795.0, 20.0, 600), (1995.0, 10.0, 300)], [(2, 620), (1, 310)], 30),
    ([(795.0, 20.0, 600), (785.0, 5.0, 300)], [(2, 620), (1, 305)], 25),
    ([(795.0, 100.0, 600), (715.0, 15.0, 300)], [(10, 700), (2, 315)], 115),
])
def test_two_restarts_in_one_step_are_each_checked(tmp_path, restarts, want, kept_s):
    """The second restart is checked against the records since the first, also when the moment it restores lies
    in the seconds the first one replayed, which are then recorded twice (the second and third cases)."""
    p, tr = write(tmp_path, with_step(DISCHARGE, restart=restarts))
    tab, meta = read(p)
    warn = [f["detail"] for f in meta["import_findings"] if f["code"] == "cex_restart"]
    assert [(d["rollback_records"], d["clock_s"]) for d in warn] == want
    tc = meta["import_report"]["cex"]["time_check"]
    assert tc["time_not_counted_s"] == sum(w[1] for w in want) and tc["disagreement"] is None
    assert tc["places_disagreeing"] == 0
    assert np.sum(tab.dq[tab.ns == 5]) / 3600 == pytest.approx(-(tr.charge[DISCHARGE] + tr.kept[DISCHARGE]), rel=1e-6)
    assert tr.kept[DISCHARGE] == pytest.approx(0.5e-3 * kept_s / 3600, rel=1e-9)   # at 0.5 mA in all
    assert [b.unsupported_edges for b in analysed(p).seg.branches] == [0, 2, 0, 0]


def test_a_restart_in_a_rest_is_read(tmp_path):
    p, _ = write(tmp_path, with_step(3, restart=(300.0, 120.0, 900)))
    _, meta = read(p)
    warn = [f for f in meta["import_findings"] if f["code"] == "cex_restart"]
    assert len(warn) == 1 and "the step is a rest" in warn[0]["message"]
    assert [c.complete for c in analysed(p).an.cycles] == [True, True]


@pytest.mark.parametrize("why", ["too far back", "counter of another moment", "records go forward",
                                 "records go forward in a rest", "across steps"])
def test_a_restart_unlike_the_ones_verified_is_refused(tmp_path, why):
    if why == "too far back":
        blob, _ = cs.write(with_step(DISCHARGE, restart=(1495.0, 130.0, 600)))
    elif why == "counter of another moment":
        blob, tr = cs.write(with_step(DISCHARGE, restart=(1495.0, 30.0, 600)))
        at = status_offsets(blob, 0x0803)[0] + 16 * 5               # the stop, the resume and its details
        t, v, i, q, w = struct.unpack_from("<Ihhff", blob, at)
        bad = bytearray(blob)
        struct.pack_into("<Ihhff", bad, at, t, v, i, q * 0.9, w)     # not the counter of the moment restored
        blob = bytes(bad)
    elif why == "records go forward":
        blob, _ = cs.write(cs.two_cycles(), inserts={(DISCHARGE, 100): cs.status(0x0803, cs.START + 9000)
                                                     + cs.resume_units(cs.START + 9600)})
    elif why == "records go forward in a rest":                   # counters at zero: only the time can tell
        blob, _ = cs.write(cs.two_cycles(), inserts={(3, 5): cs.status(0x0803, cs.START + 5700)
                                                     + cs.resume_units(cs.START + 5700)})
    else:
        blob, _ = cs.write(cs.two_cycles(), inserts={(DISCHARGE, 0): cs.status(0x0803, cs.START + 9000)
                                                     + cs.resume_units(cs.START + 9600)})
    p = tmp_path / "restart.cex"
    p.write_bytes(blob)
    assert "the records do not go back to an earlier state" in refused(p, "cex_restart_unverified")


@pytest.mark.parametrize("units,expect", [
    ("resume", "follows no pause or stop"),
    ("detail", "is not where a resume is"),
    ("pause then records", "records lie between"),
    ("pause never resumed", "without a resume event"),
    ("pause inside a pause", "was resumed"),
])
def test_events_out_of_their_verified_order_are_refused(tmp_path, units, expect):
    c = cs.START + 9000
    put = {"resume": {(DISCHARGE, 100): cs.resume_units(c)},
           "detail": {(DISCHARGE, 100): cs.status(0x1012, 0)},
           "pause then records": {(DISCHARGE, 100): cs.status(0x0802, c), (DISCHARGE, 102): cs.resume_units(c + 60)},
           "pause never resumed": {(DISCHARGE, 100): cs.status(0x0802, c)},
           "pause inside a pause": {(DISCHARGE, 100): cs.status(0x0802, c) + cs.status(0x0802, c + 5)
                                    + cs.resume_units(c + 60)}}[units]
    p, _ = write(tmp_path, inserts=put)
    assert expect in refused(p, "cex_event_break")


def test_an_event_where_the_records_break_is_refused(tmp_path):
    """An event after which the records were found to continue, at a gap of 200 s in a step logged every 10 s:
    what it means there has not been established. The same gap without the event is read."""
    for name, event in (("event.cex", cs.status(0x0404, cs.START + 9000)), ("plain.cex", b"")):
        blob, tr = cs.write(cs.two_cycles(), inserts={(DISCHARGE, 100): event} if event else None)
        offs = cs.records_of(blob)
        first = int(np.flatnonzero(np.array(tr.step) == 5)[0])
        a, b = int(offs[first + 100]), int(offs[first + 120])         # the 20 records after the event
        p = tmp_path / name
        p.write_bytes(blob[:a] + blob[b:])
        if event:
            assert "the records break at the status 0x0404 event" in refused(p, "cex_event_break")
        else:
            assert read(p)[0].n == len(tr.t) - 20


def test_an_event_where_the_counter_falls_is_refused_as_a_break(tmp_path):
    blob, tr = cs.write(cs.two_cycles(), inserts={(DISCHARGE, 100): cs.status(0x2001, cs.START + 9000)})
    k = int(np.flatnonzero(np.array(tr.step) == 5)[0]) + 100            # the record after the event
    at = int(cs.records_of(blob)[k])
    t, v, i, q, w = struct.unpack_from("<Ihhff", blob, at)
    bad = bytearray(blob)
    struct.pack_into("<Ihhff", bad, at, t, v, i, q * 0.5, w)
    p = tmp_path / "fall.cex"
    p.write_bytes(bytes(bad))
    assert "the records break at the status 0x2001 event" in refused(p, "cex_event_break")


def test_the_clock_check_allows_for_whole_seconds(tmp_path):
    """Steps 60.2 s apart in record time: on a clock that reads whole seconds, one interval in five spans 61 s
    and differs from the record time by 0.8 s, 1.3 %. That is the clock's resolution, not a disagreement."""
    steps = [cs.Step("rest", 0.0)] + [cs.Step("cc_charge" if k % 2 == 0 else "cc_discharge", 60.0, every=10.0,
                                              counts=8064, v0=3.4, v1=3.6 if k % 2 == 0 else 3.4) for k in range(40)]
    steps.append(cs.Step("rest", 60.0, v0=3.4))
    p, _ = write(tmp_path, steps, name="short_steps.cex")
    _, meta = read(p)
    tc = meta["import_report"]["cex"]["time_check"]
    assert tc["intervals"] >= 30 and tc["intervals_agreeing"] == tc["intervals"] and tc["disagreement"] is None


def test_a_restart_that_does_not_go_back_is_refused(tmp_path):
    """Records going on after a stop from exactly the last state (0 s back) were never seen: the interval across
    it would be a zero-duration one, which is not a curve break, so a fold could reach the dQ/dE unannounced."""
    blob, _ = cs.write(with_step(DISCHARGE, restart=(1495.0, 0.0, 600)))
    p = tmp_path / "zero.cex"
    p.write_bytes(blob)
    assert "more than 0 s and at most 120 s back" in refused(p, "cex_restart_unverified")


def test_records_missing_after_a_pause_are_refused(tmp_path):
    """After the pauses seen the records continue; 20 records missing after one (a 210 s jump in a step logged
    every 10 s) are refused like a break at any other event."""
    blob, tr = cs.write(with_step(1, pause=(1000.0, 600)))
    first = int(np.flatnonzero(np.array(tr.step) == 2)[0])
    j = first + next(k for k, t in enumerate(tr.t[first:]) if t - tr.t[first - 1] >= 1000.0)    # after the pause
    offs = cs.records_of(blob)
    p = tmp_path / "missing.cex"
    p.write_bytes(blob[:int(offs[j])] + blob[int(offs[j + 20]):])
    assert "the records break at the pause" in refused(p, "cex_event_break")


def test_an_event_in_a_short_step_is_judged_by_the_files_logging_interval(tmp_path):
    """A step of 10.5 s logged every 10 s has intervals of 10 s and 0.5 s; an event in its first interval is
    where the records continue, by the file's usual 10 s interval."""
    steps = cs.two_cycles()[:5] + [cs.Step("cc_discharge", 10.5, counts=8064, v0=3.6, v1=3.5)] + cs.two_cycles()[5:]
    p, tr = write(tmp_path, steps, inserts={(5, 1): cs.status(0x1013, cs.START + 9000)})
    tab, meta = read(p)
    assert tab.n == len(tr.t) and meta["import_report"]["cex"]["other_events_where"]["inside_steps"] == \
        {"periodic (0x1013)": 1}


def test_pauses_at_either_end_of_the_records_are_read_and_stops_refused(tmp_path):
    steps = cs.two_cycles()
    steps[0] = replace(steps[0], pause=(-1.0, 900))                  # before the first record of the test
    p, _ = write(tmp_path, steps)
    tab, meta = read(p)
    rep = meta["import_report"]["cex"]
    assert [(x["where"], x["clock_s"]) for x in rep["pauses"]] == [("before the first record", 900)]
    assert rep["time_check"]["time_not_counted_s"] == 900 and rep["time_check"]["disagreement"] is None
    assert tab.paused is not None and len(tab.paused) == 0           # no branch is paused partway
    blob, tr = cs.write(cs.two_cycles(), end_event=False)
    end = cs.START + 30000
    tail = cs.status(0x0802, end) + cs.block(0xCC, bytes(32)) + cs.resume_units(end + 60)
    p = tmp_path / "after.cex"
    p.write_bytes(blob + tail)
    _, meta = read(p)
    assert [x["where"] for x in meta["import_report"]["cex"]["pauses"]] == ["after the last record"]
    p = tmp_path / "stop_after.cex"
    p.write_bytes(blob + cs.status(0x0803, end) + cs.resume_units(end + 60))
    assert "after the last record" in refused(p, "cex_restart_unverified")


def test_events_at_a_step_boundary_are_listed_not_checked(tmp_path):
    p, _ = write(tmp_path, inserts={(DISCHARGE, 0): cs.status(0x2004, cs.START + 9000)})
    _, meta = read(p)
    where = meta["import_report"]["cex"]["other_events_where"]
    assert where == {"inside_steps": {}, "elsewhere": {"status 0x2004": 1}, "with_resumes": {}}
    note = next(f["message"] for f in meta["import_findings"] if f["code"] == "cex_other_events")
    assert "at a step boundary, before the first record or after the last, listed only: status 0x2004 x1" in note


def test_the_scale_check_says_when_restarts_left_it_without_intervals(tmp_path):
    steps = cs.two_cycles()
    for k, at in ((1, 1795.0), (2, 895.0), (4, 1495.0), (6, 1595.0), (7, 2995.0)):    # every step that carries current
        steps[k] = replace(steps[k], restart=(at, 30.0, 600))
    p, _ = write(tmp_path, steps)
    _, meta = read(p)
    note = next(f["message"] for f in meta["import_findings"] if f["code"] == "cex_scale_not_checked")
    assert "once its 5 step(s) with a restart are left out" in note
    assert "outside its steps with a restart, which are left out" in meta["profile_evidence"]


def test_a_file_that_ends_in_a_pause_is_read_with_a_note(tmp_path):
    blob, tr = cs.write(cs.two_cycles(), end_event=False)
    p = tmp_path / "paused.cex"
    p.write_bytes(blob + cs.status(0x0802, cs.START + 30000) + cs.block(0xCC, bytes(32)))
    tab, meta = read(p)
    assert tab.n == len(tr.t) and {"cex_ends_paused", "cex_no_end_event"} <= codes(meta, "note")
    note = next(f["message"] for f in meta["import_findings"] if f["code"] == "cex_ends_paused")
    assert note.startswith("the file ends in a pause (event at byte")
    p = tmp_path / "stopped.cex"
    p.write_bytes(blob + cs.status(0x0803, cs.START + 30000))
    _, meta = read(p)
    note = next(f["message"] for f in meta["import_findings"] if f["code"] == "cex_ends_paused")
    assert note.startswith("the file ends in a stop (event at byte")


def test_a_clock_behind_the_record_time_is_reported_as_a_clock_change(tmp_path):
    """The tester's clock set back 300 s before the fifth step: from the fourth step's start to the fifth's, the
    record time advanced 300 s more than the clock. A pause the file does not mark cannot do that (it makes the
    clock run ahead), so the warning names a change of the clock only."""
    blob, _ = cs.write(cs.two_cycles())
    k, found = 64, 0
    bad = bytearray(blob)
    while k + 16 <= len(blob):                                          # every step start from the fifth on
        w0, w1, w2, w3 = struct.unpack_from("<4I", blob, k)
        if w0 == cs.BLOCK:
            k += 16 + (w1 >> 16) + 16
            continue
        if w0 == cs.CTRL_STEP and w1 & 0xFFFF == 0x22:
            found += 1
            if found >= 5:
                struct.pack_into("<I", bad, k + 12, w3 - 300)
        k += 16
    p = tmp_path / "early.cex"
    p.write_bytes(bytes(bad))
    _, meta = read(p)
    warn = next(f for f in meta["import_findings"] if f["code"] == "cex_clock_offset")
    assert warn["detail"]["between_steps"] == [4, 5] and warn["detail"]["places_disagreeing"] == 1
    assert "the record time advanced" in warn["message"] and "(a change of the clock)" in warn["message"]
    assert "pause" not in warn["message"].split("beyond the pauses and restarts the file marks")[1]


def test_only_a_pause_inside_a_branch_stops_its_dqde(tmp_path):
    """A pause right before a charge's first record (after a rest) is not inside the charge branch, whose curve it
    cannot fold: the branch keeps its dQ/dE. A pause right before a branch's last record is inside it."""
    steps = cs.two_cycles()
    steps[1] = replace(steps[1], pause=(-1.0, 300))                 # before the first record of the first charge
    steps[4] = replace(steps[4], pause=(2999.0, 300))               # before the last record of the first discharge
    p, tr = write(tmp_path, steps)
    tab, meta = read(p)
    run = analysed(p)
    firsts = [x["record"] - 1 for x in meta["import_report"]["cex"]["pauses"]]
    assert firsts[0] == tr.step.index(2) and firsts[1] == len(tr.step) - 1 - tr.step[::-1].index(5)
    assert [b.pauses for b in run.seg.branches] == [0, 1, 0, 0]
    assert [cv.branch for _, cv in run.dqde_curves([1, 2])] == [1, 3, 4]
