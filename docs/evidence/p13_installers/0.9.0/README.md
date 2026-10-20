# Evidence for the 0.9.0 installers

The files here belong to the released build of 0.9.0 (21 October 2026), the one attached to the GitHub release.
`build_windows.log` and `build_macos.log` are the build's own log (pip command lines shortened); `wine_run_summary.txt`
is the Windows program run under Wine; `install_check.txt` the install check; `*.sha256` and `SHA256SUMS.txt` are the
checksums of the files delivered. 0.8.0's evidence is one level up, 0.7.0's in `../0.7.0/`.

## The build that was not released

A first build was made from commit ca01400 the same night. It passed the whole suite on Linux (995 passed, 2 skipped,
56 subtests, 8 min 2 s), the Windows program ran every view of the demonstration file under Wine and passed its own
suite (974 passed, 18 skipped, 56 subtests, 12 min 14 s), and it installed over 0.8.0 cleanly. An independent review
of the release's wording against the code then found a defect (Help failed on a file whose first cycle has a withheld
hysteresis), a method gap (a discharge that ended at once still gave a retention) and several claims larger than the
code; all were fixed in commit 36be5dd (`docs/handoffs/Project_Status_Addendum_2026-10-21.md`) and that build was
discarded. Its installers were never delivered.

## The released build

From a clean checkout of commit 36be5dd, the source of the program. The tag `v0.9.0` is on the next commit, which
adds only this folder, the checksums in the release notes and other documentation under `docs/`, none of which is
inside the installers.

- **Suite on Linux** (Python 3.13, offscreen Qt), on that checkout: 1002 passed, 2 skipped, 56 subtests (7 min 25 s).
- **Windows build.** CPython 3.12.15 (python-build-standalone 20261013, checksum verified), the pinned win_amd64 wheels and the toolkit; byte-code compiled; the pure-Python import passes under a real CPython 3.12.15; 259 Windows binaries, every import resolved inside the tree or Windows. The installer: `Cyclara-0.9.0-Setup.exe`, 105 361 326 bytes.
- **Under Wine 9** (`installer/winetest/run.sh STAGE --tests`): the launcher in Python mode imported every package
  (`imports ok ... 0.9.0`); `scripts/studio_images.py` rendered every view of the demonstration file (27
  pictures); the self-tests, run by the bundled Windows interpreter: 981 passed, 18 skipped, 56 subtests (11 min 34 s). The 18 skipped are the release
  tool's 15 tests and the installer's test module (neither ships with the app; 16 skips in all) and the 2 that skip on
  Linux too.
- **Install check** (32-bit Wine, `/S`): the released 0.8.0 installed first (10 800 files), then 0.9.0 over it in 38 s; the installed tree equals the staged tree as built, file for file and byte for byte (10 812 files; the 31 pytest caches the self-tests wrote into the stage afterwards left out of the comparison), plus `Uninstall.exe`; no file of 0.8.0 left behind; Start menu and Desktop shortcuts, the uninstall key (DisplayVersion 0.9.0) and "Open with" for .mpr, .mpt, .cex, .csv, .txt and .xlsx present; `Uninstall.exe /S` removed the folder, both shortcuts, the uninstall key and the "Open with" entries. `install_check.txt`; the scratch folder's path is written `<scratch>` there, and the checkout's path `/build/checkout-36be5dd` in the build logs.
- **macOS bundles.** `Cyclara-0.9.0-macOS-AppleSilicon.zip` (147 517 492 bytes) and `Cyclara-0.9.0-macOS-Intel.zip` (153 918 600 bytes), each from its own pinned wheels with universal files thinned to one slice; in each bundle 212 binaries, every library resolving inside the bundle or macOS; the pure-Python import passes under a real CPython 3.12.15.
- **Checksums**: `SHA256SUMS.txt` here, identical to the one attached to the release.

Not run: a physical Windows PC or Mac; the macOS bundles are checked statically only (every library resolves inside
the bundle or macOS), not launched.
