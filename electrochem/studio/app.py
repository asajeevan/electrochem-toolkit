"""Cyclara: the main window.

Layout (U01 section 4, adapted for cycling):

    top bar     open, undo/redo, search actions, readiness, theme, export
    left        files with their state in words
    centre      record title, view switcher, the view, the cycle strip, results
    right       inspector: questions, this record, the focused cycle, how the file was read

One selection (record, cycles, focused cycle) drives every view and table.
Every answer is one undo step and one Activity line, and re-analyses in the
background; a result is shown only for the answers it was computed from.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QProcess, QProcessEnvironment, QRectF, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QActionGroup, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap,
                           QUndoCommand, QUndoStack)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMenuBar, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QToolButton, QVBoxLayout,
                               QWidget)

from .. import __author__, __url__, __version__, methods_text, origin_export, workflow
from ..cycling import cycle_capacity
from ..metadata import _raw_header, exported_from
from ..readers import is_eclab, looks_tabular
from ..workflow import DEFAULT_CYCLES, EC_LAB_DEFAULT_MASS_MG, parse_cycles
from . import brand, platform_support, theme, worker
from .figures import FigureStudio
from .help_dialogs import CiteDialog, MethodsDialog
from .mapping import MappingPage
from .motion import (DropOverlay, FadeStack, Ignition, IngestScreen, Motion, Reactor, Ripple, Sweep, ThemeReveal,
                     animate)
from .inspector import Inspector
from .model import Answers, Record, open_questions, settings_for
from .palette import Palette
from .strip import CycleStrip, compress
from .tables import Results
from .views import (CapacityView, DataView, DifferentialView, EvolutionView, OverviewView, ProfilesView, TimelineView,
                    VoltageView, capacity_unit, ref_text)

APP_NAME = brand.APP_NAME
STORE = "electrochem-toolkit"


# ------------------------------------------------------------------ undo
class AnswerCommand(QUndoCommand):
    """One answer (or a set given together) for one file.

    Undo and redo act on the file the answer belongs to, which may not be the
    one on screen: that file is brought on screen first, so a change is never
    made out of sight (review finding r09). The first redo is the answer being
    given, so it never switches files.
    """

    def __init__(self, win, rec, new: dict, text: str | None = None, restore=False):
        old = {k: getattr(rec.answers, k) for k in new}
        names = ", ".join(k.replace("_", " ") for k in new)
        super().__init__(text or f"Set {names}")
        self.win, self.rec, self.old, self.new = win, rec, old, new
        self.restore = restore                   # restoring a session's answers: the inspector says so
        self._given = False

    def redo(self):
        if self._given:
            self.win._bring_forward(self.rec)
        self._given = True
        if self.restore:
            self.rec.restored = True
        self.win._apply_answers(self.rec, self.new)

    def undo(self):
        self.win._bring_forward(self.rec)
        if self.restore:
            self.rec.restored = False
        self.win._apply_answers(self.rec, self.old, undo=True)


# ------------------------------------------------------------------ small pieces
def app_icon() -> QIcon:
    """The app icon at every size the platforms ask for, from the bundled renders."""
    ic = QIcon()
    for sz in (16, 24, 32, 48, 64, 128, 256, 512):
        f = brand.ASSETS / f"cyclara_{sz}.png"
        if f.exists():
            ic.addFile(str(f), QSize(sz, sz))
    if ic.isNull():
        ic = QIcon(QPixmap.fromImage(brand.icon_image(256)))
    return ic


def mark_pixmap(size: int) -> QPixmap:
    """The bare mark in the current theme's colours, for the top bar and the home screen."""
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(2)
    p = QPainter(pm)
    brand.draw_mark(p, QRectF(0, 0, size, size), dark=theme.tokens().name == "dark",
                    detail="small" if size <= 32 else "full")
    p.end()
    return pm


class FileList(QListWidget):
    filesDropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(False)             # drops are handled by the window, which shows the scanner
        self.setAccessibleName("Open files")
        self.setTextElideMode(Qt.ElideMiddle)


class EmptyPage(QWidget):
    """Home: the live mark, the name, the two ways in, the four steps and recent files."""

    def __init__(self, win):
        super().__init__()
        self.setObjectName("Frame")
        self.win = win
        outer = QHBoxLayout(self); outer.setContentsMargins(40, 30, 40, 30); outer.setSpacing(48)
        outer.addStretch(1)
        left = QVBoxLayout(); left.setSpacing(10); left.setAlignment(Qt.AlignVCenter)
        self.reactor = Reactor(calm=True)
        self.reactor.setFixedSize(250, 250)
        left.addWidget(self.reactor, 0, Qt.AlignHCenter)
        name = QLabel(APP_NAME); name.setAlignment(Qt.AlignHCenter)
        name.setStyleSheet(theme.css(f"font-family: '{theme.DISPLAY}'; font-size: 26pt; font-weight: 600; "
                                     "letter-spacing: 6px;"))
        left.addWidget(name)
        tag = QLabel(brand.TAGLINE); tag.setProperty("role", "secondary"); tag.setAlignment(Qt.AlignHCenter)
        left.addWidget(tag)
        outer.addLayout(left)

        card = QFrame(); card.setObjectName("Panel"); card.setMinimumWidth(450); card.setMaximumWidth(560)
        lay = QVBoxLayout(card); lay.setContentsMargins(32, 28, 32, 26); lay.setSpacing(12)
        title = QLabel("Drop a cycling file anywhere"); title.setProperty("role", "title")
        title.setWordWrap(True)
        lay.addWidget(title)
        sub = QLabel("EC-Lab .mpr or .mpt, the text or Excel export of another cycler (Arbin, Neware, Maccor and "
                     "the rest), or a whole experiment folder. Files are read, never changed.")
        sub.setProperty("role", "secondary"); sub.setWordWrap(True)
        lay.addWidget(sub)
        row = QHBoxLayout()
        self.b1 = b1 = QPushButton("Open a file"); b1.setProperty("kind", "primary")
        b1.clicked.connect(win.open_files)
        self.b2 = b2 = QPushButton("Open a folder"); b2.clicked.connect(win.open_folder)
        self.b3 = b3 = QPushButton("Try the demonstration"); b3.setProperty("kind", "ghost")
        b3.setToolTip("A synthetic 50-cycle cell that shows every step; nothing measured")
        b3.clicked.connect(win.open_demo)
        b3.setVisible(DEMO_FILE.exists())
        row.addWidget(b1); row.addWidget(b2); row.addWidget(b3); row.addStretch(1)
        lay.addLayout(row)
        lay.addSpacing(8)
        steps = QLabel("How a session runs")
        steps.setProperty("role", "section"); lay.addWidget(steps)
        for k, (head, text) in enumerate([
                ("Open", "The file is read and segmented into charge and discharge branches."),
                ("Answer", "Three questions only you can answer: current direction, what the potential means, the mass."),
                ("Review", "Every value with its state. Pick cycles on the strip; hover any curve for the measured point."),
                ("Export", "Journal-sized figures that pass their checks, every table, and an Origin folder.")], 1):
            r = QHBoxLayout(); r.setSpacing(12)
            n = QLabel(str(k)); n.setFixedWidth(22); n.setAlignment(Qt.AlignTop | Qt.AlignRight)
            n.setProperty("role", "secondary"); n.setStyleSheet("font-weight: 600;")
            l = QLabel(f"<b>{head}</b>&nbsp;&nbsp;{text}"); l.setWordWrap(True); l.setTextFormat(Qt.RichText)
            r.addWidget(n); r.addWidget(l, 1)
            lay.addLayout(r)
        self.recent = QVBoxLayout(); self.recent.setSpacing(2)
        lay.addSpacing(6)
        lay.addLayout(self.recent)
        right = QVBoxLayout(); right.setAlignment(Qt.AlignVCenter)
        right.addWidget(card)
        outer.addLayout(right)
        outer.addStretch(1)
        self.restyle()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        side = int(max(150, min(250, (self.width() - 600) * 0.45)))
        if self.reactor.width() != side:
            self.reactor.setFixedSize(side, side)

    def restyle(self):
        self.b1.setIcon(theme.icon("file", theme.tokens().primary_text))
        self.b2.setIcon(theme.icon("folder"))
        self.reactor.update()

    def set_recent(self, paths):
        while self.recent.count():
            w = self.recent.takeAt(0).widget()
            if w:
                w.deleteLater()
        paths = [p for p in paths if Path(p).exists()][:5]
        if not paths:
            return
        h = QLabel("Recent"); h.setProperty("role", "section"); self.recent.addWidget(h)
        for p in paths:
            b = QPushButton(Path(p).name); b.setProperty("kind", "ghost"); b.setToolTip(p)
            b.setStyleSheet("text-align: left;")
            b.clicked.connect(lambda _=False, p=p: self.win.open_paths([Path(p)]))
            self.recent.addWidget(b)


class Toast(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Panel")
        lay = QHBoxLayout(self); lay.setContentsMargins(14, 10, 10, 10); lay.setSpacing(10)
        self.text = QLabel(""); self.text.setWordWrap(True); self.text.setMaximumWidth(460)
        lay.addWidget(self.text, 1)
        self.buttons = QHBoxLayout(); lay.addLayout(self.buttons)
        close = QToolButton(); close.setIcon(theme.icon("close")); close.setToolTip("Dismiss")
        close.clicked.connect(self.hide); lay.addWidget(close)
        self.hide()

    def show_message(self, text, actions=()):
        self.text.setText(text)
        while self.buttons.count():
            w = self.buttons.takeAt(0).widget()
            if w:
                w.deleteLater()
        for label, fn in actions:
            b = QPushButton(label); b.clicked.connect(fn); self.buttons.addWidget(b)
        self.adjustSize()
        p = self.parent()
        x, y = p.width() - self.width() - 24, p.height() - self.height() - 46
        self.show(); self.raise_()
        lift = 24 if Motion.moving() else 0

        def step(v):
            self.move(x, int(y + lift * (1 - v)))
        animate(self, Motion.ms(260), step, None, QEasingCurve.OutCubic)


# ------------------------------------------------------------------ window
VIEWS = [("Overview", OverviewView), ("Profiles", ProfilesView), ("Capacity", CapacityView),
         ("dQ/dE", DifferentialView), ("Evolution", EvolutionView), ("Voltage", VoltageView), ("Timeline", TimelineView),
         ("Data", DataView)]
ISSUES = f"{__url__}/issues"
# what the window opens: EC-Lab files, and the text or workbook exports of any other cycler
DATA_SUFFIXES = (".mpr", ".mpt", ".cex", ".txt", ".csv", ".tsv", ".dat", ".xlsx", ".xlsm", ".xls", ".nda", ".ndax", ".res")
ERROR_LOG = Path.home() / ".electrochem-toolkit-errors.log"
ROOT = Path(__file__).resolve().parents[2]                     # the toolkit folder: data/demo lives beside electrochem/
DEMO_FILE = ROOT / "data" / "demo" / "cyclara_demo_synthetic.mpt"


def sc(seq) -> str:
    """A shortcut as this platform writes it: Ctrl+K on Windows and Linux, the command-key glyph on macOS."""
    return platform_support.shortcut_text(seq)


def styled_menu(m: QMenu) -> QMenu:
    """Qt-drawn menus get the rounded panel of the style sheet. On Windows and macOS the corners outside
    the rounding are made transparent; on Linux a compositor cannot be assumed, so they stay square."""
    if platform_support.IS_WINDOWS or platform_support.IS_MAC:
        m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        m.setAttribute(Qt.WA_TranslucentBackground, True)
    return m


def _duration(hours: float) -> str:
    """70 h, 5.2 h, 25 min, 40 s: never "0 h" for a short run (review finding 27)."""
    if hours >= 10:
        return f"{hours:.0f} h"
    if hours >= 1:
        return f"{hours:.1f} h"
    if hours * 60 >= 1:
        return f"{hours * 60:.0f} min"
    return f"{hours * 3600:.0f} s"


def _size_text(n: int | None) -> str:
    if not n:
        return ""
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{max(n / 1e3, 0.1):.0f} kB"


class SelfCheck(QDialog):
    """Help > Check this installation: the toolkit's own test suite, run by the installed interpreter
    in a separate process, with the outcome shown in plain words. The same tests the author runs;
    passing them means the arithmetic, the readers and the window behave here as they did there."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Check this installation")
        self.setModal(False)
        self.resize(640, 420)
        self.proc = None
        self.total_done = 0
        lay = QVBoxLayout(self); lay.setContentsMargins(28, 22, 28, 20); lay.setSpacing(10)
        self.head = QLabel("Running the self-tests"); self.head.setProperty("role", "title")
        lay.addWidget(self.head)
        self.text = QLabel("Every calculation, reader and screen is tried once with the Python and the packages "
                           "installed here. It takes a few minutes; Cyclara stays usable meanwhile.")
        self.text.setProperty("role", "secondary"); self.text.setWordWrap(True)
        lay.addWidget(self.text)
        self.bar = QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0); self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.out = QPlainTextEdit(); self.out.setReadOnly(True)
        self.out.setStyleSheet(theme.css("font-family: 'Consolas', 'Menlo', monospace; font-size: 8.5pt;"))
        lay.addWidget(self.out, 1)
        row = QHBoxLayout(); row.addStretch(1)
        self.copy = QPushButton("Copy the report"); self.copy.clicked.connect(self._copy); self.copy.setEnabled(False)
        self.close_btn = QPushButton("Stop"); self.close_btn.clicked.connect(self.close)
        row.addWidget(self.copy); row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.tests = ROOT / "tests"
        self.command = [sys.executable, "-I", "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "--rootdir", str(ROOT), str(self.tests)]

    def start(self):
        if not (self.tests / "test_cycling.py").exists():
            self._finish(None, "The self-tests are not part of this installation.")
            return
        self.proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("QT_QPA_PLATFORM", "offscreen")             # the window tests draw into memory, not on screen
        env.insert("PYTHONDONTWRITEBYTECODE", "1")
        self.proc.setProcessEnvironment(env)
        self.proc.setWorkingDirectory(str(ROOT))
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(lambda code, _status: self._finish(code))
        self.proc.errorOccurred.connect(lambda _e: self._finish(None, "The test runner could not be started."))
        self.proc.start(self.command[0], self.command[1:])
        self.out.appendPlainText(" ".join(Path(self.command[0]).name if k == 0 else c for k, c in enumerate(self.command)))

    def _read(self):
        chunk = bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.out.appendPlainText(chunk.rstrip("\n"))
        for m in re.finditer(r"\[\s*(\d+)%\]", chunk):
            self.bar.setValue(int(m.group(1)))
        self.out.verticalScrollBar().setValue(self.out.verticalScrollBar().maximum())

    def _finish(self, code, message=None):
        self.close_btn.setText("Close")
        self.copy.setEnabled(True)
        if message:
            self.head.setText("Could not check"); self.text.setText(message)
            return
        self.bar.setValue(100)
        last = [l for l in self.out.toPlainText().splitlines() if "passed" in l or "failed" in l or "error" in l]
        summary = last[-1].strip() if last else f"exit code {code}"
        if code == 0:
            self.head.setText("Everything passed")
            self.text.setText(f"{summary}. This installation behaves as the author's did; the figures and tables "
                              "it produces are the ones the tests check.")
        else:
            self.head.setText("Something did not pass")
            self.text.setText(f"{summary}. Copy the report and send it with Help > Report a problem; say which "
                              "computer and Windows or macOS version this is.")
            self.head.setProperty("role", "error")
        for w in (self.head, self.text):
            w.style().unpolish(w); w.style().polish(w)

    def _copy(self):
        QApplication.clipboard().setText(self.out.toPlainText())

    def closeEvent(self, e):
        if self.proc is not None and self.proc.state() != QProcess.NotRunning:
            self.proc.kill()
        super().closeEvent(e)


class OriginSetup(QDialog):
    """Help > Set up the Origin link: installs the originpro package into the Python that runs Cyclara,
    which is what 'Build Origin project' needs. Origin itself (2021 or later, Windows) must already be
    installed; originpro is the bridge OriginLab publishes on PyPI."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Set up the Origin link")
        self.setModal(False)
        self.resize(600, 380)
        self.proc = None
        lay = QVBoxLayout(self); lay.setContentsMargins(28, 22, 28, 20); lay.setSpacing(10)
        self.head = QLabel("Installing the Origin link"); self.head.setProperty("role", "title")
        lay.addWidget(self.head)
        self.text = QLabel("This adds OriginLab's originpro package to Cyclara's own Python (an internet connection is "
                           "needed once). With it, Export offers \"Build Origin project\", which opens Origin, imports "
                           "every table, draws the graphs and saves the .opju next to the figures. Origin 2021 or later "
                           "must be installed on this PC; Origin exists for Windows only.")
        self.text.setProperty("role", "secondary"); self.text.setWordWrap(True)
        lay.addWidget(self.text)
        self.out = QPlainTextEdit(); self.out.setReadOnly(True)
        self.out.setStyleSheet(theme.css("font-family: 'Consolas', 'Menlo', monospace; font-size: 8.5pt;"))
        lay.addWidget(self.out, 1)
        row = QHBoxLayout(); row.addStretch(1)
        self.close_btn = QPushButton("Cancel"); self.close_btn.clicked.connect(self.close)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.command = [sys.executable, "-I", "-X", "utf8", "-m", "pip", "install", "--disable-pip-version-check",
                        "originpro"]

    def start(self):
        if not platform_support.IS_WINDOWS and os.environ.get("CYCLARA_ORIGIN_ANYWHERE") is None:
            self._finish(None, "Origin runs on Windows only. On this computer the Origin folder still holds every "
                               "table in Origin's import layout and the build script, for a Windows PC with Origin.")
            return
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(lambda code, _status: self._finish(code))
        self.proc.errorOccurred.connect(lambda _e: self._finish(None, "pip could not be started."))
        self.proc.start(self.command[0], self.command[1:])
        self.out.appendPlainText(Path(self.command[0]).name + " " + " ".join(self.command[1:]))

    def _read(self):
        self.out.appendPlainText(bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace").rstrip("\n"))
        self.out.verticalScrollBar().setValue(self.out.verticalScrollBar().maximum())

    def _finish(self, code, message=None):
        self.close_btn.setText("Close")
        if message:
            self.head.setText("Not set up"); self.text.setText(message)
            return
        if code == 0:
            self.head.setText("The Origin link is ready")
            self.text.setText("Export a file, then click \"Build Origin project\" in the message that follows: Origin "
                              "opens, imports the tables, draws the graphs and saves the project next to the figures.")
        else:
            self.head.setText("Could not install the Origin link")
            self.text.setText(f"pip returned code {code}. The usual reasons: no internet connection, or a proxy. "
                              "The Origin folder of every export still holds the tables and the build script; "
                              "the README in it explains the manual route.")
            self.head.setProperty("role", "error")
            self.head.style().unpolish(self.head); self.head.style().polish(self.head)

    def closeEvent(self, e):
        if self.proc is not None and self.proc.state() != QProcess.NotRunning:
            self.proc.kill()
        super().closeEvent(e)


class AboutDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setModal(True)
        self.setFixedWidth(480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 28, 40, 24)
        lay.setSpacing(4)
        self.reactor = Reactor(calm=True)
        self.reactor.setFixedSize(132, 132)
        lay.addWidget(self.reactor, 0, Qt.AlignHCenter)
        lay.addSpacing(6)
        name = QLabel(APP_NAME)
        name.setAlignment(Qt.AlignHCenter)
        name.setStyleSheet(theme.css(f"font-family: '{theme.DISPLAY}'; font-size: 20pt; font-weight: 600; "
                                     "letter-spacing: 3px;"))
        lay.addWidget(name)
        for text, role in ((brand.TAGLINE, "secondary"), (f"Version {__version__}", "muted")):
            lab = QLabel(text); lab.setProperty("role", role); lab.setAlignment(Qt.AlignHCenter)
            lay.addWidget(lab)
        lay.addSpacing(14)
        who = QLabel(f"Created by {__author__}")
        who.setAlignment(Qt.AlignHCenter)
        who.setStyleSheet(theme.css("font-size: 10.5pt; font-weight: 600;"))
        lay.addWidget(who)
        lay.addSpacing(6)
        about = QLabel("Free software under the GNU General Public License, version 3 or later. Reads BioLogic "
                       "EC-Lab .mpr and .mpt files and the text or spreadsheet exports of other cyclers; not "
                       "affiliated with any instrument maker.")
        about.setProperty("role", "secondary"); about.setWordWrap(True); about.setAlignment(Qt.AlignHCenter)
        lay.addWidget(about)                       # no alignment flag: a wrapping label then gets its full height
        fonts = QLabel("Type: Inter by Rasmus Andersson, under the SIL Open Font License.")
        fonts.setProperty("role", "muted"); fonts.setWordWrap(True); fonts.setAlignment(Qt.AlignHCenter)
        lay.addWidget(fonts)
        lay.addSpacing(16)
        row = QHBoxLayout()
        row.addStretch(1)
        src = QPushButton("Source code")
        src.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(__url__)))
        rep = QPushButton("Report a problem")
        rep.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ISSUES)))
        cite = QPushButton("How to cite")
        cite.clicked.connect(lambda: (self.accept(), parent.cite()) if hasattr(parent, "cite") else None)
        ok = QPushButton("Close"); ok.setProperty("kind", "primary"); ok.setDefault(True)
        ok.clicked.connect(self.accept)
        for b in (src, rep, cite, ok):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)


class MainWindow(QMainWindow):
    def __init__(self, store: str = STORE):
        super().__init__()
        self.settings = QSettings(store, "studio")
        self.records: list[Record] = []
        self.rec: Record | None = None
        self._ingesting: Record | None = None      # the file the reading screen is telling about
        self._intro: Ignition | None = None
        self._drop_window = None
        self._drop_ok = False
        self.undo = QUndoStack(self)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        # a 1920 x 1080 laptop screen at 150 % scaling is 1280 x 720, about 1280 x 640 inside the window frame
        self.setMinimumSize(1024, 600)
        self.setAcceptDrops(True)
        self._height_class = None                  # "tall", "short" or "low": what the layout last adapted to
        self._auto_folded = False                  # the tables were folded by a short window, not by the user
        self._auto_folding = False
        self._files_shown_for = 0                  # the file count the file list last appeared for
        worker.collect_on_gui_thread()
        self._build()
        self._actions()
        self._menus()
        self.drop = DropOverlay(self)
        self._update_chrome()
        self.empty.set_recent(self._recent())
        self._panels()
        self.resize(*self.comfortable_size())
        QTimer.singleShot(0, self._initial_focus)

    DEFAULT_SIZE = (1480, 920)

    def comfortable_size(self, screen=None) -> tuple[int, int]:
        """1480 x 920 where it fits with room around it, otherwise as much of the screen as is free,
        never less than the minimum size (a laptop at 125 or 150 % scaling has 1280 to 1536 points)."""
        scr = screen or self.screen() or QApplication.primaryScreen()
        w, h = self.DEFAULT_SIZE
        if scr is None:
            return w, h
        a = scr.availableGeometry()
        return (max(self.minimumWidth(), min(w, a.width() - 48)),
                max(self.minimumHeight(), min(h, a.height() - 72)))     # 72: the title bar and some air

    def screen_is_small(self, screen=None) -> bool:
        """True when the default size would not fit with room around it: start maximised there."""
        scr = screen or self.screen() or QApplication.primaryScreen()
        if scr is None:
            return False
        a = scr.availableGeometry()
        return a.width() < self.DEFAULT_SIZE[0] + 48 or a.height() < self.DEFAULT_SIZE[1] + 72

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())   # size, place and maximised state, for next time
        super().closeEvent(e)

    def _initial_focus(self):
        (self._intro or self.files).setFocus(Qt.OtherFocusReason)

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange and hasattr(self, "act"):
            self.act["fullscreen"].setChecked(self.isFullScreen())    # also when the system leaves full screen

    # ---------------------------------------------------------------- layout
    def _build(self):
        root = QWidget(); root.setObjectName("Frame")
        self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        # top bar: the mark (About), the menus (in the bar on Windows and Linux, in the system bar on macOS),
        # opening, undo, search, the readiness pill, theme and export
        bar = QWidget(); bar.setObjectName("Bar"); bar.setFixedHeight(54)
        b = QHBoxLayout(bar); b.setContentsMargins(10, 8, 14, 8); b.setSpacing(6)
        self.mark = QToolButton()
        self.mark.setIconSize(QSize(26, 26))
        self.mark.setStyleSheet("padding: 3px;")
        self.mark.setToolTip(f"About {APP_NAME}")
        self.mark.setAccessibleName(f"About {APP_NAME}")
        self.mark.clicked.connect(self.about)
        b.addWidget(self.mark)
        self.name = QLabel(APP_NAME)
        self.name.setStyleSheet(theme.css(f"font-family: '{theme.DISPLAY}'; font-weight: 600; font-size: 12pt; "
                                          "letter-spacing: 1px;"))
        b.addWidget(self.name)
        b.addSpacing(8)
        self.menubar = QMenuBar()
        if platform_support.IS_MAC:
            self.setMenuBar(self.menubar)              # the system menu bar at the top of the screen
        else:
            self.menubar.setNativeMenuBar(False)
            self.menubar.setObjectName("Inline")       # in the top bar: no extra row above it
            b.addWidget(self.menubar, 0, Qt.AlignVCenter)
            b.addSpacing(6)
        self.btn_open = self._tool("Open", "file", self.open_files, f"Open files ({sc(QKeySequence.Open)})")
        self.btn_folder = self._tool("Folder", "folder", self.open_folder, f"Open a folder ({sc('Ctrl+Shift+O')})")
        b.addWidget(self.btn_open); b.addWidget(self.btn_folder)
        b.addSpacing(4)
        self.btn_undo = self._tool("", "undo", self.undo.undo, f"Undo ({sc(QKeySequence.Undo)})")
        self.btn_redo = self._tool("", "redo", self.undo.redo, f"Redo ({sc(QKeySequence.Redo)})")
        b.addWidget(self.btn_undo); b.addWidget(self.btn_redo)
        self.undo.canUndoChanged.connect(self.btn_undo.setEnabled)
        self.undo.canRedoChanged.connect(self.btn_redo.setEnabled)
        self.btn_undo.setEnabled(False); self.btn_redo.setEnabled(False)
        b.addSpacing(8)
        self.search = QPushButton("  Search actions")
        self.search.setMinimumWidth(220)
        self.search.setStyleSheet("text-align: left;")
        self.search.setToolTip(f"Every action by name ({sc('Ctrl+K')})")
        self.search.clicked.connect(self.show_palette)
        self.search_key = QLabel(sc("Ctrl+K")); self.search_key.setProperty("role", "muted")
        b.addWidget(self.search); b.addWidget(self.search_key)
        b.addStretch(1)
        self.pill = QPushButton("No file open"); self.pill.setProperty("kind", "pill"); self.pill.setProperty("state", "busy")
        self.pill.clicked.connect(self._pill_clicked)
        b.addWidget(self.pill)
        self.btn_theme = self._tool("", "moon", self.toggle_theme, f"Light or dark theme ({sc('Ctrl+Shift+L')})")
        b.addWidget(self.btn_theme)
        self.btn_export = QPushButton("Export"); self.btn_export.setProperty("kind", "primary")
        self.btn_export.setToolTip(f"Export figures and tables ({sc('Ctrl+E')})")
        self.btn_export.clicked.connect(lambda: self.export(None))
        b.addWidget(self.btn_export)
        v.addWidget(bar)

        # body
        split = QSplitter(Qt.Horizontal); split.setHandleWidth(6); split.setChildrenCollapsible(False)
        body = QWidget(); body.setObjectName("Frame")
        bl = QHBoxLayout(body); bl.setContentsMargins(10, 10, 10, 6); bl.addWidget(split)
        v.addWidget(body, 1)

        left = QFrame(); left.setObjectName("Panel"); left.setMinimumWidth(210); left.setMaximumWidth(340)
        self.left_panel = left
        ll = QVBoxLayout(left); ll.setContentsMargins(8, 10, 8, 8); ll.setSpacing(6)
        lh = QLabel("Files"); lh.setProperty("role", "h2"); lh.setContentsMargins(6, 0, 0, 0); ll.addWidget(lh)
        self.files = FileList()
        self.files.currentRowChanged.connect(self._file_selected)
        self.files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._file_menu)
        ll.addWidget(self.files, 1)
        split.addWidget(left)

        # centre: home (0), the workspace (1), the reading screen (2)
        self.centre = FadeStack()
        self.empty = EmptyPage(self)
        self.centre.addWidget(self.empty)
        work = QWidget(); work.setObjectName("Frame")
        wl = QVBoxLayout(work); wl.setContentsMargins(6, 0, 6, 0); wl.setSpacing(8)
        tl = QVBoxLayout(); tl.setSpacing(1)
        self.title = QLabel(""); self.title.setProperty("role", "title")
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.meta = QLabel(""); self.meta.setProperty("role", "secondary")
        self.meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tl.addWidget(self.title); tl.addWidget(self.meta)
        wl.addLayout(tl)
        head = QHBoxLayout(); head.setContentsMargins(0, 2, 0, 0)
        seg = QWidget(); seg.setObjectName("Segmented")
        sg = QHBoxLayout(seg); sg.setContentsMargins(3, 3, 3, 3); sg.setSpacing(2)
        self.view_buttons = QButtonGroup(self)
        names = [n for n, _ in VIEWS] + ["Figures"]
        for k, n in enumerate(names):
            tb = QToolButton(); tb.setText(n); tb.setCheckable(True); tb.setChecked(k == 0)
            tb.setToolTip(f"{n} ({sc(f'Ctrl+{k + 1}')})")
            tb.setMinimumWidth(tb.fontMetrics().horizontalAdvance(n) + 30)
            if n == "Figures":
                tb.setIcon(theme.icon("figure")); tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                tb.setMinimumWidth(tb.fontMetrics().horizontalAdvance(n) + 54)
                self.figures_button = tb
            tb.clicked.connect(lambda _=False, k=k: self.show_view(k))
            self.view_buttons.addButton(tb, k); sg.addWidget(tb)
        head.addWidget(seg)
        head.addSpacing(10)
        self.stale = QLabel("Updating for your last answer: until it is done, plots and tables show your previous answers")
        self.stale.setProperty("role", "provisional")
        self.stale.setWordWrap(True)
        self.stale.hide()
        head.addWidget(self.stale, 1)
        head.addStretch(0)
        wl.addLayout(head)

        vsplit = QSplitter(Qt.Vertical); vsplit.setHandleWidth(6); vsplit.setChildrenCollapsible(False)
        self.vsplit = vsplit
        upper = QFrame(); upper.setObjectName("Panel")
        ul = QVBoxLayout(upper); ul.setContentsMargins(12, 10, 12, 8); ul.setSpacing(6)
        self.stack = FadeStack()
        self.views = []
        for n, cls in VIEWS:
            w = cls()
            w.focusRequested.connect(self.set_focus_cycle)
            self.views.append(w)
            self.stack.addWidget(w)
        self.studio = FigureStudio()
        self.studio.exportRequested.connect(self.export)
        self.studio.status.connect(self._status)
        self.stack.addWidget(self.studio)
        ul.addWidget(self.stack, 1)
        # cycle strip row
        self.strip_row = QWidget()
        sr = QVBoxLayout(self.strip_row); sr.setContentsMargins(0, 4, 0, 0); sr.setSpacing(4)
        ctl = QHBoxLayout(); ctl.setSpacing(6)
        sl = QLabel("Cycles"); sl.setProperty("role", "h2"); ctl.addWidget(sl)
        self.strip_hint = QLabel("click to add or remove, drag for a range, double-click to focus")
        self.strip_hint.setProperty("role", "muted"); ctl.addWidget(self.strip_hint)
        ctl.addStretch(1)
        self.expr = QLineEdit(); self.expr.setMinimumWidth(240); self.expr.setMaximumWidth(380)
        self.expr.setPlaceholderText("1, 2, 5:10, -1   (-1 is the last cycle)")
        self.expr.setAccessibleName("Cycles to show, as a list")
        self.expr.setToolTip("Cycle numbers and ranges: 5:10 is 5 to 10, 0:100:10 every tenth, -1 the last cycle")
        self.expr.editingFinished.connect(self._expr_changed)
        ctl.addWidget(self.expr)
        preset = QToolButton(); preset.setText("Presets"); preset.setPopupMode(QToolButton.InstantPopup)
        self.preset_button = preset
        m = styled_menu(QMenu(preset))
        for text, spec in (("Default: 1, 2, 5, 10, 20, 50, 100", DEFAULT_CYCLES), ("First and last", "1,-1"),
                           ("First five", "1:5"), ("Every tenth", "1,10:100000:10,-1"), ("Last five", "-5:-1"),
                           ("Every cycle", "1:100000")):
            m.addAction(text, lambda spec=spec: self.set_cycles_spec(spec))
        preset.setMenu(m)
        ctl.addWidget(preset)
        sr.addLayout(ctl)
        self.strip = CycleStrip()
        self.strip.selectionChanged.connect(self._strip_selection)
        self.strip.focusChanged.connect(self.set_focus_cycle)
        sr.addWidget(self.strip)
        ul.addWidget(self.strip_row)
        vsplit.addWidget(upper)
        lower = QFrame(); lower.setObjectName("Panel")
        self.lower = lower
        lo = QVBoxLayout(lower); lo.setContentsMargins(8, 4, 8, 8)
        self.results = Results()
        self.results.cycleActivated.connect(self.set_focus_cycle)
        self.results.collapsedChanged.connect(self._tables_folded)
        lo.addWidget(self.results)
        vsplit.addWidget(lower)
        vsplit.setSizes([640, 220])
        vsplit.setStretchFactor(0, 3)
        wl.addWidget(vsplit, 1)
        self.centre.addWidget(work)
        self.ingest = IngestScreen()
        self.centre.addWidget(self.ingest)
        self.mapping = MappingPage()                   # 3: an unrecognised instrument's columns, to map once
        self.mapping.confirmed.connect(self._mapping_confirmed)
        self.centre.addWidget(self.mapping)
        split.addWidget(self.centre)

        self.inspector = Inspector()
        self.inspector.answersChanged.connect(self._answer)
        self.inspector.clearRestored.connect(self._clear_restored)
        split.addWidget(self.inspector)
        split.setSizes([250, 900, 340])
        split.setStretchFactor(1, 1)

        # status bar
        sb = self.statusBar()
        self.status_text = QLabel("Ready"); sb.addWidget(self.status_text, 1)
        self.busy = QProgressBar(); self.busy.setRange(0, 0); self.busy.setMaximumWidth(120); self.busy.hide()
        sb.addPermanentWidget(self.busy)
        sb.addPermanentWidget(QLabel(f"{APP_NAME} {__version__} by {__author__}"))
        self.toast = Toast(self)

        # tab order: files -> questions -> views -> cycles -> results (P12 review finding 10, review r24).
        # The inspector chains its own controls between the file list and the first view button
        # every time it is rebuilt.
        buttons = [self.view_buttons.button(k) for k in range(len(VIEWS) + 1)]
        self.inspector.set_tab_neighbours(self.files, buttons[0])
        order = [self.files, *buttons, self.expr, self.preset_button, self.strip, self.results]
        for a, b in zip(order, order[1:]):
            QWidget.setTabOrder(a, b)
        self._restyle_chrome()

    def _tool(self, text, icon_name, fn, tip):
        b = QToolButton(); b.setText(text); b.setIconSize(QSize(18, 18))
        b.setProperty("icon_name", icon_name)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if text else Qt.ToolButtonIconOnly)
        b.setToolTip(tip); b.setAccessibleName(tip.split(" (")[0]); b.clicked.connect(fn)
        return b

    def _compact_switcher(self, compact: bool):
        """Narrow windows: the view buttons lose padding rather than the last one being cut off."""
        if getattr(self, "_compact", None) == compact:
            return
        self._compact = compact
        seg = self.view_buttons.buttons()[0].parentWidget()
        seg.layout().setSpacing(1 if compact else 2)
        seg.layout().setContentsMargins(*((2, 3, 2, 3) if compact else (3, 3, 3, 3)))
        for b in self.view_buttons.buttons():
            b.setProperty("compact", compact)
            b.style().unpolish(b); b.style().polish(b)
            extra = (12 if compact else 30) + (24 if b is self.figures_button else 0)
            b.setMinimumWidth(b.fontMetrics().horizontalAdvance(b.text()) + extra)

    def _restyle_chrome(self):
        """Everything in the frame whose colour is drawn rather than styled: icons and the mark."""
        t = theme.tokens()
        self.mark.setIcon(QIcon(mark_pixmap(26)))
        for b in (self.btn_open, self.btn_folder, self.btn_undo, self.btn_redo):
            b.setIcon(theme.icon(b.property("icon_name")))
        self.search.setIcon(theme.icon("search"))
        self.btn_export.setIcon(theme.icon("export", t.primary_text))
        self.btn_theme.setIcon(theme.icon("sun" if t.name == "dark" else "moon"))
        self.figures_button.setIcon(theme.icon("figure"))
        self.empty.restyle()

    # ---------------------------------------------------------------- actions and menus
    def _actions(self):
        self.all_actions = []                  # what the command palette lists
        A = self.act = {}

        def act(key, text, shortcut, fn, role=QAction.NoRole, palette=True, checkable=False):
            a = QAction(text, self)
            if isinstance(shortcut, QKeySequence.StandardKey):
                a.setShortcuts(shortcut)
            elif isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(x) for x in shortcut])
            elif shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setMenuRole(role)                # nothing is moved to the macOS app menu by its wording alone
            a.setCheckable(checkable)
            a.setToolTip(text)
            a.triggered.connect(fn)
            self.addAction(a)
            A[key] = a
            if palette:
                self.all_actions.append(a)
            return a

        act("open", "Open files…", QKeySequence.Open, lambda: self.open_files())
        act("folder", "Open a folder…", "Ctrl+Shift+O", lambda: self.open_folder())
        act("export", "Export figures and tables…", "Ctrl+E", lambda: self.export(None))
        act("close", "Close the selected file", QKeySequence.Close, lambda: self.close_record())
        act("quit", "Exit" if platform_support.IS_WINDOWS else f"Quit {APP_NAME}", QKeySequence.Quit,
            lambda: self.close(), role=QAction.QuitRole, palette=False)
        undo = self.undo.createUndoAction(self, "Undo")
        undo.setShortcuts(QKeySequence.Undo); undo.setMenuRole(QAction.NoRole)
        redo = self.undo.createRedoAction(self, "Redo")
        redo.setShortcuts(QKeySequence.Redo); redo.setMenuRole(QAction.NoRole)
        for key, a in (("undo", undo), ("redo", redo)):
            self.addAction(a); A[key] = a; self.all_actions.append(a)
        act("copy", "Copy the selected table rows", "", lambda: self.results.currentWidget().copy()
            if hasattr(self.results.currentWidget(), "copy") else None)
        act("all", "Use these answers for every open file", "", lambda: self.answers_to_all())
        act("next_q", "Answer the next question", "Ctrl+Return", lambda: self._pill_clicked())
        act("again", "Analyse again", ["F5", "Ctrl+R"], lambda: self.request_analysis(self.rec) if self.rec else None)
        act("search", "Search actions…", "Ctrl+K", lambda: self.show_palette())
        for k, (n, _) in enumerate(VIEWS + [("Figures", None)]):
            act(f"view{k}", f"Show {n}", f"Ctrl+{k + 1}", lambda _=False, k=k: self.show_view(k))
        act("fit", "Fit the data in view", "A", lambda: self.fit_view())
        act("tables", "Show the tables", "Ctrl+J", lambda on: self.toggle_tables(on), checkable=True)
        A["tables"].setChecked(True)
        act("prev", "Previous cycle", "[", lambda: self.step_focus(-1))
        act("next", "Next cycle", "]", lambda: self.step_focus(1))
        self._cycle_keys = []
        for k, (text, spec) in enumerate((("Cycles: default selection", DEFAULT_CYCLES), ("Cycles: first and last", "1,-1"),
                                          ("Cycles: every tenth", "1,10:100000:10,-1"), ("Cycles: every cycle", "1:100000"))):
            act(f"cycles{k}", text, "", lambda _=False, s=spec: self.set_cycles_spec(s))
            self._cycle_keys.append(f"cycles{k}")
        act("theme", "Switch light or dark theme", "Ctrl+Shift+L", lambda: self.toggle_theme())
        act("fullscreen", "Full screen", QKeySequence.FullScreen, lambda on: self.set_full_screen(on), checkable=True)
        self.motion_group = QActionGroup(self)
        for mode, text in (("full", "Full motion"), ("reduced", "Reduced motion: fades only"), ("off", "No motion")):
            a = act(f"motion_{mode}", text, "", lambda _=False, m=mode: self.set_motion(m), checkable=True)
            self.motion_group.addAction(a)
        A[f"motion_{Motion.mode}"].setChecked(True)
        act("intro", "Play the launch sequence", "", lambda on: self.settings.setValue("intro", "on" if on else "off"),
            checkable=True)
        A["intro"].setChecked(self.settings.value("intro", "on") != "off")
        guide_keys = [s.toString() for s in QKeySequence.keyBindings(QKeySequence.HelpContents)]
        act("guide", "Guide", list(dict.fromkeys(guide_keys + ["F1"])), lambda: self.guide())
        act("demo", "Open the demonstration file", "", lambda: self.open_demo())
        act("methods", "How the numbers are calculated…", "", lambda: self.methods_help())
        act("cite", "Cite Cyclara…", "", lambda: self.cite())
        act("check", "Check this installation…", "", lambda: self.self_check())
        act("origin_setup", "Set up the Origin link…", "", lambda: self.origin_setup())
        act("issues", "Report a problem…", "", lambda: QDesktopServices.openUrl(QUrl(ISSUES)))
        act("errors", "Show the error log", "", lambda: self.show_error_log())
        act("about", f"About {APP_NAME}", "", lambda: self.about(), role=QAction.AboutRole)

    def _menus(self):
        A, mb = self.act, self.menubar
        f = styled_menu(mb.addMenu("&File"))
        f.addActions([A["open"], A["folder"]])
        self.recent_menu = styled_menu(f.addMenu("Open recent"))
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        f.addSeparator(); f.addAction(A["export"])
        f.addSeparator(); f.addAction(A["close"])
        f.addSeparator(); f.addAction(A["quit"])
        e = styled_menu(mb.addMenu("&Edit"))
        e.addActions([A["undo"], A["redo"]]); e.addSeparator()
        e.addActions([A["copy"], A["all"]]); e.addSeparator()
        e.addActions([A["next_q"], A["again"]]); e.addSeparator()
        e.addAction(A["search"])
        v = styled_menu(mb.addMenu("&View"))
        v.addActions([A[f"view{k}"] for k in range(len(VIEWS) + 1)]); v.addSeparator()
        v.addActions([A["fit"], A["prev"], A["next"], A["tables"]])
        cm = styled_menu(v.addMenu("Cycles")); cm.addActions([A[k] for k in self._cycle_keys])
        v.addSeparator()
        v.addActions([A["theme"], A["fullscreen"]])
        mm = styled_menu(v.addMenu("Motion"))
        mm.addActions([A["motion_full"], A["motion_reduced"], A["motion_off"]]); mm.addSeparator()
        mm.addAction(A["intro"])
        h = styled_menu(mb.addMenu("&Help"))
        h.addActions([A["guide"], A["demo"], A["methods"], A["cite"]]); h.addSeparator()
        h.addActions([A["check"], A["origin_setup"], A["issues"], A["errors"]]); h.addSeparator()
        h.addAction(A["about"])

    def _fill_recent(self):
        m = self.recent_menu
        m.clear()
        paths = [p for p in self._recent() if Path(p).exists()]
        for p in paths[:10]:
            a = m.addAction(Path(p).name, lambda p=p: self.open_paths([Path(p)]))
            a.setToolTip(p)
        if not paths:
            m.addAction("No recent files").setEnabled(False)
        else:
            m.addSeparator()
            m.addAction("Clear the list", lambda: (self.settings.setValue("recent", "[]"), self.empty.set_recent([])))

    def set_motion(self, mode):
        Motion.mode = mode
        self.settings.setValue("motion", mode)
        self.act[f"motion_{mode}"].setChecked(True)
        self._status({"full": "Full motion", "reduced": "Reduced motion: fades only", "off": "No motion"}[mode])

    def set_full_screen(self, on):
        self.showFullScreen() if on else self.showNormal()

    def about(self):
        AboutDialog(self).exec()

    def show_error_log(self):
        """The window's own error log, or the launch log a windowed Cyclara keeps (Cyclara.exe, pythonw,
        an .app bundle): whichever exists, the launch log first because start-up trouble lands there."""
        for path in (platform_support.log_path(), ERROR_LOG):
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                return
        self._status("No error has been logged")

    def origin_setup(self):
        if getattr(self, "_origin_setup", None) is None or not self._origin_setup.isVisible():
            self._origin_setup = OriginSetup(self)
            self._origin_setup.show()
            self._origin_setup.start()
        else:
            self._origin_setup.raise_()

    def self_check(self):
        if getattr(self, "_check", None) is None or not self._check.isVisible():
            self._check = SelfCheck(self)
            self._check.show()
            self._check.start()
        else:
            self._check.raise_()

    def methods_context(self) -> methods_text.Context:
        """The open file's settings and run, for the methods window and the methods paragraph."""
        rec = self.rec
        if rec is None or rec.loaded is None:
            return methods_text.Context()
        run = rec.run
        s = rec.run_settings if (run is not None and rec.run_settings is not None) else settings_for(rec.answers)
        # rec.profile holds the profile's name (meta["profile"]); reading .name from it gave None, so the methods
        # window never named the profile a file was read with
        prof = rec.profile if isinstance(rec.profile, str) else getattr(rec.profile, "name", None)
        return methods_text.Context(
            settings=s, run=run, dqde_mv=run.dqde_mv if run is not None else 10.0,
            dqde_units=self.studio.dq.currentData() if hasattr(self.studio, "dq") else "au",
            file_name=rec.path.name, profile_name=prof,
            mass_warnings=tuple(run.warnings) if run is not None else ())

    def methods_help(self, topic: str | None = None):
        if getattr(self, "_methods", None) is None or not self._methods.isVisible():
            self._methods = MethodsDialog(self, self.methods_context())
            self._methods.show()
        else:
            self._methods.set_context(self.methods_context())
            self._methods.raise_()
        if topic:
            self._methods.select(topic)

    def _refresh_methods(self):
        d = getattr(self, "_methods", None)
        if d is not None and d.isVisible():
            d.set_context(self.methods_context())

    def cite(self):
        if getattr(self, "_cite", None) is None or not self._cite.isVisible():
            self._cite = CiteDialog(self)
            self._cite.show()
        else:
            self._cite.raise_()

    def open_demo(self):
        if DEMO_FILE.exists():
            self.open_paths([DEMO_FILE])
        else:
            self._status("The demonstration file is not part of this installation")

    # ---------------------------------------------------------------- the launch sequence
    def play_intro(self):
        """The launch sequence, drawn over the window. Any click or key cuts it short."""
        if Motion.mode == "off" or self._intro is not None:
            return
        self._intro = Ignition(self, __version__)
        self._intro.setGeometry(self.rect())
        self._intro.finished.connect(self._intro_done)
        self._intro.start()

    def _intro_done(self):
        self._intro = None
        self.files.setFocus(Qt.OtherFocusReason)

    # ---------------------------------------------------------------- dropping files
    # Drops are handled for the whole window at the window level, before any child sees them: a
    # plot under the cursor would otherwise take the drop and refuse it. The drop is always
    # accepted as a copy, never as a move, so the file manager can never delete the source.
    @staticmethod
    def _dropped_paths(mime):
        return [Path(u.toLocalFile()) for u in mime.urls() if u.isLocalFile()] if mime.hasUrls() else []

    def _drop_text(self, paths):
        files = self.expand(paths)
        if not files:
            return "Nothing here can be read: drop .mpr or .mpt files, or a folder that holds them"
        if len(paths) == 1 and paths[0].is_dir():
            return f"Release to open {len(files)} file{'s' if len(files) != 1 else ''} from {paths[0].name}"
        return f"Release to open {files[0].name}" if len(files) == 1 else f"Release to open {len(files)} files"

    @staticmethod
    def _as_copy(e):
        if e.possibleActions() & Qt.CopyAction:
            e.setDropAction(Qt.CopyAction)
            e.accept()
            return True
        e.ignore()
        return False

    def _drag_enter(self, e):
        paths = self._dropped_paths(e.mimeData())
        if not paths:
            return False
        self._drop_ok = self._as_copy(e)
        if self._drop_ok:
            self.drop.present(self._drop_text(paths))
        return True

    def _drag_move(self, e):
        if not self._dropped_paths(e.mimeData()):
            return False
        self._as_copy(e) if self._drop_ok else e.ignore()
        return True

    def _drag_leave(self):
        self.drop.dismiss()
        return True

    def _drop(self, e):
        paths = self._dropped_paths(e.mimeData())
        self.drop.dismiss()
        if not paths:
            return False
        if self._as_copy(e):
            QTimer.singleShot(0, lambda: self.open_paths(paths))     # let the file manager return first
        return True

    def eventFilter(self, obj, e):
        if obj is self._drop_window:
            t = e.type()
            if t == QEvent.DragEnter:
                return self._drag_enter(e)
            if t == QEvent.DragMove:
                return self._drag_move(e)
            if t == QEvent.DragLeave:
                return self._drag_leave()
            if t == QEvent.Drop:
                return self._drop(e)
        return super().eventFilter(obj, e)

    def showEvent(self, e):
        super().showEvent(e)
        h = self.windowHandle()
        if h is not None and h is not self._drop_window:
            h.installEventFilter(self)
            self._drop_window = h

    def dragEnterEvent(self, e):           # used only if the window-level filter is not installed
        if not self._drag_enter(e):
            e.ignore()

    def dragMoveEvent(self, e):
        if not self._drag_move(e):
            e.ignore()

    def dragLeaveEvent(self, e):
        self._drag_leave()

    def dropEvent(self, e):
        if not self._drop(e):
            e.ignore()

    # ---------------------------------------------------------------- opening
    def open_files(self):
        start = self.settings.value("last_dir", str(Path.home()))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open cycling files", start,
            "Cycling files (*.mpr *.mpt *.cex *.csv *.txt *.tsv *.dat *.xlsx *.xlsm);;EC-Lab files (*.mpr *.mpt);;"
            "LANHE files (*.cex);;Other cyclers' exports (*.csv *.txt *.tsv *.dat *.xlsx *.xlsm);;All files (*)")
        if paths:
            self.open_paths([Path(p) for p in paths])

    def open_folder(self):
        start = self.settings.value("last_dir", str(Path.home()))
        d = QFileDialog.getExistingDirectory(self, "Open an experiment folder", start)
        if d:
            self.open_paths([Path(d)])

    @staticmethod
    def expand(paths: list[Path], skipped: list | None = None) -> list[Path]:
        """Folders open every measurement in them. A text export of a run whose .mpr is in the same
        folder is skipped in favour of the .mpr (U01 interaction rules), and `skipped` says which.

        An export is recognised by its name (the .mpr's name with .mpt) or, for any other name that
        starts the same way, by its header naming the .mpr it was saved from. A shared prefix alone
        is not enough: cell1.mpr does not hide cell10.mpt (review finding r19)."""
        out = []
        for p in paths:
            if p.is_dir():
                try:
                    entries = sorted(p.iterdir())
                except OSError:
                    continue
                mpr = [m for m in entries if m.suffix.lower() == ".mpr" and m.is_file()]
                names = {m.name.lower(): m for m in mpr}
                stems = {m.stem.lower(): m for m in mpr}
                out += mpr
                for t in (e for e in entries if e.suffix.lower() in DATA_SUFFIXES and e.suffix.lower() != ".mpr"
                          and e.is_file()):
                    src = stems.get(t.stem.lower()) if t.suffix.lower() == ".mpt" else None
                    if src is None and t.suffix.lower() == ".mpt" and any(t.stem.lower().startswith(st) for st in stems):
                        try:
                            named = exported_from(_raw_header(t))
                        except OSError:
                            named = None
                        src = names.get(named.lower()) if named else None
                    if src is not None:
                        if skipped is not None:
                            skipped.append(f"{t.name} is the text export of {src.name}, which is opened instead")
                        continue
                    if t.suffix.lower() in (".txt", ".csv", ".tsv", ".dat") and not (is_eclab(t) or looks_tabular(t)):
                        if skipped is not None:
                            skipped.append(f"{t.name} holds no table of measurements")
                        continue                            # a notes file or a log, not a measurement
                    out.append(t)
            elif p.suffix.lower() in DATA_SUFFIXES:
                out.append(p)
        return out

    def _nothing_to_open(self, raw: list[Path]):
        """Say why nothing was opened, instead of doing nothing (review finding r25)."""
        dirs = [p for p in raw if p.is_dir()]
        exts = sorted({p.suffix.lower() or "(no extension)" for p in raw if p.is_file()})
        has_mps = ".mps" in exts or any(any(d.glob("*.mps")) for d in dirs)
        if has_mps:
            msg = "An .mps file holds a protocol's settings, not measurements: open the run's .mpr or .mpt file."
        elif dirs and not exts:
            msg = f"There is no measurement file in {dirs[0].name} (.mpr, .mpt, .cex, .csv, .txt or .xlsx)."
        elif exts:
            msg = (f"{', '.join(exts)} files are not read: open an EC-Lab .mpr or .mpt, a LANHE .cex, another cycler's .csv, "
                   ".txt or .xlsx export, or a folder holding them.")
        else:
            msg = "Nothing to open."
        self.toast.show_message(msg)
        self._status(msg)

    def open_paths(self, paths):
        raw = [Path(p) for p in paths]
        skipped = []
        paths = self.expand(raw, skipped)
        for msg in skipped:
            self.results.activity.log(f"Skipped {msg}")
        opened = {r.path.resolve(): r for r in self.records}
        new = [p for p in paths if p.resolve() not in opened]
        if not new:
            if paths:
                self._refresh_files(select=opened[paths[0].resolve()])
                self._status("Already open")
            else:
                self._nothing_to_open(raw)
            return
        if skipped:
            self._status(f"Skipped {len(skipped)} text export{'s' if len(skipped) != 1 else ''} of .mpr files "
                         "opened instead; the Activity tab lists them")
        self.settings.setValue("last_dir", str(new[0].parent))
        recs = []
        for p in new:
            rec = Record(p)
            self.records.append(rec)
            recs.append(rec)
            self.results.activity.log(f"Opening {p.name}")
            worker.start(worker.Job(rec, worker.in_process, workflow.open_file, p, progress=True),
                         done=self._opened, failed=self._open_failed, progress=self._reading_progress)
        self._remember_recent(new)
        first = recs[0]
        self._ingesting = first
        self.ingest.begin(first, f"Reading {first.path.name}", self._opening_line(first.path))
        self._refresh_files(select=first)
        self._busy(True, f"Reading {first.path.name}…")

    @staticmethod
    def _opening_line(path):
        try:
            size = _size_text(path.stat().st_size)
        except OSError:
            size = ""
        suffix = path.suffix.lower()
        kind = ("EC-Lab binary file" if suffix == ".mpr" else "workbook" if suffix in (".xlsx", ".xlsm", ".xls")
                else "text export")
        return f"Opening the {kind}, {size}" if size else f"Opening the {kind}"

    def _opened(self, rec, loaded):
        if rec not in self.records:
            return
        rec.loaded = loaded
        tab = loaded.tab
        if loaded.proposal is not None:                 # no profile recognises the file: map its columns first
            rec.proposal = loaded.proposal
            rec.profile = None
            self.results.activity.log(f"{rec.path.name}: no profile recognises its columns; mapping them is the next step")
            if self._ingesting is rec:
                prop = loaded.proposal
                rows = f"{prop.measured.get('rows', 0):,}".replace(",", "\u2009")
                self.ingest.step(f"A {prop.layout.kind} table with {len(prop.headers)} columns and {rows} rows")
                self.ingest.step("No profile recognises these columns: the next screen asks what the file cannot say",
                                 "note")
                self._ingest_finish(rec)
            self._refresh_files()
            if rec is self.rec:
                self._show_record()
            self._busy(any(r.loaded is None and not r.error for r in self.records))
            return
        rec.proposal = None
        if loaded.meta.get("profile"):
            rec.profile = loaded.meta.get("profile")
            if self._ingesting is rec:
                self.ingest.step(f"Read with the {loaded.meta['instrument']} profile "
                                 f"({loaded.meta['profile']})")
        if self._ingesting is rec:
            n = f"{tab.n:,}".replace(",", " ")
            self.ingest.step(f"{n} rows and {len(tab.columns)} columns read")
            pot, cur = tab.labels.get("potential"), tab.labels.get("current")
            if pot and cur:
                self.ingest.step(f"Potential from {pot}, current from {cur}")
            m = loaded.declared_mass_mg
            if m and m <= EC_LAB_DEFAULT_MASS_MG:          # the empty-field default is never offered (review r28)
                self.ingest.step(f"The header gives {m:g} mg, EC-Lab's default for an empty mass field: not offered",
                                 "note")
            elif m:
                self.ingest.step(f"The header states {m:g} mg of active material: offered, not applied", "note")
        self.results.activity.log(f"Read {rec.path.name}: {tab.n:,} rows, {tab.format}")
        restored = self._restore_answers(rec)
        if not restored and loaded.meta.get("profile") and rec.answers.charge is None:
            # the profile settled the direction (the step types named it, or the sign convention was declared
            # with evidence) and the reader made the current charge-positive: that answer is given, not guessed,
            # and it stays one undoable step with its source shown in the inspector
            rep_ = loaded.meta.get("import_report", {})
            how = ("the file's step types name the direction" if rep_.get("current_sign_declared") in ("unsigned", "detect")
                   or rep_.get("direction_from_step_types")
                   else f"the {loaded.meta['profile']} profile declares positive current as charge")
            self.results.activity.log(f"{rec.path.name}: current direction answered from the import: {how}")
            if self._ingesting is rec:
                self.ingest.step(f"Charging direction known: {how}")
            self.undo.push(AnswerCommand(self, rec, {"charge": "ox"}, "Current direction from the import"))
            restored = True                       # the command's redo started the analysis
        if self._ingesting is rec:
            self.ingest.step("Segmenting charge and discharge branches")
        if not restored:
            self.request_analysis(rec)
        self._refresh_files()
        if rec is self.rec:
            self._show_record()

    def _restore_answers(self, rec) -> bool:
        """Answers given for these exact bytes in an earlier session come back as one undo step."""
        saved = self.settings.value(f"answers/{rec.loaded.tab.source_sha256}")
        if not saved:
            return False
        try:
            answers = Answers.from_dict(json.loads(saved))
        except Exception:
            return False
        diff = {k: v for k, v in answers.to_dict().items() if getattr(rec.answers, k) != v}
        if not diff:
            return False
        self.results.activity.log(f"{rec.path.name}: answers from your last session with these exact bytes restored")
        if self._ingesting is rec:
            self.ingest.step("Your answers from the last session with this exact file restored", "note")
        self.undo.push(AnswerCommand(self, rec, diff, "Restore the answers from your last session", restore=True))
        self._status(f"Answers from your last session with this file were restored; {sc(QKeySequence.Undo)} "
                     "clears them")
        return True

    def _mapping_confirmed(self, rec, loaded, profile, save_name, instrument):
        """The import review step passed its check: open the file with that mapping, and remember the
        instrument when asked, so the next file with these columns opens without questions."""
        if rec not in self.records:
            return
        if save_name:
            from ..readers import Registry
            try:
                path = Registry(workflow.profiles_dir()).save(profile, list(rec.proposal.headers), rec.path.name)
                self.results.activity.log(f"Profile {profile.name} saved to {path}: files with these column names "
                                          "open without questions from now on")
                self._status(f"Remembered {instrument}: saved as {path.name}")
            except OSError as exc:
                self._status(f"The profile could not be saved: {exc}")
        rec.proposal = None
        self.results.activity.log(f"{rec.path.name}: mapped as {instrument} ({profile.name}); "
                                  f"evidence: {profile.conventions.evidence}")
        self._opened(rec, loaded)

    def _open_failed(self, rec, msg, tb):
        rec.error = msg
        self.results.activity.log(f"Could not read {rec.path.name}: {msg}")
        self._log_error(tb)
        if self._ingesting is rec:
            self.ingest.step(f"Could not read the file: {msg}", "error")
            self._ingest_finish(rec)
        self._refresh_files()
        if rec is self.rec:
            self._show_record()
        self._busy(any(r.loaded is None and not r.error for r in self.records))

    # ---------------------------------------------------------------- the reading screen
    def _ingest_finish(self, rec):
        self.ingest.finish()
        QTimer.singleShot(Motion.ms(650), lambda: self._ingest_done(rec))

    def _ingest_done(self, rec):
        if self._ingesting is not rec:
            return
        self._ingesting = None
        if self.rec is rec and rec.needs_mapping:
            self.centre.fade_to(3)                 # the import review step, for a file no profile recognises
            return
        if self.rec is rec:
            self.centre.fade_to(1)
            self._feed_strip(rec, grow=True)       # the bars rise once, now that they can be seen
            w = self.stack.currentWidget()
            if hasattr(w, "reveal"):
                w.reveal()                          # and the curves trace in, once

    # ---------------------------------------------------------------- analysis
    def request_analysis(self, rec):
        if rec is None or rec.loaded is None or rec.loaded.tab is None:
            return
        if rec.analysing:
            rec._again = True
            return
        rec.analysing = True
        rec._again = False
        s = settings_for(rec.answers)
        self._busy(True, f"Analysing {rec.path.name}…")
        worker.start(worker.Job((rec, s), workflow.analyse_file, rec.loaded, s),
                     done=self._analysed, failed=self._analysis_failed)
        self._refresh_files()

    def _analysed(self, token, run):
        rec, s = token
        rec.analysing = False
        if s == settings_for(rec.answers):
            first = rec.run is None
            rec.run, rec.run_settings, rec.analysis_error = run, s, None
            if first:
                av = rec.available_cycles()
                rec.focus_cycle = rec.selected_cycles()[0] if av else None
                if self._ingesting is rec:
                    self._tell_segmentation(rec)
        if getattr(rec, "_again", False) or s != settings_for(rec.answers):
            self.request_analysis(rec)                       # inputs changed meanwhile: analyse the current ones
        self._busy(any(r.analysing or (r.loaded is None and not r.error) for r in self.records))
        self._refresh_files()
        if rec is self.rec:
            self._show_record()

    def _reading_progress(self, rec, msg):
        """The reader's progress on a large file from another cycler: the reading screen's current line is
        rewritten, and the status bar says the same (both on the GUI thread; the signal crosses the thread)."""
        if rec in self.records and rec.loaded is None and not rec.error:
            if self._ingesting is rec:
                self.ingest.progress(msg)
            self._status(f"{msg}: {rec.path.name}")

    def _tell_segmentation(self, rec):
        seg, sm = rec.run.seg, rec.run.an.summary
        nb = len(seg.branches)
        self.ingest.step(f"{nb} branch{'es' if nb != 1 else ''} segmented")
        if seg.pairs:
            inc = sum(1 for c in rec.run.an.cycles if not c.complete)
            tail = f", {inc} incomplete" if inc else ""
            self.ingest.step(f"{sm.complete_cycles} complete cycle{'s' if sm.complete_cycles != 1 else ''} paired{tail}")
        else:
            self.ingest.step("Cycles wait for the charging direction: the first question", "note")
        self._ingest_finish(rec)

    def _analysis_failed(self, token, msg, tb):
        rec, s = token
        rec.analysing = False
        rec.analysis_error = msg
        self.results.activity.log(f"Analysis of {rec.path.name} failed: {msg}")
        self._log_error(tb)
        if self._ingesting is rec:
            self.ingest.step(f"Analysis failed: {msg}", "error")
            self._ingest_finish(rec)
        self._busy(False)
        self._refresh_files()
        if rec is self.rec:
            self._show_record()

    # ---------------------------------------------------------------- answers
    def _answer(self, new: dict):
        if self.rec is None:
            return
        self.undo.push(AnswerCommand(self, self.rec, new))

    def _clear_restored(self):
        rec = self.rec
        if rec is None:
            return
        rec.restored = False
        diff = {k: v for k, v in Answers().to_dict().items() if getattr(rec.answers, k) != v}
        if diff:
            self.undo.push(AnswerCommand(self, rec, diff, "Clear the restored answers"))
        else:
            self._show_record()

    def _bring_forward(self, rec):
        """Show the file an undo or redo acts on, so no change is made out of sight."""
        if rec in self.records and rec is not self.rec:
            self._refresh_files(select=rec)
            self.toast.show_message(f"Undo and redo act on the file each answer was given for: now showing "
                                    f"{rec.path.name}.")

    def _apply_answers(self, rec, values, undo=False):
        if rec not in self.records:
            self._status("That file was closed; the step was dropped")
            return
        for k, v in values.items():
            setattr(rec.answers, k, v)
        txt = ", ".join(f"{k.replace('_', ' ')} = {v if v not in (None, '') else 'not given'}" for k, v in values.items())
        self.results.activity.log(f"{rec.path.name}: {'undo, ' if undo else ''}{txt}")
        if rec.loaded:
            self.settings.setValue(f"answers/{rec.loaded.tab.source_sha256}", json.dumps(rec.answers.to_dict()))
        engine_keys = {"charge", "configuration", "reference", "mass_mg", "no_mass", "area_cm2", "molar_mass_g_mol",
                       "electrons", "reference_cycle", "cycle_order", "use_instrument_dq"}
        if engine_keys & set(values):
            self.request_analysis(rec)
        if rec is self.rec:
            self._show_record(keep_view=True)
        self._refresh_files()

    def answers_to_all(self):
        if not self.rec:
            return
        d = self.rec.answers.to_dict()
        n = 0
        self.undo.beginMacro("Use these answers for every open file")
        for r in self.records:
            if r is not self.rec and r.loaded:
                diff = {k: v for k, v in d.items() if getattr(r.answers, k) != v}
                if diff:
                    self.undo.push(AnswerCommand(self, r, diff)); n += 1
        self.undo.endMacro()
        self._status(f"Answers applied to {n} other file{'s' if n != 1 else ''}" if n else "The other files already had these answers")

    # ---------------------------------------------------------------- showing
    def _refresh_files(self, select=None):
        cur = select or self.rec
        self.files.blockSignals(True)
        self.files.clear()
        t = theme.tokens()
        for r in self.records:
            it = QListWidgetItem(f"{r.label}\n{r.state}")
            it.setToolTip(str(r.path))
            col = {"ready to export": t.ok, "could not be read": t.error, "analysis failed": t.error}.get(r.state)
            icon = "check" if r.state == "ready to export" else ("cross" if col == t.error else "file")
            it.setIcon(theme.icon(icon, col or t.muted))
            it.setSizeHint(QSize(180, 46))
            self.files.addItem(it)
        if cur in self.records:
            self.files.setCurrentRow(self.records.index(cur))
        self.files.blockSignals(False)
        if select is not None:
            self._file_selected(self.records.index(select))
        self._update_chrome()

    def _file_selected(self, row):
        if row < 0 or row >= len(self.records):
            return
        if self.records[row] is not self.rec:
            self.rec = self.records[row]
            self._show_record()

    FILES_WIDE = 1680        # from this width the file list stays in view even with one file open

    def _panels(self):
        """Home shows no side panels. The file list shows when two or more files are open, or with one
        file on a wide window (on a narrow one the title and the pill already say which file and how far
        it is, and the plots need the width). The Figures page hides the results and, once every
        question is answered, the inspector, so the preview has the room."""
        rec = self.rec
        on_figures = self.stack.currentWidget() is self.studio
        n = len(self.records)
        show = n >= 2 or (n == 1 and self.width() >= self.FILES_WIDE)
        first = show and not self.left_panel.isVisibleTo(self) and self._files_shown_for < n
        self.left_panel.setMinimumWidth(210 if self.width() >= 1280 else 170)
        self.left_panel.setVisible(show)
        if show:
            self._files_shown_for = n
        if first:                                     # the file list appears with a file: the keyboard starts there
            self.files.setFocus(Qt.OtherFocusReason)
        self.lower.setVisible(not on_figures)
        # on the Figures page the questions stay beside the preview only where there is room for both;
        # on a narrow window the pill ("1 answer needed") brings them back
        self.inspector.setVisible(rec is not None and not rec.needs_mapping and (not on_figures or (
            self.width() >= 1200 and bool(open_questions(rec.answers, rec.loaded, rec.run)))))

    def _show_record(self, keep_view=True):
        rec = self.rec
        self._update_chrome()
        self._panels()
        self._refresh_methods()
        if rec is None:
            self.empty.set_recent(self._recent())
            self.centre.fade_to(0)
            self.inspector.show_record(None)
            return
        if rec.needs_mapping:
            self.title.setText(rec.label)
            self.meta.setText(self._meta(rec))
            if self.mapping.rec is not rec:
                self.mapping.show_record(rec)
            self.centre.fade_to(2 if self._ingesting is rec else 3)
            for v in self.views:
                v.show_record(None, [], None)
            self.inspector.show_record(None)
            self.results.show_record(None)
            self.strip.set_data([], [])
            return
        self.centre.fade_to(2 if self._ingesting is rec else 1)
        self.title.setText(rec.label)
        self.meta.setText(self._meta(rec))
        sel = rec.selected_cycles()
        if rec.focus_cycle not in rec.available_cycles():
            rec.focus_cycle = sel[0] if sel else None
        self._feed_strip(rec)
        for v in self.views:
            v.show_record(rec, sel, rec.focus_cycle)
        if rec.run:
            rec.run.selected = sel                      # the figure cycles are the cycles you picked
        self.studio.show_record(rec)
        self.results.show_record(rec)
        self.inspector.show_record(rec, rec.focus_cycle)
        if rec.focus_cycle is not None:
            self.results.cycles.select_where("cycle", rec.focus_cycle)

    def _meta(self, rec):
        if rec.error:
            return "could not be read"
        if rec.needs_mapping:
            p = rec.proposal
            rows = f"{p.measured.get('rows', 0):,}".replace(",", "\u2009")
            return f"{p.layout.kind} table, {len(p.headers)} columns, {rows} rows: no profile recognises it yet"
        if rec.loaded is None:
            return "reading…"
        tab = rec.loaded.tab
        parts = []
        if rec.loaded.meta.get("instrument"):
            parts.append(rec.loaded.meta["instrument"])
        if rec.run:
            sm = rec.run.an.summary
            if rec.run.seg.pairs:
                n = sm.complete_cycles
                parts.append(f"{n} complete cycle{'s' if n != 1 else ''}")
            else:
                n = len(rec.run.seg.branches)
                parts.append(f"{n} branch{'es' if n != 1 else ''}, not yet paired into cycles")
            parts.append(_duration(sm.total_test_time_h))
        parts.append(f"{tab.n:,} rows".replace(",", " "))
        a = rec.answers
        if a.configuration == "half" and a.reference.strip():
            parts.append(f"half-cell vs. {ref_text(a.reference)}")
        elif a.configuration == "full":
            parts.append("full cell")
        if a.mass_mg and not a.no_mass:
            parts.append(f"{a.mass_mg:g} mg active material")
        elif a.no_mass:
            parts.append("no mass: " + ("capacity per cm²" if a.area_cm2 else "capacity in mAh"))
        return ", ".join(parts)

    def _feed_strip(self, rec, grow=False):
        if rec.run is None:
            self.strip.empty_text = "Cycles appear here once the file is analysed"
        elif rec.answers.charge is None:
            self.strip.empty_text = "Cycles appear here once you say which current direction charges the cell"
        else:
            self.strip.empty_text = "No charge and discharge could be paired into a cycle"
        if not rec.run:
            self.strip.set_data([], [])
            self.expr.setText(rec.cycles_spec)
            return
        s = rec.run.settings
        cyc = rec.run.an.cycles
        vals = [cycle_capacity(c, "discharge", s) if c.complete else None for c in cyc]   # the basis the unit names
        key = (rec.loaded.tab.source_sha256, id(rec)) if grow else None
        why = {c.cycle: ("no partner branch" if c.charge_branch is None or c.discharge_branch is None else
                         "a branch reaches the end of the file or has an unsupported interval")
               for c in cyc if not c.complete}
        self.strip.set_data([c.cycle for c in cyc], vals, {c.cycle: c.coulombic_efficiency_pct for c in cyc},
                            capacity_unit(s), incomplete=[c.cycle for c in cyc if not c.complete], key=key,
                            incomplete_why=why)
        self.strip.set_selection(rec.selected_cycles(), rec.focus_cycle)
        self.expr.setText(compress(rec.selected_cycles()))

    def _update_chrome(self):
        rec = self.rec
        if rec is None:
            self.pill.setText("No file open"); state = "busy"
        else:
            st = rec.state
            self.pill.setText(st[0].upper() + st[1:])
            state = ("ready" if st == "ready to export" else "failed" if st in ("could not be read", "analysis failed")
                     else "needs" if "needed" in st else "busy")
        self.pill.setProperty("state", state)
        self.pill.style().unpolish(self.pill); self.pill.style().polish(self.pill)
        f = theme.font(9.5, 600)
        from PySide6.QtGui import QFontMetrics
        self.pill.setMinimumWidth(QFontMetrics(f).horizontalAdvance(self.pill.text()) + 34)
        self.btn_export.setEnabled(bool(rec and rec.run))
        self.stale.setVisible(bool(rec and rec.run is not None and not rec.current))   # review finding r21
        self.setWindowTitle(f"{rec.label} – {APP_NAME}" if rec else APP_NAME)
        # the lock-on: once, each time a file becomes ready to export
        if rec is not None:
            ready = state == "ready"
            if ready and not getattr(rec, "_ready_seen", False) and self.isVisible():
                QTimer.singleShot(80, self._lock_on)
            rec._ready_seen = ready

    def _lock_on(self):
        if not Motion.moving() or not self.pill.isVisible():
            return
        t = theme.tokens()
        Sweep(self.pill, t.ok)
        Ripple(self, self.pill, t.ok)

    # ---------------------------------------------------------------- selection
    def _strip_selection(self, sel):
        if not self.rec:
            return
        self.rec.cycles_spec = compress(sel)
        self.expr.setText(self.rec.cycles_spec)
        self._selection_changed()

    def _expr_changed(self):
        if self.rec:
            self.set_cycles_spec(self.expr.text())

    def set_cycles_spec(self, spec):
        rec = self.rec
        if not rec or not rec.run:
            return
        missing = []
        sel = parse_cycles(spec, rec.available_cycles(), missing)
        if not sel:
            self._status("No cycle in that list exists in this file; the selection was kept")
            self.expr.setText(compress(rec.selected_cycles()))
            return
        if missing:
            av = rec.available_cycles()
            self._status(f"Not in this file, left out: {', '.join(missing[:6])}{'…' if len(missing) > 6 else ''} "
                         f"(cycles {av[0]} to {av[-1]})")
        rec.cycles_spec = compress(sel)
        self.strip.set_selection(sel, rec.focus_cycle if rec.focus_cycle in sel else sel[0])
        rec.focus_cycle = self.strip.focus
        self.expr.setText(rec.cycles_spec)
        self._selection_changed()

    def set_focus_cycle(self, c):
        """Focus a cycle. The selection, which is what is exported, is never changed by moving the focus
        (review finding r03/r27): a focused cycle outside it is previewed, dashed, in the plots."""
        rec = self.rec
        if not rec or c is None or c not in rec.available_cycles():
            return
        rec.focus_cycle = c
        self.strip.set_selection(rec.selected_cycles(), c)
        self._selection_changed()
        self.results.cycles.select_where("cycle", c)

    def step_focus(self, d):
        """[ and ]: the previous or next selected cycle from the focused one."""
        rec = self.rec
        if not rec or not rec.run:
            return
        sel = sorted(rec.selected_cycles())
        f = rec.focus_cycle
        nxt = [c for c in sel if (c > f if d > 0 else c < f)] if f is not None else sel
        if nxt:
            self.set_focus_cycle(nxt[0] if d > 0 else nxt[-1])

    def _selection_changed(self):
        rec = self.rec
        sel = rec.selected_cycles()
        for v in self.views:
            v.set_selection(sel, rec.focus_cycle)
        if rec.run:
            rec.run.selected = sel
        self.inspector.show_record(rec, rec.focus_cycle)
        if self.stack.currentWidget() is self.studio:
            self.studio.show_record(rec)

    # ---------------------------------------------------------------- views
    def show_view(self, k):
        if 0 <= k < self.stack.count():
            self.stack.fade_to(k)
            self.view_buttons.button(k).setChecked(True)
            # focus follows the selection inside the switcher, as in a tab bar: after Ctrl+5 the focus ring
            # must not stay on the view that was left, where it reads as a second selected view
            if QApplication.focusWidget() in self.view_buttons.buttons():
                self.view_buttons.button(k).setFocus(Qt.OtherFocusReason)
            self.strip_row.setVisible(True)
            on_figures = self.stack.currentWidget() is self.studio
            self._panels()
            if on_figures and self.rec:
                self.studio.show_record(self.rec)

    def fit_view(self):
        w = self.stack.currentWidget()
        if hasattr(w, "fit"):
            w.fit()

    def _pill_clicked(self):
        if self.rec and open_questions(self.rec.answers, self.rec.loaded, self.rec.run):
            self.inspector.setVisible(True)
            self.inspector.focus_first_question()
        elif self.rec and self.rec.current:
            self.show_view(len(VIEWS))

    # ---------------------------------------------------------------- export
    def export(self, opts=None):
        rec = self.rec
        if not rec or not rec.run:
            return
        if not rec.current:
            self._status("The analysis is catching up with your last answer; export again in a moment")
            return
        opts = opts or self.studio.options()
        open_q = open_questions(rec.answers, rec.loaded, rec.run)
        if open_q:
            names = "; ".join(q.title for q in open_q)
            r = QMessageBox.question(self, "Export with open questions?",
                                     f"These questions are unanswered: {names}\n\nThe values that depend on them are "
                                     "withheld and the figures that need them are left out. Export anyway?")
            if r != QMessageBox.Yes:
                return
        start = self.settings.value("export_dir", str(rec.path.parent))
        parent = QFileDialog.getExistingDirectory(self, "Choose where the results folder goes", start)
        if not parent:
            return
        self.settings.setValue("export_dir", parent)
        out = self._claim_folder(Path(parent), rec.path.stem)
        if out is None:
            return
        rec.run.selected = rec.selected_cycles()
        run = replace(rec.run, selected=list(rec.run.selected))
        self._busy(True, f"Exporting to {out.name}…")
        self.results.activity.log(f"Export of {rec.path.name} to {out} started (cycles {compress(run.selected)})")
        worker.start(worker.Job((rec, out, opts), self._export_job, run, out, opts, progress=True),
                     done=self._exported, failed=self._export_failed, progress=lambda _, m: self._status(m))

    def _claim_folder(self, parent: Path, stem: str):
        """Create the results folder now, on this thread, under a name nothing else has: a folder or a
        file of that name means the next number. Choosing the name here and creating it later let two
        quick exports share one folder (review finding r04); a file of that name stopped the export
        without a word (r18)."""
        for k in range(1, 1000):
            out = parent / (f"{stem}_analysis" if k == 1 else f"{stem}_analysis_{k}")
            try:
                out.mkdir()
                return out
            except FileExistsError:
                continue
            except OSError as exc:
                msg = f"Could not create a results folder in {parent}: {exc.strerror or exc}"
                self.toast.show_message(msg)
                self._status(msg)
                return None
        self.toast.show_message(f"{parent} already holds 999 results folders for {stem}; choose another folder")
        return None

    @staticmethod
    def _export_job(run, out, opts, progress=None):
        from .figures import RENDER_LOCK
        with RENDER_LOCK:
            record = workflow.export(run, out, opts, progress)
        return record

    def _exported(self, token, record):
        rec, out, opts = token
        self._busy(False)
        (out / "activity.txt").write_text("\n".join(self.results.activity.lines()) + "\n", encoding="utf-8")
        fails = sum(1 for cs in record.get("figure_checks", {}).values() for c in cs if c["status"] == "fail")
        nfig = len(record.get("figures", {}))
        msg = f"Exported {nfig} figure{'s' if nfig != 1 else ''} and every table to {out}."
        if fails:
            msg += f" {fails} figure check{'s' if fails > 1 else ''} failed: see settings.json."
        self.results.activity.log(msg)
        actions = [("Open folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(out))))]
        if opts.origin:
            if origin_export._python_with_originpro():
                actions.append(("Build Origin project", lambda: self._build_origin(out / "origin")))
            elif platform_support.IS_WINDOWS:
                actions.append(("Set up Origin link", self.origin_setup))      # once; then Build appears here
        self.toast.show_message(msg, actions)
        if Motion.moving() and self.btn_export.isVisible():
            Ripple(self, self.btn_export, theme.tokens().primary)
        self._status("Export finished")

    def _export_failed(self, token, msg, tb):
        self._busy(False)
        self._log_error(tb)
        self.results.activity.log(f"Export failed: {msg}")
        self.toast.show_message(f"Export failed: {msg}")

    def _build_origin(self, odir):
        self._busy(True, "Building the Origin project; Origin opens and closes by itself…")
        worker.start(worker.Job(odir, origin_export.build, odir),
                     done=lambda _, txt: (self._busy(False), self.toast.show_message(txt.splitlines()[-1] if txt else "Done")),
                     failed=lambda _, m, tb: (self._busy(False), self.toast.show_message(m)))

    # ---------------------------------------------------------------- misc
    def close_record(self):
        if not self.rec:
            return
        k = self.records.index(self.rec)
        closing = self.records.pop(k)
        if self._ingesting is closing:
            self._ingesting = None
        self.results.activity.log(f"Closed {closing.path.name}")
        self.rec = self.records[min(k, len(self.records) - 1)] if self.records else None
        self._refresh_files()
        self._show_record()

    def _file_menu(self, pos):
        it = self.files.itemAt(pos)
        if not it:
            return
        m = styled_menu(QMenu(self))
        m.addAction("Show in folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.rec.path.parent))))
        m.addAction("Use these answers for every open file", self.answers_to_all)
        m.addSeparator()
        m.addAction("Close", self.close_record)
        m.exec(self.files.mapToGlobal(pos))

    def show_palette(self):
        Palette(self, self.all_actions).exec()

    def toggle_theme(self):
        t = theme.DARK if theme.tokens().name == "light" else theme.LIGHT
        reveal = None
        if Motion.mode != "off" and self.isVisible():
            old = getattr(self, "_reveal", None)
            if old is not None:
                try:
                    old.hide(); old.deleteLater()
                except RuntimeError:
                    pass
            centre = self.btn_theme.mapTo(self, self.btn_theme.rect().center())
            reveal = self._reveal = ThemeReveal(self, self.grab(), centre)   # holds the old look while restyling
        theme.apply(QApplication.instance(), t)
        self.settings.setValue("theme", t.name)
        for v in self.views:
            v.restyle()
        self.strip.update()
        self.studio.restyle()
        self.results.restyle()
        self.mapping.restyle()
        self._restyle_chrome()
        self._refresh_files()
        if self.rec:
            self._show_record()
        if reveal is not None:
            reveal.raise_()
            reveal.start(brand.RAMP_DARK[3] if t.name == "dark" else brand.RAMP_LIGHT[3])

    def guide(self):
        o, k, z = sc(QKeySequence.Open), sc("Ctrl+K"), sc(QKeySequence.Undo)
        QMessageBox.information(self, "Guide", (
            f"1  Open a file or folder ({o}, {sc('Ctrl+Shift+O')}), or drop it anywhere on the window.\n"
            "2  Answer the questions in the inspector. Each says what it unlocks; nothing is guessed.\n"
            "3  Pick cycles on the strip under the plots: click adds or removes, drag selects a range, "
            "double-click focuses. Or type 1, 2, 5:10, -1.\n"
            "4  Hover any curve: the measured point is read out under the plot.\n"
            f"5  Figures ({sc('Ctrl+9')}) shows each figure at true size with its journal checks. Export writes "
            "figures, every table, settings.json and an Origin folder to a new folder; nothing is overwritten.\n\n"
            f"{k} searches every action. [ and ] step through the selected cycles. A fits the data. "
            f"{z} undoes any answer, in the file it was given for.\n\n"
            "A cycle here is one charge paired with one discharge, numbered from 1. EC-Lab's own cycle "
            "counter can differ by one; the Branches table lists both."))

    def _busy(self, on, text=None):
        self.busy.setVisible(bool(on))
        if text:
            self._status(text)
        elif not on:
            self._status("Ready")

    def _status(self, text):
        self.status_text.setText(text)

    def _recent(self):
        try:
            return json.loads(self.settings.value("recent", "[]"))
        except Exception:
            return []

    def _remember_recent(self, paths):
        rec = [str(p) for p in paths] + [p for p in self._recent() if p not in {str(x) for x in paths}]
        self.settings.setValue("recent", json.dumps(rec[:10]))
        self.empty.set_recent(rec[:10])

    def _log_error(self, tb):
        try:
            with open(ERROR_LOG, "a", encoding="utf-8") as fh:
                fh.write(tb + "\n")
        except Exception:
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._adapt()
        if self.toast.isVisible():
            self.toast.move(self.width() - self.toast.width() - 24, self.height() - self.toast.height() - 46)
        if self._intro is not None:
            self._intro.setGeometry(self.rect())
        if self.drop.isVisible():
            self.drop.setGeometry(self.rect())

    def _adapt(self):
        """Fit the frame to the window, so nothing is cut off from 1024 x 600 upwards.

        Width: the brand word, the shortcut hint and the folder button's word go first, then the view
        buttons lose padding and the file list leaves (see _panels). Height: below 820 points the cycle
        strip slims and the tables shrink; below 760 the tables fold to their tab row (a click opens
        them), so the plots keep a readable height."""
        w, h = self.width(), self.height()
        self.name.setVisible(w >= 1280)               # the mark stays; the word goes first on a narrow window
        self.search_key.setVisible(w >= 1220)
        self.search.setMinimumWidth(220 if w >= 1180 else 160)
        self.btn_folder.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if w >= 1180 else Qt.ToolButtonIconOnly)
        self._compact_switcher(w < 1360)
        self._panels()
        cls = "tall" if h >= 820 else "short" if h >= 760 else "low"
        self.strip.setFixedHeight(74 if cls == "tall" else 48)
        self.strip_hint.setVisible(cls == "tall" and w >= 1300)
        if cls != self._height_class:
            before, self._height_class = self._height_class, cls
            self._auto_folding = True
            try:
                if cls == "low" and not self.results.collapsed:
                    self._auto_folded = True
                    self.results.set_collapsed(True)
                elif cls != "low" and before == "low" and self._auto_folded and self.results.collapsed:
                    self._auto_folded = False
                    self.results.set_collapsed(False)
            finally:
                self._auto_folding = False
        if cls == "short" and not self.results.collapsed:
            total = sum(self.vsplit.sizes())
            if total > 0 and self.vsplit.sizes()[1] > 140:
                self.vsplit.setSizes([total - 130, 130])

    def _tables_folded(self, folded: bool):
        """The drawer folded or opened: the splitter gives the plots the room, or the tables theirs back."""
        self.act["tables"].setChecked(not folded)
        sizes = self.vsplit.sizes()
        total = sum(sizes)
        if folded:
            if sizes[1] > 60:
                self._tables_height = sizes[1]
            h = self.results.header_height() + 14       # the tab row and the panel's margins
            self.lower.setMaximumHeight(h)
            self.vsplit.setSizes([max(total - h, 0), h])
        else:
            if not self._auto_folding:
                self._auto_folded = False
            self.lower.setMaximumHeight(16777215)
            want = getattr(self, "_tables_height", 220 if self.height() >= 820 else 130)
            want = min(want, max(130, total // 2))
            self.vsplit.setSizes([max(total - want, 0), want])

    def toggle_tables(self, show: bool | None = None):
        self.results.set_collapsed(self.results.collapsed if show is None else not show)


def main(argv=None):
    os.environ.setdefault("QT_API", "pyside6")
    os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")
    argv = list(sys.argv if argv is None else argv)
    platform_support.keep_a_log(argv)                  # no console (pythonw, Cyclara.exe, an .app): log to a file
    platform_support.set_app_id(brand.APP_ID)          # Windows: the taskbar shows Cyclara, not Python
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(STORE)
    app.setWindowIcon(app_icon())                      # macOS: the Dock icon while the app runs
    theme.load_fonts()
    app.setFont(theme.font(9.5))
    s = QSettings(STORE, "studio")
    Motion.load(STORE)
    if "--no-motion" in argv:
        Motion.mode = "off"
    worker.USE_PROCESSES = "--threads" not in argv     # files are read in a separate process
    app.aboutToQuit.connect(worker.shutdown)
    name = s.value("theme", "")
    if not name:
        name = "dark" if platform_support.system_prefers_dark() else "light"
    theme.apply(app, theme.DARK if name == "dark" else theme.LIGHT)
    win = MainWindow()
    if "--no-intro" not in argv and s.value("intro", "on") != "off":
        win.play_intro()                               # before show(), so the first frame is the intro
    geometry = s.value("geometry")
    if geometry is not None and win.restoreGeometry(geometry):
        win.show()                                     # where and how large it was last time, maximised included
    elif win.screen_is_small():
        win.showMaximized()                            # a laptop screen: all of it
    else:
        win.show()
    files = [Path(a) for a in argv[1:] if not a.startswith("-")]
    if files:
        win.open_paths(files)
    return app.exec()
