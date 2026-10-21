# Evidence for the 0.9.1 installers

The files here belong to the released build of 0.9.1 (21 October 2026), the one attached to the GitHub release.
`build_windows.log` and `build_macos.log` are the build's own log (pip command lines shortened); `wine_run_summary.txt`
is the Windows program run under Wine; `install_check.txt` the install check; `*.sha256` and `SHA256SUMS.txt` are the
checksums of the files delivered. Earlier versions' evidence: `../0.9.0/`, 0.8.0's one level up, 0.7.0's in `../0.7.0/`.

## Before the build

Five independent reviews of the new code and of what the release says about it, each by an agent that had written
neither the code nor the fixes before it. The first found 18 points (a restart going back 0 s accepted, pauses folding the
potential like stops, a restart in the reference cycle removing every retention unannounced, a valid short step
refused, pauses without a continuity check, and wording that claimed more checking than the code did). The second
found 11 in the fixes (an export that stopped at the 3D figure when no branch had a dQ/dE curve, a peak whose partner
branch had no curve reported as having no partner branch, a pause or restart in a constant-voltage hold removing a
curve, a short rest with an event refused, the energy counter unchecked at a restart, and wording). The third found
11 in those fixes (the methods paragraph silent on an interruption inside a constant-voltage hold, the reader's
messages not yet following the hold rule, a stale note in the dQ/dE view, and wording), and the fourth 12 in its
fixes (the methods paragraph contradicting itself for a branch paused in its curve and restarted in its hold, the
same stale note in the Evolution view, and wording). The fifth found nothing that blocked the release but 7 points
in those fixes (an edge case of the restart warning, untested note clearings in the views, and wording), and one
outside them (the waterfall note's axis symbol). All are fixed in the source commit
(`docs/handoffs/Project_Status_Addendum_2026-10-21b.md`).

## The builds that were not released

A first build was made from commit 1dc61ee, with the second review's fixes. It passed the whole suite on a clean
checkout (1049 passed, 2 skipped, 56 subtests, 8 min 2 s), the Windows program passed its own suite under Wine (1028
passed, 18 skipped, 56 subtests, 12 min 2 s), and it installed over 0.9.0 cleanly. A second was made from commit
63fac22, with the third review's fixes: 1051 passed, 2 skipped, 56 subtests on the clean checkout (8 min 1 s), 1030
passed, 18 skipped, 56 subtests under Wine (10 min 28 s), a clean install over 0.9.0. A third, from commit 5f93a7c,
passed the suite on its clean checkout (1057 passed, 2 skipped, 56 subtests) and was stopped during its Wine run. The
next review's findings changed the code each time, so all three builds were discarded; their installers were never
delivered.

## The released build

From a clean checkout of commit 668b3ad, the source of the program. The tag `v0.9.1` is on the next commit, which
adds only this folder, the checksums and test paragraph in the release notes and other documentation under `docs/`,
none of which is inside the installers.

- **Suite on Linux** (Python 3.13, offscreen Qt), on that checkout: 1067 passed, 2 skipped, 56 subtests (8 min 39 s).
- **Windows build.** CPython 3.12.15 (python-build-standalone 20261013, checksum verified), the pinned win_amd64
  wheels and the toolkit; byte-code compiled; the pure-Python import passes under a real CPython 3.12.15; 259 Windows
  binaries, every import resolved inside the tree or Windows. The installer: `Cyclara-0.9.1-Setup.exe`, 105 464 554
  bytes.
- **Under Wine 9** (`installer/winetest/run.sh STAGE --tests`): the launcher in Python mode imported every package
  (`imports ok ... 0.9.1`); `scripts/studio_images.py` rendered every view of the demonstration file (27
  pictures); the self-tests, run by the bundled Windows interpreter: 1046 passed, 18 skipped, 56 subtests (13 min
  11 s). The 18 skipped are the release tool's 15 tests and the installer's test module (neither ships with the app;
  16 skips in all) and the 2 that skip on Linux too.
- **Install check** (32-bit Wine, `/S`): the released 0.9.0 installed first (10 813 files), then 0.9.1 over it in
  38 s; the installed tree equals the staged tree as built, file for file and byte for byte (10 814 files; the 32
  pytest caches the self-tests wrote into the stage afterwards left out of the comparison), plus `Uninstall.exe`; no
  file of 0.9.0 left behind; Start menu and Desktop shortcuts, the uninstall key (DisplayVersion 0.9.1) and "Open
  with" for .mpr, .mpt, .cex, .csv, .txt and .xlsx present; `Uninstall.exe /S` removed the folder, both shortcuts,
  the uninstall key and the two "Open with" entries checked (.mpr and .cex). `install_check.txt`; the checkout's
  path is written `/build/checkout-668b3ad` in the build logs and the Wine summary.
- **macOS bundles.** `Cyclara-0.9.1-macOS-AppleSilicon.zip` (147 662 339 bytes) and `Cyclara-0.9.1-macOS-Intel.zip`
  (154 063 452 bytes), each from its own pinned wheels with universal files thinned to one slice (43 and 37 files);
  in each bundle 212 binaries, every library resolving inside the bundle or macOS; the pure-Python import passes
  under a real CPython 3.12.15.
- **Checksums**: `SHA256SUMS.txt` here, identical to the one attached to the release.

Not run: a physical Windows PC or Mac; the macOS bundles are checked statically only (every library resolves inside
the bundle or macOS), not launched.
