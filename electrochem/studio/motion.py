"""Motion: the launch sequence, the reading screen, view transitions and small confirmations.

Rules, so motion helps instead of costing:
- Theatre at the threshold, calm at the bench. The cinematic moments are the
  launch, reading a file, the moment every answer is in, and an export. The
  surfaces where numbers are read never move by themselves.
- Everything is short (launch 1.5 s, transitions about 0.2 s) and can be cut
  short with a click or a key.
- Reduced motion (the operating system's setting or the app's own) replaces
  movement by quick cross-fades and skips the launch sequence.
- The reading screen only states what has actually happened: rows read,
  columns found, branches segmented, cycles paired. No progress is invented.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import (QEasingCurve, QElapsedTimer, QPointF, QRectF, QSettings, QSize, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
                           QRegion)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QStackedWidget, QWidget

from . import brand, platform_support, theme

STORE = "electrochem-toolkit"


class Motion:
    """One switch for the whole app: "full", "reduced" (fades only) or "off"."""
    mode = "full"

    @classmethod
    def load(cls, store=STORE):
        saved = QSettings(store, "studio").value("motion", "")
        if saved in ("full", "reduced", "off"):
            cls.mode = saved
        else:
            cls.mode = "reduced" if platform_support.system_reduces_motion() else "full"
        return cls.mode

    @classmethod
    def ms(cls, full_ms: int) -> int:
        return {"full": full_ms, "reduced": min(full_ms, 120), "off": 0}[cls.mode]

    @classmethod
    def moving(cls) -> bool:
        return cls.mode == "full"


def animate(owner, ms, on_value, on_done=None, easing=QEasingCurve.OutCubic, start=0.0, end=1.0):
    """Run a 0..1 animation owned by `owner`; returns the animation (kept alive by its parent)."""
    if ms <= 0:
        on_value(end)
        if on_done:
            on_done()
        return None
    a = QVariantAnimation(owner)
    a.setStartValue(float(start)); a.setEndValue(float(end))
    a.setDuration(ms); a.setEasingCurve(easing)
    a.valueChanged.connect(lambda v: on_value(float(v)))
    if on_done:
        a.finished.connect(on_done)
    a.start(QVariantAnimation.DeleteWhenStopped)
    return a


def _seg(p, a, b):
    """Local progress of the phase [a, b] within the master progress p."""
    return min(max((p - a) / (b - a), 0.0), 1.0)


# ------------------------------------------------------------------ the launch sequence

class Ignition(QWidget):
    """Full-window overlay: the ring traces, the cycles fire, the core lights, the name resolves.

    Drawn inside the main window rather than as a separate splash window, so it
    behaves the same on Windows and macOS (no focus or stacking surprises).
    """
    finished = Signal()
    LENGTH = 1500
    FADE = 320

    def __init__(self, parent, version=""):
        super().__init__(parent)
        self.version = version
        self.p = 0.0
        self.fade = 1.0
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"{brand.APP_NAME} is starting")
        self.resize(parent.size())
        self._clock = QElapsedTimer()
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        self._done = False

    def start(self):
        if not Motion.moving():
            self.p = 1.0
            self.show(); self.raise_()
            QTimer.singleShot(Motion.ms(250) + 120, self._leave)
            return
        self.show(); self.raise_(); self.setFocus()
        self._timer.start()              # the clock itself starts at the first painted frame (see paintEvent)

    def _tick(self):
        if not self._clock.isValid():    # not painted yet: the window may still be appearing
            self.update()
            return
        self.p = min(self._clock.elapsed() / self.LENGTH, 1.0)
        self.update()
        if self.p >= 1.0:
            self._timer.stop()
            QTimer.singleShot(140, self._leave)

    def _leave(self):
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.p = 1.0

        def step(v):
            self.fade = 1.0 - v
            self.update()

        def end():
            self.hide()
            self.finished.emit()
            self.deleteLater()
        animate(self, Motion.ms(self.FADE), step, end, QEasingCurve.InOutCubic)

    def mousePressEvent(self, e):
        self._leave()

    def keyPressEvent(self, e):
        self._leave()

    def resizeEvent(self, e):
        super().resizeEvent(e)

    def paintEvent(self, _):
        if not self._clock.isValid() and self._timer.isActive():
            self._clock.start()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setOpacity(self.fade)
        w, h = self.width(), self.height()
        c = QPointF(w / 2.0, h * 0.44)
        g = QRadialGradient(c, max(w, h) * 0.75)
        g.setColorAt(0.0, QColor("#111B30")); g.setColorAt(1.0, QColor("#04070D"))
        p.fillRect(self.rect(), g)
        P = self.p
        size = min(w, h) * 0.34
        R = size / 2.0

        # radar: faint rings and ticks that frame the mark
        rad = _seg(P, 0.0, 0.35)
        if rad > 0:
            for k, rr in enumerate((1.25, 1.62, 2.05)):
                col = QColor(124, 149, 242, int(26 * rad * (1 - 0.25 * k)))
                p.setPen(QPen(col, 1.0)); p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, R * rr, R * rr)
            ticks = 72
            for k in range(ticks):
                if k / ticks > rad:
                    break
                a = math.radians(k * 360 / ticks - 90)
                long = k % 6 == 0
                r1, r2 = R * 1.62, R * (1.62 + (0.08 if long else 0.04))
                col = QColor(124, 149, 242, 70 if long else 34)
                p.setPen(QPen(col, 1.2 if long else 0.8))
                p.drawLine(QPointF(c.x() + r1 * math.cos(a), c.y() + r1 * math.sin(a)),
                           QPointF(c.x() + r2 * math.cos(a), c.y() + r2 * math.sin(a)))

        # the mark itself, from the same function as the icon
        spin = -28.0 * (1.0 - brand.ease_out(_seg(P, 0.0, 0.85)))
        glow = 1.0 + 0.9 * math.sin(math.pi * _seg(P, 0.50, 0.85))
        brand.draw_mark(p, QRectF(c.x() - R, c.y() - R, size, size),
                        ring=_seg(P, 0.0, 0.32), bars=_seg(P, 0.12, 0.66), core=_seg(P, 0.46, 0.76),
                        orbit=_seg(P, 0.58, 0.90), glow=glow * _seg(P, 0.40, 0.70), detail="full", dark=True, spin=spin)

        # a scan line passes once
        scan = _seg(P, 0.30, 0.88)
        if 0 < scan < 1:
            y = h * (0.18 + 0.64 * scan)
            lg = QLinearGradient(0, y - 18, 0, y + 2)
            lg.setColorAt(0.0, QColor(60, 203, 178, 0)); lg.setColorAt(1.0, QColor(60, 203, 178, 46))
            p.fillRect(QRectF(0, y - 18, w, 20), lg)
            p.setPen(QPen(QColor(60, 203, 178, 90), 1.0))
            p.drawLine(QPointF(0, y + 2), QPointF(w, y + 2))

        # the name resolves: tracking tightens as it fades in
        word = brand.ease_out(_seg(P, 0.60, 0.92))
        if word > 0:
            f = QFont(theme.DISPLAY)
            f.setPixelSize(max(int(min(w, h) * 0.058), 18))
            f.setWeight(QFont.Weight(600))
            f.setLetterSpacing(QFont.AbsoluteSpacing, f.pixelSize() * (0.62 - 0.36 * word))
            p.setFont(f)
            p.setPen(QColor(230, 237, 245, int(255 * word)))
            top = c.y() + R * 1.32
            p.drawText(QRectF(0, top, w, f.pixelSize() * 1.6), Qt.AlignHCenter | Qt.AlignTop, brand.APP_NAME.upper())
            tag = brand.ease_out(_seg(P, 0.74, 1.0))
            if tag > 0:
                f2 = QFont(theme.FAMILY); f2.setPixelSize(max(int(min(w, h) * 0.020), 12))
                p.setFont(f2)
                p.setPen(QColor(166, 180, 198, int(255 * tag)))
                p.drawText(QRectF(0, top + f.pixelSize() * 1.75, w, f2.pixelSize() * 2), Qt.AlignHCenter | Qt.AlignTop,
                           brand.TAGLINE)
                p.setPen(QColor(127, 142, 163, int(200 * tag)))
                f3 = QFont(theme.FAMILY); f3.setPixelSize(max(int(min(w, h) * 0.014), 10)); p.setFont(f3)
                p.drawText(QRectF(0, h - 40, w, 24), Qt.AlignHCenter, f"version {self.version}")
        p.end()


# ------------------------------------------------------------------ the reading screen

class Reactor(QWidget):
    """The mark, alive: bars brighten in a travelling wave, the core breathes, the orbit turns."""

    def __init__(self, parent=None, calm=False):
        super().__init__(parent)
        self.setMinimumSize(96, 96)
        self.calm = calm                 # idle: a slow turn and a breathing core; active: the scan runs too
        self.phase = 0.0
        self._clock = QElapsedTimer(); self._clock.start()
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        self.done = False

    def showEvent(self, e):
        super().showEvent(e)
        if Motion.moving():
            self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def _tick(self):
        self.phase = self._clock.elapsed() / 1000.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        s = min(self.width(), self.height()) * 0.92
        r = QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s)
        dark = theme.tokens().name == "dark"
        t = self.phase
        rate = 1.1 if self.calm else 2.4
        breathe = 0.86 + 0.14 * math.sin(t * rate)
        spin = (t * (9.0 if self.calm else 40.0)) % 360 if Motion.moving() and not self.done else 0.0
        brand.draw_mark(p, r, ring=1.0, bars=1.0, core=breathe if not self.done else 1.0, orbit=1.0,
                        glow=(1.0 + 0.35 * math.sin(t * rate)) if dark else 0.6, detail="full", dark=dark, spin=spin)
        # travelling highlight over the bars, only while something is being worked on
        if Motion.moving() and not self.done and not self.calm:
            c = r.center(); R = s / 2
            a = math.radians((t * 220.0) % 360)
            col = QColor(255, 255, 255, 60 if dark else 40)
            p.setPen(QPen(col, R * 0.05, Qt.SolidLine, Qt.RoundCap))
            for k in range(6):
                aa = a - math.radians(k * 5)
                alpha = 60 * (1 - k / 6) if dark else 40 * (1 - k / 6)
                p.setPen(QPen(QColor(255, 255, 255, int(alpha)), R * 0.05, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(c.x() + R * 0.53 * math.cos(aa), c.y() + R * 0.53 * math.sin(aa)),
                           QPointF(c.x() + R * 0.80 * math.cos(aa), c.y() + R * 0.80 * math.sin(aa)))
        p.end()


class Telemetry(QWidget):
    """Lines that type themselves as each real step completes, with the elapsed time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lines: list[list] = []          # [text, shown_chars, done, kind]
        self.title = ""
        self.started = time.monotonic()
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        self.setMinimumWidth(360)

    def sizeHint(self):
        return QSize(560, 260)             # room for a whole line where the window allows; elided below that

    def reset(self, title):
        self.title = title
        self.lines = []
        self.started = time.monotonic()
        self._timer.start()
        self.update()

    def add(self, text, kind="step"):
        """kind: "step" (pulsing while current, a check once the next line starts), "note" (a statement
        about something still to come: a hollow ring, never a check) or "error" (a cross)."""
        for ln in self.lines:
            ln[2] = True
        shown = 0 if Motion.moving() else len(text)
        self.lines.append([text, shown, kind not in ("step", "progress"), kind])
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def progress(self, text):
        """A step that reports its own progress: the line is rewritten in place as the reader advances
        (a large file read in chunks), rather than one line per chunk."""
        if self.lines and self.lines[-1][3] == "progress" and not self.lines[-1][2]:
            self.lines[-1][0] = text
            self.lines[-1][1] = len(text)
            self.update()
        else:
            self.add(text, "progress")

    def finish(self):
        for ln in self.lines:
            ln[2] = True
            ln[1] = len(ln[0])
        self.update()

    def _tick(self):
        busy = False
        for ln in self.lines:
            if ln[1] < len(ln[0]):
                ln[1] = min(len(ln[0]), ln[1] + 2)
                busy = True
        self.update()
        if not self.isVisible() and not busy:
            self._timer.stop()

    def paintEvent(self, _):
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        x, y = 4, 6
        f = theme.font(15, 600, display=True)
        p.setFont(f); p.setPen(QColor(t.ink))
        p.drawText(QRectF(x, y, self.width() - 8, 30), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        y += 42
        f2 = theme.font(10, 400, tabular=True)
        p.setFont(f2)
        teal = QColor(brand.RAMP_DARK[3] if t.name == "dark" else brand.RAMP_LIGHT[3])
        for k, (text, shown, done, kind) in enumerate(self.lines):
            last = k == len(self.lines) - 1
            # status glyph: a check for finished steps, a pulsing dot for the current one
            cx, cy = x + 7, y + 11
            if kind == "error":
                p.setPen(QPen(QColor(t.error), 1.8, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(cx - 4, cy - 4), QPointF(cx + 4, cy + 4))
                p.drawLine(QPointF(cx - 4, cy + 4), QPointF(cx + 4, cy - 4))
            elif kind == "note":
                p.setPen(QPen(QColor(t.muted), 1.4)); p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), 3.8, 3.8)
            elif done:
                p.setPen(QPen(teal, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPolyline([QPointF(cx - 4, cy), QPointF(cx - 1, cy + 3), QPointF(cx + 5, cy - 4)])
            else:
                pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 6.0) if Motion.moving() else 1.0
                col = QColor(teal); col.setAlphaF(0.35 + 0.65 * pulse)
                p.setPen(Qt.NoPen); p.setBrush(col)
                p.drawEllipse(QPointF(cx, cy), 3.6, 3.6)
            p.setPen(QColor(t.error if kind == "error" else t.ink if (last and not done) else t.secondary))
            box = QRectF(x + 22, y, self.width() - x - 26, 22)
            shown_text = p.fontMetrics().elidedText(text[:shown], Qt.ElideRight, int(box.width()))
            p.drawText(box, Qt.AlignLeft | Qt.AlignVCenter, shown_text)
            y += 26
        el = time.monotonic() - self.started
        p.setPen(QColor(t.muted))
        p.setFont(theme.font(9, tabular=True))
        p.drawText(QRectF(x + 22, y + 8, 300, 20), Qt.AlignLeft | Qt.AlignVCenter, f"{el:4.1f} s")
        p.end()


class IngestScreen(QWidget):
    """What fills the centre while a file is read and first analysed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Frame")
        from PySide6.QtWidgets import QHBoxLayout
        lay = QHBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(36)
        lay.addStretch(1)
        self.reactor = Reactor(calm=False)
        self.reactor.setFixedSize(260, 260)
        lay.addWidget(self.reactor, 0, Qt.AlignVCenter)
        self.telemetry = Telemetry()
        self.telemetry.setFixedHeight(260)
        self.telemetry.setMinimumWidth(380)             # long lines are elided; 520 wide where there is room
        lay.addWidget(self.telemetry, 0, Qt.AlignVCenter)   # its preferred width; the stretches centre the pair
        lay.addStretch(1)
        self._narrow = None
        self.record = None
        self.setAccessibleName("Reading the file")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        narrow = self.width() < 900                      # beside the inspector on a 1024-point window
        if narrow != self._narrow:
            self._narrow = narrow
            lay = self.layout()
            lay.setContentsMargins(*((16, 24, 16, 24) if narrow else (40, 40, 40, 40)))
            lay.setSpacing(20 if narrow else 36)
            self.reactor.setFixedSize(*((170, 170) if narrow else (260, 260)))
            self.telemetry.setMaximumWidth(16777215 if narrow else 620)

    def begin(self, record, title, first_line):
        self.record = record
        self.reactor.done = False
        self.telemetry.reset(title)
        self.telemetry.add(first_line)
        self.setAccessibleDescription(first_line)

    def step(self, text, kind="step"):
        self.telemetry.add(text, kind)
        self.setAccessibleDescription(text)

    def progress(self, text):
        self.telemetry.progress(text)
        self.setAccessibleDescription(text)

    def finish(self):
        self.reactor.done = True
        self.telemetry.finish()


# ------------------------------------------------------------------ view transitions

class FadeStack(QStackedWidget):
    """A stacked widget whose page changes cross-fade with a short rise.

    The outgoing page is captured as an image and faded over the incoming one,
    which is cheap and works the same with plots, tables and text on every
    platform (an opacity effect on a live plot is slow and can misdraw).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ghost = QLabel(self)
        self._ghost.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._ghost.hide()
        self._fx = QGraphicsOpacityEffect(self._ghost)
        self._ghost.setGraphicsEffect(self._fx)
        self.currentChanged.connect(lambda _: self.updateGeometry())

    def minimumSizeHint(self):
        """The page on show sets the minimum, not the widest page of all: the Figures page or the reading
        screen must not hold a narrow window's plots at their width while they are hidden."""
        w = self.currentWidget()
        if w is None:
            return super().minimumSizeHint()
        h, m = w.minimumSizeHint(), w.minimumSize()
        return QSize(m.width() or max(h.width(), 0), m.height() or max(h.height(), 0))

    def fade_to(self, index: int):
        if index == self.currentIndex() or self.currentWidget() is None:
            self.setCurrentIndex(index)
            return
        ms = Motion.ms(200)
        if ms <= 0 or not self.isVisible():
            self.setCurrentIndex(index)
            return
        pix = self.currentWidget().grab()
        self._ghost.setPixmap(pix)
        self._ghost.setGeometry(self.rect())
        self._fx.setOpacity(1.0)
        self.setCurrentIndex(index)      # raises the incoming page, so the snapshot goes on top after it
        self._ghost.show(); self._ghost.raise_()
        rise = 10 if Motion.moving() else 0

        def step(v):
            self._fx.setOpacity(1.0 - v)
            self._ghost.move(0, int(-rise * v))
        animate(self, ms, step, lambda: self._ghost.hide(), QEasingCurve.OutCubic)


# ------------------------------------------------------------------ confirmations

class Sweep(QWidget):
    """A bright band that sweeps once across a widget: the lock-on when everything is ready."""

    def __init__(self, target: QWidget, color: str):
        super().__init__(target)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.color = QColor(color)
        self.x = -0.3
        self.setGeometry(target.rect())
        self.show(); self.raise_()

        def step(v):
            self.x = -0.3 + 1.6 * v
            self.update()
        animate(self, Motion.ms(650), step, self.deleteLater, QEasingCurve.InOutCubic)

    def paintEvent(self, _):
        if not Motion.moving():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        x = self.x * w
        g = QLinearGradient(x - w * 0.25, 0, x + w * 0.25, 0)
        c0 = QColor(self.color); c0.setAlpha(0)
        c1 = QColor(self.color); c1.setAlpha(120)
        g.setColorAt(0.0, c0); g.setColorAt(0.5, c1); g.setColorAt(1.0, c0)
        p.setBrush(g); p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        p.end()


class Ripple(QWidget):
    """One expanding ring from the centre of a widget, drawn over the window."""

    def __init__(self, window: QWidget, target: QWidget, color: str):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(window.rect())
        self.center = target.mapTo(window, target.rect().center())
        self.color = QColor(color)
        self.v = 0.0
        self.show(); self.raise_()

        def step(v):
            self.v = v
            self.update()
        animate(self, Motion.ms(700), step, self.deleteLater, QEasingCurve.OutCubic)

    def paintEvent(self, _):
        if not Motion.moving():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = 12 + 90 * self.v
        col = QColor(self.color); col.setAlphaF(0.55 * (1 - self.v))
        p.setPen(QPen(col, 2.0)); p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(self.center), r, r * 0.55)
        p.end()


class ThemeReveal(QWidget):
    """The theme changes as a circle that widens from the switch.

    The window as it looked is held as a picture over the window while the new theme is applied
    underneath (applying it takes a moment and would otherwise show half-restyled frames); then a
    widening hole, edged with a thin ring in the cycle ramp's teal, uncovers the new look. The
    circle starts growing at the first frame painted after the restyle, so the restyle's own work
    never eats into it, and each frame repaints only the ring of window it uncovers.
    Reduced motion: a quick cross-fade. No motion: nothing, the change is immediate."""

    LENGTH = 560

    def __init__(self, window: QWidget, picture: QPixmap, centre):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.picture = picture
        self.c = QPointF(centre)
        self.r = 0.0
        self.alpha = 1.0
        self.ring = None
        self._armed = False
        self._clock = QElapsedTimer()
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        self.setGeometry(window.rect())
        w, h = self.width(), self.height()
        self.rmax = max(math.hypot(x - self.c.x(), y - self.c.y()) for x in (0, w) for y in (0, h)) + 8
        self.show(); self.raise_()

    def start(self, ring: str):
        self.ring = QColor(ring)
        if not Motion.moving():
            def fade(v):
                self.alpha = 1.0 - v
                self.update()
            animate(self, Motion.ms(160), fade, self._done, QEasingCurve.OutCubic)
            return
        self._armed = True
        self._timer.start()
        self.update()

    def _tick(self):
        if not self._clock.isValid():
            return
        v = min(self._clock.elapsed() / self.LENGTH, 1.0)
        e = QEasingCurve(QEasingCurve.InOutCubic).valueForProgress(v)
        old, self.r = self.r, self.rmax * e
        # repaint only the band the circle moved through (and its glow), not the whole window
        outer = self.r + 6
        band = QRegion(QRectF(self.c.x() - outer, self.c.y() - outer, 2 * outer, 2 * outer).toAlignedRect(),
                       QRegion.Ellipse)
        inner = max(old - 6, 0)
        if inner > 2:
            band = band.subtracted(QRegion(QRectF(self.c.x() - inner, self.c.y() - inner, 2 * inner,
                                                  2 * inner).toAlignedRect(), QRegion.Ellipse))
        self.update(band)
        if v >= 1.0:
            self._timer.stop()
            self._done()

    def _done(self):
        self.hide()
        self.deleteLater()

    def paintEvent(self, _):
        if self._armed and not self._clock.isValid():
            self._clock.start()             # the first frame after the restyle: the circle starts now
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setOpacity(self.alpha)
        if self.r > 0:
            keep = QPainterPath(); keep.addRect(QRectF(self.rect()))
            hole = QPainterPath(); hole.addEllipse(self.c, self.r, self.r)
            p.setClipPath(keep.subtracted(hole))
        p.drawPixmap(0, 0, self.picture)
        if 0 < self.r < self.rmax and self.ring is not None:
            p.setClipping(False)
            fade = 1.0 - self.r / self.rmax
            for width, a in ((7.0, 0.12), (1.6, 0.85)):           # a soft glow under a crisp edge
                col = QColor(self.ring); col.setAlphaF(a * fade)
                p.setPen(QPen(col, width)); p.setBrush(Qt.NoBrush)
                p.drawEllipse(self.c, self.r, self.r)
        p.end()


class DropOverlay(QWidget):
    """Shown while files are dragged over the window: a scanning frame that says what will happen."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.text = ""
        self.phase = 0.0
        self._clock = QElapsedTimer()
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def present(self, text: str):
        self.text = text
        self.setGeometry(self.parent().rect())
        self._clock.start()
        if Motion.moving():
            self._timer.start()
        self.show(); self.raise_()
        self.update()

    def dismiss(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self.phase = self._clock.elapsed() / 1000.0
        self.update()

    def paintEvent(self, _):
        t = theme.tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        bg = QColor(t.window); bg.setAlphaF(0.86)
        p.fillRect(self.rect(), bg)
        m = 28
        r = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        teal = QColor(brand.RAMP_DARK[3] if t.name == "dark" else brand.RAMP_LIGHT[3])
        pen = QPen(teal, 2.0, Qt.DashLine)
        pen.setDashPattern([6, 6])
        pen.setDashOffset(-self.phase * 24 if Motion.moving() else 0)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 16, 16)
        # corner brackets: the scanner frame
        p.setPen(QPen(teal, 3.0, Qt.SolidLine, Qt.RoundCap))
        L = 34
        for (x, y, dx, dy) in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                               (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)):
            p.drawLine(QPointF(x, y + dy * 14), QPointF(x, y + dy * L))
            p.drawLine(QPointF(x + dx * 14, y), QPointF(x + dx * L, y))
        s = min(self.width(), self.height()) * 0.18
        c = QPointF(self.width() / 2, self.height() / 2 - s * 0.35)
        brand.draw_mark(p, QRectF(c.x() - s / 2, c.y() - s / 2, s, s), dark=t.name == "dark", detail="full",
                        spin=(self.phase * 60) % 360 if Motion.moving() else 0, glow=1.0)
        p.setPen(QColor(t.ink))
        p.setFont(theme.font(16, 600, display=True))
        p.drawText(QRectF(0, c.y() + s * 0.62, self.width(), 34), Qt.AlignHCenter | Qt.AlignVCenter, self.text)
        p.end()
