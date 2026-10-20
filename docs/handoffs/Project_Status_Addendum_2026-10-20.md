# Project status addendum, 2026-10-20: Cyclara 0.7.0, other cyclers and one-click installers

Supersedes the 2026-10-19 Cyclara addendum for the items below; everything else in it stands.
Repository revision 0.7.0.

## What was asked

"Are you sure this app works for every cycler? If not, make sure it works and code for that.
The installation must be very simple, like installing VLC or Adobe: a simple click. Research
it, implement it, and make the installation window look cool."

## What is true now

**Other cyclers (P08, P08d).** Cyclara reads BioLogic EC-Lab files on the validated path,
unchanged, and every other cycler's text or spreadsheet export through `electrochem/readers/`:
a typed import profile whose four conventions (current sign, direction source, capacity
semantics, cycle base) have no defaults and need a line of evidence; a generic reader that
collects every finding before refusing (45 named failure modes), measures the capacity
semantics on the file and compares the instrument's own counter with the integral of the
current, charge and discharge separately; a proposer that maps an unknown header; a registry
that remembers a confirmed instrument by its header fingerprint; and the import review page
in the window. 16 built-in profiles exist, each checked against a named real export file:
Arbin (Excel, MITS 8 CSV, `.res` table CSV, underscore CSV), Maccor (Test (Sec), Test (Min),
clock, 12-line header, signed), Neware (Excel, flat CSV), BaSyTec, Novonix, PEC (two
dialects), Landt. 21 real instrument files (Apache, BSD and MIT sources, with attribution and
manifests) are in `data/public/<vendor>/` and 120 tests re-check each one independently of
the reader. The three profiles written before any real file was seen were wrong in ways only
a real file shows (Arbin counters reset per cycle; Maccor's 12-line-header `TestTime` is in
minutes; the Neware Excel record sheet has signed current and a time cell) and are
corrected. Binary formats other than `.mpr` (`.res`, `.nda`, `.ndax`) are refused with an
instruction to export text. The exact claim, per dialect and with what was verified, is
`docs/P08d_Instrument_Compatibility_Matrix.md`. The honest summary: *any cycler's text or
spreadsheet export can be analysed; the dialects listed as verified are recognised
automatically; any other instrument is learned from one file through the review page.*

**Export variants (P08e, later the same day).** Arbin's MITS, LANDdt and the others let the user
choose, at export time, which columns to write, their order, their units and the sheet name, so
two exports of one test rarely share a header. Recognition now rests on the time, current and
voltage columns alone (units aside: the header's unit is read, never frozen); extra, absent and
reordered columns do not matter; workbooks are read by content, not sheet name; a learned
profile claims later exports by the same rule; a renamed required column reopens the review page
pre-filled from the saved profile; and a workbook whose same-header sheets restart the clock
(several channels in one file) is refused rather than merged into one cell. Verified on
re-exports of the shipped Arbin and Landt files (13 tests in `tests/test_readers_variants.py`,
one in `tests/test_review_fixes.py`); the matrix's section 8 states the rules.

**Origin output for every cycler.** The Origin folder is made from the engine's results, so an
Arbin, Neware or Landt file gets the same tables, graph specification and build script as an
EC-Lab file (tested on the shipped Arbin file). For the installed app, Help > Set up the Origin
link installs OriginLab's originpro bridge into Cyclara's own Python once; the export message then
offers Build Origin project, or the set-up when the bridge is missing.

**Installation (P13, part).** `Cyclara-0.7.0-Setup.exe` for Windows 10 (1903+) and 11,
64-bit: Next, Install, Finish; per user, no administrator password; Start menu and Desktop
icons; "Open with" for cycling files without taking a default; uninstaller in Apps &
features; replaces an older Cyclara. `Cyclara-0.7.0-macOS-AppleSilicon.zip` and `-Intel.zip`
for macOS 14 or later: drag `Cyclara.app` to Applications. Each carries its own CPython
3.12.15 and every package; nothing is installed first. The installer pages are drawn from the
app's own mark. Neither is code-signed: SmartScreen's "Run anyway" and Gatekeeper's "Open
Anyway" are documented one-time steps. `installer/build.py` rebuilds all three from Linux or
macOS; `installer/README.md` and `docs/handoffs/P13_Installers_Handoff.md` record the layout,
the decisions and the checks.

**In the app.** Help > Check this installation runs the shipped self-tests with the installed
interpreter and reports the outcome in words; Help > Open the demonstration file and a *Try
the demonstration* button; a windowed launch keeps a log file (Help > Show the error log);
folders open every measurement and leave notes and logs alone; the home page and About say
what the app reads now.

## Evidence

- Linux suite (Python 3.13, offscreen Qt): **498 passed, 2 skipped**, 56 subtests, 4 min 55 s;
  the 268 reference checks pass.
- The Windows build under Wine 9, the real `Cyclara.exe` hosting the real Windows CPython and
  win_amd64 wheels: imports; every view of the demonstration file and the public formation
  file rendered through the whole app; the whole suite run by the bundled interpreter:
  **493 passed, 3 skipped** (the installer-source tests are not shipped), 7 min 51 s.
- The installer under 32-bit Wine: silent install in under a minute, the installed tree
  byte-identical to the staged one (6 458 files hashed), shortcuts and registry keys present,
  `Uninstall.exe` removes everything it wrote; the four pages photographed under Xvfb
  (`docs/evidence/p13_installers/`).
- Static checks on every build: runtime checksums against the release's SHA256SUMS, the
  private-data scan, PE import closure (every DLL and .pyd), Mach-O load closure (every
  dylib and framework, after thinning the universal binaries), the pure-Python toolkit
  imported under a real CPython 3.12.
- Real cycler files: see the matrix; the independent checks are physical (elapsed time
  against the wall clock written in the same file, voltage rising under charge-positive
  current, the instrument counter against the trapezoidal integral, Landt's own Cycle sheet
  within 1.6 %).

## Not verified

A Windows PC or a Mac in person: the installer's pages at a real DPI, SmartScreen, the
Gatekeeper dialogue, the Dock attribution (expected to read Cyclara, since the interpreter
sits inside `Contents/MacOS`), the Intel build at all; Origin from an installed copy (needs
`originpro` installed into the bundled Python). Arbin underscore CSV with cycling data,
multi-sheet workbooks, Neware Chinese-locale headers, discharge in the BaSyTec and Novonix
files, every binary format, and any instrument not in the matrix.

## Decisions

Embed the interpreter in `Cyclara.exe` (taskbar, pinned shortcuts and Task Manager are
Cyclara's); isolated interpreter (`-I -X utf8`); per-user install; Qt pruned to the widgets
stack, with an import-closure check; byte-code written at build time; macOS interpreter in
`Contents/MacOS`; macOS 14 floor (the wheels); universal binaries thinned; unsigned for now.
P08d: a capacity declaration is accepted when the file does not contradict it and reported
verified only when the file leaves no other behaviour open; Arbin profiles are cycle-
cumulative; Maccor keeps sign detection; no binary reader until pandas (NewareNDA) or polars
(fastnda) is decided; the Landt workbook ships whole for its Cycle sheet.

## Delivered

Sent to the chat: `Cyclara-0.7.0-Setup.exe` (102 MB), `Cyclara-0.7.0-macOS-AppleSilicon.zip`
(144 MB), `Cyclara-0.7.0-macOS-Intel.zip` (150 MB), `Cyclara_v0.7.0.zip` (the source folder,
18 MB, 307 files, private-data scan clean) and the handout. The PC was not connected to the
session at the end of the work, so nothing was written to E: this time; the same files are
staged for that.

## Next

Install from the installers on a Windows PC and a Mac and open real files from the cyclers
available; note what is confusing or missing, SmartScreen and Gatekeeper included. Finish the
compatibility matrix with multi-cycle Arbin CSV and multi-sheet workbooks (the Zenodo corpus
in P08 section 7). Decide on pandas or polars for Neware binaries. Then batch mode and
impedance.
