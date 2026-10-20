"""What differs between Windows, macOS and Linux, in one place.

- Type size. Qt counts points at the platform's logical resolution: 96 per inch
  on Windows and most Linux desktops, 72 on macOS. The same 9.5 pt is 12.7 px
  on Windows and 9.5 px on a Mac, a quarter smaller than the rest of macOS.
  font_scale() makes the app's type the same physical size everywhere.
- Motion. The operating system's own "reduce motion" setting is honoured
  (Windows client-area animations, macOS Reduce motion, GNOME animations), and
  the app has its own switch on top.
- Title bar. With Qt 6.8 or later the window frame follows the app's theme on
  Windows 11 and macOS, so a dark app does not sit in a white frame.
- Taskbar. On Windows the process gets its own AppUserModelID, so the taskbar
  shows the Cyclara icon instead of Python's.
- Log. A window program (pythonw.exe, the installed Cyclara.exe, a macOS app
  bundle) has no console, so Python gives it no sys.stdout or sys.stderr and a
  traceback would vanish. keep_a_log() sends both, and faulthandler, to a file
  in the user's own folder: LOCALAPPDATA/Cyclara/cyclara.log on Windows,
  ~/Library/Logs/Cyclara/cyclara.log on macOS, ~/.local/state/cyclara on Linux.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")


def log_path() -> Path:
    """Where a windowed Cyclara writes what it would otherwise print."""
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Cyclara"
    elif IS_MAC:
        base = Path.home() / "Library" / "Logs" / "Cyclara"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "cyclara"
    return base / "cyclara.log"


def keep_a_log(argv) -> Path | None:
    """When there is no console, send stdout, stderr and faulthandler to the log file; otherwise do
    nothing. Returns the file in use, or None. The file is started afresh past a megabyte so it
    never grows without bound. Failure to open it is not an error: the app runs without a log."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 1_000_000:
            path.unlink()
        fh = open(path, "a", encoding="utf-8", errors="backslashreplace", buffering=1)
    except OSError:
        return None
    import datetime
    import faulthandler
    fh.write(f"\n---- Cyclara started {datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {sys.executable}  "
             f"{' '.join(map(str, argv[1:]))}\n")
    if sys.stdout is None:
        sys.stdout = fh
    if sys.stderr is None:
        sys.stderr = fh
    try:
        faulthandler.enable(file=fh)                 # a crash inside Qt or numpy leaves a trace too
    except Exception:
        pass
    return path


def font_scale() -> float:
    """4/3 on macOS's own screens (72 points per inch), 1 elsewhere. The offscreen platform (the self-tests,
    the screenshot script) counts 96 per inch on every system, so it is not scaled there either: a Mac then
    lays the window out exactly as the tests expect."""
    return 96.0 / 72.0 if IS_MAC and not _offscreen() else 1.0


def _offscreen() -> bool:
    import os
    try:
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.instance() is not None:
            return QGuiApplication.platformName() == "offscreen"
    except Exception:
        pass
    return os.environ.get("QT_QPA_PLATFORM", "") == "offscreen"


def set_app_id(app_id: str) -> None:
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def system_reduces_motion() -> bool:
    """True when the operating system asks applications to reduce animation."""
    try:
        if IS_WINDOWS:
            import ctypes
            SPI_GETCLIENTAREAANIMATION = 0x1042
            on = ctypes.c_int(1)
            ok = ctypes.windll.user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(on), 0)
            return bool(ok) and not bool(on.value)
        if IS_MAC:
            out = subprocess.run(["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                                 capture_output=True, text=True, timeout=2)
            return out.stdout.strip() == "1"
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"],
                             capture_output=True, text=True, timeout=2)
        return out.stdout.strip() == "false"
    except Exception:
        return False


def apply_color_scheme(dark: bool) -> None:
    """Ask Qt (6.8 or later) to draw the native window frame in the app's scheme."""
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    except Exception:
        pass


def system_prefers_dark() -> bool:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def shortcut_text(seq) -> str:
    """'Ctrl+K' as the platform writes it: Ctrl+K on Windows, the command-key glyph on macOS."""
    from PySide6.QtGui import QKeySequence
    return QKeySequence(seq).toString(QKeySequence.NativeText)
