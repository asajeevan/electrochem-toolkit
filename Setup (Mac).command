#!/bin/bash
# One-time setup on macOS: creates the Python environment, installs everything,
# runs the self-tests and builds Cyclara.app in this folder.
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
pause() { read -n 1 -s -r -p "Press any key to close this window."; echo; }
echo "Setting up Cyclara in $HERE"

PY=""
for c in python3.12 python3.11 \
         /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
         /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12; do
  if command -v "$c" >/dev/null 2>&1; then
    v=$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
    if [ "$v" = "3.12" ] || [ "$v" = "3.11" ]; then PY="$c"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.12 was not found."
  echo "Install it from https://www.python.org/downloads/macos/ (the macOS 64-bit universal2 installer), then run this again."
  pause; exit 1
fi
echo "Using $PY"

"$PY" -m venv .venv || { echo "Could not create the Python environment."; pause; exit 1; }
V="$HERE/.venv/bin/python"
"$V" -m pip install --quiet --upgrade pip
echo "Installing packages (this takes a few minutes)..."
"$V" -m pip install --quiet -r requirements.txt || { echo "Installing the analysis packages failed."; pause; exit 1; }
"$V" -m pip install --quiet -r requirements-native.txt \
  || echo "(The .mpr reader was not installed: it needs Git. Run 'xcode-select --install', then this again. .mpt files work without it.)"

# Qt for the window: the newest release that supports this macOS
if ! "$V" -m pip install --quiet -r requirements-gui.txt 2>/dev/null; then
  echo "This macOS is older than 14 (Sonoma): installing an earlier Qt release."
  "$V" -m pip install --quiet "PySide6-Essentials==6.11.0" "shiboken6==6.11.0" "pyqtgraph==0.14.0" "colorama==0.4.6" \
   || "$V" -m pip install --quiet "PySide6-Essentials==6.9.3" "shiboken6==6.9.3" "pyqtgraph==0.14.0" "colorama==0.4.6" \
   || { echo "Qt could not be installed. Cyclara needs macOS 12 (Monterey) or later."; pause; exit 1; }
fi
"$V" -m pip install --quiet pytest

echo "Running the self-tests (about five minutes; each dot is a test that passed)..."
"$V" -m pytest -q -p no:cacheprovider || echo "(Some self-tests failed. Please send the lines above to the author.)"

echo "Building Cyclara.app..."
APP="$HERE/Cyclara.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$HERE/electrochem/studio/assets/cyclara.icns" "$APP/Contents/Resources/cyclara.icns"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Cyclara</string>
  <key>CFBundleDisplayName</key><string>Cyclara</string>
  <key>CFBundleIdentifier</key><string>io.github.asajeevan.cyclara</string>
  <key>CFBundleVersion</key><string>0.8.0</string>
  <key>CFBundleShortVersionString</key><string>0.8.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>Cyclara</string>
  <key>CFBundleIconFile</key><string>cyclara</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSRequiresAquaSystemAppearance</key><false/>
</dict>
</plist>
PLIST
cat > "$APP/Contents/MacOS/Cyclara" <<LAUNCH
#!/bin/bash
cd "$HERE" && exec "$HERE/.venv/bin/python" -m electrochem.studio "\$@"
LAUNCH
chmod +x "$APP/Contents/MacOS/Cyclara"
xattr -dr com.apple.quarantine "$HERE" 2>/dev/null
touch "$APP"

echo
echo "Setup finished."
echo "Double-click Cyclara.app in this folder. To keep it in the Dock, drag it there."
echo "(Keep Cyclara.app in this folder: it starts the environment that lives here.)"
pause
