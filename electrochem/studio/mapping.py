"""The import review step: a file from an instrument no profile recognises.

The proposer has already found the table, scored every column and measured what
the data can state about itself. This page shows that proposal beside the first
rows of the file, lets the researcher correct the columns and answer the four
things no file states about itself (the sign convention, where the direction
comes from, what the capacity columns accumulate, the cycle numbering base),
checks the mapping against the file, and only then opens it. "Remember this
instrument" saves the mapping against a fingerprint of the header, so the next
file from the same instrument opens without questions.

Nothing is computed from a mapping that has not passed its check: the engine
never sees a table the reader could not vouch for.
"""
from __future__ import annotations

import re

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import workflow
from ..readers import Binding, Conventions, ImportProfile, Layout
from ..readers.profile import UNIT_FACTOR, units_for
from ..readers.propose import STEP_KIND_TEXT, STEP_KINDS, _unit_of, guess_step_kind
from ..readers.reader import _match, _split_unit
from . import theme, worker
from .inspector import Card, _label

# role, label, hint, required
ROLES = [
    ("test_time_second", "Time", "the test clock, cumulative over the whole file", True),
    ("current_ampere", "Current", "the measured current, not a setpoint", True),
    ("voltage_volt", "Potential", "cell voltage or working-electrode potential", True),
    ("step_id", "Step index", "the programmed step; branches end where it changes", False),
    ("cycle_count", "Cycle number", "the instrument's own cycle counter", False),
    ("step_type", "Step type", "a text column naming charge, discharge or rest", False),
    ("charging_capacity_ah", "Charge capacity", "the instrument's charge counter", False),
    ("discharging_capacity_ah", "Discharge capacity", "the instrument's discharge counter", False),
    ("net_capacity_ah", "Net charge (dq)", "one signed counter, or per-row increments", False),
    ("surface_temperature_celsius", "Temperature", "", False),
]
NUMERIC = {r for r, *_ in ROLES} - {"step_type"}
NONE = "(not used)"

SIGN = [("charge_positive", "Positive current is charge (most cyclers)"),
        ("discharge_positive", "Positive current is discharge"),
        ("unsigned", "The current is unsigned: the step type gives the direction")]
SEMANTICS = [("none", "Not used: the current is integrated"),
             ("per_row_increment", "Per row: each value is the charge since the previous row"),
             ("step_cumulative", "Per step: the counter resets at each step"),
             ("cycle_cumulative", "Per cycle: the counter resets at each cycle"),
             ("test_cumulative", "Over the whole test: the counter never resets")]


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "instrument"


class MappingPage(QWidget):
    """One page per unrecognised file; the window shows it in the centre."""

    confirmed = Signal(object, object, object, str, str)   # rec, loaded, profile, save_name ("" = no), instrument

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Frame")
        self.rec = None
        self._checked = None                 # the profile JSON the last passing check ran with
        self._loaded = None                  # what that check read
        self._job = None
        self.role_boxes: dict[str, QComboBox] = {}
        self.unit_boxes: dict[str, QComboBox] = {}
        self.kind_boxes: dict[str, QComboBox] = {}

        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(12)

        # ---- left: what the file holds
        left = QVBoxLayout(); left.setSpacing(8)
        self.heading = _label("", "h2")
        left.addWidget(self.heading)
        self.intro = _label("No built-in profile recognises this file's columns. Say which column is which, "
                            "answer what the file cannot state about itself, check the mapping against the file, "
                            "then open it. Nothing is calculated before the check passes.", "secondary")
        left.addWidget(self.intro)
        self.grid = QTableWidget()
        self.grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.grid.setSelectionMode(QAbstractItemView.NoSelection)
        self.grid.verticalHeader().setVisible(False)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.grid.setAccessibleName("The first rows of the file")
        self.grid.setFont(theme.font(8.5, tabular=True))
        left.addWidget(self.grid, 1)
        self.measured = _label("", "muted")
        left.addWidget(self.measured)
        root.addLayout(left, 3)

        # ---- right: the answers
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(430); scroll.setMaximumWidth(520)
        inner = QWidget(); scroll.setWidget(inner)
        inner.setMinimumWidth(0)
        col = QVBoxLayout(inner); col.setContentsMargins(0, 0, 6, 0); col.setSpacing(10)
        self.cards = col
        self.scroll, self.inner = scroll, inner
        scroll.viewport().installEventFilter(self)
        root.addWidget(scroll, 0)

    def eventFilter(self, obj, e):
        if obj is self.scroll.viewport() and e.type() == QEvent.Resize:
            # the cards wrap to the scroll area's width instead of pushing past it (the inspector does the same)
            self.inner.setMaximumWidth(max(e.size().width(), 300))
        return False

    # ------------------------------------------------------------------ building
    def _clear_cards(self):
        while self.cards.count():
            it = self.cards.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide(); w.deleteLater()
        self.role_boxes.clear(); self.unit_boxes.clear(); self.kind_boxes.clear()

    def show_record(self, rec):
        self.rec = rec
        self._checked = None; self._loaded = None
        prop = rec.proposal
        self.heading.setText(f"Map the columns of {rec.path.name}")
        self._fill_grid(prop)
        self._clear_cards()
        headers = list(prop.headers)
        prior = getattr(prop, "prior", None)
        if prior is not None:
            self.intro.setText(f"This looks like another export from {prior.instrument} (your saved profile "
                               f"{prior.name!r} binds {len(prop.prior_shared)} of these columns), with a different "
                               "selection of columns. Its columns and conventions are filled in below: confirm them, "
                               "check against the file, and tick Remember so this layout opens straight through too.")
        else:
            self.intro.setText("No built-in profile recognises this file's columns. Say which column is which, "
                               "answer what the file cannot state about itself, check the mapping against the file, "
                               "then open it. Nothing is calculated before the check passes.")

        # ---- columns
        c1 = Card("Which column is which", "The proposer's choices are marked; the ones it could not settle are "
                  "listed under it. A column with a unit in its name keeps that unit.", False, required=True)
        g = QGridLayout(); g.setHorizontalSpacing(6); g.setVerticalSpacing(5)
        for row, (role, label, hint, required) in enumerate(ROLES):
            lab = QLabel(label + (" *" if required else ""))
            lab.setToolTip(hint)
            box = QComboBox(); box.addItem(NONE)
            for h in headers:
                box.addItem(h)
            chosen = prop.chosen.get(role)
            if chosen is not None:
                box.setCurrentIndex(headers.index(chosen.column) + 1)
                box.setToolTip(f"proposed: {chosen.reason}")
            if prior is not None and role in prior.bindings:
                hit = _match(prior.bindings[role], headers)
                if hit is not None and len(hit[0]) == 1:
                    box.setCurrentIndex(hit[0][0] + 1)
                    box.setToolTip(f"from your saved profile {prior.name!r}")
            box.setAccessibleName(f"Column for {label}")
            box.setObjectName(f"map_{role}")
            box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); box.setMinimumWidth(120)
            box.currentIndexChanged.connect(lambda _=0, r=role: self._column_changed(r))
            self.role_boxes[role] = box
            g.addWidget(lab, row, 0); g.addWidget(box, row, 1)
            if role in NUMERIC:
                ub = QComboBox(); ub.setObjectName(f"unit_{role}")
                ub.setAccessibleName(f"Unit of {label}"); ub.setMinimumWidth(84)
                for u in units_for(role):
                    ub.addItem(u)
                self.unit_boxes[role] = ub
                g.addWidget(ub, row, 2)
        g.setColumnStretch(1, 1)
        c1.body.addLayout(g)
        self.unmapped = _label("", "muted")
        c1.body.addWidget(self.unmapped)
        self.cards.addWidget(c1)

        # ---- conventions
        c2 = Card("What the file cannot say", "These four decide every capacity and efficiency. The reader "
                  "re-measures the counter's behaviour and refuses the import if an answer contradicts the file.",
                  False, required=True)
        self.sign = QComboBox(); self.sign.setObjectName("conv_sign")
        for key, text in SIGN:
            self.sign.addItem(text, key)
        neg = prop.measured.get("current_has_negative_values")
        self.sign.setCurrentIndex(2 if neg is False else 0)
        c2.body.addWidget(_label("Current sign", "section")); c2.body.addWidget(self.sign)
        self.sign_note = _label(("Measured: the current column has negative values." if neg else
                                 "Measured: the current column has no negative value, so the direction must come "
                                 "from a step-type column." if neg is False else ""), "muted")
        c2.body.addWidget(self.sign_note)
        self.sign.currentIndexChanged.connect(lambda _=0: self._refresh_kinds())

        c2.body.addWidget(_label("Step types", "section"))
        self.kinds_note = _label("", "muted")
        c2.body.addWidget(self.kinds_note)
        self.kinds_grid = QGridLayout(); self.kinds_grid.setHorizontalSpacing(6); self.kinds_grid.setVerticalSpacing(4)
        c2.body.addLayout(self.kinds_grid)

        self.semantics = QComboBox(); self.semantics.setObjectName("conv_semantics")
        for key, text in SEMANTICS:
            self.semantics.addItem(text, key)
        c2.body.addWidget(_label("Capacity columns accumulate", "section")); c2.body.addWidget(self.semantics)
        self.semantics_note = _label("", "muted")
        c2.body.addWidget(self.semantics_note)

        self.base = QComboBox(); self.base.setObjectName("conv_base")
        self.base.addItem("Cycles are numbered from 1", 1); self.base.addItem("Cycles are numbered from 0", 0)
        first = prop.measured.get("first_cycle_number")
        if first == 0:
            self.base.setCurrentIndex(1)
        c2.body.addWidget(_label("Cycle numbering", "section")); c2.body.addWidget(self.base)
        if first is not None:
            c2.body.addWidget(_label(f"Measured: the first cycle number in the file is {first:g}.", "muted"))

        c2.body.addWidget(_label("How you know", "section"))
        self.evidence = QLineEdit(); self.evidence.setObjectName("conv_evidence")
        self.evidence.setPlaceholderText("e.g. MITS Pro 8 CSV export; sign checked against the schedule")
        self.evidence.setAccessibleName("Evidence for these conventions")
        c2.body.addWidget(self.evidence)
        c2.body.addWidget(_label("Saved with every result, so a reviewer can see who settled these conventions "
                                 "and from what.", "muted"))
        self.cards.addWidget(c2)

        # ---- check and use
        c3 = Card("Check, then open", "The check reads the whole file with this mapping and compares the "
                  "instrument's counter with the integrated current, charge and discharge separately.",
                  False, required=True)
        self.check_btn = QPushButton("Check this mapping against the file"); self.check_btn.setObjectName("map_check")
        self.check_btn.clicked.connect(self.check)
        c3.body.addWidget(self.check_btn)
        self.report = _label("", "muted"); self.report.setObjectName("map_report")
        c3.body.addWidget(self.report)
        self.remember = QCheckBox("Remember this instrument"); self.remember.setObjectName("map_remember")
        self.remember.setToolTip("Save the mapping: every file with these column names then opens without questions")
        c3.body.addWidget(self.remember)
        self.instrument = QLineEdit(); self.instrument.setObjectName("map_instrument")
        self.instrument.setPlaceholderText("Instrument, e.g. Arbin LBT, Neware BTS 4000, Land CT2001A")
        self.instrument.setAccessibleName("Instrument name")
        c3.body.addWidget(self.instrument)
        self.use_btn = QPushButton("Use this mapping and open the file"); self.use_btn.setObjectName("map_use")
        self.use_btn.setProperty("kind", "primary"); self.use_btn.setEnabled(False)
        self.use_btn.clicked.connect(self.use)
        c3.body.addWidget(self.use_btn)
        self.cards.addWidget(c3)
        self.cards.addStretch(1)

        for role in self.role_boxes:
            self._column_changed(role, initial=True)
        self._refresh_kinds()
        self._refresh_semantics()
        self._measured_text(prop)
        if prior is not None:
            self._apply_prior(prior)

    def _apply_prior(self, prior):
        """Start from a saved profile's conventions: the person confirms them for this layout."""
        conv = prior.conventions
        k = self.sign.findData(conv.current_sign)
        if k >= 0 and conv.current_sign != "detect":
            self.sign.setCurrentIndex(k)
        self._refresh_kinds()
        for value, kb in self.kind_boxes.items():
            kind = conv.step_type_map.get(value)
            if kind is not None and kb.findData(kind) >= 0:
                kb.setCurrentIndex(kb.findData(kind))
        self._refresh_semantics()
        if self.semantics.isEnabled():
            k = self.semantics.findData(conv.capacity_semantics)
            if k >= 0:
                self.semantics.setCurrentIndex(k)
        self.base.setCurrentIndex(0 if conv.cycle_base == 1 else 1)
        self.evidence.setText(f"{conv.evidence} [confirmed again for the columns of this export]")
        self.instrument.setText(prior.instrument)
        self.remember.setChecked(True)

    def _fill_grid(self, prop):
        g = self.grid
        g.clear()
        headers = list(prop.headers)
        rows = prop.preview[:40]
        g.setColumnCount(len(headers)); g.setRowCount(len(rows))
        g.setHorizontalHeaderLabels(headers)
        for r, row in enumerate(rows):
            for c in range(len(headers)):
                it = QTableWidgetItem(row[c] if c < len(row) else "")
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                g.setItem(r, c, it)
        g.resizeColumnsToContents()
        for c in range(len(headers)):
            g.setColumnWidth(c, min(max(g.columnWidth(c), 70), 220))

    def _measured_text(self, prop):
        m = prop.measured
        bits = [f"{m.get('rows', 0):,} rows".replace(",", " ")]
        if "current_range_in_file_units" in m:
            bits.append(f"current {m['current_range_in_file_units']} (file units)")
        if "time_span_in_file_units" in m:
            bits.append(f"time {m['time_span_in_file_units']} (file units)"
                        + ("" if m.get("time_is_monotonic", True) else ", not monotonic"))
        if m.get("step_type_values"):
            bits.append(f"step types {', '.join(m['step_type_values'][:8])}"
                        + ("…" if len(m["step_type_values"]) > 8 else ""))
        self.measured.setText("Measured from the file: " + "; ".join(bits) + ".")
        um = [h for h in prop.unmapped_columns]
        self.unmapped.setText(("Not used: " + ", ".join(um[:12]) + ("…" if len(um) > 12 else "")) if um else "")

    # ------------------------------------------------------------------ reacting
    def _column_changed(self, role, initial=False):
        box = self.role_boxes[role]
        header = box.currentText() if box.currentIndex() > 0 else None
        if role in self.unit_boxes:
            ub = self.unit_boxes[role]
            unit = _unit_of(header) if header else None
            if unit and unit in UNIT_FACTOR:
                k = ub.findText(unit)
                if k < 0:
                    ub.addItem(unit); k = ub.count() - 1
                ub.setCurrentIndex(k); ub.setEnabled(False)
                ub.setToolTip(f"{unit}: stated by the column name")
            else:
                ub.setEnabled(header is not None)
                ub.setToolTip("No unit in the column name: say which unit the values are in")
        if role == "step_type":
            self._refresh_kinds()
        if role in ("charging_capacity_ah", "discharging_capacity_ah", "net_capacity_ah"):
            self._refresh_semantics()
        self._invalidate()

    def _step_values(self):
        box = self.role_boxes.get("step_type")
        if box is None or box.currentIndex() == 0:
            return []
        k = self.rec.proposal.headers.index(box.currentText())
        seen = []
        for r in self.rec.proposal.preview:
            v = r[k].strip() if k < len(r) else ""
            if v and v not in seen:
                seen.append(v)
        for v in self.rec.proposal.measured.get("step_type_values", []):
            if v not in seen:
                seen.append(v)
        return seen[:40]

    def _refresh_kinds(self):
        while self.kinds_grid.count():
            it = self.kinds_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.kind_boxes.clear()
        values = self._step_values()
        unsigned = self.sign.currentData() == "unsigned"
        if not values:
            self.kinds_note.setText("No step-type column is chosen." + (" An unsigned current needs one." if unsigned else
                                    " Direction then comes from the sign of the current."))
            return
        self.kinds_note.setText("Each value's meaning, proposed from its wording; confirm every one"
                                + (": with an unsigned current they are the only source of direction." if unsigned
                                   else ". With a signed current they are cross-checked against the sign."))
        for row, v in enumerate(values):
            lab = QLabel(v); lab.setToolTip(f"step type value {v!r} as written in the file")
            kb = QComboBox(); kb.setObjectName(f"kind_{row}")
            for kind in STEP_KINDS:
                kb.addItem(STEP_KIND_TEXT[kind], kind)
            kb.setCurrentIndex(STEP_KINDS.index(guess_step_kind(v)))
            kb.setAccessibleName(f"Meaning of step type {v}")
            kb.currentIndexChanged.connect(lambda _=0: self._invalidate())
            self.kind_boxes[v] = kb
            self.kinds_grid.addWidget(lab, row, 0); self.kinds_grid.addWidget(kb, row, 1)
        self.kinds_grid.setColumnStretch(1, 1)

    def _refresh_semantics(self):
        caps = [r for r in ("charging_capacity_ah", "discharging_capacity_ah", "net_capacity_ah")
                if self.role_boxes[r].currentIndex() > 0]
        m = self.rec.proposal.measured
        if not caps:
            self.semantics.setCurrentIndex(0)
            self.semantics.setEnabled(False)
            self.semantics_note.setText("No capacity column is chosen: capacity is integrated from the sampled current.")
            return
        self.semantics.setEnabled(True)
        drops = [m.get(f"{r}_ever_decreases") for r in caps if f"{r}_ever_decreases" in m]
        if self.semantics.currentData() == "none":
            self.semantics.setCurrentIndex(4 if drops and not any(drops) else 2 if drops else 4)
        if drops:
            self.semantics_note.setText("Measured: the counter " + ("decreases somewhere, so it resets."
                                                                    if any(drops) else "never decreases."))
        else:
            self.semantics_note.setText("")

    def _invalidate(self):
        self._checked = None; self._loaded = None
        self.use_btn.setEnabled(False)
        self.report.setText("")

    # ------------------------------------------------------------------ the profile
    def profile(self) -> ImportProfile:
        """The profile these controls describe; raises ValueError with a sentence when it is incoherent."""
        prop = self.rec.proposal
        bindings = {}
        for role, box in self.role_boxes.items():
            if box.currentIndex() == 0:
                continue
            header = box.currentText()
            if role == "step_type":
                bindings[role] = Binding(source=(header,), assumed=True)
                continue
            # A unit written in the header ('Current(mA)') is read from the header at import time and
            # not declared here, so a later export of the same instrument in another unit ('Current(A)')
            # is read right. A unit the person supplied, or one implied by a name such as 'Amps', is
            # declared, because the reader cannot see it in the header.
            unit = self.unit_boxes[role].currentText() if role in self.unit_boxes else "1"
            stated = _split_unit(header)[1]
            bindings[role] = Binding(source=(header,), source_unit=None if stated else unit, assumed=True)
        for role, label, _, required in ROLES:
            if required and role not in bindings:
                raise ValueError(f"Choose the column for {label}.")
        chosen = [h for b in bindings.values() for h in b.source]
        dup = sorted({h for h in chosen if chosen.count(h) > 1})
        if dup:
            raise ValueError(f"One column is chosen for two roles: {', '.join(dup)}.")
        sign = self.sign.currentData()
        kinds = {v: kb.currentData() for v, kb in self.kind_boxes.items()}
        direction = "step_type" if sign == "unsigned" else "current_sign"
        if sign == "unsigned" and "step_type" not in bindings:
            raise ValueError("An unsigned current needs a step-type column to give the direction.")
        if sign == "unsigned" and any(k == "other" for k in kinds.values()):
            bad = [v for v, k in kinds.items() if k == "other"]
            raise ValueError(f"With an unsigned current every step type must state a direction or a rest: "
                             f"{', '.join(bad)} still say 'other'.")
        evidence = self.evidence.text().strip()
        if len(evidence) < 10:
            raise ValueError("Say how you know these conventions (at least a few words): it is saved with every result.")
        conv = Conventions(current_sign=sign, direction_source=direction,
                           capacity_semantics=self.semantics.currentData(), cycle_base=self.base.currentData(),
                           evidence=evidence, step_type_map=kinds if "step_type" in bindings else {})
        name = _slug(self.instrument.text() or self.rec.path.stem)
        return ImportProfile(name=name, instrument=self.instrument.text().strip() or "Unnamed instrument",
                             layout=prop.layout, bindings=bindings, conventions=conv)

    # ------------------------------------------------------------------ check and use
    def check(self):
        try:
            prof = self.profile()
        except ValueError as exc:
            self.report.setText(str(exc)); self.report.setProperty("role", "error"); self._restyle_report()
            return
        self.report.setText("Reading the file with this mapping…"); self.report.setProperty("role", "muted")
        self._restyle_report()
        self.check_btn.setEnabled(False)
        key = prof.model_dump_json()
        self._job = worker.start(worker.Job((self.rec, key), workflow.open_with_profile, self.rec.path, prof),
                                 done=self._checked_ok, failed=self._checked_failed)

    def _checked_ok(self, token, loaded):
        rec, key = token
        self.check_btn.setEnabled(True)
        if rec is not self.rec:
            return
        rep = loaded.meta["import_report"]
        cv = rep.get("counter_vs_integral") or {}
        lines = [f"Read {rep['rows']:,} rows.".replace(",", " ")]
        if rep.get("current_sign_declared") != "charge_positive":
            lines.append(f"Current converted to charge-positive from '{rep['current_sign_declared']}'.")
        if cv and cv.get("charge"):
            lines.append("Instrument counter vs. integrated current: "
                         + ", ".join(f"{side} {abs(v['relative_difference']) * 100:.2f} %"
                                     for side, v in cv.items() if isinstance(v, dict) and "relative_difference" in v
                                     and v["relative_difference"] is not None))
        elif rep.get("capacity_semantics") == "none":
            lines.append("No counter to compare with: capacity will be the integral of the sampled current.")
        warns = [f["message"] for f in loaded.meta["import_findings"] if f["severity"] == "warn"]
        for w in warns[:4]:
            lines.append("Warning: " + w)
        lines.append("The mapping passed. Open the file, or correct something and check again.")
        self.report.setText("\n".join(lines)); self.report.setProperty("role", "ok" if not warns else "provisional")
        self._restyle_report()
        self._checked = key; self._loaded = loaded
        self.use_btn.setEnabled(True)

    def _checked_failed(self, token, msg, tb):
        rec, key = token
        self.check_btn.setEnabled(True)
        if rec is not self.rec:
            return
        self.report.setText(msg); self.report.setProperty("role", "error"); self._restyle_report()
        self._checked = None; self._loaded = None
        self.use_btn.setEnabled(False)

    def _restyle_report(self):
        self.report.style().unpolish(self.report); self.report.style().polish(self.report)

    def use(self):
        if self._loaded is None:
            return
        try:
            prof = self.profile()
        except ValueError as exc:
            self.report.setText(str(exc)); return
        if prof.model_dump_json() != self._checked:
            self._invalidate()
            self.report.setText("The mapping changed since the check: check it again.")
            return
        save = prof.name if self.remember.isChecked() else ""
        self.confirmed.emit(self.rec, self._loaded, prof, save, prof.instrument)

    def restyle(self):
        self.grid.setFont(theme.font(8.5, tabular=True))
