"""Visual system: tokens, fonts, style sheet, plot styling and line icons.

Tokens are those of the P12 interface specification (U01, section 6) so the
cycling studio and the CV app read as one product: a quiet neutral frame, the
measurement carries the colour, vermilion marks the selection and nothing
else, ochre and slate mark provisional and withheld values, always with a word.

The cycle ramp is the figure ramp (violet, blue, teal; first cycle darkest) in
the light theme, so the screen matches the exported figure. The dark theme
keeps the same hue order with raised lightness, so a cycle keeps its colour
identity when the theme changes and every step keeps 3:1 against the plot.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap)

FONT_DIR = Path(__file__).with_name("fonts")


@dataclass(frozen=True)
class Tokens:
    name: str
    window: str
    panel: str
    view: str
    raised: str
    ink: str
    secondary: str
    muted: str
    line: str
    line_strong: str
    hover: str
    pressed: str
    selection: str
    selection_text: str
    selection_tint: str
    provisional: str
    withheld: str
    error: str
    ok: str
    focus: str
    primary: str
    primary_text: str
    ramp: tuple
    grid: str


LIGHT = Tokens(
    "light", window="#EDF0F3", panel="#F7F8FA", view="#FFFFFF", raised="#FFFFFF",
    ink="#16202B", secondary="#475263", muted="#636E7C", line="#D8DEE5", line_strong="#B9C2CD",
    hover="#E3E8EE", pressed="#D6DDE5", selection="#D55E00", selection_text="#B34A00", selection_tint="#FBE9DD",
    provisional="#946200", withheld="#5F6B7A", error="#B42318", ok="#1A7F37", focus="#1F5FD1",
    primary="#16202B", primary_text="#FFFFFF",
    ramp=("#2A0A4E", "#3B3B9E", "#2F78C4", "#169C8C"), grid="#EEF1F4")

DARK = Tokens(
    # deep blue ink: the night theme. Text keeps 4.5:1 on every surface, the cycle
    # ramp 3:1 on the plot ground; teal (the end of the ramp, the colour of the
    # core in the logo) is the primary action.
    "dark", window="#0A101A", panel="#0F1724", view="#0B121D", raised="#152033",
    ink="#E6EDF6", secondary="#A3B1C6", muted="#8798AE", line="#1C2A3D", line_strong="#2B3D56",
    hover="#18253A", pressed="#1F2F48", selection="#FF8A3D", selection_text="#FF9E5E", selection_tint="#3B2716",
    provisional="#E2B340", withheld="#9AA7B8", error="#F87171", ok="#4ADE80", focus="#6EA8FE",
    primary="#3CCBB2", primary_text="#06221D",
    ramp=("#A493F5", "#7C95F2", "#58B2EA", "#3CCBB2"), grid="#152033")

_T = LIGHT


def tokens() -> Tokens:
    return _T


def set_tokens(t: Tokens):
    global _T
    _T = t


def _lerp(a: str, b: str, x: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor.fromRgbF(ca.redF() + (cb.redF() - ca.redF()) * x, ca.greenF() + (cb.greenF() - ca.greenF()) * x,
                           ca.blueF() + (cb.blueF() - ca.blueF()) * x)


def ramp(n: int, t: Tokens | None = None) -> list[QColor]:
    """n colours along the cycle ramp, first darkest (light theme) or dimmest (dark theme)."""
    t = t or _T
    stops = t.ramp
    if n <= 1:
        return [QColor(stops[0])]
    out = []
    for x in np.linspace(0.0, 1.0, n):
        seg = min(int(x * (len(stops) - 1)), len(stops) - 2)
        local = x * (len(stops) - 1) - seg
        out.append(_lerp(stops[seg], stops[seg + 1], local))
    return out


# ----------------------------------------------------------------- fonts
FAMILY = "Inter"
DISPLAY = "Inter Display"


def load_fonts() -> str:
    global FAMILY, DISPLAY
    fams = set()
    for f in sorted(FONT_DIR.glob("*.otf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            fams.update(QFontDatabase.applicationFontFamilies(fid))
    FAMILY = "Inter" if "Inter" in fams else QFont().defaultFamily()
    DISPLAY = "Inter Display" if "Inter Display" in fams else FAMILY
    return FAMILY


def css(text: str) -> str:
    """An inline style sheet with its point sizes scaled like the app's (see scale())."""
    import re
    k = scale()
    return re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: f"{float(m.group(1)) * k:.2f}pt", text) if k != 1.0 else text


def scale() -> float:
    from .platform_support import font_scale
    return font_scale()


def font(pt: float = 9.5, weight: int = 400, display: bool = False, tabular: bool = False) -> QFont:
    """A font at `pt` points on Windows; scaled so it is the same physical size on macOS."""
    f = QFont(DISPLAY if display else FAMILY)
    f.setPointSizeF(pt * scale())
    f.setWeight(QFont.Weight(weight))
    f.setHintingPreference(QFont.PreferNoHinting)
    if tabular:
        try:
            f.setFeature(QFont.Tag("tnum"), 1)
        except Exception:
            pass
    return f


# ----------------------------------------------------------------- palette and style sheet
def palette(t: Tokens) -> QPalette:
    p = QPalette()
    c = QColor
    p.setColor(QPalette.Window, c(t.window))
    p.setColor(QPalette.WindowText, c(t.ink))
    p.setColor(QPalette.Base, c(t.view))
    p.setColor(QPalette.AlternateBase, c(t.panel))
    p.setColor(QPalette.Text, c(t.ink))
    p.setColor(QPalette.Button, c(t.panel))
    p.setColor(QPalette.ButtonText, c(t.ink))
    p.setColor(QPalette.ToolTipBase, c(t.raised))
    p.setColor(QPalette.ToolTipText, c(t.ink))
    p.setColor(QPalette.PlaceholderText, c(t.muted))
    p.setColor(QPalette.Highlight, c(t.selection_tint))
    p.setColor(QPalette.HighlightedText, c(t.ink))
    p.setColor(QPalette.Link, c(t.focus))
    p.setColor(QPalette.Mid, c(t.line))
    p.setColor(QPalette.Midlight, c(t.line))
    p.setColor(QPalette.Dark, c(t.line_strong))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, c(t.muted))
    return p


def _assets(t: Tokens) -> dict:
    """Small SVGs for the check mark and the drop-down and spin arrows (a style sheet cannot draw them)."""
    import tempfile
    d = Path(tempfile.gettempdir()) / "electrochem-studio-assets" / t.name
    d.mkdir(parents=True, exist_ok=True)
    files = {
        "check": f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16"><path d="M3.5 8.3l3 3 6-6.6" '
                 f'fill="none" stroke="{t.view}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "down": f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10"><path d="M2 3.5l3 3 3-3" '
                f'fill="none" stroke="{t.secondary}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "up": f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10"><path d="M2 6.5l3-3 3 3" '
              f'fill="none" stroke="{t.secondary}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    }
    out = {}
    for k, v in files.items():
        f = d / f"{k}.svg"
        f.write_text(v, encoding="utf-8")
        out[k] = f.as_posix()
    return out


def stylesheet(t: Tokens) -> str:
    import re
    k = scale()
    css = _stylesheet(t)
    return re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: f"{float(m.group(1)) * k:.2f}pt", css) if k != 1.0 else css


def _stylesheet(t: Tokens) -> str:
    a = _assets(t)
    return f"""
* {{ font-family: "{FAMILY}"; font-size: 9.5pt; }}
QMainWindow, QDialog {{ background: {t.window}; }}
QWidget#Frame {{ background: {t.window}; }}
QWidget#Panel, QFrame#Panel {{ background: {t.panel}; border: 1px solid {t.line}; border-radius: 8px; }}
QWidget#Bar {{ background: {t.panel}; border-bottom: 1px solid {t.line}; }}
QWidget#Status {{ background: {t.panel}; border-top: 1px solid {t.line}; }}
QLabel {{ color: {t.ink}; background: transparent; }}
QLabel[role="secondary"] {{ color: {t.secondary}; }}
QLabel[role="muted"] {{ color: {t.muted}; font-size: 8.5pt; }}
QLabel[role="title"] {{ font-family: "{DISPLAY}"; font-size: 15pt; font-weight: 600; color: {t.ink}; }}
QLabel[role="h2"] {{ font-size: 10.5pt; font-weight: 600; color: {t.ink}; }}
QLabel[role="section"] {{ font-size: 9pt; font-weight: 600; color: {t.secondary}; padding-top: 6px; }}
QLabel[role="value"] {{ font-size: 10pt; font-weight: 500; }}
QLabel[role="provisional"] {{ color: {t.provisional}; }}
QLabel[role="withheld"] {{ color: {t.withheld}; }}
QLabel[role="error"] {{ color: {t.error}; }}
QLabel[role="ok"] {{ color: {t.ok}; }}

QPushButton {{ background: {t.raised}; color: {t.ink}; border: 1px solid {t.line_strong}; border-radius: 6px;
              padding: 5px 12px; min-height: 18px; }}
QPushButton:hover {{ background: {t.hover}; }}
QPushButton:pressed {{ background: {t.pressed}; }}
QPushButton:disabled {{ color: {t.muted}; border-color: {t.line}; background: {t.panel}; }}
QPushButton:focus {{ border: 2px solid {t.focus}; padding: 4px 11px; }}
QPushButton[kind="primary"] {{ background: {t.primary}; color: {t.primary_text}; border: 1px solid {t.primary}; font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {t.secondary}; border-color: {t.secondary}; }}
QPushButton[kind="primary"]:disabled {{ background: {t.line}; border-color: {t.line}; color: {t.muted}; }}
QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; }}
QPushButton[kind="ghost"]:hover {{ background: {t.hover}; }}
QPushButton[kind="ghost"]:focus {{ border: 2px solid {t.focus}; }}
QPushButton[kind="choice"] {{ text-align: left; padding: 6px 10px; }}
QPushButton[kind="choice"]:checked {{ border: 2px solid {t.ink}; padding: 5px 9px; font-weight: 600; background: {t.view}; }}
QPushButton[kind="pill"] {{ border-radius: 13px; padding: 4px 12px; font-weight: 600; }}
QPushButton[kind="pill"][state="needs"] {{ background: {t.selection_tint}; color: {t.selection_text}; border: 1px solid {t.selection}; }}
QPushButton[kind="pill"][state="ready"] {{ background: {t.view}; color: {t.ok}; border: 1px solid {t.ok}; }}
QPushButton[kind="pill"][state="busy"] {{ background: {t.view}; color: {t.secondary}; border: 1px solid {t.line_strong}; }}
QPushButton[kind="pill"][state="failed"] {{ background: {t.view}; color: {t.error}; border: 1px solid {t.error}; }}

QToolButton {{ background: transparent; color: {t.secondary}; border: 1px solid transparent; border-radius: 6px;
              padding: 5px 10px; }}
QToolButton:hover {{ background: {t.hover}; color: {t.ink}; }}
QToolButton:checked {{ background: {t.view}; color: {t.ink}; border: 1px solid {t.line_strong}; font-weight: 600; }}
QToolButton:focus {{ border: 2px solid {t.focus}; }}
QWidget#Segmented {{ background: {t.window}; border: 1px solid {t.line}; border-radius: 8px; }}
QWidget#Segmented QToolButton[compact="true"] {{ padding: 5px 4px; }}

QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{ background: {t.view}; color: {t.ink}; border: 1px solid {t.line_strong};
              border-radius: 6px; padding: 4px 8px; min-height: 18px; selection-background-color: {t.selection_tint};
              selection-color: {t.ink}; }}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{ border: 2px solid {t.focus}; padding: 3px 7px; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {t.muted}; background: {t.panel}; }}
QLineEdit[invalid="true"] {{ border: 2px solid {t.error}; padding: 3px 7px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({a["down"]}); width: 10px; height: 10px; margin-right: 8px; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 18px; border: none; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({a["up"]}); width: 9px; height: 9px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({a["down"]}); width: 9px; height: 9px; }}
QComboBox QAbstractItemView {{ background: {t.raised}; color: {t.ink}; border: 1px solid {t.line_strong};
              selection-background-color: {t.hover}; selection-color: {t.ink}; outline: none; padding: 4px; }}
QCheckBox, QRadioButton {{ color: {t.ink}; spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; border: 1.5px solid {t.secondary};
              background: {t.view}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked {{ background: {t.ink}; border-color: {t.ink}; image: url({a["check"]}); }}
QListView::indicator {{ width: 15px; height: 15px; border: 1.5px solid {t.secondary}; border-radius: 4px; background: {t.view}; }}
QListView::indicator:checked {{ background: {t.ink}; border-color: {t.ink}; image: url({a["check"]}); }}
QListView::indicator:disabled {{ border-color: {t.line_strong}; background: {t.panel}; }}
QRadioButton::indicator:checked {{ background: {t.view}; border: 5px solid {t.ink}; }}
QCheckBox:focus, QRadioButton:focus {{ color: {t.ink}; outline: none; }}
QCheckBox::indicator:focus, QRadioButton::indicator:focus {{ border-color: {t.focus}; }}

QTabWidget::pane {{ border: none; background: {t.panel}; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {t.secondary}; padding: 7px 12px; border: none;
              border-bottom: 2px solid transparent; margin-right: 2px; }}
QTabBar::tab:selected {{ color: {t.ink}; border-bottom: 2px solid {t.ink}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {t.ink}; }}
QTabBar::tab:focus {{ color: {t.focus}; }}

QTableView, QListView, QTreeView {{ background: {t.view}; alternate-background-color: {t.panel}; color: {t.ink};
              border: none; gridline-color: {t.line}; selection-background-color: {t.selection_tint};
              selection-color: {t.ink}; outline: none; }}
QTableView::item, QListView::item {{ padding: 3px 6px; border: none; }}
QListView::item {{ padding: 6px 8px; border-radius: 6px; margin: 1px 4px; }}
QListView::item:hover {{ background: {t.hover}; }}
QListView::item:selected {{ background: {t.selection_tint}; color: {t.ink}; }}
QHeaderView {{ background: {t.panel}; border: none; }}
QHeaderView::section {{ background: {t.panel}; color: {t.secondary}; border: none; border-bottom: 1px solid {t.line};
              border-right: 1px solid {t.line}; padding: 5px 8px; font-weight: 600; font-size: 8.5pt; }}
QTableCornerButton::section {{ background: {t.panel}; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle {{ background: {t.line_strong}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {t.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QSplitter::handle {{ background: {t.window}; }}
QSplitter::handle:hover {{ background: {t.line}; }}
QToolTip {{ background: {t.raised}; color: {t.ink}; border: 1px solid {t.line_strong}; padding: 6px 8px; border-radius: 6px; }}
QMenu {{ background: {t.raised}; color: {t.ink}; border: 1px solid {t.line_strong}; padding: 6px; border-radius: 8px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t.hover}; }}
QMenu::separator {{ height: 1px; background: {t.line}; margin: 5px 8px; }}
QMenuBar {{ background: {t.panel}; color: {t.ink}; border-bottom: 1px solid {t.line}; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; border-radius: 5px; }}
QMenuBar::item:selected {{ background: {t.hover}; }}
QMenuBar#Inline {{ background: transparent; border: none; }}
QMenuBar#Inline::item {{ padding: 6px 9px; color: {t.secondary}; border-radius: 6px; }}
QMenuBar#Inline::item:selected, QMenuBar#Inline::item:pressed {{ background: {t.hover}; color: {t.ink}; }}
QProgressBar {{ background: {t.line}; border: none; border-radius: 2px; height: 4px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {t.ink}; border-radius: 2px; }}
QStatusBar {{ background: {t.panel}; color: {t.muted}; border-top: 1px solid {t.line}; }}
QStatusBar QLabel {{ color: {t.muted}; font-size: 8.5pt; }}
"""


# ----------------------------------------------------------------- plots
def plain_axes(integer_bottom: bool = False) -> dict:
    """Axes whose tick labels are always the plotted numbers.

    pyqtgraph 0.14's AxisItem.updateAutoSIPrefix ignores the autoSIPrefix flag:
    with the flag off it still computes a scale whenever its label is visible,
    and later range changes no longer recompute it. A x1000 factor taken while an
    axis showed 0.3 to 0.55 mAh then stays in the tick labels of 50 to 100
    mAh g-1, and the "(x0.001)" that would reveal it is suppressed because the
    flag is off. Found while reviewing this app's screenshots; see
    tests/test_studio.py::test_axis_ticks_are_never_rescaled.
    """
    import pyqtgraph as pg

    class PlainAxis(pg.AxisItem):
        def __init__(self, orientation, **kw):
            super().__init__(orientation, **kw)
            self.autoSIPrefix = False

        def updateAutoSIPrefix(self):
            self.autoSIPrefixScale = 1.0
            self.labelUnitPrefix = ""
            self._updateLabel()

    class IntegerAxis(PlainAxis):
        """Cycle numbers: whole-number ticks only (not 1.0, 1.2, 1.4 for a two-cycle file)."""

        def tickValues(self, minVal, maxVal, size):
            import math
            levels = [(sp, [v for v in ticks if abs(v - round(v)) < 1e-9])
                      for sp, ticks in super().tickValues(minVal, maxVal, size) if sp >= 1]
            levels = [(sp, ticks) for sp, ticks in levels if ticks]
            if not levels:
                lo, hi = math.ceil(minVal), math.floor(maxVal)
                levels = [(1.0, [float(v) for v in range(lo, hi + 1)])] if hi >= lo else []
            return levels

        def tickStrings(self, values, scale, spacing):
            return [str(int(round(v))) for v in values]

    axes = {k: PlainAxis(k) for k in ("left", "bottom", "right", "top")}
    if integer_bottom:
        axes["bottom"] = IntegerAxis("bottom")
    return axes


def style_plot(plot, t: Tokens | None = None, xlabel=None, ylabel=None):
    """Thin axes, light grid, units in every label, the interface font, ticks inward.

    An axis title may be one text or a sequence of texts from the fullest to the shortest
    (for example "Specific capacity (mAh g⁻¹)", "Q (mAh g⁻¹)"): the longest that fits along
    the axis is shown, and the choice is made again whenever the plot changes size
    (fit_titles), so a small window or panel never cuts a title off."""
    import pyqtgraph as pg
    t = t or _T
    pi = plot.getPlotItem() if hasattr(plot, "getPlotItem") else plot
    if hasattr(plot, "setBackground"):
        plot.setBackground(t.view)
    pen = pg.mkPen(QColor(t.muted), width=1)
    for name in ("left", "bottom", "right", "top"):
        ax = pi.getAxis(name)
        ax.setPen(pen)
        ax.setTextPen(pg.mkPen(QColor(t.secondary)))
        ax.setStyle(tickFont=font(8.5, tabular=True), tickLength=5, tickTextOffset=4, autoExpandTextSpace=True)
    pi.showAxis("right"); pi.showAxis("top")
    for name in ("right", "top"):
        ax = pi.getAxis(name)
        ax.setStyle(showValues=False, tickLength=5)
    pi.showGrid(x=True, y=True, alpha=0.10 if t.name == "light" else 0.14)
    lab = {"color": t.secondary, "font-size": f"{TITLE_PT * scale():.2f}pt", "font-family": FAMILY}
    titles = pi.__dict__.setdefault("_cyclara_titles", {})
    for side, text in (("bottom", xlabel), ("left", ylabel)):
        if text is not None:
            titles[side] = [text] if isinstance(text, str) else [str(x) for x in text]
            pi.getAxis(side).__dict__.pop("_cyclara_title", None)
    for side in titles:
        pi.getAxis(side).__dict__["_cyclara_style"] = dict(lab)
        pi.getAxis(side).__dict__.pop("_cyclara_title", None)        # re-apply in the new colours
    if titles and not pi.__dict__.get("_cyclara_fitting"):
        import weakref
        ref = weakref.ref(pi)
        pi.getViewBox().sigResized.connect(lambda *_: ref() is not None and fit_titles(ref()))
        pi.__dict__["_cyclara_fitting"] = True
    fit_titles(pi)
    pi.getViewBox().setBorder(None)
    pi.setMenuEnabled(False)
    pi.hideButtons()
    for name in ("left", "bottom"):
        pi.getAxis(name).enableAutoSIPrefix(False)


TITLE_PT = 9.0
TITLE_PAD = 12          # the label's own margins (4 + 4) and a little air at the ends of the axis


def title_width(text: str) -> float:
    from PySide6.QtGui import QFontMetricsF
    f = QFont(FAMILY)
    f.setPointSizeF(TITLE_PT * scale())
    return QFontMetricsF(f).horizontalAdvance(text)


def pick_title(variants, room: float) -> str:
    """The fullest variant that fits in `room` points; the shortest if none does."""
    for v in variants:
        if title_width(v) + TITLE_PAD <= room:
            return v
    return variants[-1]


def fit_titles(pi):
    """Choose each axis title's variant for the room along its axis (the view box's height or width)."""
    titles = pi.__dict__.get("_cyclara_titles") or {}
    vb = pi.getViewBox()
    for side, variants in titles.items():
        room = vb.height() if side == "left" else vb.width()
        ax = pi.getAxis(side)
        if room <= 1:                       # not laid out yet: the full title, refitted on the first resize
            text = variants[0]
        else:
            text = pick_title(variants, room)
        if ax.__dict__.get("_cyclara_title") != text:
            ax.__dict__["_cyclara_title"] = text
            pi.setLabel(side, text, **ax.__dict__.get("_cyclara_style", {}))
            ax.resizeEvent()                # pyqtgraph centres the title only on a resize: centre the new text now


# ----------------------------------------------------------------- icons
def icon(name: str, color: str | None = None, size: int = 18) -> QIcon:
    """Line icons drawn for this app on a 24-unit grid, 1.6-unit strokes. Always shown beside words."""
    col = QColor(color or _T.secondary)
    pm = QPixmap(QSize(size * 2, size * 2))
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(2.0)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    pen = QPen(col, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    if name == "file":
        path.moveTo(6, 3); path.lineTo(14, 3); path.lineTo(19, 8); path.lineTo(19, 21); path.lineTo(6, 21); path.closeSubpath()
        path.moveTo(14, 3); path.lineTo(14, 8); path.lineTo(19, 8)
    elif name == "folder":
        path.moveTo(3, 7); path.lineTo(3, 19); path.lineTo(21, 19); path.lineTo(21, 9); path.lineTo(11, 9)
        path.lineTo(9, 6); path.lineTo(3, 6); path.closeSubpath()
    elif name == "export":
        path.moveTo(12, 15); path.lineTo(12, 3); path.moveTo(7.5, 7.5); path.lineTo(12, 3); path.lineTo(16.5, 7.5)
        path.moveTo(5, 13); path.lineTo(5, 21); path.lineTo(19, 21); path.lineTo(19, 13)
    elif name == "search":
        path.addEllipse(QPointF(10.5, 10.5), 6.5, 6.5); path.moveTo(15.5, 15.5); path.lineTo(21, 21)
    elif name == "sun":
        path.addEllipse(QPointF(12, 12), 4, 4)
        for a in range(0, 360, 45):
            v = np.deg2rad(a)
            path.moveTo(12 + 7 * np.cos(v), 12 + 7 * np.sin(v)); path.lineTo(12 + 9.5 * np.cos(v), 12 + 9.5 * np.sin(v))
    elif name == "moon":
        path.moveTo(19, 14.5)
        path.cubicTo(17, 19, 11, 21, 7, 18); path.cubicTo(3, 15, 3, 8, 8, 5); path.cubicTo(6, 10, 10, 17, 19, 14.5)
    elif name == "figure":
        path.addRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
        path.moveTo(6, 16); path.lineTo(10, 11); path.lineTo(13, 14); path.lineTo(18, 8)
    elif name == "check":
        path.moveTo(5, 12.5); path.lineTo(10, 17.5); path.lineTo(19, 7)
    elif name == "warn":
        path.moveTo(12, 3.5); path.lineTo(21.5, 20); path.lineTo(2.5, 20); path.closeSubpath()
        path.moveTo(12, 9.5); path.lineTo(12, 14); path.moveTo(12, 17); path.lineTo(12, 17.2)
    elif name == "cross":
        path.moveTo(6, 6); path.lineTo(18, 18); path.moveTo(18, 6); path.lineTo(6, 18)
    elif name == "undo":
        path.moveTo(9, 5); path.lineTo(4, 10); path.lineTo(9, 15); path.moveTo(4, 10)
        path.cubicTo(13, 10, 20, 10, 20, 15); path.cubicTo(20, 18, 17, 20, 13, 20)
    elif name == "redo":
        path.moveTo(15, 5); path.lineTo(20, 10); path.lineTo(15, 15); path.moveTo(20, 10)
        path.cubicTo(11, 10, 4, 10, 4, 15); path.cubicTo(4, 18, 7, 20, 11, 20)
    elif name == "close":
        path.moveTo(7, 7); path.lineTo(17, 17); path.moveTo(17, 7); path.lineTo(7, 17)
    elif name == "cycles":
        for k, h in enumerate((14, 12, 10.5, 9, 8)):
            x = 4 + k * 4
            path.moveTo(x, 20); path.lineTo(x, 20 - h)
    elif name == "info":
        path.addEllipse(QPointF(12, 12), 9, 9); path.moveTo(12, 11); path.lineTo(12, 16.5); path.moveTo(12, 7.6); path.lineTo(12, 7.8)
    elif name == "chevron-down":
        path.moveTo(6, 9.5); path.lineTo(12, 15.5); path.lineTo(18, 9.5)
    elif name == "chevron-up":
        path.moveTo(6, 14.5); path.lineTo(12, 8.5); path.lineTo(18, 14.5)
    else:
        path.addEllipse(QPointF(12, 12), 8, 8)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


_STYLE = None


def _style():
    """Fusion, without the permanent underline under menu mnemonics (Alt+F still opens File)."""
    global _STYLE
    if _STYLE is None:
        from PySide6.QtWidgets import QProxyStyle, QStyle

        class Style(QProxyStyle):
            def styleHint(self, hint, option=None, widget=None, data=None):
                if hint == QStyle.SH_UnderlineShortcut:
                    return 0
                return super().styleHint(hint, option, widget, data)
        _STYLE = Style("Fusion")
    return _STYLE


def apply(app, t: Tokens):
    set_tokens(t)
    # once per application: app.style() returns Qt's style-sheet wrapper once a sheet is set, so comparing
    # it with _STYLE re-set (and re-polished) the whole style on every theme switch
    if not getattr(app, "_cyclara_style", False):
        app.setStyle(_style())
        app._cyclara_style = True
    app.setPalette(palette(t))
    app.setStyleSheet(stylesheet(t))
    from .platform_support import apply_color_scheme
    apply_color_scheme(t.name == "dark")
