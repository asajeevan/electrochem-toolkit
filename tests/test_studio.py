"""The desktop app and the workflow layer it shares with the command line.

Run offscreen. Each test names the rule it protects; several reproduce a defect
found while building the app, and fail if the fix is removed.
"""
import json
import os
import re
import time
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
pg = pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QEvent, QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from electrochem import workflow
from electrochem.cycling import Settings
from electrochem.studio import theme
from electrochem.studio.model import Answers, Record, open_questions, parse_number, settings_for
from electrochem.studio.strip import compress

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "public" / "mpt" / "020-formation_CB5.mpt"
STORE = "electrochem-studio-pytest"


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    theme.load_fonts()
    theme.apply(a, theme.LIGHT)
    from electrochem.studio.motion import Motion
    Motion.mode = "off"            # results are checked, not animations: those have their own tests
    return a


def pump(app, timeout=60.0, quiet=0.25):
    """Process events until no background job has run for `quiet` seconds.

    A result handler can start another job (an answer given during an analysis);
    returning at the first idle moment could miss that job's result (independent
    review, finding r30: a flaky test). The pool must stay idle for a whole quiet
    period while events keep being processed."""
    end = time.time() + timeout
    idle_since, passes = None, 0
    while time.time() < end:
        app.processEvents()
        if QThreadPool.globalInstance().activeThreadCount() == 0:
            idle_since = idle_since or time.time()
            passes += 1
            if time.time() - idle_since >= quiet and passes >= 3:
                app.processEvents()               # a result posted during the last pass may start another job
                if QThreadPool.globalInstance().activeThreadCount() == 0:
                    return
                idle_since, passes = None, 0
        else:
            idle_since, passes = None, 0
        time.sleep(0.01)
    raise TimeoutError("background work did not finish")


@pytest.fixture
def win(app):
    """A fresh settings store per test: a window from an earlier test can write its
    remembered answers back when it is garbage-collected, after any clear()."""
    import uuid
    store = f"{STORE}-{uuid.uuid4().hex[:8]}"
    from electrochem.studio.app import MainWindow
    w = MainWindow(store=store)
    w.resize(1500, 950)
    w.show()
    yield w
    w.close()
    w.settings.clear(); w.settings.sync()
    w.deleteLater()
    # processEvents() does not run deferred deletions outside an event loop: without this, every
    # window stays alive and each later style change re-polishes all of them (minutes, not seconds)
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def opened(win, app, answers=()):
    win.open_paths([DATA])
    pump(app)
    for a in answers:
        win._answer(a)
        pump(app)
    return win.rec


FULL = ({"charge": "ox"}, {"configuration": "full"}, {"mass_mg": 10.0})


# ------------------------------------------------------------------ workflow

def test_command_line_and_workflow_write_identical_tables(tmp_path):
    """The command line runs on the workflow layer; its tables equal an engine run done by hand."""
    from electrochem.analyze import main
    from electrochem.cycling import analyse, rows
    from electrochem.segment import segment
    from electrochem.table import load
    out = tmp_path / "cli"
    main([str(DATA), "--no-prompt", "--charge", "ox", "--terminal-voltage", "--mass-mg", "10", "--formats", "pdf",
          "--no-origin", "--out", str(out)])
    tab = load(DATA)
    s = Settings(charge="ox", terminal_voltage=True, active_mass_mg=10.0)
    an = analyse(tab, segment(tab, charge="ox", order=s.cycle_order, rest_current_a=0.0), s)
    workflow.write_csv(tmp_path / "cycles.csv", rows(an.cycles))
    assert (out / "cycles.csv").read_bytes() == (tmp_path / "cycles.csv").read_bytes()
    record = json.loads((out / "settings.json").read_text())
    assert all(c["status"] != "fail" for cs in record["figure_checks"].values() for c in cs)


def test_cycle_lists_parse_ranges_negatives_and_steps():
    av = list(range(1, 51))
    assert workflow.parse_cycles("1, 2, 5:8, -1", av) == [1, 2, 5, 6, 7, 8, 50]
    assert workflow.parse_cycles("0:50:10", av) == [10, 20, 30, 40, 50]
    assert workflow.parse_cycles("-3:-1", av) == [48, 49, 50]
    assert workflow.parse_cycles("99, abc", av) == []
    assert compress([1, 2, 3, 4, 7, 9, 10, 11]) == "1:4, 7, 9:11"
    assert workflow.parse_cycles(compress([3, 4, 5, 9]), av) == [3, 4, 5, 9]


def test_a_mass_typed_with_a_decimal_comma_is_not_multiplied():
    """P12 review finding 2: '1,5' must be 1.5 mg, never 15 mg."""
    assert parse_number("1,5") == 1.5
    assert parse_number("4.817") == 4.817
    for bad in ("1,500.5", "1.500,5", "1.2.3", "abc"):
        with pytest.raises(ValueError):
            parse_number(bad)


def test_answers_map_to_settings_without_guessing():
    a = Answers()
    s = settings_for(a)
    assert s.charge is None and s.reference is None and not s.terminal_voltage and s.active_mass_mg is None
    a.configuration = "half"            # half-cell without a reference names nothing yet
    assert settings_for(a).reference is None
    a.reference = "Li+/Li"
    assert settings_for(a).reference == "Li+/Li" and settings_for(a).energy_allowed
    assert len(open_questions(Answers(), None)) == 3


# ------------------------------------------------------------------ the pyqtgraph axis defect

def test_axis_ticks_are_never_rescaled(app):
    """pyqtgraph 0.14 keeps an SI scale computed while autoSIPrefix is off: ticks of 60 and 80
    then read 60000 and 80000 with nothing to say so. Found in this app's screenshots."""
    for axes, expect in ((None, None), (theme.plain_axes(), ["60", "80"])):
        w = pg.PlotWidget(**({"axisItems": axes} if axes else {}))
        w.resize(400, 300); w.show()
        pi = w.getPlotItem()
        pi.setLabel("left", "Capacity (mAh)")
        pi.getAxis("left").enableAutoSIPrefix(False)
        item = pi.plot([0, 1], [0.3, 0.55]); app.processEvents()
        pi.getAxis("left").enableAutoSIPrefix(False)
        item.setData([0, 1], [50, 100]); pi.enableAutoRange(); app.processEvents()
        ax = pi.getAxis("left")
        got = ax.tickStrings([60.0, 80.0], ax.autoSIPrefixScale * ax.scale, 20)
        if expect is None:
            stock_defect = got != ["60", "80"]
        else:
            assert got == expect
        w.close()
    if not stock_defect:
        pytest.skip("this pyqtgraph no longer has the defect; plain_axes() is then a no-op")


def test_every_view_uses_axes_that_cannot_rescale(win, app):
    opened(win, app, FULL)
    from electrochem.studio.theme import plain_axes
    cls = type(plain_axes()["left"]).__name__
    plots = [p for v in win.views for p in getattr(v, "plots", [])]
    plots += [p for v in win.views[0].children_views for p in v.plots]
    assert plots and all(type(p.getPlotItem().getAxis("left")).__name__ == cls for p in plots)


# ------------------------------------------------------------------ the window

def test_nothing_is_analysed_as_cycles_until_the_direction_is_given(win, app):
    rec = opened(win, app)
    assert rec.run is not None and not rec.run.seg.pairs
    assert rec.state == "3 answers needed"
    assert win.views[0].raw.isVisibleTo(win.views[0]), "the overview shows the recorded data instead of empty axes"
    win._answer({"charge": "ox"}); pump(app)
    assert rec.run.seg.pairs and rec.run.settings.charge == "ox"


def test_the_header_mass_is_offered_never_applied(win, app):
    from electrochem.table import load
    rec = opened(win, app)
    assert rec.answers.mass_mg is None and rec.run.settings.active_mass_mg is None


def test_answers_change_results_and_undo_restores_them(win, app):
    rec = opened(win, app, FULL)
    assert rec.state == "ready to export" and rec.current
    first = rec.run.an.cycles[0].discharge_specific_mAh_g
    win._answer({"mass_mg": 20.0}); pump(app)
    assert rec.run.an.cycles[0].discharge_specific_mAh_g == pytest.approx(first / 2)
    win.undo.undo(); pump(app)
    assert rec.answers.mass_mg == 10.0 and rec.run.an.cycles[0].discharge_specific_mAh_g == pytest.approx(first)


def test_a_result_is_shown_only_for_the_answers_it_was_computed_from(win, app):
    rec = opened(win, app, FULL)
    rec.answers.mass_mg = 99.0                   # changed behind the analysis's back
    assert not rec.current and rec.state != "ready to export"
    win.request_analysis(rec); pump(app)
    assert rec.current and rec.run.settings.active_mass_mg == 99.0


def test_answers_given_during_an_analysis_are_not_dropped(win, app):
    """P12 review finding 1: the analysis that arrives must use the latest answers."""
    win.open_paths([DATA]); pump(app)
    rec = win.rec
    win._answer({"charge": "ox"})
    win._answer({"configuration": "full"})
    win._answer({"mass_mg": 7.0})                # all three before any analysis returns
    pump(app)
    assert rec.current and rec.run.settings.active_mass_mg == 7.0 and rec.run.settings.charge == "ox"


def test_strip_selection_drives_every_view_and_the_figure_cycles(win, app):
    rec = opened(win, app, FULL)
    win.set_cycles_spec("2")
    assert rec.selected_cycles() == [2] and rec.focus_cycle == 2
    assert all(v.selected == [2] for v in win.views if hasattr(v, "selected") and v is not win.views[0])
    assert rec.run.selected == [2]
    win.set_cycles_spec("999")                   # nothing valid: the selection is kept
    assert rec.selected_cycles() == [2]


def test_withheld_values_say_why(win, app):
    rec = opened(win, app, ({"charge": "ox"},))
    from electrochem.studio.model import state_of
    st, why = state_of("average_charge_voltage_V", None, rec.answers)
    assert st == "withheld" and "potential column" in why
    st, why = state_of("discharge_specific_mAh_g", None, rec.answers)
    assert "mass" in why


def test_export_writes_a_new_folder_and_never_overwrites(win, app, tmp_path, monkeypatch):
    rec = opened(win, app, FULL)
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(tmp_path)))
    win.export(None); pump(app, 180)
    first = tmp_path / f"{DATA.stem}_analysis"
    assert (first / "cycles.csv").exists() and (first / "settings.json").exists() and (first / "activity.txt").exists()
    stamp = (first / "cycles.csv").stat().st_mtime_ns
    win.export(None); pump(app, 180)
    assert (tmp_path / f"{DATA.stem}_analysis_2" / "cycles.csv").exists()
    assert (first / "cycles.csv").stat().st_mtime_ns == stamp
    rec_json = json.loads((first / "settings.json").read_text())
    assert rec_json["plotted_cycles"] == rec.selected_cycles()


def test_a_file_that_cannot_be_read_says_so_in_words(win, app, tmp_path):
    bad = tmp_path / "empty.mpt"
    bad.write_bytes(b"")
    win.open_paths([bad]); pump(app)
    rec = win.records[-1]
    assert rec.error and rec.state == "could not be read"
    assert "Traceback" not in rec.error


def test_a_folder_prefers_the_native_file(tmp_path):
    from electrochem.studio.app import MainWindow
    for n in ("run_C01.mpr", "run_C01.mpt", "other.mpt", "notes.txt"):
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "log.txt").write_text("Started the run at 09:00\nChanged the clamp at 10:15\n")
    (tmp_path / "cycler.csv").write_text("Test_Time(s),Current(A),Voltage(V)\n0,0.001,3.5\n1,0.001,3.6\n2,0.001,3.7\n")
    skipped = []
    got = [p.name for p in MainWindow.expand([tmp_path], skipped)]
    assert got == ["run_C01.mpr", "cycler.csv", "other.mpt"]       # a notes file and a log are left alone
    assert any("notes.txt" in s for s in skipped) and any("log.txt" in s for s in skipped)
    assert [p.name for p in MainWindow.expand([tmp_path / "notes.txt"])] == ["notes.txt"]   # chosen by hand: opened


def test_theme_contrast(app):
    from electrochem.plotting import contrast
    for t in (theme.LIGHT, theme.DARK):
        for text in (t.ink, t.secondary, t.muted, t.provisional, t.withheld, t.error, t.selection_text):
            for surface in (t.window, t.panel, t.view):
                assert contrast(text, surface) >= 4.5, (t.name, text, surface)
        for c in theme.ramp(7, t):
            assert contrast(c.name(), t.view) >= 3.0, (t.name, c.name())
        assert contrast(t.selection, t.view) >= 3.0 and contrast(t.focus, t.view) >= 3.0


def test_no_em_dash_in_interface_text():
    src = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "electrochem" / "studio").glob("*.py"))
    assert "\u2014" not in src


def test_theme_switch_keeps_the_record(win, app):
    rec = opened(win, app, FULL)
    win.toggle_theme(); pump(app)
    assert theme.tokens().name == "dark" and win.rec is rec and rec.current
    win.toggle_theme(); pump(app)
    assert theme.tokens().name == "light"


def test_a_windowed_launch_keeps_a_log(tmp_path, monkeypatch):
    """pythonw, Cyclara.exe and the macOS bundle give Python no console: what would have been printed,
    and any crash, must land in a file in the user's own folder, and Help > Show the error log opens it."""
    import sys
    from electrochem.studio import platform_support as ps
    monkeypatch.setattr(ps, "log_path", lambda: tmp_path / "logs" / "cyclara.log")
    assert ps.keep_a_log(["x"]) is None                     # a console is present: nothing changes
    out, err = sys.stdout, sys.stderr
    try:
        sys.stdout = None; sys.stderr = None
        path = ps.keep_a_log(["cyclara", "--no-intro"])
        assert path == tmp_path / "logs" / "cyclara.log" and path.exists()
        print("hello from a window program")
        sys.stdout.flush()
        text = path.read_text(encoding="utf-8")
        assert "Cyclara started" in text and "--no-intro" in text and "hello from a window program" in text
        assert sys.stderr is sys.stdout
        import faulthandler
        assert faulthandler.is_enabled()
    finally:
        sys.stdout, sys.stderr = out, err
        import faulthandler
        faulthandler.disable()


def test_the_demonstration_is_one_click_away(win, app):
    from electrochem.studio.app import DEMO_FILE
    assert DEMO_FILE.exists() and win.empty.b3.isVisible() or not DEMO_FILE.exists()
    assert "demo" in win.act and win.act["demo"].text().startswith("Open the demonstration")
    win.open_demo(); pump(app, 180)
    rec = win.records[-1]
    assert rec.loaded is not None and rec.loaded.tab is not None and Path(rec.path) == DEMO_FILE
    assert "Try the demonstration" in win.empty.b3.text()
    texts = [w.text() for w in win.empty.findChildren(QtWidgets.QLabel)]
    assert any("Drop a cycling file" in t for t in texts) and any("Arbin" in t for t in texts)   # not EC-Lab only


def test_the_self_check_runs_the_suite_in_a_separate_process(win, app, tmp_path, monkeypatch):
    """Help > Check this installation starts the installed interpreter on the test folder and reads the
    outcome back; here the suite is a stand-in that prints pytest's own progress and summary lines."""
    import sys
    from electrochem.studio import app as A
    fake = tmp_path / "tests"
    fake.mkdir()
    (fake / "test_cycling.py").write_text("def test_one():\n    assert True\n")
    monkeypatch.setattr(A, "ROOT", tmp_path)
    dlg = A.SelfCheck(win)
    assert dlg.command[0] == sys.executable and dlg.command[1:4] == ["-I", "-X", "utf8"] and "pytest" in dlg.command
    dlg.command = [sys.executable, "-c",
                   "print('.' * 3 + '  [ 50%]'); print('.' * 3 + '  [100%]'); print('6 passed in 0.10s')"]
    dlg.start()
    end = time.time() + 30
    while dlg.close_btn.text() != "Close" and time.time() < end:
        app.processEvents(); time.sleep(0.02)
    assert dlg.head.text() == "Everything passed" and "6 passed" in dlg.text.text() and dlg.bar.value() == 100
    dlg.command = [sys.executable, "-c", "print('F.  [100%]'); print('1 failed, 1 passed in 0.1s'); raise SystemExit(1)"]
    dlg2 = A.SelfCheck(win); dlg2.command = dlg.command; dlg2.start()
    end = time.time() + 30
    while dlg2.close_btn.text() != "Close" and time.time() < end:
        app.processEvents(); time.sleep(0.02)
    assert dlg2.head.text() == "Something did not pass" and "1 failed" in dlg2.text.text()
    monkeypatch.setattr(A, "ROOT", tmp_path / "nowhere")
    dlg3 = A.SelfCheck(win); dlg3.start()
    assert dlg3.head.text() == "Could not check"
    for d in (dlg, dlg2, dlg3):
        d.close()


def test_the_origin_link_can_be_set_up_from_the_help_menu(win, app, monkeypatch):
    """Help > Set up the Origin link runs pip in Cyclara's own Python; the dialog reports the outcome in
    words. Here pip is a stand-in command; on a Mac the dialog says Origin is Windows-only."""
    import sys
    from electrochem.studio import app as A
    from electrochem.studio import platform_support as ps
    assert "origin_setup" in win.act and win.act["origin_setup"].text().startswith("Set up the Origin link")
    monkeypatch.setattr(ps, "IS_WINDOWS", True)
    dlg = A.OriginSetup(win)
    assert dlg.command[0] == sys.executable and dlg.command[-1] == "originpro" and "pip" in dlg.command
    dlg.command = [sys.executable, "-c", "print('Successfully installed originpro-1.1.11')"]
    dlg.start()
    end = time.time() + 30
    while dlg.close_btn.text() != "Close" and time.time() < end:
        app.processEvents(); time.sleep(0.02)
    assert dlg.head.text() == "The Origin link is ready" and "Build Origin project" in dlg.text.text()
    dlg2 = A.OriginSetup(win)
    dlg2.command = [sys.executable, "-c", "print('ERROR: Could not find a version'); raise SystemExit(1)"]
    dlg2.start()
    end = time.time() + 30
    while dlg2.close_btn.text() != "Close" and time.time() < end:
        app.processEvents(); time.sleep(0.02)
    assert dlg2.head.text() == "Could not install the Origin link" and "code 1" in dlg2.text.text()
    monkeypatch.setattr(ps, "IS_WINDOWS", False)
    monkeypatch.delenv("CYCLARA_ORIGIN_ANYWHERE", raising=False)
    dlg3 = A.OriginSetup(win); dlg3.start()
    assert dlg3.head.text() == "Not set up" and "Windows only" in dlg3.text.text()
    for d in (dlg, dlg2, dlg3):
        d.close()


def test_an_export_offers_the_origin_build_or_its_set_up(win, app, tmp_path, monkeypatch):
    """After an export the message offers 'Build Origin project' when originpro is available, and on
    Windows 'Set up Origin link' when it is not; a file from another cycler gets the Origin folder too."""
    from electrochem import origin_export
    from electrochem.studio import platform_support as ps
    from tests import reader_fixtures as fixtures
    monkeypatch.setenv("ELECTROCHEM_PROFILES", str(tmp_path / "profiles"))
    p = fixtures.write_neware_like(tmp_path / "cell.xlsx")
    win.open_paths([p]); pump(app)
    rec = win.rec
    assert rec.profile == "neware-xlsx"
    for a in ({"configuration": "full"}, {"no_mass": True, "mass_mg": None}):   # no open question: no modal box
        win._answer(a); pump(app)
    shown = []
    monkeypatch.setattr(win.toast, "show_message", lambda msg, actions=None: shown.append((msg, [a[0] for a in (actions or [])])))
    monkeypatch.setattr(origin_export, "_python_with_originpro", lambda: None)
    monkeypatch.setattr(ps, "IS_WINDOWS", True)
    monkeypatch.setattr(QtWidgets.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(tmp_path)))
    win.export(None); pump(app, 180)
    assert shown and "Set up Origin link" in shown[-1][1] and "Build Origin project" not in shown[-1][1]
    out = tmp_path / f"{p.stem}_analysis"
    assert (out / "origin" / "build_origin_project.py").exists() and (out / "origin" / "origin_spec.json").exists()
    monkeypatch.setattr(origin_export, "_python_with_originpro", lambda: ["python"])
    win.export(None); pump(app, 180)
    assert "Build Origin project" in shown[-1][1] and "Set up Origin link" not in shown[-1][1]


def test_help_cite_puts_the_citation_on_the_clipboard(win, app):
    """Help > Cite Cyclara: four forms, each copied as the citation module writes it."""
    from electrochem import citation
    assert "cite" in win.act and win.act["cite"].text().startswith("Cite")
    win.cite(); pump(app, 10)
    d = win._cite
    assert d.isVisible()
    forms = citation.all_forms()
    for k, name in enumerate(d.FORMS):
        d.tabs.setCurrentIndex(k); app.processEvents()
        d.copy_current(); app.processEvents()
        assert QApplication.clipboard().text() == forms[name] and forms[name].strip()
        assert d.copy.text() == "Copied"
    win.cite(); assert win._cite is d                         # a second call raises the same window
    d.close()


def test_the_methods_window_explains_every_number_with_the_files_settings(win, app):
    """Help > How the numbers are calculated: every topic renders, 'For this file' follows the answers of the
    open file and refreshes when they change, and the methods paragraph is written from the same settings."""
    from electrochem import citation, methods_text
    rec = opened(win, app, FULL)
    assert "methods" in win.act and win.act["methods"].text().startswith("How the numbers")
    win.methods_help("energy"); pump(app, 10)
    d = win._methods
    assert d.isVisible() and d.current_topic().key == "energy"
    text = d.browser.toPlainText()
    assert "For this file" in text and "cell voltage" in text and "capacity-weighted mean" in text
    assert "average charge potential" in text                  # a number of this file, not a template
    d.select("basis"); app.processEvents()
    assert "10 mg" in d.browser.toPlainText()
    for r in range(d.list.count()):
        d.list.setCurrentRow(r); app.processEvents()
        assert len(d.browser.toPlainText()) > 400, d.current_topic().key
    d.copy_explanation(); app.processEvents()
    assert QApplication.clipboard().text().endswith(citation.sentence())
    d.copy_paragraph(); app.processEvents()
    para = QApplication.clipboard().text()
    assert para == methods_text.paragraph(win.methods_context()) and "10 mg" in para and para.endswith(citation.plain())
    win._answer({"mass_mg": 20.0}); pump(app)                  # the open window follows the answers
    d.select("basis"); app.processEvents()
    assert "20 mg" in d.browser.toPlainText() and "20 mg" in d.paragraph_text()
    win.close_record(); pump(app)                              # no file: the general text, no 'For this file'
    assert win.rec is None and d.isVisible()
    assert "Open a file" in d.intro.text() and "For this file" not in d.browser.toPlainText()
    d.close()


def test_the_inspector_reports_the_plateaus_of_the_focused_cycle_in_factual_words(win, app, tmp_path):
    """On the synthetic multi-plateau cell: three pairs with their separation, the first-charge-only peak as
    'unpaired, no counterpart within 200 mV', never 'irreversible'; the block follows the focused cycle, and the
    Evolution view is one of the views."""
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    import plateau_cell
    from electrochem.studio.app import VIEWS
    assert "Evolution" in [n for n, _ in VIEWS]
    p = plateau_cell.write(tmp_path / "plateaus.mpt")
    win.open_paths([p]); pump(app)
    rec = win.rec
    for a in ({"charge": "ox"}, {"configuration": "full"}, {"mass_mg": 5.0}):
        win._answer(a); pump(app)
    win.set_focus_cycle(1); app.processEvents()
    texts = [l.text() for l in win.inspector.findChildren(QtWidgets.QLabel)]
    block = [t for t in texts if t.startswith(("Plateaus, cycle", "Pair ", "Unpaired"))]
    assert block[0] == "Plateaus, cycle 1 (dQ/dE peaks)"
    assert sum(t.startswith("Pair ") for t in block) == 3 and all("60 mV apart" in t for t in block if t.startswith("Pair"))
    unpaired = [t for t in block if t.startswith("Unpaired")]
    assert len(unpaired) == 1 and "4.100 V" in unpaired[0] and "no counterpart within 200 mV" in unpaired[0] \
        and "first cycle only" in unpaired[0]
    assert "irreversible" not in " ".join(texts).lower()
    win.set_focus_cycle(3); app.processEvents()
    texts = [l.text() for l in win.inspector.findChildren(QtWidgets.QLabel)]
    assert any(t == "Plateaus, cycle 3 (dQ/dE peaks)" for t in texts)
    assert not any(t.startswith("Unpaired charge peak at 4.100") for t in texts)
    assert any(t.startswith("Appearing later") and "2.680 V" in t and "appears from cycle 3" in t for t in texts)


def test_a_large_table_draws_in_every_view_without_an_error(win, app, tmp_path, capfd):
    """Above 100 000 rows the time views downsample and clip to the view. pyqtgraph 0.14 looks the item's
    view up while the scene adopts it, so clip-to-view set before addItem raised AttributeError
    (autoRangeEnabled) on every large file; the item is now configured after it is in its ViewBox."""
    from electrochem.table import _text_header
    from electrochem.studio.app import DEMO_FILE
    src = DEMO_FILE.read_bytes()
    header, names, block = _text_header(src, "cp1252")
    ti = names.index("time/s")
    lines = [l for l in block.split(b"\n") if l.strip()]
    last_t = float(lines[-1].split(b"\t")[ti])
    out = []
    for r in range(6):                                                  # 119 514 rows
        off = r * (last_t + 1.0)
        for l in lines:
            f = l.split(b"\t"); f[ti] = f"{float(f[ti]) + off:.6f}".encode(); out.append(b"\t".join(f))
    p = tmp_path / "big.mpt"
    p.write_bytes(src[:len(src) - len(block)] + b"\n".join(out) + b"\n")
    win.open_paths([p]); pump(app, 180)
    rec = win.rec
    assert rec.loaded is not None and rec.loaded.tab.n > 100_000
    for a in ({"charge": "ox"}, {"configuration": "full"}, {"mass_mg": 5.0}):
        win._answer(a); pump(app, 180)
    for k in range(len(win.views)):
        win.show_view(k); app.processEvents()
    data = next(v for v in win.views if type(v).__name__ == "DataView")
    data.x.setCurrentText("Time (s)"); data.y.setCurrentText("Current (mA)"); app.processEvents()
    err = capfd.readouterr().err
    assert "Traceback" not in err and "autoRangeEnabled" not in err, err[-2000:]


def test_reading_a_file_from_another_cycler_reports_its_progress_in_place(win, app, tmp_path, monkeypatch):
    """The reader's progress (rows, share of the file) reaches the reading screen as one line rewritten in
    place, not one line per chunk, and the status bar says the same; the worker turns the reader's
    (rows, bytes, total) into words at most five times a second."""
    from tests import reader_fixtures as fixtures
    from electrochem.studio import worker
    monkeypatch.setenv("ELECTROCHEM_PROFILES", str(tmp_path / "profiles"))
    p = fixtures.write_neware_like(tmp_path / "cell.xlsx")
    seen = []
    orig = win._reading_progress
    monkeypatch.setattr(win, "_reading_progress", lambda rec, msg: (seen.append(msg), orig(rec, msg)))
    win.open_paths([p]); pump(app)
    assert win.rec.loaded is not None and seen and all(m.startswith("Reading: ") for m in seen)
    assert seen[-1].endswith("100 % of the file")
    lines = [l[0] for l in win.ingest.telemetry.lines]
    assert sum(l.startswith("Reading: ") for l in lines) == 1          # rewritten, not appended
    # the text formatter itself: throttled, and always the final state
    said = []
    cb = worker._text_progress(said.append)
    cb(10, 10, 100); cb(20, 20, 100); cb(100, 100, 100)
    assert said[0] == "Reading: 10 rows, 10 % of the file" and said[-1] == "Reading: 100 rows, 100 % of the file"
    assert len(said) == 2                                               # the second call came too soon


def test_the_focus_ring_follows_the_selected_view(win, app):
    """With the keyboard focus in the view switcher, a view chosen by shortcut takes the focus with it, so the
    focus ring never marks a view that is no longer shown (it read as two selected views)."""
    opened(win, app, FULL)
    win.view_buttons.button(0).setFocus(); app.processEvents()
    k = [n for n, _ in __import__("electrochem.studio.app", fromlist=["VIEWS"]).VIEWS].index("Evolution")
    win.show_view(k); app.processEvents()
    assert QApplication.focusWidget() is win.view_buttons.button(k)
    win.files.setFocus(); app.processEvents()                 # focus elsewhere stays where it is
    win.show_view(0); app.processEvents()
    assert QApplication.focusWidget() is win.files


def test_a_lanhe_cex_opens_with_its_direction_answered_and_its_checks_listed(win, app, tmp_path):
    """A LANHE .cex is read natively (readers.lanhe_cex): the window answers the current direction from the
    file's step types and says why, asks the cycle order when the file opens with a step that ended at once,
    lists the reader's checks among the diagnostics, and tells a cut-short cycle from an unpaired one."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent))
    import cex_synthetic as cs
    from test_degenerate_pairs import HOLD
    from electrochem.studio.model import open_questions
    blob, _ = cs.write(HOLD)
    p = tmp_path / "hold.cex"
    p.write_bytes(blob)
    win.open_paths([p]); pump(app)
    rec = win.rec
    assert rec.loaded.meta["profile"] == "lanhe-cex" and rec.answers.charge == "ox"
    assert [q.key for q in open_questions(rec.answers, rec.loaded, rec.run)][0] == "order"
    for a in ({"configuration": "full"}, {"no_mass": True}, {"cycle_order": "discharge-first"}):
        win._answer(a); pump(app)
    texts = [win.results.diagnostics.item(k).text() for k in range(win.results.diagnostics.count())]
    assert any("integrates to the tester's capacity counter" in t for t in texts)
    assert any(re.search(r"follows the tester's clock in (\d+) of \1 intervals between step starts \(slope", t)
               for t in texts)
    assert any(t.startswith("1 incomplete cycle (no partner branch): 1") for t in texts)
    assert any(t.startswith("1 incomplete cycle (a branch reaches the end of the file") for t in texts)
    assert win.strip.incomplete_why == {1: "no partner branch",
                                        2: "a branch reaches the end of the file or has an unsupported interval"}


def test_the_dqde_view_says_why_it_has_no_curve(win, app, tmp_path):
    """A LANHE file whose every branch was paused partway: the dQ/dE view (and its compact copy in the overview)
    says why it is empty instead of showing an empty scale; with one branch paused, the view's note names it and
    why; going from a selection with a curve to one without leaves no note of the first above the sentence."""
    import sys as _sys
    from dataclasses import replace
    _sys.path.insert(0, str(Path(__file__).parent))
    import cex_synthetic as cs
    from electrochem.studio.views import NO_DQDE, DifferentialView
    for name, paused in (("all.cex", (1, 4, 6, 7)), ("one.cex", (4,)), ("mixed.cex", (4, 6, 7))):
        steps = cs.two_cycles()
        for k in paused:
            steps[k] = replace(steps[k], pause=(steps[k].duration / 2, 120))
        p = tmp_path / name
        p.write_bytes(cs.write(steps)[0])
        win.open_paths([p]); pump(app)
        for a in ({"configuration": "full"}, {"no_mass": True}):
            win._answer(a); pump(app)
        assert win.rec.run is not None and [b.pauses for b in win.rec.run.seg.branches] == \
            [int(k in paused) for k in (1, 4, 6, 7)]
        view = next(v for v in win.views if isinstance(v, DifferentialView))
        view.show_record(win.rec, [1, 2], None)
        empty = NO_DQDE.format(sym="V")                   # the cell voltage: the axis reads dQ/dV
        if name == "all.cex":
            assert not view.empty.isHidden() and view.empty.text() == empty
            compact = [v for v in win.findChildren(DifferentialView) if v.compact]
            assert compact and all(v.empty.text() == empty for v in compact)
        elif name == "one.cex":
            assert view.empty.isHidden()
            assert "No dQ/dV curve for cycle 1 discharge (paused partway)." in view.note.text()
        else:
            view.show_record(win.rec, [1], None)
            assert view.empty.isHidden() and "cycle 1 discharge (paused partway)" in view.note.text()
            view.set_selection([2], None)
            assert not view.empty.isHidden() and view.empty.text() == empty and view.note.isHidden()
