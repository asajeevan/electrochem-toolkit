"""Cyclara: name, mark and icons.

The mark is a "cycle reactor": radial bars sweep anticlockwise around a
glowing core, the way a pen writes the letter C, each bar a little shorter
than the one before, as capacity fades from cycle to cycle. Colours run along
the app's cycle ramp (violet to teal). It is the cycle strip bent into a ring.

One parametric function, draw_mark(), draws it for the static icons and for
every frame of the launch animation, so the two can never disagree.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient)

APP_NAME = "Cyclara"
TAGLINE = "Every cycle, clearly."
APP_ID = "io.github.asajeevan.cyclara"
ASSETS = Path(__file__).with_name("assets")

# ramps for dark and light grounds (the dark one is the app's dark-theme cycle ramp)
RAMP_DARK = ("#A493F5", "#7C95F2", "#58B2EA", "#3CCBB2")
RAMP_LIGHT = ("#2A0A4E", "#3B3B9E", "#2F78C4", "#169C8C")
CORE = ("#FFFFFF", "#C8FBF1", "#3CCBB2")
GROUND = ("#141E33", "#070B14")


def _lerp(stops, x):
    x = min(max(x, 0.0), 1.0)
    f = x * (len(stops) - 1)
    i = min(int(f), len(stops) - 2)
    a, b = QColor(stops[i]), QColor(stops[i + 1])
    t = f - i
    return QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * t, a.greenF() + (b.greenF() - a.greenF()) * t,
                           a.blueF() + (b.blueF() - a.blueF()) * t)


def geometry(n=30, sweep=300.0):
    """Bars as (angle in degrees clockwise from east, length as a fraction of the radius)."""
    out = []
    for k in range(n):
        f = k / (n - 1)
        theta = -30.0 - f * sweep                       # anticlockwise from the top end of the C
        length = 0.22 + 0.19 * (1.0 - f) ** 1.6        # capacity fading cycle by cycle
        out.append((theta, length))
    return out


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def draw_mark(p: QPainter, rect: QRectF, *, ring=1.0, bars=1.0, core=1.0, orbit=1.0, glow=1.0,
              detail="full", dark=True, spin=0.0):
    """Draw the mark inside rect. Progress arguments run 0 to 1 (used by the launch animation).

    detail: "full" (orbit and halo), "medium", or "small" (fewer, bolder bars for 16 to 32 px).
    """
    ramp = RAMP_DARK if dark else RAMP_LIGHT
    c = rect.center()
    R = min(rect.width(), rect.height()) / 2.0
    n = {"full": 30, "medium": 24, "small": 14}[detail]
    bars_geo = geometry(n)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)

    # halo behind the core
    if glow > 0 and detail != "small":
        g = QRadialGradient(c, R * 0.62)
        col = QColor(CORE[2]); col.setAlphaF(0.30 * glow if dark else 0.12 * glow)
        g.setColorAt(0.0, col)
        col2 = QColor(CORE[2]); col2.setAlphaF(0.0)
        g.setColorAt(1.0, col2)
        p.setPen(Qt.NoPen); p.setBrush(g)
        p.drawEllipse(c, R * 0.62, R * 0.62)

    # the guide ring the bars stand on, traced first
    if ring > 0:
        pen = QPen(_lerp(ramp, 0.55), max(R * (0.018 if detail != "small" else 0.05), 0.8))
        pen.setCapStyle(Qt.RoundCap)
        col = pen.color(); col.setAlphaF(0.55 if dark else 0.45); pen.setColor(col)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        r0 = R * 0.47
        span = -300.0 * ease_out(ring)
        path = QPainterPath()
        path.arcMoveTo(QRectF(c.x() - r0, c.y() - r0, 2 * r0, 2 * r0), 30.0)
        path.arcTo(QRectF(c.x() - r0, c.y() - r0, 2 * r0, 2 * r0), 30.0, -span)
        p.drawPath(path)

    if detail == "small":
        # at 16 to 32 px bars turn to noise: a solid C in the ramp, drawn as short overlapping segments
        r_mid = R * 0.66
        steps = 40
        for k in range(steps):
            f0, f1 = k / steps, (k + 1.15) / steps
            if f0 > bars:
                break
            pen = QPen(_lerp(ramp, f0), R * 0.30 * (1.0 - 0.35 * f0))
            pen.setCapStyle(Qt.FlatCap if 0 < k < steps - 1 else Qt.RoundCap)
            p.setPen(pen)
            a0, a1 = -30.0 - 300.0 * f0, -30.0 - 300.0 * min(f1, 1.0)
            rr = QRectF(c.x() - r_mid, c.y() - r_mid, 2 * r_mid, 2 * r_mid)
            p.drawArc(rr, int(-a0 * 16), int(-(a1 - a0) * 16))
        bars = 0.0

    # the bars, one cycle each, fired in order
    width = R * (0.062 if detail == "full" else 0.075 if detail == "medium" else 0.13)
    for k, (theta, length) in enumerate(bars_geo if detail != "small" else []):
        local = ease_out((bars * (n + 6) - k) / 6.0) if bars < 1.0 else 1.0
        if local <= 0:
            continue
        a = math.radians(theta + spin)
        r_in = R * 0.53
        r_out = r_in + R * length * local
        col = _lerp(ramp, k / (n - 1))
        pen = QPen(col, width)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(c.x() + r_in * math.cos(a), c.y() + r_in * math.sin(a)),
                   QPointF(c.x() + r_out * math.cos(a), c.y() + r_out * math.sin(a)))

    # the core: charge, lit last. A centred glow with a thin bright rim, not a glossy ball.
    if core > 0:
        e = ease_out(core)
        rc = R * (0.20 if detail != "small" else 0.24) * (0.6 + 0.4 * e)
        g = QRadialGradient(c, rc)
        cols = CORE if dark else ("#FFFFFF", "#9FE9DA", "#169C8C")
        for pos, hexcol, alpha in ((0.0, cols[0], 1.0), (0.55, cols[1], 0.95), (1.0, cols[2], 0.9)):
            col = QColor(hexcol); col.setAlphaF(alpha * e)
            g.setColorAt(pos, col)
        p.setPen(Qt.NoPen); p.setBrush(g)
        p.drawEllipse(c, rc, rc)
        if detail != "small":
            rim = QColor(cols[1]); rim.setAlphaF(0.9 * e)
            pen = QPen(rim, R * 0.012)
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, rc * 1.28, rc * 1.28)

    # a thin outer orbit with one brighter arc: the HUD trace
    if orbit > 0 and detail == "full":
        ro = R * 0.985
        pen = QPen(QColor(255, 255, 255, int(40 * orbit)) if dark else QColor(22, 32, 43, int(30 * orbit)), R * 0.008)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, ro, ro)
        pen2 = QPen(_lerp(ramp, 1.0), R * 0.014)
        pen2.setCapStyle(Qt.RoundCap)
        col = pen2.color(); col.setAlphaF(0.85 * orbit); pen2.setColor(col)
        p.setPen(pen2)
        start = 20.0 + spin * 0.5
        p.drawArc(QRectF(c.x() - ro, c.y() - ro, 2 * ro, 2 * ro), int(start * 16), int(-48 * ease_out(orbit) * 16))
    p.restore()


def icon_image(size: int, ground: bool = True) -> QImage:
    """The app icon: the mark on a rounded deep-ink square (or on transparency)."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    detail = "small" if size <= 32 else "medium" if size <= 64 else "full"
    if ground:
        inset = size * 0.06
        r = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0.0, QColor(GROUND[0])); grad.setColorAt(1.0, QColor(GROUND[1]))
        path = QPainterPath(); path.addRoundedRect(r, r.width() * 0.225, r.width() * 0.225)
        p.fillPath(path, grad)
        p.setPen(QPen(QColor(255, 255, 255, 26), max(size / 256.0, 0.6)))
        p.drawPath(path)
        mr = r.adjusted(r.width() * 0.10, r.height() * 0.10, -r.width() * 0.10, -r.height() * 0.10)
    else:
        mr = QRectF(0, 0, size, size).adjusted(size * 0.04, size * 0.04, -size * 0.04, -size * 0.04)
    draw_mark(p, mr, detail=detail, dark=True)
    p.end()
    return img


def mark_svg(size: int = 512, dark: bool = True) -> str:
    """A hand-written SVG of the mark (no ground), for documents and the web."""
    ramp = RAMP_DARK if dark else RAMP_LIGHT
    R = size / 2.0
    cx = cy = R
    n = 30
    w = R * 0.062
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">',
             "<defs>",
             f'<radialGradient id="core" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{CORE[0]}"/>'
             f'<stop offset="0.45" stop-color="{"#C8FBF1" if dark else "#9FE9DA"}"/><stop offset="1" stop-color="{CORE[2] if dark else "#169C8C"}"/></radialGradient>',
             f'<radialGradient id="halo"><stop offset="0" stop-color="{CORE[2]}" stop-opacity="{0.30 if dark else 0.12}"/>'
             f'<stop offset="1" stop-color="{CORE[2]}" stop-opacity="0"/></radialGradient>',
             "</defs>",
             f'<circle cx="{cx}" cy="{cy}" r="{R * 0.62:.2f}" fill="url(#halo)"/>']
    r0 = R * 0.47
    a0, a1 = math.radians(-30), math.radians(-330)
    x0, y0 = cx + r0 * math.cos(a0), cy + r0 * math.sin(a0)
    x1, y1 = cx + r0 * math.cos(a1), cy + r0 * math.sin(a1)
    ring = _lerp(ramp, 0.55).name()
    parts.append(f'<path d="M {x0:.2f} {y0:.2f} A {r0:.2f} {r0:.2f} 0 1 0 {x1:.2f} {y1:.2f}" fill="none" '
                 f'stroke="{ring}" stroke-opacity="{0.55 if dark else 0.45}" stroke-width="{R * 0.018:.2f}" stroke-linecap="round"/>')
    for k, (theta, length) in enumerate(geometry(n)):
        a = math.radians(theta)
        r_in = R * 0.53
        r_out = r_in + R * length
        col = _lerp(ramp, k / (n - 1)).name()
        parts.append(f'<line x1="{cx + r_in * math.cos(a):.2f}" y1="{cy + r_in * math.sin(a):.2f}" '
                     f'x2="{cx + r_out * math.cos(a):.2f}" y2="{cy + r_out * math.sin(a):.2f}" stroke="{col}" '
                     f'stroke-width="{w:.2f}" stroke-linecap="round"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{R * 0.20:.2f}" fill="url(#core)"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{R * 0.256:.2f}" fill="none" stroke="{"#C8FBF1" if dark else "#9FE9DA"}" '
                 f'stroke-opacity="0.9" stroke-width="{R * 0.012:.2f}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def export_assets(out: Path = ASSETS) -> dict:
    """PNG sizes, a Windows .ico, a macOS .icns and SVGs. Needs Pillow for .ico and .icns."""
    out.mkdir(parents=True, exist_ok=True)
    made = {}
    for s in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
        p = out / f"cyclara_{s}.png"
        icon_image(s).save(str(p))
        made[s] = p
    (out / "cyclara_mark_dark.svg").write_text(mark_svg(512, dark=True), encoding="utf-8")
    (out / "cyclara_mark_light.svg").write_text(mark_svg(512, dark=False), encoding="utf-8")
    icon_image(1024, ground=False).save(str(out / "cyclara_mark_1024.png"))
    try:
        from PIL import Image
        imgs = [Image.open(made[s]).convert("RGBA") for s in (16, 24, 32, 48, 64, 128, 256)]
        imgs[-1].save(out / "cyclara.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)],
                      append_images=imgs[:-1])
        Image.open(made[1024]).convert("RGBA").save(out / "cyclara.icns")
    except Exception as exc:                                    # icons stay optional
        print("icon export skipped:", exc)
    return made


if __name__ == "__main__":
    import os
    import sys
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication(sys.argv)
    print(export_assets(Path(sys.argv[1]) if len(sys.argv) > 1 else ASSETS))
