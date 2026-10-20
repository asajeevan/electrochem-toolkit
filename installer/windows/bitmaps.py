"""The two pictures the Windows installer shows, drawn from the same mark as the app.

    python installer/windows/bitmaps.py OUT_DIR        (version from electrochem.__version__)

NSIS's Modern UI takes a 164 x 314 bitmap for the Welcome and Finish pages and a
150 x 57 bitmap for the header of every other page, both as 24-bit .bmp files.
The dialog scales them with the display, so they are drawn at 2x and reduced with
smooth filtering, which keeps the thin bars of the mark clean.

Welcome: the deep-ink ground of the app icon, the mark large with its glow, the
name beneath and the tagline under that. Header: the mark small on white, so it
sits in the white header band of the other pages. Nothing is hand-placed that the
app does not already own: colours and geometry come from electrochem.studio.brand.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter

from electrochem.studio import brand, theme

WELCOME = (164, 314)
HEADER = (150, 57)
SCALE = 2


def welcome(version: str) -> QImage:
    w, h = WELCOME[0] * SCALE, WELCOME[1] * SCALE
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(0, 0, 0, h)
    grad.setColorAt(0.0, QColor(brand.GROUND[0]))
    grad.setColorAt(1.0, QColor(brand.GROUND[1]))
    p.fillRect(0, 0, w, h, grad)
    # a faint sweep of the cycle ramp low on the panel, the HUD trace of the launch screen
    sweep = QLinearGradient(0, h * 0.55, 0, h)
    c0 = QColor(brand.RAMP_DARK[3]); c0.setAlphaF(0.0)
    c1 = QColor(brand.RAMP_DARK[3]); c1.setAlphaF(0.10)
    sweep.setColorAt(0.0, c0); sweep.setColorAt(1.0, c1)
    p.fillRect(0, int(h * 0.55), w, h, sweep)
    side = w * 0.72
    brand.draw_mark(p, QRectF((w - side) / 2, h * 0.14, side, side), detail="full", dark=True)
    p.setPen(QColor("#F2F5FA"))
    f = QFont(theme.FAMILY if hasattr(theme, "FAMILY") else "Segoe UI")
    f.setPointSizeF(15.5 * SCALE); f.setWeight(QFont.DemiBold); f.setLetterSpacing(QFont.PercentageSpacing, 104)
    p.setFont(f)
    p.drawText(QRectF(0, h * 0.56, w, h * 0.10), Qt.AlignHCenter | Qt.AlignVCenter, brand.APP_NAME)
    f2 = QFont(f); f2.setPointSizeF(7.4 * SCALE); f2.setWeight(QFont.Normal); f2.setLetterSpacing(QFont.PercentageSpacing, 100)
    p.setFont(f2); p.setPen(QColor("#9FB0C8"))
    p.drawText(QRectF(0, h * 0.65, w, h * 0.06), Qt.AlignHCenter | Qt.AlignVCenter, brand.TAGLINE)
    f3 = QFont(f2); f3.setPointSizeF(6.6 * SCALE)
    p.setFont(f3); p.setPen(QColor("#5F6F88"))
    p.drawText(QRectF(0, h * 0.90, w, h * 0.06), Qt.AlignHCenter | Qt.AlignVCenter, f"Version {version}")
    p.end()
    return img.scaled(WELCOME[0], WELCOME[1], Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def header() -> QImage:
    w, h = HEADER[0] * SCALE, HEADER[1] * SCALE
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    side = h * 0.78
    brand.draw_mark(p, QRectF(w - side - h * 0.18, (h - side) / 2, side, side), detail="medium", dark=False, glow=0.0)
    p.end()
    return img.scaled(HEADER[0], HEADER[1], Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def main(out: Path, version: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    theme.load_fonts()
    made = {}
    for name, img in (("welcome.bmp", welcome(version)), ("header.bmp", header())):
        rgb = img.convertToFormat(QImage.Format_RGB888)            # 24-bit, no alpha: what NSIS expects
        path = out / name
        if not rgb.save(str(path), "BMP"):
            raise SystemExit(f"could not write {path}")
        made[name] = path
    return made


if __name__ == "__main__":
    QGuiApplication(sys.argv)
    from electrochem import __version__
    print(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "installer" / "windows" / "generated", __version__))
