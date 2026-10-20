"""Figure studio: true-size preview, journal rules, automatic checks, export.

The preview is drawn by the same function table the export uses
(workflow.figure_builders) with the same options, so what is previewed is what
is written. Rendering is Matplotlib on the Agg canvas in a worker thread, one
figure at a time (pyplot keeps global state, so a lock serialises it).
"""
from __future__ import annotations

import io
import threading

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget, QToolButton)

from .. import plotting, workflow
from . import theme, worker

RENDER_LOCK = threading.Lock()


class CheckList(QScrollArea):
    """The figure checks, each with its whole detail wrapped to the panel's width, never cut off."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.inner = QWidget()
        self.lay = QVBoxLayout(self.inner)
        self.lay.setContentsMargins(0, 0, 6, 0)
        self.lay.setSpacing(9)
        self.lay.addStretch(1)
        self.setWidget(self.inner)
        self.setAccessibleName("Figure checks")

    def clear(self):
        while self.lay.count() > 1:
            w = self.lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()

    def add(self, icon, title, detail):
        import html
        row = QWidget()
        h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(8)
        ic = QLabel(); ic.setPixmap(icon.pixmap(16, 16)); ic.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        ic.setFixedWidth(18)
        tx = QLabel(f"<b>{html.escape(title)}</b><br>{html.escape(detail)}")
        tx.setTextFormat(Qt.RichText); tx.setWordWrap(True)
        tx.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tx.setAccessibleName(f"{title}: {detail}")
        h.addWidget(ic); h.addWidget(tx, 1)
        self.lay.insertWidget(self.lay.count() - 1, row)

    def count(self):
        return self.lay.count() - 1

NAMES = {"summary": "Summary, four panels", "potential_capacity": "Potential vs. capacity",
         "capacity_efficiency": "Capacity and efficiency", "dqde": "Differential capacity",
         "average_voltage": "Average voltage and hysteresis", "overview_time": "Potential and current vs. time",
         "dqde_map": "dQ/dE map over cycles", "dqde_surface": "dQ/dE surfaces in 3D"}
ORDER = ["summary", "potential_capacity", "capacity_efficiency", "dqde", "average_voltage", "overview_time",
         "dqde_map", "dqde_surface"]
# preview size for "fit": (journal width role, height / width), as the figure functions draw them
SHAPES = {"summary": ("double", 0.80), "overview_time": ("double", 0.42), "dqde_map": ("one_half", 0.50),
          "dqde_surface": ("double", 0.28)}


def render(run, opts, name, dpi):
    """Draw one figure; returns (png bytes, checks, size in mm). Runs in a worker."""
    with RENDER_LOCK:
        builders = workflow.figure_builders(run, opts)
        if name not in builders:
            raise ValueError(f"{NAMES.get(name, name)} is not available for this record")
        fig = builders[name]()
        checks = plotting.check_figure(fig, opts.journal)
        w, h = fig.get_size_inches() * 25.4
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, metadata={"Software": "electrochem-toolkit"})
        import matplotlib.pyplot as plt
        plt.close(fig)
        return buf.getvalue(), checks, (w, h)


class FigureStudio(QWidget):
    exportRequested = Signal(object)          # ExportOptions
    status = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rec = None
        self.current = "summary"
        self.picked = None                        # the figure you chose; kept while it stays available
        self.ticks = {}                           # per record: figure -> exported or not, as you left it (r05)
        self.zoom = "fit"
        self._token = 0
        self._timer = QTimer(self, singleShot=True, interval=180)
        self._timer.timeout.connect(self._render)

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(12)

        # ---- controls
        side_panel = QFrame(); side_panel.setObjectName("Panel"); side_panel.setFixedWidth(280)
        self.side_panel = side_panel
        spl = QVBoxLayout(side_panel); spl.setContentsMargins(0, 0, 0, 0)
        side_scroll = QScrollArea(); side_scroll.setWidgetResizable(True)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side = QWidget(); side_scroll.setWidget(side)
        spl.addWidget(side_scroll)
        sl = QVBoxLayout(side); sl.setContentsMargins(12, 12, 12, 12); sl.setSpacing(5)
        h = QLabel("Figures"); h.setProperty("role", "h2"); sl.addWidget(h)
        hint = QLabel("Choose a figure to preview. Ticked figures are exported.")
        hint.setProperty("role", "muted"); hint.setWordWrap(True); sl.addWidget(hint)
        self.list = QListWidget()
        self.list.setFixedHeight(len(ORDER) * 34 + 10)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(lambda it: self._pick(self.list.row(it)))
        self.list.currentRowChanged.connect(lambda r: self._pick(r) if self.list.hasFocus() else None)
        self.list.itemChanged.connect(self._ticked)
        self.list.setAccessibleName("Figures")
        sl.addWidget(self.list)

        def combo(label, items, attr):
            l = QLabel(label); l.setProperty("role", "section")
            c = QComboBox()
            for text, data in items:
                c.addItem(text, data)
            c.currentIndexChanged.connect(self._changed)
            c.setAccessibleName(label)
            l.setBuddy(c)
            sl.addWidget(l); sl.addWidget(c)
            setattr(self, attr, c)

        combo("Journal rules", [(f"{j.name} ({', '.join(f'{v:g}' for v in j.widths_mm.values())} mm)", k)
                                for k, j in plotting.JOURNALS.items()], "journal")
        combo("Cycle colours", [("Violet to teal (default)", "blues"), ("Viridis, dark end", "viridis"),
                                ("Okabe and Ito, up to seven cycles", "okabe")], "palette")
        combo("Coulombic efficiency axis", [("Zoomed to the data", "auto"), ("0 to 100 %", "full")], "ce")
        combo("Differential capacity", [("Normalised (a.u.)", "au"), ("Real units", "real")], "dq")
        combo("dQ/dE map and surface", [("Every cycle", "all"), ("Selected cycles", "selected")], "evo")
        l = QLabel("Files"); l.setProperty("role", "section"); sl.addWidget(l)
        self.fmt = {}
        row = QHBoxLayout()
        for f, on in (("pdf", True), ("svg", True), ("png", True)):
            cb = QCheckBox(f.upper() if f != "png" else "PNG 600 dpi"); cb.setChecked(on)
            self.fmt[f] = cb; row.addWidget(cb)
        sl.addLayout(row)
        self.origin = QCheckBox("Origin folder (tables and build script)"); self.origin.setChecked(True)
        self.origin.setToolTip("An Origin folder: the tables in Origin's import layout and a script that builds "
                               "the project")
        sl.addWidget(self.origin)
        sl.addStretch(1)
        self.export_btn = QPushButton("Export figures and tables…")
        self.export_btn.setProperty("kind", "primary")
        self.export_btn.setIcon(theme.icon("export", theme.tokens().primary_text))
        self.export_btn.clicked.connect(lambda: self.exportRequested.emit(self.options()))
        brow = QHBoxLayout(); brow.setContentsMargins(12, 4, 12, 12); brow.addWidget(self.export_btn)
        spl.addLayout(brow)
        root.addWidget(side_panel)

        # ---- preview
        mid = QVBoxLayout(); mid.setSpacing(6)
        bar = QHBoxLayout()
        self.size_label = QLabel(" "); self.size_label.setProperty("role", "secondary")
        self.size_label.setFont(theme.font(9, tabular=True))
        self.size_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)     # shrinks before the buttons
        bar.addWidget(self.size_label); bar.addStretch(1)
        seg = QWidget(); seg.setObjectName("Segmented")
        sg = QHBoxLayout(seg); sg.setContentsMargins(3, 3, 3, 3); sg.setSpacing(2)
        self.zoom_group = QButtonGroup(self)
        for key, text in (("true", "True size"), ("fit", "Fit"), ("x2", "200 %")):
            b = QToolButton(); b.setText(text); b.setCheckable(True); b.setChecked(key == "fit")
            b.setMinimumWidth(b.fontMetrics().horizontalAdvance(text) + 22)
            b.clicked.connect(lambda _=False, k=key: self._set_zoom(k))
            self.zoom_group.addButton(b); sg.addWidget(b)
        bar.addWidget(seg)
        mid.addLayout(bar)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.canvas = QWidget(); self.canvas.setObjectName("Frame")
        cl = QVBoxLayout(self.canvas); cl.setContentsMargins(28, 28, 28, 28); cl.setAlignment(Qt.AlignCenter)
        self.sheet = QLabel(); self.sheet.setAlignment(Qt.AlignCenter)
        self.sheet.setStyleSheet("background: white; border: 1px solid #D8DEE5;")
        shadow = QGraphicsDropShadowEffect(self.sheet); shadow.setBlurRadius(28); shadow.setOffset(0, 6)
        shadow.setColor(QColor(10, 20, 30, 50)); self.sheet.setGraphicsEffect(shadow)
        self.sheet.setAccessibleName("Figure preview")
        cl.addWidget(self.sheet)
        self.scroll.setWidget(self.canvas)
        mid.addWidget(self.scroll, 1)
        self.scale_note = QLabel(" "); self.scale_note.setProperty("role", "muted"); self.scale_note.setWordWrap(True)
        mid.addWidget(self.scale_note)
        root.addLayout(mid, 1)

        # ---- checks
        chk = QFrame(); chk.setObjectName("Panel"); chk.setFixedWidth(240)
        self.check_panel = chk
        self._narrow = None
        cl2 = QVBoxLayout(chk); cl2.setContentsMargins(12, 12, 12, 12); cl2.setSpacing(6)
        h2 = QLabel("Figure checks"); h2.setProperty("role", "h2"); cl2.addWidget(h2)
        self.verdict = QLabel(" "); self.verdict.setWordWrap(True); cl2.addWidget(self.verdict)
        self.checks = CheckList()
        cl2.addWidget(self.checks, 1)
        self.rules = QLabel(""); self.rules.setProperty("role", "muted"); self.rules.setWordWrap(True)
        cl2.addWidget(self.rules)
        root.addWidget(chk)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        narrow = self.width() < 820                     # beside the inspector on a narrow window
        if narrow != self._narrow:
            self._narrow = narrow
            self.side_panel.setFixedWidth(232 if narrow else 280)
            self.check_panel.setFixedWidth(200 if narrow else 240)
            self.origin.setText("Origin folder" if narrow else "Origin folder (tables and build script)")
            self.fmt["png"].setText("PNG" if narrow else "PNG 600 dpi")

    # ---------------------------------------------------------------- state
    def options(self) -> workflow.ExportOptions:
        plots = {self.list.item(k).data(Qt.UserRole) for k in range(self.list.count())
                 if self.list.item(k).checkState() == Qt.Checked}
        return workflow.ExportOptions(plots=plots, formats=tuple(f for f, cb in self.fmt.items() if cb.isChecked()) or ("pdf",),
                                      palette=self.palette.currentData(), ce_range=self.ce.currentData(),
                                      dqde_units=self.dq.currentData(), origin=self.origin.isChecked(),
                                      journal=self.journal.currentData(), evolution_cycles=self.evo.currentData())

    def _key(self, rec):
        return id(rec)

    def _ticked(self, it):
        if self.rec is not None:
            self.ticks.setdefault(self._key(self.rec), {})[it.data(Qt.UserRole)] = it.checkState() == Qt.Checked
        self._sync_export()

    def show_record(self, rec):
        self.rec = rec
        self.list.blockSignals(True)
        self.list.clear()
        avail = workflow.figure_builders(rec.run, self.options()) if rec and rec.run else {}
        kept = self.ticks.get(self._key(rec), {}) if rec else {}
        for name in ORDER:
            it = QListWidgetItem(NAMES[name])
            it.setData(Qt.UserRole, name)
            if name in avail:
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if kept.get(name, True) else Qt.Unchecked)
            else:
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
                why = self._why_missing(name, rec)
                it.setToolTip(why)
                it.setText(NAMES[name] + f"  ({self._short_why(rec)})")
            self.list.addItem(it)
        self.list.blockSignals(False)
        if not avail:
            self._clear(self._why_missing(None, rec))
        names = [n for n in ORDER if n in avail]
        self.current = self.picked if self.picked in names else (names[0] if names else None)
        if self.current:
            self.list.blockSignals(True)                 # a programmatic selection is not your pick
            self.list.setCurrentRow(ORDER.index(self.current))
            self.list.blockSignals(False)
        self._sync_export()
        j = plotting.JOURNALS[self.journal.currentData()]
        self.rules.setText(f"{j.name}: text {j.min_pt:g} to {j.max_pt:g} pt, panel labels {j.panel_pt:g} pt bold, "
                           f"maximum height {j.max_height_mm:g} mm. Source: {j.source}.")
        self._timer.start()

    @staticmethod
    def _short_why(rec):
        if rec is None or rec.error:
            return "the file could not be read"
        if rec.loaded is None or rec.run is None:
            return "not analysed yet"
        return "needs an answer"

    def _clear(self, why):
        """Nothing can be drawn for this record: no figure of another file stays on the sheet (r20)."""
        self._token += 1                          # a render still running for the previous record is dropped
        self.sheet.setPixmap(QPixmap())
        self.sheet.setText(why or "")
        self.sheet.setFixedSize(QSize(420, 120))
        self.size_label.setText(" ")
        self.scale_note.setText(" ")
        self.checks.clear()
        self.verdict.setText(" ")

    def restyle(self):
        self.export_btn.setIcon(theme.icon("export", theme.tokens().primary_text))

    def _why_missing(self, name, rec):
        if rec is not None and rec.error:
            return f"This file could not be read: {rec.error}"
        if not rec or not rec.run:
            return "The file has not been analysed yet."
        s = rec.run.settings
        if name in ("average_voltage", "summary") and not s.energy_allowed:
            return "Needs what the potential column measures."
        if name in ("capacity_efficiency", "average_voltage", "summary"):
            return "Needs at least one complete cycle, which needs the charging direction."
        return "Not available for this file."

    def _sync_export(self):
        ok = self.rec is not None and self.rec.run is not None and bool(self.options().plots)
        self.export_btn.setEnabled(ok)

    def _pick(self, row):
        if row < 0:
            return
        it = self.list.item(row)
        if not (it.flags() & Qt.ItemIsEnabled):
            return
        self.current = it.data(Qt.UserRole)
        self.picked = self.current
        self._timer.start()

    def _changed(self, *_):
        if self.rec:
            j = plotting.JOURNALS[self.journal.currentData()]
            self.rules.setText(f"{j.name}: text {j.min_pt:g} to {j.max_pt:g} pt, panel labels {j.panel_pt:g} pt bold, "
                               f"maximum height {j.max_height_mm:g} mm. Source: {j.source}.")
        self._timer.start()

    def _set_zoom(self, key):
        self.zoom = key
        self._timer.start()

    # ---------------------------------------------------------------- rendering
    def _px_per_mm(self):
        scr = self.screen() or QGuiApplication.primaryScreen()
        phys = scr.physicalSize()
        if phys.width() > 50:
            return scr.geometry().width() / phys.width(), True
        return scr.logicalDotsPerInch() / 25.4, False

    def _render(self):
        if not self.rec or not self.rec.run or not self.current or not self.isVisible():
            return
        self._token += 1
        token = self._token
        ppm, calibrated = self._px_per_mm()
        dpr = self.devicePixelRatioF()
        zoom = {"true": 1.0, "x2": 2.0}.get(self.zoom, None)
        if zoom is None:                                      # fit: scale so the width fills the view
            j = plotting.JOURNALS[self.journal.currentData()]
            role, ratio = SHAPES.get(self.current, ("single", 0.86))
            wmm = j.widths_mm.get(role, j.widths_mm["single"])
            hmm = wmm * ratio
            vp = self.scroll.viewport()
            zoom = max(0.3, min((vp.width() - 70) / (wmm * ppm), (vp.height() - 70) / (hmm * ppm)))
        dpi = ppm * 25.4 * zoom * dpr
        self._scale = (ppm, calibrated, zoom)
        self.status.emit(f"Drawing {NAMES[self.current].lower()}…")
        worker.start(worker.Job(token, render, self.rec.run, self.options(), self.current, dpi),
                     done=self._rendered, failed=self._failed)

    def _rendered(self, token, out):
        if token != self._token:
            return
        png, checks, (w, h) = out
        pm = QPixmap()
        pm.loadFromData(png, "PNG")
        pm.setDevicePixelRatio(self.devicePixelRatioF())
        self.sheet.setPixmap(pm)
        self.sheet.setFixedSize(pm.size() / self.devicePixelRatioF() + QSize(2, 2))
        ppm, calibrated, zoom = self._scale
        self.size_label.setText(f"{w:.1f} × {h:.1f} mm, drawn at {zoom * 100:.0f} %")
        self.scale_note.setText(("True size is calibrated from the size your screen reports. "
                                 if calibrated else "Your screen does not report its size; true size assumes 96 dpi. ")
                                + "Hold a ruler to the sheet to check it once.")
        self._show_checks(checks)
        self.status.emit("Figure drawn")

    def _failed(self, token, msg, tb):
        if token != self._token:
            return
        self.sheet.setText(msg)
        self.status.emit(msg)

    def _show_checks(self, checks):
        t = theme.tokens()
        self.checks.clear()
        fails = [c for c in checks if c.status == "fail"]
        warns = [c for c in checks if c.status == "warn"]
        skips = [c for c in checks if c.status == "skip"]       # not evaluated, with the reason in the detail
        for c in checks:
            ic = {"pass": ("check", t.ok), "warn": ("warn", t.provisional), "fail": ("cross", t.error),
                  "skip": ("info", t.muted)}.get(c.status, ("info", t.muted))
            self.checks.add(theme.icon(*ic), c.name.capitalize(), c.detail)
        if fails:
            self.verdict.setText(f"{len(fails)} check{'s' if len(fails) > 1 else ''} failed. Fix before submitting.")
            self.verdict.setStyleSheet(f"color: {t.error}; font-weight: 600;")
        elif warns:
            self.verdict.setText(f"Passes the journal rules, with {len(warns)} note{'s' if len(warns) > 1 else ''}.")
            self.verdict.setStyleSheet(f"color: {t.provisional}; font-weight: 600;")
        elif skips:
            self.verdict.setText(f"{len(checks) - len(skips)} checks pass; {len(skips)} could not be evaluated.")
            self.verdict.setStyleSheet(f"color: {t.provisional}; font-weight: 600;")
        else:
            self.verdict.setText(f"All {len(checks)} checks pass.")
            self.verdict.setStyleSheet(f"color: {t.ok}; font-weight: 600;")

    def showEvent(self, e):
        super().showEvent(e)
        self._timer.start()
