"""Interactive views (pyqtgraph).

Every curve is computed with the same functions the publication figures use
(cumulative_charge, capacity_basis, differential.curve), from the analysed
Table, never from a display copy. One selection (cycles and a focused cycle)
drives every view; the focused cycle is drawn on top and thicker, and named in
the readout under each plot, never over the data.

Values that need an answer the researcher has not given are not drawn; the
view's note line says which and why (U01 principle P10).
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
                               QCheckBox)

from ..cycling import CAPACITY_UNITS, capacity_basis as basis_of, cumulative_charge, cycle_capacity
from ..plotting import capacity_basis
from . import theme
from .model import Record, reason_for
from .motion import Motion, animate

pg.setConfigOptions(antialias=True, useOpenGL=False)

SUP_M1 = "⁻¹"
SUP_M2 = "⁻²"


# ------------------------------------------------------------------ labels (plain text for the screen)
def ref_text(ref: str) -> str:
    import re
    m = re.fullmatch(r"([A-Z][a-z]?)(\d?\+)?/([A-Z][a-z]?)(\d?\+)?", ref.strip().replace(" ", ""))
    if m and m.group(1) == m.group(3):
        charge = (m.group(2) or m.group(4) or "+").replace("+", "⁺")
        return f"{m.group(1)}{charge}/{m.group(1)}"
    return ref


def potential_text(tab, s) -> str:
    if s.terminal_voltage:
        return "Cell voltage (V)"
    if s.reference:
        return f"Potential vs. {ref_text(s.reference)} (V)"
    return f"Potential, {tab.labels.get('potential', 'E').split('/')[0]} (V)"


def capacity_text(s) -> str:
    """Axis title from the one basis decision (cycling.capacity_basis), as are all capacity values."""
    return {"specific": f"Specific capacity (mAh g{SUP_M1})", "areal": f"Areal capacity (mAh cm{SUP_M2})",
            "absolute": "Capacity (mAh)"}[basis_of(s)]


def capacity_unit(s) -> str:
    return CAPACITY_UNITS[basis_of(s)]


def what_potential(s) -> tuple[str, str]:
    """('cell voltage', 'V') or ('potential vs. Li⁺/Li', 'E') or ('potential', 'E')."""
    if s.terminal_voltage:
        return "cell voltage", "V"
    if s.reference:
        return f"potential vs. {ref_text(s.reference)}", "E"
    return "potential", "E"


# Axis titles as variants, fullest first: the plot shows the longest one that fits along its axis
# (theme.fit_titles), so a title is shortened, never cut off. The quantity symbol keeps the unit.
CYCLE_TITLES = ("Cycle number", "Cycle")
CE_TITLES = ("Coulombic efficiency (%)", "CE (%)")


def capacity_titles(s) -> tuple:
    unit = CAPACITY_UNITS[basis_of(s)]
    first = capacity_text(s)
    return tuple(dict.fromkeys((first, f"Capacity ({unit})", f"Q ({unit})")))


def potential_titles(tab, s) -> tuple:
    """Still names the reference for as long as there is room for it."""
    if s.terminal_voltage:
        return ("Cell voltage (V)", "Voltage (V)", "V (V)")
    if s.reference:
        r = ref_text(s.reference)
        return (f"Potential vs. {r} (V)", f"E vs. {r} (V)", "E (V)")
    return (potential_text(tab, s), "E (V)")


def average_titles(s) -> tuple:
    what, sym = what_potential(s)
    out = [f"Average {what} (V)"]
    if s.reference and not s.terminal_voltage:
        out.append(f"Mean {sym} vs. {ref_text(s.reference)} (V)")
    out.append(f"Mean {sym} (V)")
    return tuple(out)



NO_CYCLES = ("Cycles appear once you say which current direction charges the cell. "
             "Until then the Timeline and Data views show every recorded row.")
NO_DQDE = ("None of the shown cycles has a dQ/d{sym} curve: every branch is interrupted or paused partway, or has "
           "fewer than four points outside constant-voltage stages, or spans less than two potential bins. The cycle "
           "notes name the interrupted and paused branches.")


def no_curve_why(run, cycle, direction) -> str:
    """Why that branch has no dQ/dE curve, in a few words: the conditions of differential.curve."""
    pair = next((p for p in run.seg.pairs if p.index == cycle), None)
    br = (pair.charge if direction == "charge" else pair.discharge) if pair is not None else None
    if br is not None and getattr(br, "curve_breaks", 0):
        return "interrupted"
    if br is not None and getattr(br, "pauses", 0):
        return "paused partway"
    return "too few points or too narrow a range outside constant-voltage stages"


def withheld_note(run, withheld, sym="E", shown=6) -> str:
    """The branches of the shown cycles that have no dQ/dE curve (Run.dqde_and_withheld) and why, for a note."""
    if not withheld:
        return ""
    keys = sorted(withheld, key=lambda x: (x[0], x[1] != "charge"))
    items = [f"cycle {c} {d} ({no_curve_why(run, c, d)})" for c, d in keys[:shown]]
    more = f" and {len(keys) - shown} more" if len(keys) > shown else ""
    return f"No dQ/d{sym} curve for {', '.join(items)}{more}."


def fmt(v, d=4):
    return "n/a" if v is None or not np.isfinite(v) else f"{v:.{d}g}"


# ------------------------------------------------------------------ base

class View(QWidget):
    """A view with a note line above and a readout line below its plots."""
    focusRequested = Signal(int)
    title = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rec: Record | None = None
        self.selected: list[int] = []
        self.focus: int | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setProperty("role", "withheld")
        self.note.hide()
        lay.addWidget(self.note)
        self.body = QWidget()
        lay.addWidget(self.body, 1)
        self.empty = QLabel("")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setProperty("role", "secondary")
        self.empty.setMinimumHeight(120)
        self.empty.hide()
        lay.addWidget(self.empty, 1)
        self.readout = QLabel(" ")
        self.readout.setProperty("role", "muted")
        self.readout.setFont(theme.font(8.5, tabular=True))
        lay.addWidget(self.readout)
        self.plots: list[pg.PlotWidget] = []
        self._points: list = []            # (plot, x, y, label) for the readout
        self._drawn: list = []             # (item, x, y) for the first-reveal animation

    def new_plot(self, xlabel=None, ylabel=None, cycles_x=False) -> pg.PlotWidget:
        w = pg.PlotWidget(axisItems=theme.plain_axes(integer_bottom=cycles_x))
        w.setFocusPolicy(Qt.ClickFocus)       # not a Tab stop: Tab goes from the questions to the cycle list
        w.setMinimumHeight(120)
        theme.style_plot(w, xlabel=xlabel, ylabel=ylabel)
        w.scene().sigMouseMoved.connect(lambda pos, w=w: self._hover(w, pos))
        w.setAccessibleName(self.title or "plot")
        self.plots.append(w)
        return w

    def set_empty(self, text: str | None):
        """Replace the plots by a sentence saying what is missing, instead of empty axes."""
        self.empty.setText(text or "")
        self.empty.setVisible(bool(text))
        self.body.setVisible(not text)

    def set_note(self, lines):
        lines = [x for x in lines if x]
        self.note.setText("  ".join(lines))
        self.note.setVisible(bool(lines))

    def show_record(self, rec, selected, focus):
        self.rec, self.selected, self.focus = rec, list(selected), focus
        self.redraw()

    def set_selection(self, selected, focus):
        self.selected, self.focus = list(selected), focus
        self.redraw()

    def colors(self) -> dict:
        """Selected cycles take the ramp; a focused cycle outside the selection (browsing with the keyboard
        or the table) is drawn as a preview in the selection colour, dashed, and is not exported."""
        sel = sorted(self.selected)
        cols = {c: col for c, col in zip(sel, theme.ramp(len(sel)))}
        if self.focus is not None and self.focus not in cols:
            cols[self.focus] = QColor(theme.tokens().selection)
        return cols

    def drawn(self) -> list:
        """Cycles to draw, the focused one last so it sits on top."""
        cyc = list(dict.fromkeys(list(self.selected) + ([self.focus] if self.focus is not None else [])))
        return sorted(cyc, key=lambda c: (c == self.focus, c))

    def preview(self, c) -> bool:
        return c == self.focus and c not in self.selected

    def keep(self, item, x, y):
        self._drawn.append((item, np.asarray(x), np.asarray(y)))
        return item

    def reveal(self):
        """Trace the curves in once, the first time a file's results are shown. Never on later redraws."""
        items = [d for d in self._drawn if d[1].size > 1]
        if not items or not Motion.moving():
            return
        boxes = [w.getPlotItem().getViewBox() for w in self.plots]
        for vb in boxes:
            vb.disableAutoRange()              # hold the final range so nothing jumps while the data grow

        def step(v):
            for it, x, y in items:
                n = max(2, int(len(x) * v))
                it.setData(x[:n], y[:n])

        def done():
            for it, x, y in items:
                it.setData(x, y)
        animate(self, Motion.ms(700), step, done)

    def redraw(self):
        pass

    def restyle(self):
        for w in self.plots:
            theme.style_plot(w)
        self.redraw()

    def fit(self):
        for w in self.plots:
            w.getPlotItem().enableAutoRange()

    # nearest measured point under the cursor, in screen distance
    def _hover(self, w, pos):
        pi = w.getPlotItem()
        vb = pi.getViewBox()
        if not vb.sceneBoundingRect().contains(pos):
            return
        p = vb.mapSceneToView(pos)
        px, py = vb.viewPixelSize()
        best, best_d = None, 18.0 ** 2
        for plot, x, y, label in self._points:
            if plot is not w or x.size == 0:
                continue
            d = ((x - p.x()) / px) ** 2 + ((y - p.y()) / py) ** 2
            k = int(np.nanargmin(d)) if np.isfinite(d).any() else None
            if k is not None and d[k] < best_d:
                best_d, best = d[k], (label, x[k], y[k], k)
        if best:
            label, xv, yv, k = best
            self.readout.setText(label(k) if callable(label) else f"{label}: {fmt(xv)}, {fmt(yv)}")
        else:
            self.readout.setText(" ")


def _legend(plot, t):
    """The plot's legend (created once; pyqtgraph keeps one per plot), in the current theme's colours."""
    lg = plot.getPlotItem().addLegend(offset=(-10, 10))
    lg.setLabelTextColor(t.secondary)
    lg.setLabelTextSize(f"{8.5 * theme.scale():.1f}pt")
    return lg


def _pen(color, width=1.4, style=Qt.SolidLine):
    return pg.mkPen(color, width=width, style=style, cosmetic=True, capStyle=Qt.RoundCap, joinStyle=Qt.RoundJoin)


# ------------------------------------------------------------------ potential vs capacity

class ProfilesView(View):
    title = "Voltage profiles"

    def __init__(self, parent=None, compact=False):
        super().__init__(parent)
        self.compact = compact
        lay = QVBoxLayout(self.body); lay.setContentsMargins(0, 0, 0, 0)
        self.plot = self.new_plot()
        lay.addWidget(self.plot)

    def redraw(self):
        pi = self.plot.getPlotItem()
        pi.clear()
        self._points = []
        self._drawn = []
        rec = self.rec
        if not rec or not rec.run:
            self.set_note([])
            return
        run, s, tab = rec.run, rec.run.settings, rec.run.tab
        self.set_empty(None if run.seg.pairs else NO_CYCLES)
        theme.style_plot(self.plot, xlabel=capacity_titles(s), ylabel=potential_titles(tab, s))
        notes = []
        if s.charge is None:
            notes.append("Branches are paired by current sign only until the charging direction is stated.")
        if not s.energy_allowed:
            notes.append("The potential axis is named from the file column until you say what it measures.")
        self.set_note(notes if not self.compact else [])
        pairs = {p.index: p for p in run.seg.pairs}
        cols = self.colors()
        order = self.drawn()
        unit = capacity_unit(s)
        for c in order:
            p = pairs.get(c)
            if p is None:
                continue
            for br in (p.charge, p.discharge):
                if br is None:
                    continue
                q = capacity_basis(cumulative_charge(tab, run.seg, br, s.use_instrument_dq), s)
                e = tab.e[br.rows]
                focus = c == self.focus
                item = pg.PlotDataItem(q, e, pen=_pen(cols[c], 2.6 if focus else 1.3,
                                                      Qt.DashLine if self.preview(c) else Qt.SolidLine))
                item.setZValue(10 if focus else 1)
                pi.addItem(self.keep(item, q, e))
                d = br.direction
                self._points.append((self.plot, q, e,
                                     lambda k, c=c, d=d, q=q, e=e: f"Cycle {c}, {d}: {q[k]:.4g} {unit} at {e[k]:.4f} V"))
        pi.enableAutoRange()


# ------------------------------------------------------------------ capacity and efficiency

class CapacityView(View):
    title = "Capacity and efficiency"

    def __init__(self, parent=None, compact=False):
        super().__init__(parent)
        self.compact = compact
        lay = QVBoxLayout(self.body); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        self.top = self.new_plot(cycles_x=True)
        self.bottom = self.new_plot(cycles_x=True)
        self.bottom.setXLink(self.top)
        # the lower plot also carries the cycle axis: in a small panel equal heights leave it a usable plot area
        lay.addWidget(self.top, 1 if compact else 3)
        lay.addWidget(self.bottom, 1 if compact else 2)
        for w in (self.top, self.bottom):
            w.scene().sigMouseClicked.connect(lambda ev, w=w: self._click(w, ev))

    def _click(self, w, ev):
        if not self.rec or not self.rec.run:
            return
        vb = w.getPlotItem().getViewBox()
        if vb.sceneBoundingRect().contains(ev.scenePos()):
            c = int(round(vb.mapSceneToView(ev.scenePos()).x()))
            if c in self.rec.available_cycles():
                self.focusRequested.emit(c)

    def redraw(self):
        for w in (self.top, self.bottom):
            w.getPlotItem().clear()
        self._points = []
        self._drawn = []
        rec = self.rec
        if not rec or not rec.run:
            return
        s, an = rec.run.settings, rec.run.an
        rows = [c for c in an.cycles if c.complete]
        both = any(c.charge_branch is not None and c.discharge_branch is not None for c in an.cycles)
        self.set_empty(None if rows else (NO_CYCLES if s.charge is None else
                                          "No cycle is complete: a branch of each pair reaches the end of the file or "
                                          "has an unsupported interval (the Cycles table says which)." if both else
                                          "No cycle has both a charge and a discharge."))
        theme.style_plot(self.top, xlabel=None, ylabel=capacity_titles(s))
        theme.style_plot(self.bottom, xlabel=CYCLE_TITLES, ylabel=CE_TITLES)
        t = theme.tokens()
        n = np.array([c.cycle for c in rows], float)

        def get(c, side):                     # the same basis as the axis title (review finding r01)
            v = cycle_capacity(c, side, s)
            return np.nan if v is None else v
        qd = np.array([get(c, "discharge") for c in rows], float)
        qc = np.array([get(c, "charge") for c in rows], float)
        ce = np.array([np.nan if c.coulombic_efficiency_pct is None else c.coulombic_efficiency_pct for c in rows], float)
        notes = []
        if not rows:
            r = reason_for("discharge_capacity_mAh", rec.answers, rec.run) or "no complete charge and discharge pair"
            notes.append(f"Capacity per cycle is withheld: {r}.")
        if rows and not np.isfinite(ce).any():
            notes.append(f"Coulombic efficiency is withheld: {reason_for('coulombic_efficiency_pct', rec.answers, rec.run) or 'not defined'}.")
        self.set_note(notes if not self.compact else [])
        if not rows:
            return
        base = QColor(t.secondary)
        size = 6 if len(n) <= 150 else 4
        if not self.compact:
            _legend(self.top, t)
        self.top.addItem(self.keep(pg.ScatterPlotItem(n, qc, symbol="o", size=size, pen=pg.mkPen(base, width=1.1),
                                                      brush=pg.mkBrush(t.view), name="Charge (open)"), n, qc))
        self.top.addItem(self.keep(pg.ScatterPlotItem(n, qd, symbol="o", size=size, pen=None, brush=pg.mkBrush(base),
                                                      name="Discharge (filled)"), n, qd))
        if np.isfinite(ce).any():
            self.bottom.addItem(self.keep(pg.ScatterPlotItem(n, ce, symbol="t1", size=size + 1, pen=None,
                                                             brush=pg.mkBrush(t.ink)), n, ce))
        cols = self.colors()
        idx = {int(c): k for k, c in enumerate(n)}
        for c, col in cols.items():
            if c in idx:
                k = idx[c]
                ring = pg.mkPen(t.selection, width=2.0) if c == self.focus else pg.mkPen(col, width=1.0)
                self.top.addItem(pg.ScatterPlotItem([n[k]], [qd[k]], symbol="o", size=size + 5, pen=ring,
                                                    brush=pg.mkBrush(col)))
        if self.focus in idx:
            for w in (self.top, self.bottom):
                w.addItem(pg.InfiniteLine(self.focus, angle=90, pen=pg.mkPen(t.selection, width=1, style=Qt.DashLine)))
        unit = capacity_unit(s)

        def lab(k):
            return (f"Cycle {int(n[k])}: discharge {fmt(qd[k])} {unit}, charge {fmt(qc[k])} {unit}, "
                    f"CE {fmt(ce[k], 5)} %")
        self._points += [(self.top, n, qd, lab), (self.top, n, qc, lab), (self.bottom, n, ce, lab)]
        for w in (self.top, self.bottom):
            w.getPlotItem().enableAutoRange()


# ------------------------------------------------------------------ differential capacity

class DifferentialView(View):
    title = "Differential capacity"

    def __init__(self, parent=None, compact=False):
        super().__init__(parent)
        self.compact = compact
        lay = QVBoxLayout(self.body); lay.setContentsMargins(0, 0, 0, 0)
        self.plot = self.new_plot()
        lay.addWidget(self.plot)

    def redraw(self):
        pi = self.plot.getPlotItem()
        pi.clear()
        self._points = []
        self._drawn = []
        rec = self.rec
        if not rec or not rec.run:
            return
        run, s, tab = rec.run, rec.run.settings, rec.run.tab
        sym = "V" if s.terminal_voltage else "E"
        unit = f"{capacity_unit(s)} V{SUP_M1}"
        if not run.seg.pairs:
            self.set_note([])
            self.set_empty(NO_CYCLES)
            return
        self.set_empty(None)
        theme.style_plot(self.plot, xlabel=(f"dQ/d{sym} ({unit})", f"dQ/d{sym}"), ylabel=potential_titles(tab, s))
        t = theme.tokens()
        pi.addItem(pg.InfiniteLine(0, angle=90, pen=pg.mkPen(t.line_strong, width=1)))
        cols = self.colors()
        order = self.drawn()
        curves, withheld = run.dqde_and_withheld(order)
        if withheld and not curves:
            self.set_note([])                        # no note of an earlier selection above the sentence
            self.set_empty(NO_DQDE.format(sym=sym))
            return
        for c, cv in curves:
            focus = c == self.focus
            item = pg.PlotDataItem(cv.dqdv, cv.voltage_V, pen=_pen(cols.get(c, t.muted), 2.4 if focus else 1.2,
                                                                   Qt.DashLine if self.preview(c) else Qt.SolidLine))
            item.setZValue(10 if focus else 1)
            pi.addItem(self.keep(item, cv.dqdv, cv.voltage_V))
            self._points.append((self.plot, cv.dqdv, cv.voltage_V,
                                 lambda k, c=c, cv=cv: f"Cycle {c}, {cv.direction}: dQ/d{sym} {cv.dqdv[k]:.4g} {unit} "
                                                       f"at {cv.voltage_V[k]:.4f} V ({cv.bin_mV:g} mV bins)"))
        self.set_note([] if self.compact else
                      [f"Capacity interpolated on a {run.dqde_mv:g} mV grid; constant-voltage stages excluded; "
                       "discharge left, charge right.", withheld_note(run, withheld, sym)])
        self.note.setProperty("role", "muted"); self.note.style().unpolish(self.note); self.note.style().polish(self.note)
        pi.enableAutoRange()


# ------------------------------------------------------------------ average voltage

class VoltageView(View):
    title = "Average voltage"

    def __init__(self, parent=None, compact=False):
        super().__init__(parent)
        self.compact = compact
        lay = QVBoxLayout(self.body); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        self.top = self.new_plot(cycles_x=True)
        self.bottom = self.new_plot(cycles_x=True)
        self.bottom.setXLink(self.top)
        lay.addWidget(self.top, 1 if compact else 3)
        lay.addWidget(self.bottom, 1 if compact else 2)

    def redraw(self):
        for w in (self.top, self.bottom):
            w.getPlotItem().clear()
        self._points = []
        self._drawn = []
        rec = self.rec
        if not rec or not rec.run:
            return
        s, an, tab = rec.run.settings, rec.run.an, rec.run.tab
        what, sym = what_potential(s)          # names the reference, as every other potential axis does
        theme.style_plot(self.top, ylabel=average_titles(s))
        theme.style_plot(self.bottom, xlabel=CYCLE_TITLES, ylabel=(f"Hysteresis, Δ{sym} (V)", f"Δ{sym} (V)"))
        rows = [c for c in an.cycles if c.complete and c.average_charge_voltage_V is not None
                and c.average_discharge_voltage_V is not None]
        if not rows:
            why = reason_for('average_charge_voltage_V', rec.answers, rec.run) or "no complete cycle"
            self.set_empty(NO_CYCLES if s.charge is None else f"Average voltages are withheld: {why}.")
            self.set_note([])
            return
        self.set_empty(None)
        self.set_note([])
        t = theme.tokens()
        n = np.array([c.cycle for c in rows], float)
        vc = np.array([c.average_charge_voltage_V for c in rows]); vd = np.array([c.average_discharge_voltage_V for c in rows])
        # the cycle's own hysteresis: withheld (nan) for a pair with a step that ended at once (cycling.degenerate)
        hy = np.array([np.nan if c.average_voltage_hysteresis_V is None else c.average_voltage_hysteresis_V
                       for c in rows], float)
        ok = np.isfinite(hy)
        size = 6 if len(n) <= 150 else 4
        if not self.compact:
            _legend(self.top, t)
        self.top.addItem(self.keep(pg.ScatterPlotItem(n, vc, symbol="t1", size=size + 1, pen=None, name="Charge",
                                                      brush=pg.mkBrush("#A8507F" if t.name == "light" else "#E59AC5")), n, vc))
        self.top.addItem(self.keep(pg.ScatterPlotItem(n, vd, symbol="t", size=size + 1, pen=None, name="Discharge",
                                                      brush=pg.mkBrush("#0072B2" if t.name == "light" else "#56B4E9")), n, vd))
        self.bottom.addItem(self.keep(pg.ScatterPlotItem(n[ok], hy[ok], symbol="s", size=size, pen=None,
                                                         brush=pg.mkBrush(t.ink)), n[ok], hy[ok]))
        if self.focus is not None:
            for w in (self.top, self.bottom):
                w.addItem(pg.InfiniteLine(self.focus, angle=90, pen=pg.mkPen(t.selection, width=1, style=Qt.DashLine)))

        def lab(k):
            return (f"Cycle {int(n[k])}: average charge {vc[k]:.4f} V, discharge {vd[k]:.4f} V, "
                    + (f"hysteresis {hy[k]:.4f} V" if ok[k] else "hysteresis withheld (a step that ended at once)"))

        def lab_ok(k):
            return lab(int(np.flatnonzero(ok)[k]))
        self._points += [(self.top, n, vc, lab), (self.top, n, vd, lab), (self.bottom, n[ok], hy[ok], lab_ok)]
        for w in (self.top, self.bottom):
            w.getPlotItem().enableAutoRange()


# ------------------------------------------------------------------ timeline

class TimelineView(View):
    title = "Timeline"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self.body); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        self.top = self.new_plot()
        self.bottom = self.new_plot()
        self.bottom.setXLink(self.top)
        lay.addWidget(self.top, 1)
        lay.addWidget(self.bottom, 1)
        for w in (self.top, self.bottom):
            w.scene().sigMouseClicked.connect(lambda ev, w=w: self._click(w, ev))
        self._spans = []

    def _click(self, w, ev):
        vb = w.getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(ev.scenePos()):
            return
        th = vb.mapSceneToView(ev.scenePos()).x()
        for c, a, b in self._spans:
            if a <= th <= b:
                self.focusRequested.emit(c)
                return

    def redraw(self):
        for w in (self.top, self.bottom):
            w.getPlotItem().clear()
        self._points = []
        self._spans = []
        rec = self.rec
        if not rec or not rec.loaded:
            return
        tab = rec.run.tab if rec.run else rec.loaded.tab          # the potential column the analysis uses
        s = rec.run.settings if rec.run else None
        t = theme.tokens()
        th = tab.t / 3600.0
        theme.style_plot(self.top, ylabel=potential_titles(tab, s) if s else ("Potential (V)", "E (V)"))
        theme.style_plot(self.bottom, xlabel=("Time (h)", "t (h)"), ylabel=("Current (mA)", "I (mA)"))
        big = tab.n > 100_000
        for w, y, col in ((self.top, tab.e, "#0072B2" if t.name == "light" else "#56B4E9"),
                          (self.bottom, tab.i * 1e3 if tab.i is not None else None, "#D55E00" if t.name == "light" else "#FF8A3D")):
            if y is None:
                continue
            item = pg.PlotDataItem(th, y, pen=_pen(col, 1.0))
            w.addItem(item)
            if big:
                # after addItem: pyqtgraph 0.14 looks up the item's view while the scene adopts it, before the
                # ViewBox is its parent, and clip-to-view then asks the PlotWidget for autoRangeEnabled (an
                # AttributeError on every large file). Time is monotonic, so peak downsampling is valid.
                item.setDownsampling(auto=True, method="peak")
                item.setClipToView(True)
        self.bottom.addItem(pg.InfiniteLine(0, angle=0, pen=pg.mkPen(t.line_strong, width=1)))
        if rec.run:
            pairs = {p.index: p for p in rec.run.seg.pairs}
            cols = self.colors()
            for c in sorted(set(self.selected) | ({self.focus} if self.focus else set())):
                p = pairs.get(c)
                if p is None:
                    continue
                brs = [b for b in (p.charge, p.discharge) if b is not None]
                a = float(tab.t[brs[0].start] / 3600.0)
                b = float(tab.t[brs[-1].rows][-1] / 3600.0)
                self._spans.append((c, a, b))
                col = QColor(cols.get(c, QColor(t.muted)))
                col.setAlphaF(0.16)
                for w in (self.top, self.bottom):
                    reg = pg.LinearRegionItem((a, b), movable=False, brush=pg.mkBrush(col),
                                              pen=pg.mkPen(t.selection, width=1.5) if c == self.focus else pg.mkPen(None))
                    reg.setZValue(-10)
                    w.addItem(reg)
        if tab.e is not None:
            self._points.append((self.top, th, tab.e, lambda k: f"t = {th[k]:.4f} h, row {k + 1}: {tab.e[k]:.4f} V, "
                                                              f"{tab.i[k] * 1e3:.5g} mA"))
        if tab.i is not None:
            self._points.append((self.bottom, th, tab.i * 1e3, lambda k: f"t = {th[k]:.4f} h, row {k + 1}: {tab.i[k] * 1e3:.5g} mA, "
                                                                       f"{tab.e[k]:.4f} V"))
        self.set_note(["Click a shaded stretch to focus its cycle. Every recorded row is drawn."
                       + (" Display decimation keeps each chunk's minimum and maximum." if big else "")])
        self.note.setProperty("role", "muted"); self.note.style().unpolish(self.note); self.note.style().polish(self.note)
        for w in (self.top, self.bottom):
            w.getPlotItem().enableAutoRange()


# ------------------------------------------------------------------ overview (2 x 2)

class OverviewView(View):
    """The four cycling panels at a glance, arranged for the room there is.

    2 x 2 where each row of panels gets a readable height; one row of four on a short, wide area;
    on a short, narrow one, the two main panels (profiles, capacity and efficiency), since
    dQ/dE and average voltage have their own views one click away."""
    title = "Overview"
    ROW_MIN = 250            # a panel row below this height cannot show a stacked pair legibly
    COL_MIN = 200            # nor a panel narrower than this
    ASPECT = 1.4             # when both arrangements fit, the one whose panels are nearest this width/height

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self.body); grid.setContentsMargins(0, 0, 0, 0); grid.setSpacing(10)
        self.grid = grid
        self.children_views = [ProfilesView(compact=True), CapacityView(compact=True),
                               DifferentialView(compact=True), VoltageView(compact=True)]
        for k, v in enumerate(self.children_views):
            v.focusRequested.connect(self.focusRequested)
            for w in v.plots:
                w.setMinimumHeight(56)       # the overview decides the arrangement; the panels may be small
            grid.addWidget(v, k // 2, k % 2)
        self.shape = "grid"
        self.body.installEventFilter(self)           # the panels' room changes with the note line, not only the view
        self.readout.hide()
        self.raw = TimelineView()                    # what the file holds, before cycles exist
        self.layout().insertWidget(2, self.raw, 1)
        self.raw.hide()

    def show_record(self, rec, selected, focus):
        self.rec = rec
        no_cycles = bool(rec and rec.loaded and (rec.run is None or not rec.run.seg.pairs))
        self.body.setVisible(not no_cycles)
        self.raw.setVisible(no_cycles)
        if no_cycles:
            self.raw.show_record(rec, [], None)
            self.set_note(["The recorded potential and current. Say which current direction charges the cell "
                           "to pair the branches into cycles; the four cycling panels then replace this view."])
            self.note.setProperty("role", "secondary"); self.note.style().unpolish(self.note); self.note.style().polish(self.note)
            return
        self.note.setProperty("role", "withheld"); self.note.style().unpolish(self.note); self.note.style().polish(self.note)
        for v in self.children_views:
            v.show_record(rec, selected, focus)
        notes = []
        if rec and rec.run:
            s = rec.run.settings
            if s.charge is None:
                notes.append("Efficiency, retention and paired capacities are withheld until the charging direction is stated.")
            if not s.energy_allowed:
                notes.append("Average voltage and energy are withheld until you say what the potential column measures.")
        self.set_note(notes)

    def set_selection(self, selected, focus):
        for v in self.children_views:
            v.set_selection(selected, focus)

    def eventFilter(self, obj, e):
        if obj is self.body and e.type() == QEvent.Resize:
            self.arrange(e.size())
        return False

    def arrange(self, size=None):
        w, h = (size.width(), size.height()) if size is not None else (self.body.width(), self.body.height())
        if w <= 0 or h <= 0:
            return
        grid_ok, row_ok = h >= 2 * self.ROW_MIN + 10, w >= 4 * self.COL_MIN + 30
        if grid_ok and row_ok:
            import math                  # aspect ratios compare as ratios: distance in log space
            shape = min(("grid", (w / 2) / (h / 2)), ("row", (w / 4) / h),
                        key=lambda s: abs(math.log(s[1] / self.ASPECT)))[0]
        else:
            shape = "grid" if grid_ok else "row" if row_ok else "pair"
        if shape == self.shape:
            return
        self.shape = shape
        g = self.grid
        places = {"grid": [(0, 0), (0, 1), (1, 0), (1, 1)], "row": [(0, 0), (0, 1), (0, 2), (0, 3)],
                  "pair": [(0, 0), (0, 1), None, None]}[shape]
        for v in self.children_views:
            g.removeWidget(v)
        for v, place in zip(self.children_views, places):
            if place is None:
                v.hide()
            else:
                g.addWidget(v, *place)
                v.show()
        cols = {"grid": 2, "row": 4, "pair": 2}[shape]
        for c in range(4):
            g.setColumnStretch(c, 1 if c < cols else 0)
        for r in range(2):
            g.setRowStretch(r, 1 if (r == 0 or shape == "grid") else 0)

    def reveal(self):
        for v in self.children_views:
            if v.isVisible():
                v.reveal()

    def restyle(self):
        for v in self.children_views:
            v.restyle()
        self.raw.restyle()

    def fit(self):
        for v in self.children_views + [self.raw]:
            v.fit()


# ------------------------------------------------------------------ any column

class DataView(View):
    title = "Data"
    COLUMNS = [("Time (h)", lambda t: t.t / 3600.0), ("Time (s)", lambda t: t.t),
               ("Potential (V)", lambda t: t.e), ("Current (mA)", lambda t: None if t.i is None else t.i * 1e3),
               ("Step (Ns)", lambda t: t.ns), ("Mode", lambda t: t.mode), ("Cycle number (file)", lambda t: t.cycle),
               ("Instrument charge (mAh)", lambda t: None if t.q_instrument is None else t.q_instrument / 3.6),
               ("Temperature (°C)", lambda t: t.temperature), ("Row", lambda t: np.arange(1, t.n + 1, dtype=float))]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self.body); lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.x = QComboBox(); self.y = QComboBox()
        for c in (self.x, self.y):
            c.setMinimumWidth(170)
            c.currentIndexChanged.connect(self.redraw)
        lx, ly = QLabel("Horizontal"), QLabel("Vertical")
        lx.setBuddy(self.x); ly.setBuddy(self.y)
        bar.addWidget(lx); bar.addWidget(self.x); bar.addSpacing(12); bar.addWidget(ly); bar.addWidget(self.y)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.plot = self.new_plot()
        lay.addWidget(self.plot, 1)

    def show_record(self, rec, selected, focus):
        self.rec, self.selected, self.focus = rec, list(selected), focus
        tab = (rec.run.tab if rec.run else rec.loaded.tab) if rec and rec.loaded else None
        for combo, default in ((self.x, "Time (h)"), (self.y, "Potential (V)")):
            keep = combo.currentText() or default
            combo.blockSignals(True)
            combo.clear()
            if tab is not None:
                for name, fn in self.COLUMNS:
                    if fn(tab) is not None:
                        combo.addItem(name)
            combo.setCurrentText(keep if combo.findText(keep) >= 0 else default)
            combo.blockSignals(False)
        self.redraw()

    def redraw(self):
        pi = self.plot.getPlotItem()
        pi.clear()
        self._points = []
        rec = self.rec
        if not rec or not rec.loaded:
            return
        tab = rec.run.tab if rec.run else rec.loaded.tab
        f = dict(self.COLUMNS)
        xn, yn = self.x.currentText(), self.y.currentText()
        if xn not in f or yn not in f:
            return
        x, y = f[xn](tab), f[yn](tab)
        if x is None or y is None:
            return
        theme.style_plot(self.plot, xlabel=xn, ylabel=yn)
        t = theme.tokens()
        item = pg.PlotDataItem(x, y, pen=_pen("#0072B2" if t.name == "light" else "#56B4E9", 1.0))
        pi.addItem(item)
        if tab.n > 100_000 and np.all(np.diff(x) >= 0):          # after addItem: see TimelineView.redraw
            item.setDownsampling(auto=True, method="peak"); item.setClipToView(True)
        self._points.append((self.plot, np.asarray(x, float), np.asarray(y, float),
                             lambda k: f"row {k + 1}: {xn} {x[k]:.6g}, {yn} {y[k]:.6g}"))
        self.set_note(["Columns as recorded, read from the analysed table. Nothing here is recalculated."])
        self.note.setProperty("role", "muted"); self.note.style().unpolish(self.note); self.note.style().polish(self.note)
        pi.enableAutoRange()


# ------------------------------------------------------------------ dQ/dE evolution over cycles

class EvolutionView(View):
    """dQ/dE against potential for every cycle: a colour map (potential across, cycle up, |dQ/dE| as colour) or
    a waterfall of the selected cycles, offset one above the other.

    The map shows differential.evolution_grid of run.dqde_curves(every cycle), the grid figures 6 and 7 and
    dqde_map.csv use; the waterfall draws the selected cycles' own curves, the numbers of dqde_curves.csv.
    Nothing here is recalculated for display: the readout under the cursor gives the stored value."""
    title = "dQ/dE evolution"
    WATERFALL_OFFSET = 0.7            # of the largest |dQ/dE| drawn

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self.body); lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.mode = QComboBox(); self.mode.addItem("Colour map", "map"); self.mode.addItem("Waterfall", "waterfall")
        self.direction = QComboBox(); self.direction.addItem("Charge", "charge"); self.direction.addItem("Discharge", "discharge")
        for label, combo in (("Show", self.mode), ("Branch", self.direction)):
            lab = QLabel(label); lab.setBuddy(combo)
            combo.setAccessibleName(label)
            combo.currentIndexChanged.connect(self.redraw)
            bar.addWidget(lab); bar.addWidget(combo); bar.addSpacing(12)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.plot = self.new_plot()
        lay.addWidget(self.plot, 1)
        self.plot.scene().sigMouseClicked.connect(self._click)
        self.image = pg.ImageItem()
        self.image.setZValue(-5)
        self.cbar = None
        self.grid = None                   # the filled DqdeGrid on display (map mode)
        self._cache_run = None
        self._curves = []
        self._grids = {}
        self._dirty = False

    # the data: computed once per analysis, from the run, with the functions the figures use
    def curves_for(self, run):
        if self._cache_run is not run:
            self._cache_run = run
            self._curves = run.dqde_curves(run.all_cycles)
            self._grids = {}
        return self._curves

    def grid_for(self, run, direction):
        from ..differential import evolution_grid
        curves = self.curves_for(run)
        if direction not in self._grids:
            g = evolution_grid(curves, direction)
            self._grids[direction] = g.filled() if g is not None else None
        return self._grids[direction]

    def _cmap(self):
        import matplotlib.pyplot as plt
        from ..plotting import MAP_CMAP
        cm = plt.get_cmap(MAP_CMAP)
        x = np.linspace(0.0, 1.0, 64)
        return pg.ColorMap(x, (np.array([cm(v) for v in x]) * 255).astype(np.ubyte))

    def showEvent(self, e):
        super().showEvent(e)
        if self._dirty:
            self.redraw()

    def redraw(self):
        pi = self.plot.getPlotItem()
        pi.clear()
        self._points = []
        self._drawn = []
        self.grid = None
        rec = self.rec
        if not rec or not rec.run:
            self.set_note([])
            return
        if not self.isVisible() and self._cache_run is not rec.run:
            self._dirty = True                 # every cycle's curve is computed only when the view is shown
            return
        self._dirty = False
        run, s, tab = rec.run, rec.run.settings, rec.run.tab
        if not run.seg.pairs:
            self.set_note([])
            self.set_empty(NO_CYCLES)
            self._show_cbar(False)
            return
        direction = self.direction.currentData()
        sym = "V" if s.terminal_voltage else "E"
        unit = f"{capacity_unit(s)} V{SUP_M1}"
        t = theme.tokens()
        left = pi.getAxis("left")
        left.setTicks(None)
        if self.mode.currentData() == "map":
            g = self.grid_for(run, direction)
            if g is None:
                self.set_note([])
                self.set_empty(f"No {direction} branch has a dQ/d{sym} curve.")
                self._show_cbar(False)
                return
            self.set_empty(None)
            self.grid = g
            theme.style_plot(self.plot, xlabel=potential_titles(tab, s), ylabel=CYCLE_TITLES)
            pi.showGrid(x=False, y=False)              # no grid lines drawn across the colours
            step = g.bin_mV / 1000.0
            from PySide6.QtCore import QRectF
            from PySide6.QtWidgets import QGraphicsRectItem
            rect = QRectF(float(g.voltage_V[0]) - step / 2, float(g.cycles[0]) - 0.5, len(g.voltage_V) * step, len(g.cycles))
            bg = QGraphicsRectItem(rect)
            from ..plotting import NOT_MEASURED
            bg.setBrush(pg.mkBrush(NOT_MEASURED if t.name == "light" else t.line_strong))
            bg.setPen(pg.mkPen(None))
            bg.setZValue(-10)
            pi.addItem(bg)
            mag = np.abs(g.dqde)
            top = float(np.nanmax(mag)) if np.isfinite(mag).any() else 1.0
            self.image.setImage(mag.T, levels=(0.0, top or 1.0), autoLevels=False)
            self.image.setColorMap(self._cmap())
            self.image.setRect(rect)
            pi.addItem(self.image)
            label = f"|dQ/d{sym}| ({unit})"
            if self.cbar is None:
                self.cbar = pg.ColorBarItem(values=(0.0, top or 1.0), colorMap=self._cmap(), interactive=False,
                                            colorMapMenu=False)
                self.cbar.setImageItem(self.image, insert_in=pi)
            else:
                self.cbar.setLevels((0.0, top or 1.0))
                self.cbar.setColorMap(self._cmap())
                self.cbar.setImageItem(self.image)
            self._style_cbar(label, t)
            self._show_cbar(True)
            if self.focus is not None and g.cycles[0] <= self.focus <= g.cycles[-1]:
                pi.addItem(pg.InfiniteLine(self.focus, angle=0, pen=pg.mkPen(t.selection, width=1, style=Qt.DashLine)))
            self.set_note([f"|dQ/d{sym}| of every cycle on one grid of {g.bin_mV:g} mV nodes (each curve resampled by "
                           "less than one bin); grey where the branch was not measured or has no dQ/d" + sym +
                           " curve (interrupted or paused inside it, as its cycle note says, or too few points or "
                           "too narrow a range outside constant-voltage stages). Peak tables use each branch's own "
                           "grid. The dashed line marks the focused cycle."])
        else:
            self._show_cbar(False)
            curves = {c: cv for c, cv in self.curves_for(run) if cv.direction == direction}
            cyc = [c for c in sorted(set(self.drawn())) if c in curves]
            if not cyc:
                self.set_note([])
                self.set_empty(f"None of the selected cycles has a {direction} dQ/d{sym} curve.")
                return
            self.set_empty(None)
            theme.style_plot(self.plot, xlabel=potential_titles(tab, s),
                             ylabel=("Cycle (curves offset, |dQ/d" + sym + "| upward)", "Cycle"))
            top = max(float(np.nanmax(np.abs(curves[c].dqdv))) for c in cyc) or 1.0
            off = self.WATERFALL_OFFSET * top
            cols = self.colors()
            ticks = []
            for rank, c in enumerate(cyc):
                cv = curves[c]
                y = np.abs(cv.dqdv) + rank * off
                focus = c == self.focus
                item = pg.PlotDataItem(cv.voltage_V, y, pen=_pen(cols.get(c, t.muted), 2.4 if focus else 1.2,
                                                                 Qt.DashLine if self.preview(c) else Qt.SolidLine))
                item.setZValue(10 if focus else 1)
                pi.addItem(self.keep(item, cv.voltage_V, y))
                ticks.append((rank * off, str(c)))
                self._points.append((self.plot, cv.voltage_V, y,
                                     lambda k, c=c, cv=cv, o=rank * off: f"Cycle {c}, {cv.direction}: dQ/d{sym} {cv.dqdv[k]:.4g} "
                                                                       f"{unit} at {cv.voltage_V[k]:.4f} V ({cv.bin_mV:g} mV bins; "
                                                                       f"drawn {o:.3g} higher)"))
            left.setTicks([ticks, []])
            self.set_note([f"The selected cycles' own dQ/d{sym} curves, |dQ/d{sym}| upward, each raised by "
                           f"{self.WATERFALL_OFFSET:g} of the largest value drawn; the axis marks each curve's zero."])
        self.note.setProperty("role", "muted"); self.note.style().unpolish(self.note); self.note.style().polish(self.note)
        pi.enableAutoRange()

    def _click(self, ev):
        """A click on the map focuses the cycle under it, as a click on the capacity plot does."""
        if self.grid is None or self.mode.currentData() != "map" or not self.rec or not self.rec.run:
            return
        vb = self.plot.getPlotItem().getViewBox()
        if vb.sceneBoundingRect().contains(ev.scenePos()):
            c = int(round(vb.mapSceneToView(ev.scenePos()).y()))
            if c in self.rec.available_cycles():
                self.focusRequested.emit(c)

    def _show_cbar(self, on):
        if self.cbar is not None:
            self.cbar.setVisible(on)

    def _style_cbar(self, label, t):
        ax = getattr(self.cbar, "axis", None)
        if ax is None:
            return
        ax.setPen(pg.mkPen(QColor(t.muted), width=1))
        ax.setTextPen(pg.mkPen(QColor(t.secondary)))
        ax.setStyle(tickFont=theme.font(8.5, tabular=True))
        ax.setLabel(label, color=t.secondary)

    def readout_at(self, x, y) -> str:
        """The stored value of the grid node under (potential x, cycle y), in words."""
        g = self.grid
        if g is None or not len(g.cycles):
            return " "
        step = g.bin_mV / 1000.0
        j = int(round((x - float(g.voltage_V[0])) / step))
        k = int(round(y)) - int(g.cycles[0])
        if not (0 <= j < len(g.voltage_V) and 0 <= k < len(g.cycles)):
            return " "
        s = self.rec.run.settings
        sym = "V" if s.terminal_voltage else "E"
        c, v, d = int(g.cycles[k]), float(g.voltage_V[j]), float(g.dqde[k, j])
        if not np.isfinite(g.dqde[k]).any():
            return f"Cycle {c}: no {g.direction} dQ/d{sym} curve"
        if not np.isfinite(d):
            return f"Cycle {c}, {g.direction}: not measured at {v:.4f} V"
        return (f"Cycle {c}, {g.direction}: dQ/d{sym} {d:.4g} {capacity_unit(s)} V{SUP_M1} at {v:.4f} V "
                f"(grid node, {g.bin_mV:g} mV bins)")

    def _hover(self, w, pos):
        if self.mode.currentData() != "map" or self.grid is None:
            return super()._hover(w, pos)
        vb = w.getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(pos):
            return
        p = vb.mapSceneToView(pos)
        self.readout.setText(self.readout_at(p.x(), p.y()))
