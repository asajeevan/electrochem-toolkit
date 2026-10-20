"""Regression tests for the independent review of 2026-10-19 and for the Cyclara window:
brand, motion, drops and menus.

Each test names the reviewer's reproduction script it replaces (r01 to r29);
docs/reviews/Cyclara_Review_2026-10-19.md maps those to the 31 findings. Each
test fails if its fix is removed. Run offscreen.
"""
import gc
import json
import os
import shutil
import time
import warnings
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("pyqtgraph")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QSettings, Qt, QThreadPool, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from electrochem import plotting, workflow
from electrochem.cycling import Settings, capacity_basis, cycle_capacity
from electrochem.studio import theme
from electrochem.studio.model import Answers, parse_number, questions, reason_for, settings_for

ROOT = Path(__file__).resolve().parents[1]
CB5 = ROOT / "data" / "public" / "mpt" / "020-formation_CB5.mpt"
CB5_MPR = ROOT / "data" / "public" / "mpr" / "020-formation_CB5.mpr"
NO_NS = ROOT / "data" / "public" / "mpr" / "bio_logic1.mpr"
MM = plotting.MM


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    theme.load_fonts()
    theme.apply(a, theme.LIGHT)
    from electrochem.studio.motion import Motion
    Motion.mode = "off"
    return a


def pump(app, timeout=60.0, quiet=0.25):
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
    import uuid
    from electrochem.studio.app import MainWindow
    w = MainWindow(store=f"cyclara-review-{uuid.uuid4().hex[:8]}")
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


def open_cb5(win, app, *answers, path=CB5):
    win.open_paths([path])
    pump(app)
    for a in answers:
        win._answer(a)
        pump(app)
    return win.rec


def run_for(path=CB5, **kw):
    return workflow.analyse_file(workflow.open_file(path), Settings(**kw))


# ======================================================================= wrong results

def test_r01_capacities_are_on_the_basis_their_label_names(app, win):
    """Area given, no mass: values are mAh per cm2 wherever the label says mAh cm-2."""
    run = run_for(charge="ox", terminal_voltage=True, area_cm2=2.0)
    c = next(c for c in run.an.cycles if c.complete)
    assert capacity_basis(run.settings) == "areal"
    assert cycle_capacity(c, "discharge", run.settings) == pytest.approx(c.discharge_capacity_mAh / 2.0)
    # exported figure: the plotted values are areal
    fig = plotting.capacity_efficiency(run.an.cycles, run.settings)
    ys = [ln.get_ydata() for ln in fig.axes[0].get_lines() if ln.get_label() == "Discharge"][0]
    assert ys[0] == pytest.approx(c.discharge_capacity_mAh / 2.0)
    assert "Areal" in fig.axes[0].get_ylabel()
    plt.close(fig)
    # the app: capacity view, strip and inspector
    rec = open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"}, {"area_cm2": 2.0})
    cap = win.views[2]
    pts = [it for it in cap.top.getPlotItem().items if getattr(it, "name", lambda: "")() == "Discharge (filled)"][0]
    assert pts.data["y"][0] == pytest.approx(c.discharge_capacity_mAh / 2.0)
    assert win.strip.values[0] == pytest.approx(c.discharge_capacity_mAh / 2.0)
    labels = [w.text() for w in win.inspector.inner.findChildren(QtWidgets.QLabel)]
    k = labels.index("Discharge, cycle 1")
    assert labels[k + 1].startswith(f"{c.discharge_capacity_mAh / 2.0:.2f} mAh cm⁻²")


def test_r01_the_origin_tables_are_on_the_same_basis(tmp_path):
    """The Origin folder's cycles.csv plots areal values under the areal unit (the review named the Origin script)."""
    import csv
    from electrochem import origin_export
    run = run_for(charge="ox", terminal_voltage=True, area_cm2=2.0)
    origin_export.write(tmp_path, run.tab, run.seg, run.an, run.settings, run.selected, run.dqde_curves())
    with open(tmp_path / "origin" / "cycles.csv", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    k = rows[2].index("discharge_plotted")
    c = next(c for c in run.an.cycles if c.complete)
    assert rows[1][k] == "mAh/cm²" and float(rows[3][k]) == pytest.approx(c.discharge_capacity_mAh / 2.0)


def test_r02_every_efficiency_point_is_inside_the_axis():
    """A cycle above 100 % is drawn, never cut off by the axis (M01.06: no clipping above 100 %)."""
    lo, hi = plotting.ce_limits([99.6, 99.7, 99.8, 101.2, 99.7])
    assert lo < 99.6 and hi > 101.2
    lo, hi = plotting.ce_limits([100.76])
    assert lo < 100.76 < hi
    lo, hi = plotting.ce_limits([99.0, 130.0], "full")
    assert lo == 0 and hi > 130
    run = run_for(charge="red", terminal_voltage=True, active_mass_mg=10.0)
    fig = plotting.capacity_efficiency(run.an.cycles, run.settings)
    checks = {c.name: c.status for c in plotting.check_figure(fig)}
    assert checks["data inside the axes"] == "pass"
    plt.close(fig)


def test_r02_the_cycle_order_is_asked_when_the_file_starts_with_a_discharge(app, win):
    rec = open_cb5(win, app, {"charge": "red"})                 # with red charging, CB5 starts with a discharge
    keys = {q.key: q for q in questions(rec.answers, rec.loaded, rec.run)}
    assert keys["order"].required and not keys["order"].answered
    assert "1 answer" not in rec.state and "answers needed" in rec.state
    win._answer({"cycle_order": "discharge-first"}); pump(app)
    first = rec.run.an.cycles[0]
    assert first.complete and first.discharge_branch == 1 and first.charge_branch == 2
    # a file that starts with a charge: the question is shown but not required
    rec2 = open_cb5(win, app, {"charge": "ox"}, path=CB5_MPR)
    q2 = {q.key: q for q in questions(rec2.answers, rec2.loaded, rec2.run)}
    assert not q2["order"].required and q2["order"].answered


def test_r13_without_a_step_column_a_current_reversal_ends_a_branch():
    run = run_for(NO_NS, charge="ox")
    assert run.tab.ns is None
    q = sorted(round(b.charge_mAh, 4) for b in run.an.branches)
    assert q == [1.439, 2.5975]                                   # not one branch of their difference, 1.1585
    assert any("No step (Ns) column" in n for n in run.seg.convention["notes"])


def test_r15_a_three_electrode_file_uses_the_column_the_answer_calls_for(tmp_path):
    lines = CB5.read_bytes().decode("cp1252").split("\r\n")
    n_hdr = int(lines[1].split(":")[1])
    cols = lines[n_hdr - 1].split("\t"); k = cols.index("Ecell/V")
    out = lines[:n_hdr - 1] + ["\t".join(cols[:k + 1] + ["Ewe/V"] + cols[k + 1:])]
    for ln in lines[n_hdr:]:
        if not ln.strip():
            out.append(ln); continue
        f = ln.split("\t")
        out.append("\t".join(f[:k + 1] + [f"{float(f[k].replace(',', '.')) + 0.3:.7f}"] + f[k + 1:]))
    p = tmp_path / "three_electrode.mpt"
    p.write_bytes("\r\n".join(out).encode("cp1252"))
    L = workflow.open_file(p)
    half = workflow.analyse_file(L, settings_for(Answers(charge="ox", configuration="half", reference="Li+/Li")))
    full = workflow.analyse_file(L, settings_for(Answers(charge="ox", configuration="full")))
    assert half.tab.labels["potential"] == "Ewe/V" and full.tab.labels["potential"] == "Ecell/V"
    dh = next(c for c in half.an.cycles if c.complete).average_discharge_voltage_V
    df = next(c for c in full.an.cycles if c.complete).average_discharge_voltage_V
    assert dh - df == pytest.approx(0.3, abs=1e-6)
    # a file with one potential column is not changed by either answer
    one = workflow.open_file(CB5)
    assert workflow.analyse_file(one, settings_for(Answers(charge="ox", configuration="half", reference="Li+/Li"))
                                 ).tab.labels["potential"] == "Ecell/V"


def test_r16_r28_header_mass_in_grams_and_the_ec_lab_default(tmp_path):
    from electrochem.workflow import Loaded, mass_warnings
    L = Loaded(CB5, None, {"active_mass_declared": {"value": 0.004817, "unit": "g"}}, None)
    assert mass_warnings(L, Settings(active_mass_mg=4.817)) == []
    assert "differs" in mass_warnings(L, Settings(active_mass_mg=6.0))[0]
    D = Loaded(CB5, None, {"active_mass_declared": {"value": 0.001, "unit": "mg"}}, None)
    assert any("EC-Lab's default" in w for w in mass_warnings(D, Settings()))
    assert not any("--mass-mg" in w for w in mass_warnings(D, Settings()))     # GUI wording, no CLI flags


def test_r28_the_default_mass_is_not_offered_and_implausible_capacity_is_flagged(app, win):
    rec = open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"})
    assert rec.loaded.declared_mass_mg == pytest.approx(0.001)
    assert win.inspector.inner.findChild(QPushButton, "q_mass_header") is None
    win._answer({"mass_mg": 0.001}); pump(app)
    from electrochem.studio.tables import implausible_capacity
    assert implausible_capacity(rec)
    texts = [win.results.diagnostics.item(k).text() for k in range(win.results.diagnostics.count())]
    assert any("above the theoretical capacity" in t for t in texts)


def test_r14_the_column_name_is_not_presented_as_evidence(app, win):
    open_cb5(win, app, path=CB5_MPR)
    text = " ".join(w.text() for w in win.inspector.inner.findChildren(QtWidgets.QLabel))
    assert "as in a half-cell" not in text and "as in a full cell" not in text
    assert "names the column Ewe/V whatever the set-up" in text


def test_r22_withheld_values_name_the_real_reason(app, win):
    rec = open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"}, {"mass_mg": 10.0}, {"reference_cycle": 5})
    assert "reference cycle, 5, is not a complete cycle" in reason_for("capacity_retention_pct", rec.answers, rec.run)
    assert reason_for("discharge_c_rate", rec.answers, rec.run) == "needs molar mass and electrons per formula unit"
    shown = [w.text() for w in win.inspector.inner.findChildren(QtWidgets.QLabel)]
    assert "⊘ withheld: the reference cycle, 5, is not a complete cycle of this file" in shown
    # typing a reference cycle that does not exist is refused at the field
    ed = win.inspector.inner.findChild(QLineEdit, "q_refcycle")
    ed.setText("7"); ed.editingFinished.emit(); pump(app)
    assert rec.answers.reference_cycle == 5


def test_r07_r11_numbers_and_cycle_lists_cannot_overflow_or_freeze():
    with pytest.raises(ValueError):
        parse_number("1e400")
    av = list(range(1, 112))
    t = time.time()
    assert workflow.parse_cycles("1:2000000000", av) == av
    assert workflow.parse_cycles("0:100000000:10", av) == list(range(10, 111, 10))
    assert workflow.parse_cycles("100000:1:20", av)[:2] == [100, 80]
    assert time.time() - t < 0.5
    missing = []
    assert workflow.parse_cycles("1, 2, 999", av[:2], missing) == [1, 2] and missing == ["999"]


def test_r19_r29_exports_are_recognised_by_their_header_not_a_shared_prefix(tmp_path):
    from electrochem.metadata import sibling_export
    from electrochem.studio.app import MainWindow
    hdr = CB5.read_bytes()
    shutil.copy(CB5_MPR, tmp_path / "cell1.mpr")
    (tmp_path / "cell10.mpt").write_bytes(hdr)                      # another run that happens to share a prefix
    (tmp_path / "cell1_IxQ.mpt").write_bytes(hdr.replace(b"020-formation_CB5.mpr", b"cell1.mpr"))
    skipped = []
    opened = [p.name for p in MainWindow.expand([tmp_path], skipped)]
    assert opened == ["cell1.mpr", "cell10.mpt"]
    assert len(skipped) == 1 and "cell1_IxQ.mpt" in skipped[0]
    cand, lines = sibling_export(tmp_path / "cell1.mpr")
    assert cand.name == "cell1_IxQ.mpt" and lines
    assert workflow.open_file(tmp_path / "cell1.mpr").header_source == "cell1_IxQ.mpt"
    (tmp_path / "cell1_IxQ.mpt").unlink()                          # only the unrelated cell10.mpt is left
    assert workflow.open_file(tmp_path / "cell1.mpr").header_source is None
    # r29: only the header block of the export is read, never its rows (a 31 MB export took 3 s)
    n_hdr = int(hdr.split(b"\r\n")[1].split(b":")[1])
    head = b"\r\n".join(hdr.split(b"\r\n")[:n_hdr]).replace(b"020-formation_CB5.mpr", b"cell1.mpr")
    (tmp_path / "cell1_big.mpt").write_bytes(head + b"\r\n" + b"\xff\xfe not rows \x00" * 3_000_000)   # 60 MB
    t = time.time()
    cand, lines = sibling_export(tmp_path / "cell1.mpr")
    assert cand.name == "cell1_big.mpt" and len(lines) == n_hdr and time.time() - t < 0.5
    # and opening the .mpr takes only the header from that export: its rows here could not even be parsed
    assert workflow.open_file(tmp_path / "cell1.mpr").header_source == "cell1_big.mpt"


def test_r12_the_checker_catches_what_it_claims_to_check():
    def base(w=89):
        plotting.apply_style("nature")
        fig = plt.figure(figsize=(w * MM, 70 * MM), layout="constrained")
        return fig, fig.add_subplot()

    def status(fig, name, journal="nature"):
        st = {c.name: c.status for c in plotting.check_figure(fig, journal)}[name]
        plt.close(fig)
        return st
    x = np.linspace(0, 1, 60)
    fig, ax = base(); ax.plot(x, x, color="#0072B2"); plotting.finalize(fig, {ax: "A"})
    assert status(fig, "type size") == "fail"
    fig, ax = base(); ax.scatter(x, np.full_like(x, 0.95), s=6, color="#0072B2", label="p"); ax.set_ylim(0, 1)
    ax.legend(loc="upper left")
    assert status(fig, "legends clear of data") == "fail"
    fig, ax = base(); ax.fill_between(x, 0.8, 1.0, color="#0072B2", label="b"); ax.set_ylim(0, 1); ax.legend(loc="upper left")
    assert status(fig, "legends clear of data") == "fail"
    fig, ax = base(); ax.plot(x, np.full_like(x, 0.5), color="#0072B2", label="a long entry"); ax.set_ylim(0, 1)
    fig.legend(loc="center")
    assert status(fig, "legends clear of data") == "fail"
    fig, ax = base(); ax.plot(x, np.full_like(x, 0.5), color="#0072B2"); ax.text(0.5, 0.5, "over the curve", ha="center")
    assert status(fig, "text clear of data") == "fail"
    fig, ax = base(); ax.plot([1, 2, 3], [99.5, 100.8, 99.7], "^", color="black"); ax.set_ylim(99, 100.08)
    assert status(fig, "data inside the axes") == "fail"
    fig, ax = base(); ax.plot(x, x, color="#0072B2"); ax.tick_params(width=0.1)
    assert status(fig, "line weights") == "fail"
    # and a clean figure passes all of them
    fig, ax = base(); ax.plot(x, x, color="#0072B2", label="line"); ax.legend(loc="lower right")
    assert all(c.status == "pass" for c in plotting.check_figure(fig) if c.name != "typeface")
    plt.close(fig)


@pytest.mark.parametrize("journal,minimum", [("nature", 5.0), ("elsevier", 6.0)])
def test_r12_superscripts_meet_the_journal_minimum(journal, minimum):
    """Matplotlib draws superscripts at 0.7 of the text: 4.9 pt for 7 pt text. Exported ones are raised to the minimum."""
    from matplotlib.mathtext import MathTextParser
    run = run_for(charge="ox", terminal_voltage=True, active_mass_mg=10.0)
    fig = workflow.figure_builders(run, workflow.ExportOptions(journal=journal))["potential_capacity"]()
    checks = {c.name: c for c in plotting.check_figure(fig, journal)}
    assert checks["type size"].status == "pass" and "superscripts at least" in checks["type size"].detail
    lab = fig.axes[0].xaxis.label
    vp = MathTextParser("path").parse(lab.get_text(), dpi=72, prop=lab.get_fontproperties())
    assert min(g[1] for g in vp.glyphs) >= minimum
    plt.close(fig)


# ======================================================================= crash, undo, data safety

def test_r10_garbage_is_collected_on_the_gui_thread_only(app, win):
    from electrochem.studio import worker
    assert worker._COLLECTOR is not None and not gc.isenabled()
    rec = open_cb5(win, app)
    old = win.inspector.widget()
    win.inspector.show_record(rec)
    assert win.inspector.widget() is not old
    assert not old.isVisible()                    # taken away and deleted later, never inside its own signal


def test_r17_undo_after_closing_and_reopening_a_file(app, win):
    open_cb5(win, app, {"charge": "ox"}, {"mass_mg": 10.0})
    win.close_record(); pump(app)
    open_cb5(win, app)
    win.undo.undo(); pump(app)                    # the restored answers of the reopened file
    win.undo.undo(); pump(app)                    # a step of the closed record: dropped, no exception
    assert win.status_text.text() == "That file was closed; the step was dropped"


def test_r09_undo_shows_the_file_it_acts_on(app, win):
    a = open_cb5(win, app, {"mass_mg": 10.0})
    b = open_cb5(win, app, path=CB5_MPR)
    assert win.rec is b
    win.undo.undo(); pump(app)
    assert win.rec is a and a.answers.mass_mg is None


def test_r08_restored_answers_are_one_undo_step_and_announced(app, win):
    rec = open_cb5(win, app, {"charge": "ox"}, {"mass_mg": 10.0})
    store = win.settings.fileName()
    win.close_record(); pump(app)
    win.undo.clear()
    rec2 = open_cb5(win, app)
    assert rec2.answers.charge == "ox" and rec2.answers.mass_mg == 10.0
    assert win.undo.canUndo() and getattr(rec2, "restored", False)
    assert win.inspector.inner.findChild(QPushButton, "restored_clear") is not None
    win.undo.undo(); pump(app)
    assert rec2.answers.charge is None and not rec2.restored


def test_r06_text_being_typed_survives_a_result_and_is_not_committed(app, win):
    from PySide6.QtTest import QTest
    rec = open_cb5(win, app, {"charge": "ox"})
    win.activateWindow(); app.processEvents()
    ed = win.inspector.inner.findChild(QLineEdit, "q_mass")
    ed.setFocus(); app.processEvents()
    QTest.keyClicks(ed, "5.7")                                 # typing, with the keyboard focus in the field
    win.inspector.show_record(rec, rec.focus_cycle)           # what a returning analysis does
    pump(app)
    ed2 = win.inspector.inner.findChild(QLineEdit, "q_mass")
    assert ed2 is not ed and ed2.text() == "5.7"
    assert rec.answers.mass_mg is None                       # nothing half-typed was committed


def test_r04_r18_each_export_claims_its_own_folder(app, win, tmp_path):
    (tmp_path / "cell_analysis").write_text("a file, not a folder")
    a = win._claim_folder(tmp_path, "cell")
    b = win._claim_folder(tmp_path, "cell")
    assert a.name == "cell_analysis_2" and b.name == "cell_analysis_3"
    assert a.is_dir() and b.is_dir()


# ======================================================================= interaction

def test_r03_r27_moving_the_focus_never_changes_the_selection(app, win):
    rec = open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"})
    win.set_cycles_spec("1")
    win.set_focus_cycle(2)
    assert rec.selected_cycles() == [1] and rec.focus_cycle == 2
    assert win.strip.focus == 2
    # the plots preview the focused cycle, dashed, without exporting it
    assert 2 in win.views[1].drawn() and win.views[1].preview(2)
    assert rec.run.selected == [1]
    # the strip's own arrow keys move the focus only
    from PySide6.QtTest import QTest
    win.set_focus_cycle(1)
    QTest.keyClick(win.strip, Qt.Key_Right); pump(app)
    assert rec.selected_cycles() == [1] and rec.focus_cycle == 2


def test_r03_removing_the_focused_cycle_moves_the_focus_and_tells_the_app(app, win):
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    rec = open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"})
    win.set_cycles_spec("1, 2"); win.set_focus_cycle(2)
    s = win.strip
    r, w = s._slot()
    x = r.left() + 1.5 * w
    for t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        s.event(QMouseEvent(t, QPointF(x, r.center().y()), QPointF(x, r.center().y()), Qt.LeftButton,
                            Qt.LeftButton, Qt.NoModifier))
    pump(app)
    assert rec.selected_cycles() == [1] and rec.focus_cycle == 1 and s.focus == 1


def test_r05_unticked_figures_stay_unticked(app, win):
    open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"}, {"mass_mg": 10.0})
    win.show_view(len(win.views))                      # the Figures page follows the views
    st = win.studio
    k = [st.list.item(i).data(Qt.UserRole) for i in range(st.list.count())].index("overview_time")
    st.list.item(k).setCheckState(Qt.Unchecked)
    win.set_cycles_spec("2"); pump(app)
    assert "overview_time" not in st.options().plots


def test_r20_an_unreadable_file_leaves_no_figure_on_the_sheet(app, win, tmp_path):
    open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"}, {"mass_mg": 10.0})
    win.show_view(len(win.views)); pump(app)           # the Figures page
    bad = tmp_path / "empty.mpt"; bad.write_bytes(b"")
    win.open_paths([bad]); pump(app)
    assert win.rec.error and win.studio.sheet.pixmap().isNull()
    assert "could not be read" in win.studio.list.item(0).text()


def test_r21_results_of_earlier_answers_are_marked_while_updating(app, win):
    rec = open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"}, {"mass_mg": 10.0})
    win._answer({"mass_mg": 20.0})                 # the analysis starts; results are now stale
    assert not rec.current and win.stale.isVisibleTo(win)
    texts = [w.text() for w in win.inspector.inner.findChildren(QtWidgets.QLabel)]
    assert any(t.startswith("Updating for your last answer") for t in texts)
    roles = [w.property("role") for w in win.inspector.inner.findChildren(QtWidgets.QLabel)
             if w.property("role") in ("value", "provisional")]
    assert roles and all(r == "provisional" for r in roles)   # every value marked, not only the banner
    pump(app)
    assert rec.current and not win.stale.isVisibleTo(win)


def test_r23_icons_follow_the_theme(app, win):
    """Switching the theme redraws every drawn icon in the new colours (non-text contrast at least 3:1)."""
    from PySide6.QtGui import QImage
    from electrochem.plotting import contrast

    def colour(button):
        img = button.icon().pixmap(18, 18).toImage().convertToFormat(QImage.Format_ARGB32)
        px = [img.pixelColor(x, y) for y in range(img.height()) for x in range(img.width())]
        opaque = [c for c in px if c.alpha() > 200]
        assert opaque, button
        return opaque[0].name()
    start = theme.tokens().name
    try:
        for _ in range(2):                                   # light to dark, then back
            win.toggle_theme(); pump(app)
            t = theme.tokens()
            for b in (win.btn_open, win.btn_folder, win.btn_undo, win.btn_redo, win.search):
                assert contrast(colour(b), t.panel) >= 3.0, (t.name, b.toolTip())
            assert contrast(colour(win.studio.export_btn), t.primary) >= 3.0, t.name
    finally:
        if theme.tokens().name != start:
            win.toggle_theme(); pump(app)


def _cut_off(win, app):
    """Everything the window shows that is cut off: view buttons, top-bar items, axis titles, squeezed widgets."""
    import pyqtgraph as pg
    from PySide6.QtCore import QRect
    bad = []
    for b in win.view_buttons.buttons():
        if b.width() < b.fontMetrics().horizontalAdvance(b.text()) + 8:
            bad.append(f"view button {b.text()!r} narrower than its name")
        if not win.rect().contains(QRect(b.mapTo(win, QPoint(0, 0)), b.size())):
            bad.append(f"view button {b.text()!r} outside the window")
    bar = [w for w in (win.btn_open, win.btn_folder, win.btn_undo, win.btn_redo, win.search, win.search_key,
                       win.pill, win.btn_theme, win.btn_export) if w.isVisible()]
    boxes = [QRect(w.mapTo(win, QPoint(0, 0)), w.size()) for w in bar]
    for i in range(len(boxes)):
        if not win.rect().contains(boxes[i]):
            bad.append(f"{bar[i].toolTip() or bar[i].text()} outside the window")
        for j in range(i + 1, len(boxes)):
            if boxes[i].intersects(boxes[j]):
                bad.append(f"{bar[i].toolTip() or bar[i].text()} overlaps {bar[j].toolTip() or bar[j].text()}")
    tabs = win.results.bar
    if tabs.isVisible():
        for k in range(tabs.count()):
            if tabs.tabRect(k).right() > tabs.width():
                bad.append(f"results tab {tabs.tabText(k)!r} cut off")
    for k in range(len(win.views)):
        win.show_view(k); pump(app)
        for plot in win.views[k].findChildren(pg.PlotWidget):
            if not plot.isVisible():
                continue
            for side in ("left", "bottom"):
                ax = plot.getPlotItem().getAxis(side)
                if not ax.isVisible() or not ax.label.isVisible() or not ax.label.toPlainText():
                    continue
                g = ax.geometry()
                r = ax.label.mapRectToItem(ax, ax.label.boundingRect())
                lo, hi, a, b = (r.top(), r.bottom(), g.top() - g.top(), g.height()) if side == "left" else \
                               (r.left(), r.right(), 0, g.width())
                if lo < a - 1 or hi > b + 1:
                    bad.append(f"view {k} {side} title {ax.label.toPlainText()!r} spans {lo:.0f}..{hi:.0f} of 0..{b:.0f}")
    win.show_view(0); pump(app)

    def squeezed(w):
        for c in w.findChildren(QtWidgets.QWidget, options=Qt.FindDirectChildrenOnly):
            if c.isVisible():
                if c.minimumSizeHint().width() > c.width() + 2:
                    bad.append(f"{type(c).__name__} {c.objectName()!r} squeezed to {c.width()} of "
                               f"{c.minimumSizeHint().width()}")
                squeezed(c)
    squeezed(win)
    return bad


@pytest.mark.parametrize("size", [(1024, 600), (1280, 640), (1480, 920)])
def test_finding26_nothing_is_cut_off_from_the_smallest_window_up(app, win, size):
    """From the minimum size (1024 x 600, about what a 1280 x 720 laptop screen at 150 % leaves) up:
    each view button shows its whole name, the top bar's items do not overlap, every axis title fits
    along its axis and is centred on it (the review saw "E (%)" and "nAh g-1)" at 1100 x 700), and no
    visible widget is squeezed below its minimum width."""
    open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"}, {"mass_mg": 10.0})
    win.resize(*size); pump(app)
    assert (win.width(), win.height()) == size
    assert _cut_off(win, app) == []


def test_the_overview_arranges_its_panels_for_the_room(app):
    from PySide6.QtCore import QSize
    from electrochem.studio.views import OverviewView
    ov = OverviewView()
    for size, shape in (((1260, 645), "grid"), ((1076, 365), "row"), ((620, 243), "pair"), ((1900, 930), "grid")):
        ov.arrange(QSize(*size))
        assert ov.shape == shape, size
    ov.arrange(QSize(620, 243))
    assert [v.isHidden() for v in ov.children_views] == [False, False, True, True]


def test_the_tables_fold_on_a_low_window_and_come_back(app, win):
    open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"})
    win.resize(1480, 920); pump(app)
    assert not win.results.collapsed and win.act["tables"].isChecked()
    win.resize(1280, 640); pump(app)                           # low: folded to the tab row
    assert win.results.collapsed and not win.act["tables"].isChecked()
    assert win.lower.height() <= win.results.header_height() + 16
    win.results.bar.tabBarClicked.emit(1)                      # a tab click opens the drawer
    assert not win.results.collapsed
    win.act["tables"].trigger()                                # Ctrl+J folds it again
    assert win.results.collapsed
    win.resize(1480, 920); pump(app)                           # the user folded it: it stays folded
    assert win.results.collapsed
    win.act["tables"].trigger(); pump(app)
    assert not win.results.collapsed
    win.resize(1280, 640); pump(app); win.resize(1480, 920); pump(app)   # folded by the window: unfolds with it
    assert not win.results.collapsed


def test_the_window_fits_the_screen_and_remembers_its_place(app, win):
    from PySide6.QtCore import QRect

    class Screen:
        def __init__(self, w, h):
            self.r = QRect(0, 0, w, h)

        def availableGeometry(self):
            return self.r
    assert win.comfortable_size(Screen(1920, 1040)) == (1480, 920) and not win.screen_is_small(Screen(1920, 1040))
    assert win.comfortable_size(Screen(1280, 672)) == (1232, 600) and win.screen_is_small(Screen(1280, 672))
    assert win.comfortable_size(Screen(800, 600)) == (1024, 600)             # never below the minimum size
    assert (win.minimumWidth(), win.minimumHeight()) == (1024, 600)
    win.close()
    assert win.settings.value("geometry") is not None


def test_the_theme_changes_as_a_widening_circle(app, win):
    from electrochem.studio.motion import Motion, ThemeReveal
    start = theme.tokens().name
    try:
        Motion.mode = "full"
        win.toggle_theme()
        reveal = win._reveal
        assert isinstance(reveal, ThemeReveal) and reveal.isVisible() and not reveal.picture.isNull()
        t = time.time()
        while time.time() - t < 3:
            app.processEvents(); time.sleep(0.01)
            try:
                if not reveal.isVisible():
                    break
            except RuntimeError:                                 # deleted: the circle has finished
                break
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)   # what the event loop does after the circle
        with pytest.raises(RuntimeError):
            reveal.isVisible()                                   # finished, hidden and deleted
        Motion.mode = "off"                                      # no motion: no overlay at all
        before = win.findChildren(ThemeReveal)
        win.toggle_theme(); app.processEvents()
        assert win.findChildren(ThemeReveal) == before
    finally:
        Motion.mode = "off"
        if theme.tokens().name != start:
            win.toggle_theme(); pump(app)


def test_r24_tab_goes_from_the_files_to_the_questions(app, win):
    open_cb5(win, app)
    w = win.files.nextInFocusChain()
    for _ in range(500):                         # the next Tab stop after the file list
        if (w.focusPolicy() & Qt.TabFocus) and w.isVisibleTo(win) and w.isEnabled() and not win.files.isAncestorOf(w):
            break
        w = w.nextInFocusChain()
    assert win.inspector.isAncestorOf(w)


def test_r25_inputs_that_cannot_be_opened_are_explained(app, win, tmp_path):
    (tmp_path / "data.bin").write_bytes(b"\x00\x01binary")
    (tmp_path / "empty").mkdir()
    (tmp_path / "mps").mkdir()
    shutil.copy(ROOT / "data" / "public" / "mps" / "BioTest_000001.mps", tmp_path / "mps")
    for p, words in ((tmp_path / "data.bin", ".bin files are not read"), (tmp_path / "empty", "no measurement file"),
                     (tmp_path / "mps", "protocol's settings")):
        win.open_paths([p])
        assert words in win.status_text.text()
    from electrochem.studio.worker import friendly
    (tmp_path / "empty.mpt").write_bytes(b"")
    with pytest.raises(Exception) as info:
        workflow.open_file(tmp_path / "empty.mpt")
    assert friendly(info.value) == "The file is empty."


def test_r26_labels_and_states(app, win):
    from electrochem.studio.app import _duration
    rec = open_cb5(win, app)
    cards = {q.key: q for q in questions(rec.answers, rec.loaded, rec.run)}
    assert not cards["optional"].answered                              # "Optional", not "Answered"
    assert "say which current direction" in win.strip.empty_text
    win._answer({"charge": "ox"}); pump(app)
    ticks = win.views[2].top.getPlotItem().getAxis("bottom").tickValues(0.8, 2.2, 400)
    assert all(abs(v - round(v)) < 1e-9 for _, vs in ticks for v in vs)
    win.set_cycles_spec("1, 2, 999")
    assert "999" in win.status_text.text()
    assert _duration(0.4) == "24 min" and _duration(0.005) == "18 s" and _duration(70) == "70 h"
    data = next(v for v in win.views if type(v).__name__ == "DataView")
    data.x.setCurrentText("Row"); data.redraw()
    assert data._points[0][1][0] == 1.0
    # the Capacity view names its markers
    win.show_view(2); pump(app)
    lg = win.views[2].top.getPlotItem().legend
    assert lg is not None and {lab.text for _, lab in lg.items} >= {"Charge (open)", "Discharge (filled)"}
    # the Voltage view's title names the reference
    win._answer({"configuration": "half"}); pump(app)
    win._answer({"reference": "Li+/Li"}); pump(app)
    voltage = next(v for v in win.views if type(v).__name__ == "VoltageView")
    win.show_view(win.views.index(voltage)); pump(app)
    assert "Li⁺/Li" in voltage.top.getPlotItem().getAxis("left").labelText
    # one branch is a branch
    from types import SimpleNamespace as NS
    one = NS(run=NS(seg=NS(branches=[object()], pairs=[]), an=NS(summary=NS(complete_cycles=0), cycles=[])))
    win._ingesting = one
    win._tell_segmentation(one); pump(app)
    assert "1 branch segmented" in [ln[0] for ln in win.ingest.telemetry.lines]
    win._ingesting = None


# ======================================================================= the Cyclara window

def test_drops_are_accepted_as_copies_and_open_the_file(app, win):
    """The window takes drops anywhere and never as a move, so a file manager can never delete the source.
    (On a real screen a plot under the cursor used to refuse the drag; the window-level filter fixes that.
    Offscreen, Qt hands a drag that a child ignores up to the window anyway, so this test cannot tell the
    filter's part apart: it checks the window's own handling, the copy action and the opened file.)"""
    win.show(); app.processEvents()
    md = QMimeData(); md.setUrls([QUrl.fromLocalFile(str(CB5))])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        # Shift held: the file manager proposes a move, which would delete the source after the drop
        e = QDragEnterEvent(QPoint(400, 400), Qt.CopyAction | Qt.MoveAction, md, Qt.LeftButton, Qt.ShiftModifier)
    assert e.proposedAction() == Qt.MoveAction
    QApplication.sendEvent(win.windowHandle(), e)
    assert e.isAccepted() and e.dropAction() == Qt.CopyAction
    assert win.drop.isVisible() and "020-formation_CB5.mpt" in win.drop.text
    d = QDropEvent(QPointF(400, 400), Qt.CopyAction | Qt.MoveAction, md, Qt.LeftButton, Qt.ShiftModifier)
    QApplication.sendEvent(win.windowHandle(), d)
    assert d.dropAction() == Qt.CopyAction and not win.drop.isVisible()
    pump(app)
    assert win.records and win.records[-1].path == CB5


def test_the_reading_screen_states_only_what_happened(app, win):
    rec = open_cb5(win, app)                                            # no answer: nothing redraws the window
    assert win.centre.currentIndex() == 1                               # it hands over to the workspace by itself
    lines = [ln[0] for ln in win.ingest.telemetry.lines]
    n = f"{rec.loaded.tab.n:,}".replace(",", " ")
    real = ("Opening the ", f"{n} rows and ", "Potential from ", "The header ", "Segmenting charge and discharge",
            f"{len(rec.run.seg.branches)} branches segmented", "Cycles wait for the charging direction")
    assert all(ln.startswith(real) for ln in lines), lines             # no invented step
    assert any(f"{len(rec.run.seg.branches)} branches segmented" == ln for ln in lines)
    # CB5's header holds EC-Lab's empty-field default, 0.001 mg: never "offered" (review finding 16)
    mass = [ln for ln in lines if ln.startswith("The header ")]
    assert mass and "default" in mass[0] and "offered, not applied" not in mass[0]


def test_menus_and_motion_setting(app, win):
    titles = [a.text().replace("&", "") for a in win.menubar.actions()]
    assert titles == ["File", "Edit", "View", "Help"]
    from electrochem.studio.motion import Motion
    win.set_motion("reduced")
    assert Motion.mode == "reduced" and win.settings.value("motion") == "reduced"
    win.set_motion("off")
    from PySide6.QtGui import QAction
    assert win.act["about"].menuRole() == QAction.AboutRole and win.act["quit"].menuRole() == QAction.QuitRole
    assert all(a.menuRole() == QAction.NoRole for a in win.all_actions     # nothing moved by its wording alone
               if a is not win.act["about"])


def test_reveal_ends_with_every_point_drawn(app, win):
    from electrochem.studio.motion import Motion
    rec = open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"})
    v = win.views[1]
    win.show_view(1); pump(app)
    full = {id(it): len(x) for it, x, _ in v._drawn}
    Motion.mode = "full"
    try:
        v.reveal()
        t = time.time()
        while time.time() - t < 1.2:
            app.processEvents(); time.sleep(0.01)
    finally:
        Motion.mode = "off"
    for it, x, _ in v._drawn:
        assert len(it.xData) == full[id(it)]


def test_the_launch_sequence_can_be_cut_short(app, win):
    from electrochem.studio.motion import Ignition, Motion
    Motion.mode = "full"
    try:
        done = []
        ig = Ignition(win, "test")
        ig.finished.connect(lambda: done.append(True))
        ig.start()
        app.processEvents()
        ig._leave()
        t = time.time()
        while not done and time.time() - t < 5:
            app.processEvents(); time.sleep(0.01)
        assert done and time.time() - t < 1.0      # the whole sequence lasts about 2 s; cut short, a fade
    finally:
        Motion.mode = "off"


def test_brand_assets_and_icon_renders(app):
    from electrochem.studio import brand
    for sz in (16, 32, 256):
        img = brand.icon_image(sz)
        assert img.width() == sz and img.height() == sz
        assert img.pixelColor(sz // 2, sz // 2).alpha() > 0
    for name in ("cyclara.ico", "cyclara.icns", "cyclara_256.png", "cyclara_mark_dark.svg"):
        assert (brand.ASSETS / name).exists()
    import xml.dom.minidom
    xml.dom.minidom.parseString(brand.mark_svg(64))


def test_no_mass_is_an_answer_and_capacities_stay_in_mah(app, win):
    """A full cell without a known mass can still be complete: "No mass" answers the question."""
    rec = open_cb5(win, app, {"charge": "ox"}, {"configuration": "full"}, {"no_mass": True, "mass_mg": None})
    assert rec.state == "ready to export"
    assert capacity_basis(rec.run.settings) == "absolute" and "no mass" in win.meta.text()
    ed = win.inspector.inner.findChild(QLineEdit, "q_mass")
    ed.setText("12"); ed.editingFinished.emit(); pump(app)
    assert rec.answers.mass_mg == 12.0 and not rec.answers.no_mass
    assert capacity_basis(rec.run.settings) == "specific"


def test_the_synthetic_demo_matches_its_known_answer():
    """End to end on a file with a known answer: data/demo (synthetic, scripts/make_demo_data.py)."""
    import json
    demo = ROOT / "data" / "demo" / "cyclara_demo_synthetic.mpt"
    truth = json.loads((demo.parent / "cyclara_demo_synthetic_truth.json").read_text())["cycles"]
    L = workflow.open_file(demo)
    assert "SYNTHETIC" in " ".join(L.tab.header)
    run = workflow.analyse_file(L, Settings(charge="ox", reference="Li+/Li", active_mass_mg=5.0))
    cyc = [c for c in run.an.cycles if c.complete]
    assert len(cyc) == len(truth) == 50
    for c, t in zip(cyc, truth):
        assert c.charge_capacity_mAh == pytest.approx(t["charge_mAh"], rel=1e-9)
        assert c.discharge_capacity_mAh == pytest.approx(t["discharge_mAh"], rel=1e-9)
        assert c.coulombic_efficiency_pct == pytest.approx(t["coulombic_efficiency_pct"], rel=1e-9)
    assert not run.seg.edges.reason                    # every interval integrated


# ======================================================================= other instruments (P08b)

def test_a_file_from_an_unknown_instrument_is_mapped_once_and_then_recognised(app, win, tmp_path, monkeypatch):
    """The import review step: the proposal, a check against the file, opening it, remembering the instrument."""
    monkeypatch.setenv("ELECTROCHEM_PROFILES", str(tmp_path / "profiles"))
    p = tmp_path / "strange.csv"
    p.write_text("Elapsed Time(s),Amps,Volts(V),Cycle Index,Step Index,Md\n" + "\n".join(
        f"{k * 60},0.001,{3.5 + 0.001 * k},1,{1 if k < 60 else 2},{'C' if k < 60 else 'D'}" for k in range(120)) + "\n")
    win.open_paths([p]); pump(app)
    rec = win.rec
    assert rec.needs_mapping and rec.state == "columns to map" and win.centre.currentIndex() == 3
    m = win.mapping
    assert m.role_boxes["current_ampere"].currentText() == "Amps" and m.sign.currentData() == "unsigned"
    assert {v: kb.currentData() for v, kb in m.kind_boxes.items()} == {"C": "cc_charge", "D": "cc_discharge"}
    m.check()                                                     # no evidence yet: refused before reading
    assert "how you know" in m.report.text().lower() and not m.use_btn.isEnabled()
    m.evidence.setText("written by the test: C charges, D discharges")
    m.instrument.setText("Strange cycler")
    m.check(); pump(app)
    assert "passed" in m.report.text() and m.use_btn.isEnabled()
    m.remember.setChecked(True)
    m.use(); pump(app)
    assert not rec.needs_mapping and rec.profile == "strange-cycler" and win.centre.currentIndex() == 1
    assert rec.answers.charge == "ox" and win.undo.canUndo()         # the direction came from the file's step types
    assert rec.run is not None and {b.direction for b in rec.run.an.branches} == {"charge", "discharge"}
    assert (tmp_path / "profiles" / "strange-cycler.json").exists()
    texts = [win.results.diagnostics.item(k).text() for k in range(win.results.diagnostics.count())]
    assert any(t.startswith("Import:") for t in texts)
    # the same columns again: recognised, no questions
    q = tmp_path / "strange2.csv"; q.write_bytes(p.read_bytes())
    win.open_paths([q]); pump(app)
    assert win.rec.path == q and not win.rec.needs_mapping and win.rec.profile == "strange-cycler"


def test_a_re_export_of_a_learned_instrument_needs_no_questions_and_a_renamed_column_starts_from_it(app, win, tmp_path, monkeypatch):
    """P08e: the instrument is learned once. An export with other columns, another order and another
    unit opens straight through; one with a renamed required column opens the review page with the
    saved profile's columns and conventions already filled in."""
    monkeypatch.setenv("ELECTROCHEM_PROFILES", str(tmp_path / "profiles"))
    p = tmp_path / "strange.csv"
    p.write_text("Elapsed Time(s),Amps,Volts(V),Cycle Index,Step Index,Md\n" + "\n".join(
        f"{k * 60},0.001,{3.5 + 0.001 * k},1,{1 if k < 60 else 2},{'C' if k < 60 else 'D'}" for k in range(120)) + "\n")
    win.open_paths([p]); pump(app)
    m = win.mapping
    m.evidence.setText("written by the test: C charges, D discharges"); m.instrument.setText("Strange cycler")
    m.check(); pump(app); m.remember.setChecked(True); m.use(); pump(app)
    q0 = {b.direction: b.charge_mAh for b in win.rec.run.an.branches}
    # other columns, another order, the voltage in millivolts: no questions
    q = tmp_path / "later.csv"
    q.write_text("Md,Volts(mV),Temp(C),Amps,Elapsed Time(s)\n" + "\n".join(
        f"{'C' if k < 60 else 'D'},{(3.5 + 0.001 * k) * 1000:.3f},25,0.001,{k * 60}" for k in range(120)) + "\n")
    win.open_paths([q]); pump(app)
    assert not win.rec.needs_mapping and win.rec.profile == "strange-cycler"
    assert {b.direction: b.charge_mAh for b in win.rec.run.an.branches} == pytest.approx(q0)
    assert abs(win.rec.loaded.tab.e[0] - 3.5) < 1e-9                   # millivolts read as the header says
    # a renamed time column: asked again, but from the saved profile
    r = tmp_path / "renamed.csv"
    r.write_text("Total Elapsed(s),Amps,Volts(V),Cycle Index,Step Index,Md\n" + "\n".join(
        f"{k * 60},0.001,{3.5 + 0.001 * k},1,{1 if k < 60 else 2},{'C' if k < 60 else 'D'}" for k in range(120)) + "\n")
    win.open_paths([r]); pump(app)
    rec = win.rec
    assert rec.needs_mapping and rec.proposal.prior is not None and rec.proposal.prior.name == "strange-cycler"
    assert "strange-cycler" in m.intro.text() and "Strange cycler" in m.intro.text()
    assert m.instrument.text() == "Strange cycler" and m.remember.isChecked()
    assert m.sign.currentData() == "unsigned" and "confirmed again" in m.evidence.text()
    assert m.role_boxes["current_ampere"].currentText() == "Amps" and m.role_boxes["step_type"].currentText() == "Md"
    assert {v: kb.currentData() for v, kb in m.kind_boxes.items()} == {"C": "cc_charge", "D": "cc_discharge"}
    m.check(); pump(app)
    assert "Time" in m.report.text() and not m.use_btn.isEnabled()      # the one thing the saved profile cannot say
    m.role_boxes["test_time_second"].setCurrentText("Total Elapsed(s)")
    m.check(); pump(app)
    assert "passed" in m.report.text() and m.use_btn.isEnabled()
    m.use(); pump(app)
    assert not win.rec.needs_mapping and {b.direction: b.charge_mAh for b in win.rec.run.an.branches} == pytest.approx(q0)
    saved = json.loads((tmp_path / "profiles" / "strange-cycler.json").read_text())
    assert saved["profile"]["bindings"]["test_time_second"]["source"] == ["Total Elapsed(s)"]   # the profile moved on


def test_a_recognised_instrument_opens_straight_through(app, win, tmp_path, monkeypatch):
    monkeypatch.setenv("ELECTROCHEM_PROFILES", str(tmp_path / "profiles"))
    from tests import reader_fixtures as fixtures
    p = fixtures.write_neware_like(tmp_path / "cell.xlsx")
    win.open_paths([p]); pump(app)
    rec = win.rec
    assert not rec.needs_mapping and rec.profile == "neware-xlsx" and "Neware" in win.meta.text()
    assert rec.answers.charge == "ox"                                  # Neware's Status column names the direction
    q = {b.direction: b.charge_mAh for b in rec.run.an.branches}
    assert q["charge"] == pytest.approx(1.0) and q["discharge"] == pytest.approx(0.5)
    shown = " ".join(w.text() for w in win.inspector.inner.findChildren(QtWidgets.QLabel))
    assert "neware-xlsx profile" in shown and "Profile evidence" in shown
