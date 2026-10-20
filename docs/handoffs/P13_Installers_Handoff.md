# P13 (part): one-click installers for Windows and macOS

Date: 2026-10-20. Version 0.7.0. Status: **implemented and verified on the build
machine (Linux, with Wine for the Windows build); not yet run on a Windows PC or a
Mac.**

## Deliverable

`installer/` in the repository:

| File | What |
|---|---|
| `build.py` | the whole build, reproducible from Linux or macOS: downloads and checksums the CPython runtime, resolves the pinned wheels for each target platform, stages the tree, prunes, writes 3.12 byte-code, runs the checks, compiles the launcher, builds the NSIS installer and the two macOS bundles |
| `runtime.json`, `requirements-bundle.txt` | the pins: python-build-standalone release 20261013 (CPython 3.12.15) with SHA-256 per archive; every wheel by exact version |
| `windows/launcher.c`, `launcher.rc.in`, `Cyclara.exe.manifest` | `Cyclara.exe`: hosts `python312.dll` in its own process; single-dash first argument means "behave as python.exe" (used by Python's own helper processes), double-dash options and file paths go to the app |
| `windows/cyclara.nsi` | NSIS 3 Modern UI 2: Welcome, folder, installing, finish; per user, no UAC; Start menu and Desktop shortcuts; "Open with" registration without taking a default; uninstaller registered in Apps & features; replaces an earlier Cyclara in the same folder |
| `windows/bitmaps.py` | the Welcome/Finish sidebar and the header, drawn from `electrochem.studio.brand.draw_mark` |
| `macos/Cyclara.sh` | `Cyclara.app/Contents/MacOS/Cyclara`: execs the bundled interpreter (`Contents/MacOS/cyclara-python`) on `electrochem.studio` |
| `winetest/` | the Wine harness: imports, every view of the demonstration file, the self-test suite, with the two things Wine 9 lacks supplied to the test prefix only (its README says what and why) |
| `README.md` | layout of each build, what is verified, signing |

Outputs (`installer/dist/`): `Cyclara-0.7.0-Setup.exe` (102 MB; 429 MB installed),
`Cyclara-0.7.0-macOS-AppleSilicon.zip` (144 MB), `Cyclara-0.7.0-macOS-Intel.zip`
(150 MB), each with a `.sha256` file. Evidence of the build and the checks below:
`docs/evidence/p13_installers/`.

In the app (0.7.0): `platform_support.keep_a_log` (a windowed launch keeps
stdout, stderr and faulthandler in a log file), Help > Show the error log opens
it; Help > Check this installation (`SelfCheck`: the shipped self-tests, run by
the installed interpreter in a separate process, reported in words); Help > Open
the demonstration file and a *Try the demonstration* button; the home page and
About say what the app reads now.

## Verification

| Check | How | Result |
|---|---|---|
| Runtime archives | SHA-256 against the release's `SHA256SUMS` | 4 of 4 match |
| No private data in `app/` | the release zip's marker scan over the staged tree; `tests/test_installer.py` shows it stops the build | pass |
| Windows: every import of every DLL and .pyd resolves in the bundle or in Windows | PE import tables, 256 binaries | pass |
| macOS: every library load resolves inside the bundle or in macOS | Mach-O load commands, 201 (arm64) and 210 (x86_64) binaries; the check caught the first build, which had pruned every Qt framework (the frameworks are `QtCore.framework`, the DLLs `Qt6Core.dll`; a test now covers it) and then the missing QtDBus | pass |
| Pure-Python toolkit under a real 3.12 | the Linux build of the same CPython release imports `electrochem`, `eclab_import`, the readers, the workflow and the CLI with the pinned pure-Python packages | pass |
| The Windows build runs | Wine 9 (`winetest/run.sh`): `Cyclara.exe` hosting the bundled Python imports Qt, numpy, scipy, matplotlib, galvani, openpyxl; `scripts/studio_images.py` opens the demonstration file and the public formation file and renders every view and the figures (21 pictures) | pass |
| The self-tests with the Windows build | the same, `-m pytest` on the shipped `tests/`, the whole suite including the 120 real-file and 13 export-variant reader tests | **493 passed, 3 skipped** (the two usual skips and the installer-source tests, which are not shipped) in 7 min 11 s. A first run had 3 failures, which changed the build: `PySide6.QtTest` is kept, `data/examples` is shipped, and the harness and Help > Check this installation run from the app folder. |
| The installer itself | 32-bit Wine, silent (`/S`): installs in 27 s into `%LOCALAPPDATA%\Programs\Cyclara`; the installed tree is byte-identical to the stage (6 458 files hashed, pyc files included); Start menu and Desktop shortcuts, the uninstall key, the `Open with` registration present; `Uninstall.exe /S` removes the folder, both shortcuts and every key. The runtime DLLs at the root were missing from the first script (`File "${STAGE}\*.dll"` added) and are present in the final build. | pass |
| The installer's pages | run under Xvfb and photographed (`docs/evidence/p13_installers/*.png`): Welcome (sidebar with the mark, name, tagline, version), folder, installing with the installer's own progress lines, finish with *Open Cyclara now* | as designed; the finish text was too long for the page and was shortened, and the installing page showed every extracted file name until `SetDetailsPrint none` |

## Decisions

1. **Embed, do not spawn.** `Cyclara.exe` hosts the interpreter rather than starting `pythonw.exe`, so the window's process is Cyclara's: taskbar, Task Manager, pinned shortcuts. Only `Py_SetPythonHome` and `Py_Main` are used, resolved at run time, so no Windows SDK or Python headers are needed to build it with mingw.
2. **Isolated interpreter** (`-I -X utf8`): a user's `PYTHONPATH`, user site-packages or other Python installations cannot change what Cyclara imports. UTF-8 mode makes Windows behave as the Linux test environment does for text files.
3. **Per-user install, no administrator prompt**, like VS Code's user setup: a researcher on a managed laboratory PC can install it.
4. **Pruned Qt**: the widgets stack and its plugins only; the import-closure check is what makes pruning safe.
5. **Byte-code written at build time** with the Linux build of the same CPython, `unchecked-hash`, so the first launch does not compile a few thousand files.
6. **macOS: the interpreter binary in `Contents/MacOS`**, with the runtime's `lib/` as `Contents/lib`: CPython finds its files relative to the executable, and macOS attributes the process to the bundle.
7. **macOS 14 floor**, set by the PySide6 6.12, numpy 2.3.5 and scipy 1.18 wheels for Apple Silicon.
8. **Universal Qt binaries thinned** to the bundle's architecture (`lipo -thin` in Python); each slice is an independently signed Mach-O image.
9. **Unsigned.** SmartScreen and Gatekeeper prompts are documented as one-time steps; a signing certificate is the only way to remove them.

## Not verified

- A Windows PC: the installer's pages at a real DPI, SmartScreen, the shortcuts' icons, file association behaviour, a second launch with saved settings.
- A Mac at all: Gatekeeper on first launch, the Dock and menu attribution with the interpreter in `Contents/MacOS` (expected to read Cyclara), the Intel build.
- Origin building from an installed copy (`originpro` must be installed into the bundled Python).

## Next

Install on a Windows PC and a Mac, open real files, note what is confusing. Then
sign, if a certificate becomes available. The release zip of the source folder
and `Setup.bat` / `Setup (Mac).command` remain for anyone who wants the code.

## The 0.8.0 build (later the same day)

0.8.0 adds the plateau analysis, the Evolution view, large-file reading and Help > How the numbers are
calculated and Cite Cyclara (`docs/handoffs/Project_Status_Addendum_2026-10-20b.md`). Outputs:
`Cyclara-0.8.0-Setup.exe` (105.3 MB; about 434 MB installed), `Cyclara-0.8.0-macOS-AppleSilicon.zip`
(147.4 MB), `Cyclara-0.8.0-macOS-Intel.zip` (153.8 MB); checksums in `docs/evidence/p13_installers/`.

| Check | Result |
|---|---|
| Static checks of the build (checksums, private-data scan, PE and Mach-O closure, pure-Python import under 3.12) | pass |
| The whole suite with the Windows build under Wine 9 | **920 passed, 3 skipped**, 56 subtests, 12 min 52 s (build A) |
| Upgrade: the morning's 0.7.0 installed silently, then 0.8.0 over it | no file of 0.7.0 left; the installed tree byte-identical to the stage (10 799 files) plus `Uninstall.exe`; DisplayVersion 0.8.0; clean uninstall |
| The installer's pages | photographed under Xvfb, version 0.8.0 on the sidebar and the header (`docs/evidence/p13_installers/*.png`) |
| The delivered build (B) against the tested one (A) | the same 10 799 files; only `STATUS.md`, `docs/U02_Cyclara.md` (A's results written in) and the launcher's PE time stamp and header checksum differ; B run under Wine (imports, every view) and install-checked again |

Changed in the build for 0.8.0: `scripts/studio_images.py` and `scripts/capture_reader_reference.py` ship in
`app/scripts/`, because the shipped tests import the second and the Wine harness renders every view with the
first; the harness no longer copies files into the staged tree or deletes them afterwards, so the tree tested is
the tree installed (a first 0.8.0 build failed the harness because the reader reference test could not find the
capture script). Under Windows the generated test workbooks differ in their XML bytes from those generated under
Linux (Python 3.12 and 3.13 serialise empty elements differently); the reference test now accepts the same cells
with other bytes, with a test of that rule, and the large-file test reads the peak memory on Windows from
`GetProcessMemoryInfo`.

Next for the build: link the launcher with `-Wl,--no-insert-timestamp` so that two builds of the same sources give
the same `Cyclara.exe`.

## Published (20 October 2026)

The release build of 0.8.0 (clean checkout of c7014cc) is published as an immutable GitHub release,
https://github.com/asajeevan/electrochem-toolkit/releases/tag/v0.8.0: tag on 1463d92, the three installers, the
handout and `SHA256SUMS.txt`. `scripts/check_github_release.py` checks a draft against the release folder before it
is published and the release after (immutable, tag commit, GitHub's digest of each file, the signed attestation's
contents); `tests/test_check_github_release.py` gives it the faults it must catch. Its record and output:
`docs/evidence/p13_installers/github_release_v0.8.0*`. The procedure for the next release:
`docs/releases/RELEASING.md`.
