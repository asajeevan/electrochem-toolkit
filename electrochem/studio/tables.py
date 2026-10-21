"""Result tables: cycles, branches, rests, diagnostics and activity.

Column names are written out with units. A value the engine could not
compute is shown as the word "withheld" in slate with the reason on hover,
never as an empty cell. Ctrl+C copies the selected rows as tab-separated text
with the headers, units and a States column (P12 review finding 15), so
Excel and Origin receive numbers, not a bitmap.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import fields
from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem,
                               QStackedWidget, QTabBar, QTableView, QToolButton, QVBoxLayout, QWidget)

from . import theme
from .model import reason_for
from .platform_support import shortcut_text

UNITS = [("_mAh_g", "mAh g⁻¹"), ("_mAh_cm2", "mAh cm⁻²"), ("_mA_g", "mA g⁻¹"),
         ("_mA_cm2", "mA cm⁻²"), ("_Wh_kg", "Wh kg⁻¹"), ("_mWh", "mWh"), ("_mAh", "mAh"),
         ("_mA", "mA"), ("_pct", "%"), ("_V", "V"), ("_s", "s"), ("_h", "h"), ("_C", "°C")]
WORDS = {"cv": "CV", "cc": "CC", "ocv": "OCV", "ce": "CE", "c_rate": "C-rate", "delta_x": "Δx"}


def heading(name: str) -> str:
    unit = ""
    for suf, u in UNITS:
        if name.endswith(suf):
            name, unit = name[: -len(suf)], u
            break
    name = name.replace("c_rate", "C-rate").replace("delta_x", "Δx")
    words = [WORDS.get(w, w) for w in name.split("_")]
    text = " ".join(words)
    text = text[0].upper() + text[1:] if text else text
    text = re.sub(r"\bCv\b", "CV", text)
    return f"{text} ({unit})" if unit else text


def _cell(v):
    if isinstance(v, float):
        if abs(v) >= 1e5 or (0 < abs(v) < 1e-3):
            return f"{v:.4e}"
        return f"{v:.6g}" if abs(v) < 1000 else f"{v:.1f}"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return "" if v is None else str(v)


_ROLES = {Qt.DisplayRole, Qt.UserRole, Qt.ForegroundRole, Qt.ToolTipRole, Qt.TextAlignmentRole,
          Qt.AccessibleDescriptionRole}
_RIGHT = int(Qt.AlignRight | Qt.AlignVCenter)
_LEFT = int(Qt.AlignLeft | Qt.AlignVCenter)


class RowsModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []
        self.cols: list[str] = []
        self.answers = None

    def set_rows(self, objs, answers=None, run=None):
        self.beginResetModel()
        names = [f.name for f in fields(objs[0])] if objs else []
        self.rows = [{k: getattr(o, k) for k in names} for o in objs]   # flat records: no deep copy (asdict)
        self.cols = names
        self.answers = answers
        self.run = run
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.cols)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return heading(self.cols[section])
        if orientation == Qt.Horizontal and role == Qt.ToolTipRole:
            return self.cols[section]
        return None

    def data(self, idx, role=Qt.DisplayRole):
        if role not in _ROLES or not idx.isValid():
            return None
        name = self.cols[idx.column()]
        v = self.rows[idx.row()][name]
        if role == Qt.TextAlignmentRole:
            return _RIGHT if isinstance(v, (int, float)) and not isinstance(v, bool) else _LEFT
        t = theme.tokens()
        if role == Qt.DisplayRole:
            if v is None:
                return "withheld" if self._reason(name) else "–"
            return _cell(v)
        if role == Qt.UserRole:                       # sort key
            return (1, 0.0) if v is None else (0, v) if isinstance(v, (int, float)) else (0, str(v))
        if role == Qt.ForegroundRole and v is None:
            return QColor(t.withheld)
        if role == Qt.ToolTipRole and v is None:
            r = self._reason(name)
            return f"Withheld: {r}" if r else "Not defined for this row"
        if role == Qt.AccessibleDescriptionRole and v is None:
            return "withheld"
        return None

    def _reason(self, name):
        return reason_for(name, self.answers, getattr(self, "run", None)) if self.answers is not None else None


class SortProxy(QSortFilterProxyModel):
    def lessThan(self, a, b):
        return (self.sourceModel().data(a, Qt.UserRole) or (1, 0)) < (self.sourceModel().data(b, Qt.UserRole) or (1, 0))


class Table(QTableView):
    rowActivated = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model_ = RowsModel(self)
        self.proxy = SortProxy(self)
        self.proxy.setSourceModel(self.model_)
        self.setModel(self.proxy)
        self.setSortingEnabled(True)
        self.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)   # keep the engine's order until clicked
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setDefaultSectionSize(118)
        self.horizontalHeader().setHighlightSections(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(24)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setTabKeyNavigation(False)                                   # P12 review finding 10
        self.setFont(theme.font(9, tabular=True))
        self.setShowGrid(False)
        self.selectionModel().currentRowChanged.connect(self._current)

    def set_rows(self, objs, answers=None, run=None):
        self.model_.set_rows(objs, answers, run)
        self.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        # Column widths from the header and a sample of rows, measured here: Qt's resizeColumnsToContents
        # asks the model for every role of every sampled cell and froze the window for seconds after
        # each answer on a long file.
        fm, hfm = self.fontMetrics(), self.horizontalHeader().fontMetrics()
        rows = self.model_.rows
        sample = rows[:20] + rows[-5:] if len(rows) > 25 else rows
        for k, c in enumerate(self.model_.cols):
            wd = hfm.horizontalAdvance(heading(c)) + 26
            for r in sample:
                v = r[c]
                wd = max(wd, fm.horizontalAdvance(_cell(v) if v is not None else "withheld") + 18)
            self.setColumnWidth(k, min(max(wd, 70), 220))

    def _current(self, cur, _):
        if cur.isValid():
            src = self.proxy.mapToSource(cur)
            self.rowActivated.emit(self.model_.rows[src.row()])

    def select_where(self, key, value):
        for r, row in enumerate(self.model_.rows):
            if row.get(key) == value:
                idx = self.proxy.mapFromSource(self.model_.index(r, 0))
                self.blockSignals(True)
                self.selectRow(idx.row())
                self.scrollTo(idx, QAbstractItemView.PositionAtCenter)
                self.blockSignals(False)
                return

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Copy):
            self.copy()
            return
        super().keyPressEvent(e)

    def set_placeholder(self, text):
        """A sentence in place of an empty table, saying why it is empty (review finding 27)."""
        self._placeholder = text
        self.viewport().update()

    def paintEvent(self, e):
        super().paintEvent(e)
        text = getattr(self, "_placeholder", None)
        if text and self.model_.rowCount() == 0:
            from PySide6.QtGui import QPainter
            p = QPainter(self.viewport())
            p.setPen(QColor(theme.tokens().secondary))
            p.setFont(theme.font(9.5))
            p.drawText(self.viewport().rect().adjusted(24, 12, -24, -12), Qt.AlignCenter | Qt.TextWordWrap, text)
            p.end()

    def copy(self):
        rows = sorted({self.proxy.mapToSource(i).row() for i in self.selectionModel().selectedRows()})
        if not rows:
            return
        cols = self.model_.cols
        lines = ["\t".join(heading(c) for c in cols) + "\tStates"]
        for r in rows:
            row = self.model_.rows[r]
            states = [f"{heading(c)}: withheld" for c in cols if row[c] is None and self.model_._reason(c)]
            lines.append("\t".join("" if row[c] is None else repr(row[c]) if isinstance(row[c], float) else str(row[c])
                                   for c in cols) + "\t" + ("; ".join(states) or "available"))
        QGuiApplication.clipboard().setText("\n".join(lines))


class Diagnostics(QListWidget):
    """Grouped messages: repeated ones are counted, not repeated (U01 principle P9)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAlternatingRowColors(False)

    def show_record(self, rec):
        self.clear()
        if rec is None or rec.loaded is None:
            return
        t = theme.tokens()
        items = []
        if rec.run:
            bad = implausible_capacity(rec)
            if bad:
                items.append(("warn", bad))
            for w in rec.run.warnings:
                items.append(("warn", w))
            for n in rec.run.seg.convention.get("notes", []):
                items.append(("info", n))
            reasons = Counter(rec.run.seg.edges.reason.values())
            for r, n in reasons.most_common():
                items.append(("info", f"{n} edge{'s' if n > 1 else ''} not integrated: {r}"))
            import numpy as np
            for d in ("charge", "discharge"):
                brs = [b for b in rec.run.an.branches if b.direction == d]
                done = [b.charge_mAh for b in brs if b.complete]
                if len(done) >= 3:
                    med = float(np.median(done))
                    for b in brs:
                        if med > 0 and b.charge_mAh > 3 * med:
                            v = (f", potential {b.voltage_start_V:.3f} to {b.voltage_end_V:.3f} V"
                                 if b.voltage_start_V is not None and b.voltage_end_V is not None else "")
                            items.append(("warn", f"{d.capitalize()} branch {b.branch} passed {b.charge_mAh:.3g} mAh, "
                                                  f"{b.charge_mAh / med:.0f} times the median {d} ({med:.3g} mAh), over "
                                                  f"{b.duration_s / 3600:.1f} h{v}; it ended by {b.terminated_by}. "
                                                  "The data alone do not say why; check the cell and the protocol."))
            def listed(cs):
                return ", ".join(map(str, cs[:12])) + ("…" if len(cs) > 12 else "")
            lone = [c.cycle for c in rec.run.an.cycles if not c.complete and
                    (c.charge_branch is None or c.discharge_branch is None)]
            partial = [c.cycle for c in rec.run.an.cycles if not c.complete and
                       c.charge_branch is not None and c.discharge_branch is not None]
            if lone:
                items.append(("info", f"{len(lone)} incomplete cycle{'s' if len(lone) > 1 else ''} (no partner branch): "
                                      + listed(lone)))
            if partial:                    # both branches present, one cut short: the end of the file, or a gap
                items.append(("info", f"{len(partial)} incomplete cycle{'s' if len(partial) > 1 else ''} (a branch "
                                      "reaches the end of the file or has an unsupported interval): " + listed(partial)))
            for n in (rec.run.an.summary.notes or "").split("; "):
                if n:
                    items.append(("info", n))
        if rec.loaded.tab.invalid_rows:
            items.append(("warn", f"{rec.loaded.tab.invalid_rows} unreadable values became NaN and are not integrated"))
        # a file read through an import profile: what the reader concluded and compared (readers.checks)
        rep_ = rec.loaded.meta.get("import_report")
        if rep_:
            sem = rep_.get("capacity_semantics", "none")
            items.append(("info", f"Import: read with the {rec.loaded.meta.get('profile')} profile; current in the file "
                                  f"{rep_.get('current_sign_declared', '?').replace('_', ' ')}, analysed charge-positive; "
                                  + ("capacity from the sampled current (no counter used)" if sem == "none" else
                                     f"charge from the instrument's counter ({sem.replace('_', ' ')})")))
        for f in rec.loaded.meta.get("import_findings", []):
            items.append(("warn" if f.get("severity") == "warn" else "info", f"Import: {f.get('message', '')}"))
        cex = (rep_ or {}).get("cex") or {}
        sc, tc = cex.get("scale_check") or {}, cex.get("time_check") or {}
        if sc.get("basis"):                # a .cex read natively: its scales against the tester's own counters
            items.append(("info", f"Import: the decoded current integrates to the tester's capacity counter within "
                                  f"{abs(sc['current_ratio'] - 1) * 100:.2g} %"
                                  + (f", and the decoded voltage reproduces the mean voltage of its energy and "
                                     f"capacity counters within {abs(sc['voltage_ratio'] - 1) * 100:.2g} %"
                                     if sc.get("voltage_ratio") else "")
                                  + f" ({sc['intervals']} intervals of {sc['basis']})"))
        if tc.get("intervals"):
            added = tc.get("time_not_counted_s") or 0
            items.append(("info", f"Import: the record time follows the tester's clock in {tc['intervals_agreeing']} of "
                                  f"{tc['intervals']} intervals between step starts"
                                  + (f", once {added:.0f} s of pauses and stops are added back" if added else "")
                                  + f" (slope {tc['slope']:.6f}, largest offset between consecutive step starts "
                                  f"{tc['largest_offset_s']:.2f} s)"))
        cv = (rec.loaded.meta.get("import_report") or {}).get("counter_vs_integral") or {}
        parts = [f"{side} {abs(v['relative_difference']) * 100:.3f} %" for side, v in cv.items()
                 if isinstance(v, dict) and v.get("relative_difference") is not None]
        if parts:
            items.append(("info", "Import: the instrument's counter and the integrated current differ by "
                          + ", ".join(parts) + " (charge and discharge compared separately)"))
        if not items:
            items.append(("ok", "Nothing to report: every edge was integrated and every branch has a partner."))
        for kind, text in items:
            it = QListWidgetItem(theme.icon({"warn": "warn", "info": "info", "ok": "check"}[kind],
                                            {"warn": t.provisional, "info": t.muted, "ok": t.ok}[kind]), text)
            it.setToolTip(text)
            self.addItem(it)


class Activity(QListWidget):
    def log(self, text):
        it = QListWidgetItem(f"{datetime.now().strftime('%H:%M:%S')}   {text}")
        self.addItem(it)
        self.scrollToBottom()

    def lines(self):
        return [self.item(k).text() for k in range(self.count())]


IMPLAUSIBLE_SPECIFIC_MAH_G = 5000.0     # above lithium metal (3861) and silicon (about 4200) mAh/g


def implausible_capacity(rec) -> str | None:
    """A warning when the specific capacities cannot be those of an electrode material: the usual
    cause is a wrong mass, such as EC-Lab's 0.001 mg default (review finding 16)."""
    if not rec or not rec.run or not rec.run.settings.active_mass_mg:
        return None
    vals = [b.specific_capacity_mAh_g for b in rec.run.an.branches if b.specific_capacity_mAh_g is not None]
    if not vals or max(vals) <= IMPLAUSIBLE_SPECIFIC_MAH_G:
        return None
    big = f"{max(vals):,.0f}".replace(",", "\u2009")
    return (f"The largest specific capacity, {big} mAh g⁻¹, is above the theoretical capacity of any insertion or "
            "alloying electrode (lithium metal and silicon are about 3\u2009900 to 4\u2009200 mAh g⁻¹). Check the "
            f"active-material mass ({rec.run.settings.active_mass_mg:g} mg). If it is right, for example capacity per "
            "gram of carbon in a metal-air cell, this note can be ignored.")


class Results(QWidget):
    """The result tables under the plots, as a drawer: a row of tabs that can fold the tables away.

    Folded, only the tab row stays (one line), so a short window gives the plots the room;
    clicking a tab, the chevron or Ctrl+J opens it again. The API mirrors the QTabWidget it
    replaces (addTab, setTabText, currentWidget, currentIndex, setCurrentIndex, count, widget).
    """
    cycleActivated = Signal(int)
    collapsedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.collapsed = False
        self.bar = QTabBar()
        self.bar.setDrawBase(False)
        self.bar.setExpanding(False)
        self.bar.setUsesScrollButtons(True)
        self.bar.setElideMode(Qt.ElideNone)
        self.stack = QStackedWidget()
        self.toggle = QToolButton()
        self.toggle.setObjectName("DrawerToggle")
        self.toggle.setAutoRaise(True)
        self.toggle.setIconSize(QSize(16, 16))
        self.toggle.clicked.connect(lambda: self.set_collapsed(not self.collapsed))
        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 0); head.setSpacing(4)
        head.addWidget(self.bar, 1)                 # the whole row: a tab whose text grows is never cut off
        head.addWidget(self.toggle, 0, Qt.AlignVCenter)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        lay.addLayout(head)
        lay.addWidget(self.stack, 1)
        self.bar.currentChanged.connect(self.stack.setCurrentIndex)
        self.bar.tabBarClicked.connect(self._tab_clicked)
        self.cycles = Table(); self.branches = Table(); self.rests = Table()
        self.diagnostics = Diagnostics(); self.activity = Activity()
        self.addTab(self.cycles, "Cycles")
        self.addTab(self.branches, "Branches")
        self.addTab(self.rests, "Rests")
        self.addTab(self.diagnostics, "Diagnostics")
        self.addTab(self.activity, "Activity")
        self.cycles.rowActivated.connect(lambda row: self.cycleActivated.emit(int(row["cycle"])))
        self.cycles.setAccessibleName("Cycles table")
        self.branches.setAccessibleName("Branches table")
        self.restyle()

    # the QTabWidget API the window uses
    def addTab(self, w, text):
        self.stack.addWidget(w)
        return self.bar.addTab(text)

    def setTabText(self, k, text):
        self.bar.setTabText(k, text)

    def currentWidget(self):
        return self.stack.currentWidget()

    def currentIndex(self):
        return self.bar.currentIndex()

    def setCurrentIndex(self, k):
        self.bar.setCurrentIndex(k)

    def count(self):
        return self.bar.count()

    def widget(self, k):
        return self.stack.widget(k)

    def header_height(self) -> int:
        return max(self.bar.sizeHint().height(), self.toggle.sizeHint().height())

    def _tab_clicked(self, k):
        if self.collapsed and k >= 0:          # a folded drawer opens on the tab that was clicked
            self.set_collapsed(False)

    def set_collapsed(self, on: bool):
        on = bool(on)
        if on == self.collapsed:
            return
        self.collapsed = on
        self.stack.setVisible(not on)
        self.restyle()
        self.collapsedChanged.emit(on)

    def restyle(self):
        t = theme.tokens()
        self.toggle.setIcon(theme.icon("chevron-up" if self.collapsed else "chevron-down", t.secondary, 16))
        self.toggle.setToolTip(("Show the tables" if self.collapsed else "Hide the tables, to give the plots the room")
                               + f" ({shortcut_text('Ctrl+J')})")
        self.toggle.setAccessibleName("Show the tables" if self.collapsed else "Hide the tables")

    @staticmethod
    def _why_no_cycles(rec):
        if rec is None or rec.loaded is None or rec.error:
            return None
        if rec.run is None:
            return "Analysing…"
        if rec.answers.charge is None:
            return ("Cycles appear once you say which current direction charges the cell: the first question in the "
                    "inspector. The Branches table already lists every charge and discharge by current sign.")
        return "No charge and discharge could be paired into a cycle; the Branches table lists what the file holds."

    def show_record(self, rec):
        an = rec.run.an if rec and rec.run else None
        a = rec.answers if rec else None
        run = rec.run if rec else None
        self.cycles.set_rows(an.cycles if an else [], a, run)
        self.branches.set_rows(an.branches if an else [], a, run)
        self.rests.set_rows(an.rests if an else [], a, run)
        self.cycles.set_placeholder(None if (an and an.cycles) else self._why_no_cycles(rec))
        self.diagnostics.show_record(rec)
        n = self.diagnostics.count()
        self.setTabText(3, f"Diagnostics ({n})" if n else "Diagnostics")
