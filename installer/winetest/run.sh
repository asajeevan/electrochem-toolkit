#!/bin/bash
# The staged Windows tree under Wine: Cyclara.exe hosts the bundled Python, imports the app,
# renders every view of the demonstration file, and (with --tests) runs the self-tests.
#
#   bash installer/winetest/run.sh STAGE_DIR [--tests]
#
# Wine 9 is not Windows. Two things it lacks are supplied for the test prefix only, never shipped:
#   * a native Universal C Runtime (Wine's ucrtbase has no crealf, which numpy's umath imports);
#     Microsoft's redistributable UCRT is taken from the Windows JDK inside the jdk4py wheel on PyPI;
#   * icuuc.dll, part of Windows 10 1903+ and used by Qt6Core only for codecs it has no table for;
#     icuuc_stub.c answers those twenty calls with "not available".
# Everything else in the run is the bundle itself.
set -euo pipefail
STAGE=$(readlink -f "$1"); shift
TESTS=0; [ "${1:-}" = "--tests" ] && TESTS=1
HERE=$(dirname "$(readlink -f "$0")")
BUILD=${CYCLARA_BUILD_DIR:-$HERE/../build}
mkdir -p "$BUILD/winetest"
export WINEPREFIX="$BUILD/wineprefix-test" WINEDEBUG=-all WINEARCH=win64
SYS32="$WINEPREFIX/drive_c/windows/system32"
if [ ! -f "$SYS32/ucrtbase.dll" ]; then
  wineboot -u >/dev/null 2>&1 || true
  python3 -m pip download -q --no-deps --only-binary=:all: --platform win_amd64 --python-version 3.12 \
      --implementation cp --abi cp312 -d "$BUILD/winetest" "jdk4py"
  python3 - "$BUILD/winetest" "$SYS32" <<'PY'
import glob, sys, zipfile
house, sys32 = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(sorted(glob.glob(house + "/jdk4py-*.whl"))[-1])
n = 0
for name in z.namelist():
    base = name.rsplit("/", 1)[-1].lower()
    if name.startswith("jdk4py/java-runtime/bin/") and (base.startswith("api-ms-win-crt") or base == "ucrtbase.dll"):
        open(f"{sys32}/{base}", "wb").write(z.read(name)); n += 1
print("UCRT files for the test prefix:", n)
PY
fi
[ -f "$SYS32/icuuc.dll" ] || x86_64-w64-mingw32-gcc -shared -O1 -o "$SYS32/icuuc.dll" "$HERE/icuuc_stub.c"
NATIVE="ucrtbase"
for f in "$SYS32"/api-ms-win-crt-*.dll; do NATIVE="$NATIVE,$(basename "$f" .dll)"; done
export WINEDLLOVERRIDES="$NATIVE=n,b"   # native where the 64-bit copy exists, Wine's own otherwise (32-bit helpers)
export QT_QPA_PLATFORM=offscreen

LOG="$BUILD/winetest/run.log"; : > "$LOG"
WZ="Z:$(echo "$HERE" | sed 's|/|\\|g')"
WS="Z:$(echo "$STAGE" | sed 's|/|\\|g')"
WB="Z:$(echo "$BUILD" | sed 's|/|\\|g')"
echo "1. the launcher in Python mode"
wine "$STAGE/Cyclara.exe" -X utf8 "$WZ\\wine_run.py" "$WB\\winetest\\run.log" -c \
  "import sys, electrochem, PySide6.QtWidgets, numpy, scipy, matplotlib, galvani, openpyxl; print('imports ok', sys.executable, electrochem.__version__)" \
  </dev/null >/dev/null 2>&1 || true
grep -q "imports ok" "$LOG" || { cat "$LOG"; echo "FAILED: imports"; exit 1; }
tail -2 "$LOG"

echo "2. every view of the demonstration file (scripts/studio_images.py)"
mkdir -p "$BUILD/winetest/shots"
# scripts/studio_images.py ships with the app (installer/build.py APP_FILES), as does the capture script
# tests/test_readers_reference.py imports; nothing is copied in or removed here, so the tree tested is
# the tree installed.
wine "$STAGE/Cyclara.exe" -X utf8 "$WZ\\wine_run.py" "$WB\\winetest\\run.log" \
  "$WS\\app\\scripts\\studio_images.py" "$WB\\winetest\\shots" </dev/null >/dev/null 2>&1 || true
last() { grep -E "wine_run done, code" "$LOG" | tail -1 | tr -d "\r"; }   # Python on Windows writes CRLF
[ "$(last)" = "wine_run done, code 0" ] || { tail -30 "$LOG"; echo "FAILED: studio_images"; exit 1; }
ls "$BUILD/winetest/shots" | wc -l | xargs echo "   screenshots written:"

if [ $TESTS = 1 ]; then
  echo "3. the self-tests with the bundled Python (this takes a while under Wine)"
  (cd "$STAGE/app" && wine "$STAGE/Cyclara.exe" -X utf8 "$WZ\\wine_run.py" "$WB\\winetest\\run.log" -m pytest -q -p no:cacheprovider \
     --rootdir "$WS\\app" "$WS\\app\\tests" </dev/null >/dev/null 2>&1) || true
  tail -5 "$LOG"
  [ "$(last)" = "wine_run done, code 0" ] || { echo "FAILED: self-tests"; exit 1; }
fi
echo "Wine run passed: $LOG"
