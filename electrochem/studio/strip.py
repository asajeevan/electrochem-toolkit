"""The cycle strip: overview, legend and cycle selector in one band.

One bar per cycle, its height the discharge capacity (or, before the
charging direction is known, the larger of the two branch charges). Selected
cycles take the colour their curves have in every plot, so the strip is the
legend; unselected cycles stay neutral. The focused cycle is underlined in the
selection colour.

Mouse: click toggles a cycle, drag selects a range (Ctrl adds to the
selection), double-click focuses a cycle. Keyboard: Left/Right move the
focus without changing the selection (a focused cycle outside the selection
is previewed in the plots, not exported), Space toggles it, Home/End jump to
the ends, Ctrl+A selects every cycle. Everything the strip does can also be
typed in the expression box.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import theme
from .motion import Motion, animate


def compress(cycles: list[int]) -> str:
    """[1,2,3,4,7,9,10,11] -> '1:4, 7, 9:11' (runs of three or more as ranges)."""
    cs = sorted(set(cycles))
    out, k = [], 0
    while k < len(cs):
        j = k
        while j + 1 < len(cs) and cs[j + 1] == cs[j] + 1:
            j += 1
        if j - k >= 2:
            out.append(f"{cs[k]}:{cs[j]}")
        else:
            out.extend(str(c) for c in cs[k:j + 1])
        k = j + 1
    return ", ".join(out)


class CycleStrip(QWidget):
    selectionChanged = Signal(list)
    focusChanged = Signal(int)

    PAD_L, PAD_R, PAD_T, AXIS_H = 10, 10, 8, 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(70)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Cycle strip")
        self.cycles: list[int] = []
        self.incomplete: set = set()
        self.incomplete_why: dict = {}          # cycle -> why it is incomplete, in words
        self.values = np.array([])
        self.ce: dict[int, float] = {}
        self.unit = ""
        self.selected: list[int] = []
        self.focus: int | None = None
        self.empty_text = "Cycles appear here once the file is read"
        self.hover: int | None = None
        self._drag_from: int | None = None
        self._drag_to: int | None = None
        self._dragging = False
        self._grow = 1.0                 # 0..1 while the bars rise for a newly shown file
        self._focus_x: float | None = None   # where the focus marker is drawn, gliding to its cycle
        self._glide = None
        self._shown_key = None

    def sizeHint(self):
        return QSize(600, 74)

    # -------------------------------------------------------------- data
    def set_data(self, cycles, values, ce=None, unit="", incomplete=(), key=None, incomplete_why=None):
        """key identifies the file: the bars rise once per file, not on every redraw."""
        self.incomplete = set(incomplete)
        self.incomplete_why = dict(incomplete_why or {})
        if key is not None and key != self._shown_key and cycles:
            self._shown_key = key
            self._grow = 0.0

            def step(v):
                self._grow = v
                self.update()
            animate(self, Motion.ms(700), step, None)
        self.cycles = list(cycles)
        self.values = np.array([np.nan if v is None else v for v in values], float)
        self.ce = dict(ce or {})
        self.unit = unit
        self._describe()
        self.update()

    def _target_x(self, c):
        if c is None or c not in self.cycles:
            return None
        r, w = self._slot()
        return r.left() + self.cycles.index(c) * w

    def _glide_to(self, c):
        tx = self._target_x(c)
        if tx is None:
            self._focus_x = None
            return
        if self._focus_x is None or not Motion.moving():
            self._focus_x = tx
            self.update()
            return
        x0 = self._focus_x

        def step(v):
            self._focus_x = x0 + (tx - x0) * v
            self.update()
        animate(self, Motion.ms(220), step, None)

    def set_selection(self, selected, focus=None, emit=False):
        self.selected = [c for c in selected if c in self.cycles] if self.cycles else list(selected)
        old_focus = self.focus
        if focus is not None:
            self.focus = focus
        elif self.focus not in self.selected:
            self.focus = self.selected[0] if self.selected else None
        if self.focus != old_focus or self._focus_x is None:
            self._glide_to(self.focus)
        self._describe()
        self.update()
        if emit:
            self.selectionChanged.emit(list(self.selected))

    def colors(self) -> dict:
        sel = sorted(self.selected)
        return {c: col for c, col in zip(sel, theme.ramp(len(sel)))}

    def _describe(self):
        self.setAccessibleDescription(
            f"{len(self.cycles)} cycles; selected {compress(self.selected) or 'none'}; "
            f"focused cycle {self.focus if self.focus is not None else 'none'}. "
            "The cycles table lists the same values.")

    # -------------------------------------------------------------- geometry
    def _plot_rect(self) -> QRectF:
        return QRectF(self.PAD_L, self.PAD_T, self.width() - self.PAD_L - self.PAD_R,
                      self.height() - self.PAD_T - self.AXIS_H)

    def _slot(self):
        r = self._plot_rect()
        n = max(len(self.cycles), 1)
        return r, r.width() / n

    def _index_at(self, x: float) -> int | None:
        if not self.cycles:
            return None
        r, w = self._slot()
        k = int((x - r.left()) // w)
        return max(0, min(len(self.cycles) - 1, k))

    # -------------------------------------------------------------- painting
    def paintEvent(self, _):
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(self.rect(), QColor(t.view))
        r, w = self._slot()
        if not self.cycles:
            p.setPen(QColor(t.muted))
            p.setFont(theme.font(8.5))
            p.drawText(self.rect().adjusted(12, 0, -12, 0), Qt.AlignCenter | Qt.TextWordWrap, self.empty_text)
            p.end()
            return
        vmax = np.nanmax(self.values) if np.isfinite(self.values).any() else 1.0
        vmax = vmax if vmax > 0 else 1.0
        cols = self.colors()
        neutral = QColor(t.line_strong)
        gap = 1.0 if w >= 4 else 0.0
        lo_drag = hi_drag = None
        n_bars = len(self.cycles)
        if self._dragging and self._drag_from is not None and self._drag_to is not None:
            lo_drag, hi_drag = sorted((self._drag_from, self._drag_to))
        # baseline
        p.setPen(QPen(QColor(t.line), 1))
        p.drawLine(QPointF(r.left(), r.bottom() + 0.5), QPointF(r.right(), r.bottom() + 0.5))
        for k, (c, v) in enumerate(zip(self.cycles, self.values)):
            x0 = r.left() + k * w
            bw = max(w - gap, 1.0)
            if c in self.incomplete or not np.isfinite(v):
                # no paired value: an outlined stub, never a height that would rescale the strip
                col = cols.get(c, QColor(t.muted))
                p.setPen(QPen(col, 1)); p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(x0, r.bottom() - 7, max(bw - 1, 1.0), 6))
                continue
            g = 1.0
            if self._grow < 1.0:
                g = min(max((self._grow * (n_bars + 12) - k) / 12.0, 0.0), 1.0)
                g = 1 - (1 - g) ** 3
            h = max(2.0, (v / vmax) * (r.height() - 6) * g)
            rect = QRectF(x0, r.bottom() - h, bw, h)
            if lo_drag is not None and lo_drag <= k <= hi_drag:
                p.fillRect(QRectF(x0, r.top(), w, r.height()), QColor(t.selection_tint))
            color = cols.get(c, neutral)
            if c == self.hover and c not in cols:
                color = QColor(t.muted)
            p.fillRect(rect, color)
        if self.focus in self.cycles:
            fx = self._focus_x if self._focus_x is not None else self._target_x(self.focus)
            bw = max(w - gap, 1.0)
            p.fillRect(QRectF(fx - (1 if w < 4 else 0), r.bottom() + 2, max(bw, 3.0), 3), QColor(t.selection))
        # axis labels: nice steps in cycle number
        p.setPen(QColor(t.muted))
        p.setFont(theme.font(8, tabular=True))
        n = len(self.cycles)
        target = max(2, int(r.width() / 70))
        step = _nice_step(max(self.cycles) - min(self.cycles) + 1, target)
        idx = {c: k for k, c in enumerate(self.cycles)}
        for c in range(int(np.ceil(min(self.cycles) / step) * step), max(self.cycles) + 1, step):
            if c in idx:
                x = r.left() + (idx[c] + 0.5) * w
                p.drawText(QRectF(x - 30, r.bottom() + 5, 60, self.AXIS_H - 4), Qt.AlignHCenter | Qt.AlignTop, str(c))
        if 1 in idx and step > 1:
            x = r.left() + 0.5 * w
            p.drawText(QRectF(x - 6, r.bottom() + 5, 30, self.AXIS_H - 4), Qt.AlignLeft | Qt.AlignTop, "1")
        if self.hasFocus():
            p.setPen(QPen(QColor(t.focus), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(1, 1, self.width() - 2, self.height() - 2))
        p.end()

    # -------------------------------------------------------------- interaction
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.cycles:
            return
        k = self._index_at(e.position().x())
        self._drag_from = self._drag_to = k
        self._dragging = True
        self._ctrl = bool(e.modifiers() & Qt.ControlModifier)
        self.update()

    def mouseMoveEvent(self, e):
        k = self._index_at(e.position().x())
        if k is None:
            return
        c = self.cycles[k]
        if c != self.hover:
            self.hover = c
            v = self.values[k]
            txt = f"Cycle {c}" + (f" (incomplete: {self.incomplete_why.get(c, 'no partner branch')})"
                                  if c in self.incomplete else "")
            if np.isfinite(v):
                txt += f": {v:.4g} {self.unit}"
            if c in self.ce and self.ce[c] is not None:
                txt += f", CE {self.ce[c]:.2f} %"
            QToolTip.showText(e.globalPosition().toPoint(), txt, self)
            self.update()
        if self._dragging:
            self._drag_to = k
            self.update()

    def mouseReleaseEvent(self, e):
        if not self._dragging or self._drag_from is None:
            return
        a, b = sorted((self._drag_from, self._drag_to))
        self._dragging = False
        if a == b:
            c = self.cycles[a]
            sel = list(self.selected)
            moved = False
            if c in sel and len(sel) > 1:
                sel.remove(c)
                if self.focus == c:                    # the removed cycle is not left focused and undrawn:
                    self.focus = min(sel, key=lambda x: (abs(x - c), x))   # the nearest selected one takes over,
                    moved = True                       # and the app is told (review finding r03)
            elif c not in sel:
                sel.append(c)
                self.focus = c
                moved = True
            self.set_selection(sorted(sel), self.focus, emit=True)
            if moved:
                self.focusChanged.emit(self.focus)
        else:
            rng = self.cycles[a:b + 1]
            sel = sorted(set(self.selected) | set(rng)) if self._ctrl else rng
            self.set_selection(sel, rng[0], emit=True)
            self.focusChanged.emit(rng[0])
        self._drag_from = self._drag_to = None

    def mouseDoubleClickEvent(self, e):
        k = self._index_at(e.position().x())
        if k is None:
            return
        c = self.cycles[k]
        sel = sorted(set(self.selected) | {c})
        self.set_selection(sel, c, emit=True)
        self.focusChanged.emit(c)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._focus_x = None               # slots changed width: the marker snaps to its cycle

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def keyPressEvent(self, e):
        if not self.cycles:
            return super().keyPressEvent(e)
        k = self.cycles.index(self.focus) if self.focus in self.cycles else 0
        key = e.key()
        if key in (Qt.Key_Right, Qt.Key_Left, Qt.Key_Home, Qt.Key_End):
            k = {Qt.Key_Right: min(k + 1, len(self.cycles) - 1), Qt.Key_Left: max(k - 1, 0),
                 Qt.Key_Home: 0, Qt.Key_End: len(self.cycles) - 1}[key]
            self.focus = self.cycles[k]
            self.focusChanged.emit(self.focus)
            self._describe()
            self.update()
        elif key == Qt.Key_Space and self.focus is not None:
            sel = list(self.selected)
            if self.focus in sel and len(sel) > 1:
                sel.remove(self.focus)
            elif self.focus not in sel:
                sel.append(self.focus)
            self.set_selection(sorted(sel), self.focus, emit=True)
        elif key == Qt.Key_A and e.modifiers() & Qt.ControlModifier:
            self.set_selection(list(self.cycles), self.focus, emit=True)
        else:
            super().keyPressEvent(e)


def _nice_step(span: int, target: int) -> int:
    raw = max(span / max(target, 1), 1)
    mag = 10 ** int(np.floor(np.log10(raw)))
    for m in (1, 2, 5, 10):
        if m * mag >= raw:
            return int(m * mag)
    return int(10 * mag)
