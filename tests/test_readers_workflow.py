"""The profile readers behind the workflow: EC-Lab files keep the validated path, other instruments
go through a profile, an unknown file yields a proposal, and the module graph keeps the two apart."""
import ast
import json
from pathlib import Path

import numpy as np
import pytest

from electrochem import workflow
from electrochem.cycling import Settings
from electrochem.readers import BUILTIN, Conventions, Registry, confirm, is_eclab, looks_tabular
from tests import reader_fixtures as fixtures

ROOT = Path(__file__).resolve().parents[1]
CB5 = ROOT / "data" / "public" / "mpt" / "020-formation_CB5.mpt"
CB5_MPR = ROOT / "data" / "public" / "mpr" / "020-formation_CB5.mpr"
DEMO = ROOT / "data" / "demo" / "cyclara_demo_synthetic.mpt"


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("ELECTROCHEM_PROFILES", str(tmp_path / "profiles"))
    return tmp_path / "profiles"


def test_eclab_files_are_recognised_by_their_signature_not_their_extension(tmp_path):
    assert is_eclab(CB5) and is_eclab(CB5_MPR) and is_eclab(DEMO)
    renamed = tmp_path / "export.txt"
    renamed.write_bytes(CB5.read_bytes())
    assert is_eclab(renamed)                                  # an EC-Lab export with another extension
    bom = tmp_path / "bom.mpt"
    bom.write_bytes(b"\xef\xbb\xbf" + CB5.read_bytes())
    assert is_eclab(bom)
    other = tmp_path / "cell.mpt"
    other.write_text("Test_Time(s),Current(A),Voltage(V)\n0,0,3\n")
    assert not is_eclab(other)                                # the extension alone proves nothing


def test_eclab_files_still_take_the_validated_path(profiles):
    L = workflow.open_file(CB5)
    assert L.proposal is None and L.tab.format == "mpt" and "import_report" not in L.meta
    assert L.tab.labels["current"] == "I/mA"
    M = workflow.open_file(CB5_MPR)
    assert M.tab.format == "mpr"


@pytest.mark.parametrize("name,writer,profile", [("cell.csv", fixtures.write_arbin_like, "arbin-csv"),
                                                 ("cell.xlsx", fixtures.write_neware_like, "neware-xlsx"),
                                                 ("cell.txt", fixtures.write_maccor_like, "maccor-txt")])
def test_a_recognised_instrument_gives_the_engine_the_known_capacities(tmp_path, profiles, name, writer, profile):
    """The fixture's truth: 1.0 mAh charged, 0.5 mAh discharged, whatever the dialect."""
    p = writer(tmp_path / name)
    L = workflow.open_file(p)
    assert L.proposal is None and L.meta["profile"] == profile
    assert L.tab.format == profile and L.tab.i is not None and L.tab.e is not None
    run = workflow.analyse_file(L, Settings(charge="ox", terminal_voltage=True))
    q = {b.direction: b.charge_mAh for b in run.an.branches}
    assert q["charge"] == pytest.approx(1.0, rel=1e-9) and q["discharge"] == pytest.approx(0.5, rel=1e-9)
    assert np.all(np.isfinite(L.tab.t)) and L.meta["import_report"]["current_sign_applied"] == "charge_positive"


def test_an_unknown_instrument_yields_a_proposal_and_is_learned_once(tmp_path, profiles):
    p = tmp_path / "strange.csv"
    p.write_text("Elapsed Time(s),Amps(A),Volts(V),Cycle Index,Step Index\n" + "\n".join(
        f"{k * 60},{0.001 if k < 60 else -0.001},{3.5 + 0.001 * k},1,{1 if k < 60 else 2}" for k in range(120)) + "\n")
    L = workflow.open_file(p)
    assert L.tab is None and L.proposal is not None
    prop = L.proposal
    assert {"test_time_second", "current_ampere", "voltage_volt"} <= set(prop.chosen)
    assert prop.ready                                         # a signed current: nothing blocks, one confirmation asked
    conv = Conventions(current_sign="charge_positive", direction_source="current_sign", capacity_semantics="none",
                       cycle_base=1, evidence="confirmed in the test against the writer's own numbers")
    confirm(prop, name="strange-csv", instrument="Strange cycler", conventions=conv, registry=Registry(profiles))
    assert (profiles / "strange-csv.json").exists()
    again = workflow.open_file(p)                             # recognised by its header fingerprint now
    assert again.proposal is None and again.meta["profile"] == "strange-csv"
    run = workflow.analyse_file(again, Settings(charge="ox", terminal_voltage=True))
    q = {b.direction: b.charge_mAh for b in run.an.branches}
    assert q["charge"] == pytest.approx(0.001 * 59 * 60 / 3.6, rel=1e-9)


def test_a_profile_can_be_named_or_given_as_a_file(tmp_path, profiles):
    p = fixtures.write_arbin_like(tmp_path / "cell.csv")
    assert workflow.open_file(p, profile="arbin-csv").meta["profile"] == "arbin-csv"
    reg = Registry(profiles)
    saved = reg.save(BUILTIN["arbin-csv"], ["Test_Time(s)"], "cell.csv")
    assert workflow.open_file(p, profile=saved).meta["profile"] == "arbin-csv"


def test_readers_and_engine_never_import_each_other():
    """The blast radius of a new instrument is zero: readers see no engine, the engine sees no reader.
    Only workflow (the front door) and the bridge (which builds the engine's Table) connect them."""
    def imports(path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                out.add((node.level, node.module or ""))
            elif isinstance(node, ast.Import):
                out.update((0, a.name) for a in node.names)
        return out
    engine = ("segment", "cycling", "differential", "plotting", "origin_export", "metadata", "table")
    for f in (ROOT / "electrochem" / "readers").glob("*.py"):
        if f.name == "bridge.py":
            continue
        for level, mod in imports(f):
            assert not (level >= 2 or mod.startswith("electrochem.")), f"{f.name} imports the engine: {mod}"
    for name in engine:
        for level, mod in imports(ROOT / "electrochem" / f"{name}.py"):
            assert "readers" not in mod, f"{name}.py imports the readers"


def test_the_folder_screen_keeps_tables_and_drops_notes(tmp_path):
    """looks_tabular is the cheap screen behind opening a folder: it must keep every kind of
    measurement file and leave notes, logs and binaries alone."""
    assert looks_tabular(CB5) and looks_tabular(DEMO)
    assert looks_tabular(fixtures.write_arbin_like(tmp_path / "a.csv"))
    assert looks_tabular(fixtures.write_neware_like(tmp_path / "n.xlsx"))
    assert looks_tabular(fixtures.write_maccor_like(tmp_path / "m.txt"))
    notes = tmp_path / "notes.txt"
    notes.write_text("cell 3 was weighed twice\nthe second value is the right one\n")
    assert not looks_tabular(notes)
    (tmp_path / "x").write_bytes(b"x")
    assert not looks_tabular(tmp_path / "x")
    assert not looks_tabular(tmp_path / "missing.txt")
    binary = tmp_path / "data.bin"
    binary.write_bytes(bytes(range(256)) * 16)
    assert not looks_tabular(binary)


def test_a_file_from_another_cycler_exports_the_origin_folder_too(tmp_path, profiles):
    """The Origin export (tables in Origin's import layout, the build script, the graph spec) is made
    from the engine's results, so it is the same for an Arbin file as for an EC-Lab one."""
    p = ROOT / "data" / "public" / "arbin" / "arbin_example.csv"       # three complete cycles (TRI, Apache-2.0)
    L = workflow.open_file(p)
    run = workflow.analyse_file(L, Settings(charge="ox", terminal_voltage=True))
    out = tmp_path / "out"
    record = workflow.export(run, out, workflow.ExportOptions(origin=True))
    origin = out / "origin"
    for name in ("build_origin_project.py", "origin_spec.json", "cycles.csv", "branches.csv",
                 "curves_potential_capacity_wide.csv", "dqde_wide.csv", "overview_time.csv", "README.txt"):
        assert (origin / name).exists(), name
    spec = json.loads((origin / "origin_spec.json").read_text())
    assert spec["cell"] == "arbin_example.csv" and spec["potential_label_title"] == "Cell voltage (V)"
    assert spec["capacity_unit"] == "mAh" and spec["n_cycles"] >= 1
    head = (origin / "cycles.csv").read_text().splitlines()[:3]
    assert len(head) == 3 and "mAh" in head[1]                      # Long Name, Units, Comments rows for Origin
    assert record["import"]["profile"]["name"] == "arbin-res-table-csv"   # settings.json carries the profile that read it
    assert "Set up the Origin link" in (origin / "README.txt").read_text()
