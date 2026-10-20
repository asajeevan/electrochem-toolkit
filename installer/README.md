# The one-click installers

What a user receives:

| File | For | Size | What it does |
|---|---|---|---|
| `Cyclara-<version>-Setup.exe` | Windows 10 (1903+) and 11, 64-bit | about 105 MB | Welcome, folder, install, open. Per user (`%LOCALAPPDATA%\Programs\Cyclara`), no administrator prompt, Start menu and Desktop shortcuts, "Open with" for .mpr/.mpt/.cex/.csv/.txt/.xlsx without taking any default, an uninstaller in Settings > Apps. Replaces an older Cyclara in the same folder. |
| `Cyclara-<version>-macOS-AppleSilicon.zip` | macOS 14+ on M1 to M4 | about 150 MB | `Cyclara.app`: drag to Applications. |
| `Cyclara-<version>-macOS-Intel.zip` | macOS 14+ on Intel | about 155 MB | the same, for Intel. |

Each carries its own CPython 3.12.15, the pinned scientific packages, Qt, and the
toolkit (`app/`: `electrochem`, `eclab_import`, the demonstration and public
data, the documents, and the self-tests that *Help > Check this installation*
runs). Nothing is downloaded at install time and nothing outside the user's
folder is touched.

## Building

From Linux (as done for the 0.7.0, 0.8.0 and 0.9.0 releases) or macOS:

```sh
python installer/build.py --windows --wine     # Setup.exe, then the Wine run
python installer/build.py --macos              # both .zip bundles
```

Needs: Python 3.10+ with pip, git (to build galvani from its pinned commit),
`x86_64-w64-mingw32-gcc` and `-windres` (package `mingw-w64`), `makensis`
(package `nsis`, 3.x), and for `--wine`, `wine64`. Network: github.com for the
CPython builds, pypi.org for wheels. Output goes to `installer/dist/`; the
working tree to `installer/build/` (or `$CYCLARA_BUILD_DIR`).

What is pinned, and where:

* `runtime.json`: the python-build-standalone release (`20261013`) and the
  SHA-256 of each archive. Verified before extraction.
* `requirements-bundle.txt`: every wheel, by exact version, the same versions
  the test suite runs against (STATUS.md). pip resolves them for the target
  platform (`--platform win_amd64`, `macosx_14_0_arm64`, `macosx_14_0_x86_64`),
  never for the build machine.
* `requirements-native.txt`: galvani's commit, built into a wheel once.

## How the Windows build is put together

```
Cyclara/
  Cyclara.exe          windows/launcher.c: hosts python312.dll in its own process
  LICENSE              msvcp140.dll, vcruntime140.dll ... (from the PySide6 wheel)
  python/              CPython 3.12 (pruned: no tcl/tk, idle, test, .pdb) + site-packages
    Lib/site-packages/cyclara.pth   -> ..\..\..\app
  app/                 the toolkit
  Uninstall.exe
```

`Cyclara.exe` loads `python\python312.dll`, calls `Py_SetPythonHome` on
`python\` and `Py_Main` with `-I -X utf8 -m electrochem.studio <files>`. So the
window, the taskbar button and a pinned shortcut belong to Cyclara.exe, and
Python's own helper processes (the file readers) start the same exe in Python
mode (`Cyclara.exe -I -X utf8 -c ...`): the first argument decides, single-dash
options are Python's, double-dash options (`--no-intro`) are Cyclara's. The
interpreter runs isolated: no `PYTHONPATH`, no user site-packages, so a user's
own Python installation cannot interfere. Byte-code for 3.12 is written at
build time (by the Linux build of the same CPython release), so the first launch
does not compile.

PySide6-Essentials is pruned to the modules a widgets application uses (Core,
Gui, Widgets, Svg, SvgWidgets, OpenGL, OpenGLWidgets, PrintSupport) and their
plugins (platforms, styles, image formats, icon engines). The QML, Quick,
Designer, Help, Sql, Network and tooling parts are dropped; `check_windows_tree`
then parses every remaining DLL and .pyd and refuses to build if any imports a
library that is neither in the bundle nor part of Windows.

The installer is NSIS 3 Modern UI 2 (`windows/cyclara.nsi`), LZMA solid, with
the Welcome/Finish sidebar and the header drawn from the app's own mark
(`windows/bitmaps.py`, which calls `electrochem.studio.brand.draw_mark`).

## How the macOS bundle is put together

```
Cyclara.app/Contents/
  Info.plist           CFBundleExecutable Cyclara, LSMinimumSystemVersion 14.0
  MacOS/Cyclara        a shell script: exec cyclara-python -I -X utf8 -m electrochem.studio "$@"
  MacOS/cyclara-python the CPython 3.12 binary (python-build-standalone, statically linked)
  lib/                 libpython3.12.dylib, python3.12/ (stdlib, lib-dynload, site-packages)
    python3.12/site-packages/cyclara.pth  -> ../../../Resources/app
  Resources/cyclara.icns, Resources/app/
```

The interpreter binary sits in `Contents/MacOS` because that is where CPython
looks for `../lib/python3.12/os.py` to find its own files, and because macOS
attributes a process to the bundle its executable lives in: the Dock, the
application menu and Force Quit then say Cyclara, not python3.12.
`check_macos_tree` parses every Mach-O file's load commands and refuses to
build if a library would be resolved outside the bundle and outside
`/usr/lib` or `/System`.

macOS 14 is the floor because the PySide6 6.12, numpy 2.3.5 and scipy 1.18
wheels for Apple Silicon are built for it.

## What is verified, and what is not

Checked by `build.py` on every build:

1. CPython archive checksums against the release's `SHA256SUMS`.
2. No private data in `app/` (the same marker scan as the release zip).
3. Windows: every DLL and .pyd import resolves (PE import tables).
4. macOS: every dylib load command resolves inside the bundle or macOS.
5. The pure-Python toolkit imports under a real CPython 3.12 (the Linux build
   of the same release), with the same pinned pure-Python packages.
6. With `--wine`: the staged Windows tree under Wine 9, the real Cyclara.exe
   with the real Windows Python and wheels: imports, then every view of the
   demonstration file rendered through `scripts/studio_images.py` (shipped in
   `app/scripts/`, with `capture_reader_reference.py`, which the reader
   reference tests import; the harness tests the tree exactly as installed),
   and with `--tests` the whole self-test suite. `winetest/README.md` explains the two
   things Wine lacks (its UCRT misses a function numpy needs; Windows' own ICU)
   and how the test prefix supplies them. They are not shipped.

Not verified here, because it needs the real operating system: the installer's
own pages and shortcuts on a Windows PC, DPI scaling on a real display, the
first-launch Gatekeeper dialogue and the bundle attribution on a Mac, and the
Intel macOS build at all (no Intel Mac and no emulation). The release notes say
so, and the first run on each system is the remaining acceptance step.

## Signing

Neither installer is code-signed. Windows SmartScreen shows "Windows protected
your PC" for a download without reputation. A signed installer shares its
certificate's reputation from one version to the next, but Microsoft states
that a newly signed file may still be warned about until that reputation
builds, and that EV certificates no longer bypass SmartScreen;
`docs/adr/ADR-006_Distribution.md` compares the certificates open to an
individual developer. macOS Gatekeeper requires an Apple Developer ID (paid)
and notarisation for a silent first launch. The user guide describes the
one-time "Run anyway" and "Open Anyway" steps. With a certificate (a
university's, if one is available): sign `Cyclara.exe` and the installer with
`signtool`, the .app with `codesign`, and submit it with `notarytool`.

## Publishing

The installers are published as immutable GitHub releases; the procedure,
with the check of the draft before it is published, is
`docs/releases/RELEASING.md`.
