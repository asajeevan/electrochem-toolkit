"""Inspector: what only you can tell, this record, the focused cycle, how the file was read.

Each question card shows what the file itself says (evidence, never a
decision), the control, and what the answer unlocks. Values are shown with
their state: a withheld value is replaced by the word and its reason, in slate,
never by a blank or a zero.

The inspector is rebuilt whenever its record changes. Two rules make that safe:
- text typed into a field and not yet committed survives a rebuild, with the
  cursor and the keyboard focus (independent review, finding r06: a result
  arriving while you typed a mass used to wipe it);
- the old widgets are silenced before they are taken away, so hiding a field
  you are typing in can never commit half a number, and they are deleted only
  once control is back in the event loop (finding r10: deleting them inside
  their own signal could crash).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ..cycling import capacity_basis, cycle_capacity
from ..workflow import EC_LAB_DEFAULT_MASS_MG
from . import theme
from .model import Record, degenerate_start, first_branch_direction, parse_number, questions, state_of
from .tables import implausible_capacity
from .views import capacity_unit, ref_text


def _label(text, role=None, wrap=True):
    lab = QLabel(text)
    if role:
        lab.setProperty("role", role)
    lab.setWordWrap(wrap)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


class Card(QFrame):
    def __init__(self, title, changes, answered, required=True):
        super().__init__()
        self.setObjectName("Panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(7)
        head = QHBoxLayout(); head.setSpacing(6)
        t = theme.tokens()
        state = "Answered" if answered else ("Needed" if required else "Optional")
        color = t.ok if answered else (t.selection_text if required else t.muted)
        dot = QLabel("●" if not answered else "✓")
        dot.setStyleSheet(f"color: {color}; font-weight: 700;")
        head.addWidget(dot)
        st = QLabel(state)
        st.setStyleSheet(theme.css(f"color: {color}; font-size: 8.5pt; font-weight: 600;"))
        head.addWidget(st)
        head.addStretch(1)
        lay.addLayout(head)
        lay.addWidget(_label(title, "h2"))
        self.body = QVBoxLayout(); self.body.setSpacing(6)
        lay.addLayout(self.body)
        lay.addWidget(_label(changes, "muted"))
        self.setAccessibleName(f"{title} ({state})")


class Notice(QFrame):
    """A short message at the top of the inspector: restored answers, an implausible value, a stale result."""
    def __init__(self, text, role, actions=()):
        super().__init__()
        self.setObjectName("Panel")
        t = theme.tokens()
        col = {"error": t.error, "provisional": t.provisional, "info": t.secondary}[role]
        self.setStyleSheet(f"QFrame#Panel {{ border: 1px solid {col}; }}")
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 9, 12, 9); lay.setSpacing(6)
        lay.addWidget(_label(text, role if role != "info" else "secondary"))
        if actions:
            row = QHBoxLayout(); row.setSpacing(6)
            for name, label, fn in actions:
                b = QPushButton(label); b.setObjectName(name); b.clicked.connect(fn)
                row.addWidget(b)
            row.addStretch(1)
            lay.addLayout(row)
        self.setAccessibleName(text)


class ChoiceButton(QPushButton):
    """A checkable answer with a title and a wrapping explanation (a plain button cannot wrap)."""

    def __init__(self, title, sub):
        super().__init__()
        self.setProperty("kind", "choice")
        self.setCheckable(True)
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 6, 10, 6); lay.setSpacing(1)
        self.t = QLabel(title); self.t.setWordWrap(True)
        self.t.setStyleSheet("font-weight: 600; background: transparent;")
        lay.addWidget(self.t)
        if sub:
            self.s = QLabel(sub); self.s.setWordWrap(True); self.s.setProperty("role", "muted")
            lay.addWidget(self.s)
        for lab in self.findChildren(QLabel):
            lab.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAccessibleName(f"{title}. {sub}" if sub else title)
        self.setMinimumWidth(0)

    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        h = self.layout().minimumSize()
        return h.expandedTo(h)


class Inspector(QScrollArea):
    answersChanged = Signal(dict)        # partial answers to apply
    clearRestored = Signal()             # "Clear them" on the restored-answers notice
    focusQuestion = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.NoFocus)          # the scroll area itself is not a Tab stop (review finding r24)
        self.setMinimumWidth(300)
        self.rec: Record | None = None
        self.first_open = None
        self._before = self._after = None        # Tab neighbours: the file list and the view switcher
        self._pending = {}                       # drafts and focus carried over a rebuild
        self.inner = None
        self._fresh()
        self._attach()

    def set_tab_neighbours(self, before, after):
        self._before, self._after = before, after

    def _fresh(self):
        """A new container for every rebuild: no stale widget can be painted under the new ones."""
        self.inner = QWidget()
        self.inner.setObjectName("Frame")
        self.lay = QVBoxLayout(self.inner)
        self.lay.setContentsMargins(4, 4, 10, 12)
        self.lay.setSpacing(10)

    def _attach(self):
        """Attach the filled container. Filling first matters: children added to a container that is
        already on screen stay hidden until shown one by one."""
        self.inner.setMaximumWidth(max(self.viewport().width(), 260))
        old = self.widget()
        if old is not None:
            for w in [old] + old.findChildren(QWidget):
                w.blockSignals(True)             # silenced before it is taken away: a field losing the focus
            self.takeWidget()                    # would otherwise commit the half-typed number it holds
        self.setWidget(self.inner)
        if old is not None:
            old.hide()
            old.deleteLater()
        self._restore_pending()
        self._chain_tab_order()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.inner is not None:
            self.inner.setMaximumWidth(self.viewport().width())

    # ---------------------------------------------------------------- drafts and focus over a rebuild
    def _capture(self, rec):
        """Uncommitted text, cursor and focus of every field, kept only if the same record is rebuilt."""
        from PySide6.QtWidgets import QApplication
        drafts, focus = {}, None
        if self.inner is not None and rec is not None and rec is self.rec:
            fw = QApplication.focusWidget()
            if fw is not None and self.inner.isAncestorOf(fw):
                focus = fw.objectName() or None
            for ed in self.inner.findChildren(QLineEdit):
                name = ed.objectName()
                if name and ed.text() != (ed.property("committed") or ""):
                    drafts[name] = (ed.text(), ed.cursorPosition())
        self._pending = {"drafts": drafts, "focus": focus}

    def _restore_pending(self):
        pend, self._pending = self._pending, {}
        for name, (text, cursor) in pend.get("drafts", {}).items():
            ed = self.inner.findChild(QLineEdit, name)
            if ed is not None and ed.text() != text:
                ed.setText(text)
                ed.setCursorPosition(cursor)
                check = ed.property("validate")
                if callable(check):
                    check(ed, commit=False)
        name = pend.get("focus")
        if name:
            QTimer.singleShot(0, lambda: self._refocus(name))

    def _refocus(self, name):
        w = self.inner.findChild(QWidget, name)
        if w is not None:
            w.setFocus(Qt.OtherFocusReason)

    def _chain_tab_order(self):
        """Tab goes files, then the questions in reading order, then the views (review finding r24)."""
        ws = [w for w in self.inner.findChildren(QWidget)
              if (w.focusPolicy() & Qt.TabFocus) and not w.isHidden() and w.isEnabled()]
        if not ws:
            return
        chain = ([self._before] if self._before is not None else []) + ws + \
                ([self._after] if self._after is not None else [])
        for a, b in zip(chain, chain[1:]):
            QWidget.setTabOrder(a, b)

    # ---------------------------------------------------------------- build
    def show_record(self, rec: Record | None, focus_cycle=None):
        self._capture(rec)
        try:
            self._build(rec, focus_cycle)
        finally:
            self._attach()

    def _build(self, rec, focus_cycle):
        bar = self.verticalScrollBar().value()
        same = rec is self.rec
        self.rec = rec
        self._fresh()
        if same:
            QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(bar))
        self.first_open = None
        if rec is None:
            self.lay.addWidget(_label("Open a file to see what it holds.", "secondary"))
            self.lay.addStretch(1)
            return
        if rec.error:
            self.lay.addWidget(_label("This file could not be read", "h2"))
            self.lay.addWidget(_label(rec.error, "error"))
            self.lay.addStretch(1)
            return
        if rec.loaded is None:
            self.lay.addWidget(_label("Reading the file…", "secondary"))
            self.lay.addStretch(1)
            return
        self._notices(rec)
        self.lay.addWidget(_label("What only you can tell", "section"))
        for q in questions(rec.answers, rec.loaded, rec.run):
            card = Card(q.title, q.changes, q.answered, q.required)
            getattr(self, f"_q_{q.key}")(card, rec)
            self.lay.addWidget(card)
            if q.required and not q.answered and self.first_open is None:
                self.first_open = card
        self._summary(rec)
        self._cycle(rec, focus_cycle)
        self._plateaus(rec, focus_cycle)
        self._how_read(rec)
        self.lay.addStretch(1)

    def _notices(self, rec):
        if rec.run is not None and not rec.current:
            self.lay.addWidget(Notice("Updating for your last answer. Until it is done, the values here and in "
                                      "the plots are those of your previous answers.", "provisional"))
        bad = implausible_capacity(rec) if rec.current else None
        if bad:
            self.lay.addWidget(Notice(bad, "error"))
        if getattr(rec, "restored", False):
            self.lay.addWidget(Notice(
                "These answers were restored from your last session with this exact file.", "info",
                [("restored_keep", "Keep them", self._keep_restored),
                 ("restored_clear", "Clear them", self.clearRestored.emit)]))

    def _keep_restored(self):
        if self.rec is not None:
            self.rec.restored = False
            self.show_record(self.rec, self.rec.focus_cycle)

    def focus_first_question(self):
        if self.first_open is not None:
            self.ensureWidgetVisible(self.first_open)
            for w in self.first_open.findChildren((QPushButton, QLineEdit)):
                w.setFocus(Qt.TabFocusReason)
                break

    # ---------------------------------------------------------------- questions
    def _choices(self, card, key, options, current):
        group = QButtonGroup(card)
        group.setExclusive(True)
        for value, text, sub in options:
            b = ChoiceButton(text, sub)
            b.setObjectName(f"q_{key}_{value}")
            b.setChecked(current == value)
            b.clicked.connect(lambda _=False, v=value: self.answersChanged.emit({key: v}))
            group.addButton(b)
            card.body.addWidget(b)
        return group

    def _q_charge(self, card, rec):
        tab = rec.loaded.tab
        ev = None
        meta = rec.loaded.meta
        if meta.get("profile"):
            rep_ = meta.get("import_report", {})
            src = ("its step types name charge, discharge and rest" if rep_.get("current_sign_declared") in ("unsigned", "detect")
                   else "its step types name charge, discharge and rest, and the sign of its current agrees on every step"
                   if rep_.get("direction_from_step_types")
                   else f"the {meta['profile']} profile declares which sign is charge")
            card.body.addWidget(_label(f"Answered from the import: the current was made charge-positive when the file "
                                       f"was read, because {src}. Evidence: {meta.get('profile_evidence', '')}", "muted"))
        elif tab.i is not None:
            import numpy as np
            nz = np.flatnonzero(np.abs(np.nan_to_num(tab.i)) > 0)
            if nz.size:
                first = "positive" if tab.i[nz[0]] > 0 else "negative"
                ev = f"The first non-zero current in the file is {first}."
        if ev:
            card.body.addWidget(_label(ev + " That is evidence, not an answer: a protocol may start with discharge.", "muted"))
        self._choices(card, "charge", [("ox", "Positive current charges", "oxidation at the working electrode (EC-Lab ox)"),
                                       ("red", "Negative current charges", "reduction at the working electrode")],
                      rec.answers.charge)

    def _q_order(self, card, rec):
        first = first_branch_direction(rec.answers, rec.run)
        if first:
            lead = degenerate_start(rec.run)
            card.body.addWidget(_label(f"With the direction you gave, the file starts with a {first}"
                                       + (f"; {lead}." if lead else "."), "muted"))
        self._choices(card, "cycle_order", [
            ("charge-first", "Charge, then discharge",
             "each charge is paired with the discharge after it; a discharge before the first charge stays unpaired"),
            ("discharge-first", "Discharge, then charge",
             "each discharge is paired with the charge after it, as for a cell assembled in the charged state")],
            rec.answers.cycle_order)
        card.body.addWidget(_label("Either way, coulombic efficiency is the discharge capacity divided by the charge "
                                   "capacity of the same cycle. For a negative-electrode half-cell whose charge is "
                                   "delithiation, the delithiation/lithiation ratio is its reciprocal.", "muted"))

    def _q_configuration(self, card, rec):
        from ..table import CELL_NAMES, WORKING_NAMES
        tab = rec.loaded.tab
        names = list(tab.potentials) or [tab.labels.get("potential", "?")]
        working = next((n for n in WORKING_NAMES if n in names), None)
        cell = next((n for n in CELL_NAMES if n in names), None)
        if working and cell:
            ev = (f"This file has {working} (working electrode against the reference) and {cell} (cell voltage). "
                  f"A half-cell answer uses {working}; a full-cell answer uses {cell}.")
        else:
            ev = (f"The file's potential column is {names[0]}. Its name does not settle this: a two-electrode "
                  "half-cell against a metal counter electrode is recorded the same way as a full cell"
                  + (", and an .mpr names the column Ewe/V whatever the set-up." if tab.format == "mpr" else "."))
        card.body.addWidget(_label(ev, "muted"))
        self._choices(card, "configuration",
                      [("half", "Half-cell", "potential vs. a reference or a metal counter electrode"),
                       ("full", "Full cell", "two-electrode terminal voltage")], rec.answers.configuration)
        if rec.answers.configuration == "half":
            row = QHBoxLayout()
            lab = QLabel("Reference")
            ed = QLineEdit(rec.answers.reference)
            ed.setObjectName("q_reference")
            ed.setProperty("committed", rec.answers.reference)
            ed.setPlaceholderText("for example Li+/Li or Na+/Na")
            ed.setAccessibleName("Reference electrode")
            lab.setBuddy(ed)
            ed.editingFinished.connect(lambda ed=ed: self.answersChanged.emit({"reference": ed.text().strip()})
                                       if ed.text().strip() != (self.rec.answers.reference if self.rec else "") else None)
            row.addWidget(lab); row.addWidget(ed, 1)
            card.body.addLayout(row)
            if rec.answers.reference.strip():
                card.body.addWidget(_label(f"Axis reads: potential vs. {ref_text(rec.answers.reference)}", "muted"))

    def _number_row(self, card, label, key, value, unit, name, integer=False, check=None, also=None):
        row = QHBoxLayout()
        lab = QLabel(label)
        shown = "" if value is None else (f"{int(value)}" if integer else f"{value:g}")
        ed = QLineEdit(shown)
        ed.setObjectName(name)
        ed.setProperty("committed", shown)
        ed.setAccessibleName(label)
        ed.setPlaceholderText("not given")
        ed.setMaximumWidth(120)
        lab.setBuddy(ed)
        err = _label("", "error")
        err.hide()

        def validate(ed=ed, err=err, commit=True):
            try:
                v = parse_number(ed.text())
                if v is not None and v <= 0:
                    raise ValueError("must be greater than zero")
                if v is not None and integer:
                    if v != int(v):
                        raise ValueError("a whole number is needed")
                    v = int(v)
                if v is not None and check is not None:
                    problem = check(v)
                    if problem:
                        raise ValueError(problem)
            except ValueError as exc:
                ed.setProperty("invalid", True); ed.style().unpolish(ed); ed.style().polish(ed)
                err.setText(f"Not used: {exc}."); err.show()
                return
            ed.setProperty("invalid", False); ed.style().unpolish(ed); ed.style().polish(ed)
            err.hide()
            if not commit:
                return
            if integer and v is None:
                v = 1                                  # an empty reference cycle means the first cycle
            cur = getattr(self.rec.answers, key) if self.rec else None
            extra = {k: x for k, x in (also or {}).items() if v is not None and self.rec
                     and getattr(self.rec.answers, k) != x}
            if v != cur or extra:
                ed.setProperty("committed", ed.text())
                self.answersChanged.emit({key: v, **extra})
        ed.setProperty("validate", validate)
        ed.editingFinished.connect(validate)
        row.addWidget(lab, 1); row.addWidget(ed); row.addWidget(QLabel(unit))
        card.body.addLayout(row)
        card.body.addWidget(err)
        return ed

    def _q_mass(self, card, rec):
        declared = rec.loaded.declared_mass_mg
        if declared is not None:
            src = rec.loaded.header_source or rec.path.name
            if declared <= EC_LAB_DEFAULT_MASS_MG:
                card.body.addWidget(_label(f"The header of {src} gives {declared:g} mg, EC-Lab's default when the mass "
                                           "field is left empty, so it is not offered as an answer.", "muted"))
            else:
                card.body.addWidget(_label(f"The header of {src} declares {declared:g} mg. It is used only if you "
                                           "confirm it.", "muted"))
                if rec.answers.mass_mg is None or abs(rec.answers.mass_mg - declared) > 1e-9:
                    b = QPushButton(f"Use {declared:g} mg from the header")
                    b.setObjectName("q_mass_header")
                    b.clicked.connect(lambda: self.answersChanged.emit({"mass_mg": declared}))
                    card.body.addWidget(b)
        self._number_row(card, "Active-material mass", "mass_mg", None if rec.answers.no_mass else rec.answers.mass_mg,
                         "mg", "q_mass", also={"no_mass": False})
        card.body.addWidget(_label("Active material only, not the composite or the whole electrode. "
                                   "A decimal point or comma; no thousands separator.", "muted"))
        b = ChoiceButton("No mass", "capacities in mAh, or per cm² if you give the electrode area")
        b.setObjectName("q_no_mass")
        b.setChecked(rec.answers.no_mass)
        b.clicked.connect(lambda: self.answersChanged.emit({"no_mass": True, "mass_mg": None})
                          if not (self.rec and self.rec.answers.no_mass) else b.setChecked(True))
        card.body.addWidget(b)

    def _q_optional(self, card, rec):
        a = rec.answers
        self._number_row(card, "Electrode area", "area_cm2", a.area_cm2, "cm²", "q_area")
        self._number_row(card, "Molar mass", "molar_mass_g_mol", a.molar_mass_g_mol, "g mol⁻¹", "q_molar")
        self._number_row(card, "Electrons per formula unit", "electrons", a.electrons, "", "q_electrons")
        complete = rec.complete_cycles()

        def is_complete(v):
            if rec.run is None or not complete or v in complete:
                return None
            span = f"{complete[0]} to {complete[-1]}" if len(complete) > 1 else f"{complete[0]}"
            return f"cycle {v} is not a complete cycle of this file (complete cycles: {span})"
        self._number_row(card, "Retention reference cycle", "reference_cycle", a.reference_cycle, "", "q_refcycle",
                         integer=True, check=is_complete)

    # ---------------------------------------------------------------- values
    def _value_grid(self, title, items, rec, note=None):
        box = QFrame(); box.setObjectName("Panel")
        lay = QVBoxLayout(box); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        lay.addWidget(_label(title, "h2"))
        stale = not rec.current
        g = QGridLayout(); g.setHorizontalSpacing(10); g.setVerticalSpacing(5)
        for r, (name, field_name, value, unit, digits) in enumerate(items):
            g.addWidget(_label(name, "secondary"), r, 0)
            state, reason = state_of(field_name, value, rec.answers, rec.run)
            if state == "available":
                txt = f"{value:.{digits}f} {unit}".strip() if isinstance(value, float) else f"{value} {unit}".strip()
                v = _label(txt, "provisional" if stale else "value", wrap=False)
                v.setFont(theme.font(9.5, 500, tabular=True))
                v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                v.setToolTip("From your previous answers: updating" if stale else field_name)
            else:
                v = _label(f"⊘ withheld: {reason}", "withheld")
                v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                v.setToolTip(field_name)
            g.addWidget(v, r, 1)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        if note:                                  # the cycle's own note: why a value of this cycle is withheld
            lay.addWidget(_label(note[0].upper() + note[1:] + ".", "muted"))
        self.lay.addWidget(box)

    def _summary(self, rec):
        if not rec.run:
            return
        sm, s = rec.run.an.summary, rec.run.settings
        u = capacity_unit(s)
        dig = 4 if capacity_basis(s) == "absolute" else 2
        ok = [c for c in rec.run.an.cycles if c.complete]
        first = ok[0] if ok else None
        n1 = f", cycle {first.cycle}" if first else ""            # the cycle each value comes from (review finding 4)
        items = [
            ("Complete cycles", "complete_cycles", sm.complete_cycles, "", 0),
            (f"Discharge{n1}", "first_cycle_discharge_mAh", cycle_capacity(first, "discharge", s) if first else None,
             u, dig),
            (f"Coulombic efficiency{n1}", "first_cycle_coulombic_efficiency_pct",
             sm.first_cycle_coulombic_efficiency_pct, "%", 2),
            (f"Mean coulombic efficiency after cycle {first.cycle}" if first else "Mean coulombic efficiency",
             "mean_coulombic_efficiency_pct", sm.mean_coulombic_efficiency_pct, "%", 2),
            (f"Retention at cycle {sm.last_cycle}" if sm.last_cycle else "Retention", "retention_at_last_cycle_pct",
             sm.retention_at_last_cycle_pct, "%", 1),
            ("Fade", "capacity_fade_pct_per_cycle", sm.capacity_fade_pct_per_cycle, "% per cycle", 3),
            ("80 % retention reached", "cycle_reaching_80pct_retention",
             sm.cycle_reaching_80pct_retention, "(cycle)", 0),
            ("Mean average discharge", "mean_average_discharge_voltage_V", sm.mean_average_discharge_voltage_V, "V", 3),
            ("Mean hysteresis", "mean_voltage_hysteresis_V", sm.mean_voltage_hysteresis_V, "V", 3),
            ("Theoretical capacity", "theoretical_capacity_mAh_g", sm.theoretical_capacity_mAh_g, "mAh g⁻¹", 1),
            (f"Utilisation{n1}", "first_cycle_utilisation_pct", sm.first_cycle_utilisation_pct, "%", 1),
            ("Test time", "total_test_time_h", sm.total_test_time_h, "h", 2 if sm.total_test_time_h < 10 else 1),
        ]
        if sm.cycle_reaching_80pct_retention is None and sm.retention_at_last_cycle_pct is not None \
                and sm.retention_at_last_cycle_pct > 80:
            items[6] = ("80 % retention reached", "x", "not within the test", "", 0)
        self._value_grid("This record", items, rec)

    def _cycle(self, rec, c):
        if not rec.run or c is None:
            return
        row = next((x for x in rec.run.an.cycles if x.cycle == c), None)
        if row is None:
            return
        s = rec.run.settings
        u = capacity_unit(s)
        dig = 4 if capacity_basis(s) == "absolute" else 2
        items = [
            ("Charge", "charge_capacity_mAh", cycle_capacity(row, "charge", s), u, dig),
            ("Discharge", "discharge_capacity_mAh", cycle_capacity(row, "discharge", s), u, dig),
            ("Coulombic efficiency", "coulombic_efficiency_pct", row.coulombic_efficiency_pct, "%", 2),
            ("Retention", "capacity_retention_pct", row.capacity_retention_pct, "%", 1),
            ("Average charge", "average_charge_voltage_V", row.average_charge_voltage_V, "V", 4),
            ("Average discharge", "average_discharge_voltage_V", row.average_discharge_voltage_V, "V", 4),
            ("Hysteresis", "average_voltage_hysteresis_V", row.average_voltage_hysteresis_V, "V", 4),
            ("Energy efficiency", "energy_efficiency_pct", row.energy_efficiency_pct, "%", 2),
            ("CV share of charge", "charge_cv_fraction_pct", row.charge_cv_fraction_pct, "%", 1),
            ("C-rate, discharge", "discharge_c_rate", row.discharge_c_rate, "C", 3),
        ]
        title = f"Cycle {c}" + ("" if row.complete else " (incomplete)")
        if c not in rec.selected_cycles():
            title += ", previewed: not in the selection"
        self._value_grid(title, items, rec, note=row.note or None)

    def _plateaus(self, rec, c):
        """The dQ/dE peaks of the focused cycle as the tables report them: pairs with their separation, peaks
        without a counterpart, peaks of the first cycle only. Factual wording; no peak is called reversible or
        irreversible here (M01 section 9)."""
        if not rec.run or c is None or not rec.current:
            return
        try:
            rep = rec.run.plateaus()
        except Exception:                                  # a dQ/dE failure must not take the inspector down
            return
        if c not in rep.cycles:
            return
        peaks = [p for p in rep.peaks if p.cycle == c]
        pairs = [p for p in rep.pairs if p.cycle == c]
        if not peaks:
            return
        box = QFrame(); box.setObjectName("Panel")
        lay = QVBoxLayout(box); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(6)
        lay.addWidget(_label(f"Plateaus, cycle {c} (dQ/dE peaks)", "h2"))
        unit = peaks[0].charge_unit
        for q in pairs:
            lay.addWidget(_label(f"Pair {q.pair}: charge {q.charge_voltage_V:.3f} V, discharge {q.discharge_voltage_V:.3f} V, "
                                 f"{q.separation_mV:.0f} mV apart; {q.charge_capacity:.3g} and {q.discharge_capacity:.3g} "
                                 f"{unit} under the peaks", "value"))
        for p in peaks:
            if p.pairing != "paired":
                gap = (f" (no {p.direction} dQ/dE curve in cycle{'s' if any(x in p.no_curve_cycles for x in ',-') else ''} "
                       f"{p.no_curve_cycles})" if p.no_curve_cycles else "")
                lay.addWidget(_label(f"Unpaired {p.direction} peak at {p.voltage_V:.3f} V, {p.charge:.3g} {unit} under it: "
                                     f"{p.pairing_note}; "
                                     + ("present in the first cycle only" if p.evolution == "first cycle only" else p.evolution)
                                     + gap + ".", "provisional" if p.evolution == "first cycle only" else "value"))
        later = [p for p in peaks if p.evolution.startswith("appears from")]
        if later:
            lay.addWidget(_label("Appearing later: " + "; ".join(f"{p.direction} {p.voltage_V:.3f} V, {p.evolution}" for p in later), "value"))
        capped = [p for p in peaks if p.capped]
        if capped:
            lay.addWidget(_label(capped[0].peaks_note, "muted"))
        lay.addWidget(_label(f"Peak potentials describe the measured curve at this rate; pairing is by proximity within "
                             f"{rep.window_mV:g} mV. Full table: dqde_peaks.csv in the export; Help > How the numbers "
                             "are calculated explains it.", "muted"))
        self.lay.addWidget(box)

    def _how_read(self, rec):
        tab = rec.run.tab if rec.run else rec.loaded.tab
        box = QFrame(); box.setObjectName("Panel")
        lay = QVBoxLayout(box); lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(4)
        lay.addWidget(_label("How the file was read", "h2"))
        meta = rec.loaded.meta
        kind = (f"{meta['instrument']} file read with the {meta['profile']} profile" if meta.get("profile")
                else f"{tab.format.upper()} file")
        lines = [f"{kind}, {tab.n:,} rows".replace(",", " "),
                 "Columns used: " + ", ".join(f"{k} = {v}" for k, v in tab.labels.items()),
                 f"Header read from {rec.loaded.header_source}" if rec.loaded.header_source else "No header found",
                 f"SHA-256 {tab.source_sha256[:16]}…"]
        if meta.get("profile"):
            rep_ = meta.get("import_report", {})
            lines.append(f"Current sign in the file: {rep_.get('current_sign_declared', '?')}; analysed charge-positive")
            if rep_.get("capacity_semantics", "none") != "none":
                lines.append(f"Instrument counter: {rep_['capacity_semantics'].replace('_', ' ')}"
                             + (", as measured in this file" if rep_.get("capacity_semantics_verified") else ""))
            lines.append(f"Profile evidence: {meta.get('profile_evidence', '')}")
        if tab.invalid_rows:
            lines.append(f"Unreadable values: {tab.invalid_rows}")
        if rec.run:
            seg = rec.run.seg
            nb, npairs, ne = len(seg.branches), len(seg.pairs), len(seg.edges.reason)
            lines.append(f"{nb} branch{'es' if nb != 1 else ''}, {npairs} cycle{'s' if npairs != 1 else ''}, "
                         f"{ne} edge{'s' if ne != 1 else ''} not integrated")
            for n in seg.convention.get("notes", [])[:4]:
                lines.append(n)
            lines.append("Charge from the instrument's dq increments" if rec.run.settings.use_instrument_dq and tab.dq is not None
                         else "Charge by integrating the sampled current")
        for w in rec.run.warnings if rec.run else []:
            lines.append(w)
        for line in lines:
            lay.addWidget(_label(line, "muted"))
        self.lay.addWidget(box)
