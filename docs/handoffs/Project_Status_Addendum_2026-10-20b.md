# Project status addendum, 2026-10-20 (later the same day): large files, several plateaus, methods and citation

Supersedes the morning's 2026-10-20 addendum for the items below; everything else in it stands.
Repository revision 0.8.0: a new minor version for the features added since the morning's 0.7.0, so that a citation names one build.

## What was asked

"Sometimes Arbin files will be very large; how can you handle such files efficiently, without any
buffering? Include an option for citing the software easily, copy and paste. An information section
within the app explaining simply and in detail how each calculation is done. What happens with three
or four reversible plateaus and two or three irreversible ones: how is each mean potential calculated,
how are irreversible peaks reported, and are advanced 3D plots possible?"

## What is true now

**Large files (P08f, implemented and tested).** Measured before anything was changed: a 1 000 000-row
EC-Lab export took 33 s and 2.1 GB to open; a 2 000 000-row table took 8.1 s to segment; the generic
reader for other cyclers held every token of the file at once (3.9 GB for a 2 000 000-row Arbin CSV)
and refused files over 512 MiB. Now: EC-Lab text and `.mpr` files go through numpy fast paths that
reproduce the strict P03 importers bit for bit on every public file and on the author's own files, and
step aside for anything unusual (the 1 000 000-row export: 2.7 s, about 0.5 GB); segmentation is
vectorised with the row-by-row rules kept as the test's reference (2 000 000 rows: 0.17 s); the readers
for other cyclers stream text in 4 MiB blocks and workbooks sheet by sheet, keep only the bound columns
(the 2 000 000-row CSV: 322 MB and 11.7 s; a 1 000 000-row workbook: 257 MB and 107 s, openpyxl's
parsing being the limit), accept up to 2 GiB, and report progress, which the window shows as one line
rewritten in place on the reading screen and in the status bar (in process mode through a manager
queue). A frozen reference of every public file and 299 synthetic cases guards the readers' output
(`tests/test_readers_reference.py`, 344 tests). Found on the way: every file above 100 000 rows raised
an `AttributeError` in the time views (pyqtgraph 0.14 and clip-to-view set before `addItem`); fixed,
with a test. `docs/handoffs/P08f_Large_Files_Handoff.md`; matrix section 9.

**Several plateaus (P14, implemented and tested on a synthetic cell; not experimentally validated).** For
every cycle, each dQ/dE peak gets the capacity under it (valley to valley), its share of the branch,
its partner in the opposite branch of the same cycle (the nearest within `peak_pair_window_mV`, 200 mV
by default) with separation and apparent mid-point, or the status *unpaired: no counterpart within
200 mV in the discharge of the same cycle*, and its presence across cycles (*seen in cycles a-b*,
*first cycle only*, *appears from cycle k*). The branch's average potential stays energy / charge, the
charge-weighted mean potential, which for several plateaus is the capacity-weighted mean of the plateau
potentials; nothing is called reversible or irreversible by the software (a test checks the outputs for
the words). Outputs: `dqde_peaks.csv` for every cycle with 19 new columns, `dqde_pairs.csv`,
`dqde_map.csv`, `summary.json` → `plateaus`, `fig6_dqde_map` (colour map, charge and discharge),
`fig7_dqde_surface` (two 3D panels), the Evolution view (map with readout, or waterfall), the
inspector's plateau block for the focused cycle, `--peak-pair-window-mv`. The synthetic cell
(`tests/plateau_cell.py`: three reversible plateaus at 60 mV hysteresis, one in the first charge only,
one from cycle 3): peak potentials within half a bin, separations 60.0 mV, capacity under each peak
within 2 % of the plateau capacity, the branch mean within 1.3 µV of ∫E dQ / Q. M01 sections 9 and
10; `docs/handoffs/P14_Plateaus_and_Evolution_Handoff.md`.

**Methods and citation in the app.** Help > *How the numbers are calculated*: twelve topics, each in
plain words and in full (equation, symbols, units, sign convention, what the file must contain, the
settings, when it is not produced, where it appears, the M01 card), with the open file's answers and a
few of its own numbers under each topic, and *Copy a methods paragraph* for a manuscript, ending with
the reference. The texts are tied to the code by `tests/test_methods_text.py` (the thresholds and the
Faraday constant read from the functions that use them; every column named checked against the result
dataclasses; the three-plateau example run through the engine; the multi-plateau lines checked on the
synthetic cell). Help > *Cite Cyclara*: the reference, BibTeX, `CITATION.cff` and a methods sentence,
all generated from one source (`electrochem/citation.py`); the committed `CITATION.cff` must equal the
generated one (a test; `python -m electrochem.citation --write` regenerates it);
`python -m electrochem.analyze --cite`; `settings.json` carries the paragraph and the citation.

**Also changed while finishing.** The Evolution view is wired in (Figures moves to Ctrl+9); the view
switcher keeps nine whole names at 1024 x 600; the keyboard focus follows the selected view (a focus ring
left on the previous view read as a second selection); both panels of figures 6 and 7 share one potential
scale, so a pair lines up; the handout has a page on several plateaus and the 3D figures and its
definition of the average voltage is corrected (charge-weighted, not energy-weighted, as `methods()` also
said); the reader reference test accepts a generated workbook whose bytes differ only because Python 3.12
and 3.13 write XML differently (same cells, checked by a content digest; tested), and the large-file test
measures memory on Windows too; `scripts/studio_images.py` and `scripts/capture_reader_reference.py` ship
with the app because the shipped tests use them, and the Wine harness tests the tree exactly as
installed.

## Evidence

- Linux suite (Python 3.13, offscreen Qt): **925 passed, 2 skipped**, 56 subtests, 7 min 51 s; the 268
  reference checks pass.
- The Windows build under Wine 9, the real `Cyclara.exe` hosting the bundled CPython 3.12.15 and the win_amd64
  wheels: imports, every view of the demonstration file, then the whole suite: **920 passed, 3 skipped**,
  56 subtests, 12 min 52 s (the installer-source tests are not shipped).
- The installer under 32-bit Wine: the morning's 0.7.0 installed silently, then 0.8.0 over it in 38 s; the
  installed tree byte-identical to the stage (10 799 files) with no file of 0.7.0 left, `Uninstall.exe`
  added; shortcuts, the uninstall key (0.8.0) and the Open-with registration present; a clean uninstall; the
  four pages photographed with 0.8.0 on them. The delivered build differs from the one the suite ran on only
  in `STATUS.md`, `docs/U02_Cyclara.md` and the launcher's link time stamp (compared file by file;
  `docs/evidence/p13_installers/README.md`).
- Measurements: in the two handoffs, verbatim.

## Not verified

A real large export from a cycler (none is shipped; the measurements are on synthetic files built from
the shipped ones). Experimental validation of the plateau descriptors (the synthetic cell's answers are
known by construction; a real multi-plateau material has not been run through them). A Windows PC or a
Mac in person, as before.

## Decisions

Peak tables cover every cycle; the capacity under a peak runs valley to valley and its share refers to
the branch capacity outside constant-voltage stages; peaks are followed across cycles by nearest
neighbour within the window; the evolution grid resamples each curve onto bin multiples (a shift of
less than one bin) so `curve()` did not change; the fast paths step aside rather than guess; the strict
importers stay as the reference (`load(fast=False)`); `invalid_layout` is the one deliberate change of
reader behaviour (a layout the old reader silently counted from the end of the file).

## Delivered

Sent to the chat: `Cyclara-0.8.0-Setup.exe` (105 MB), `Cyclara-0.8.0-macOS-AppleSilicon.zip` (147 MB),
`Cyclara-0.8.0-macOS-Intel.zip` (154 MB), `Cyclara_v0.8.0.zip` (the source folder, private-data scan clean)
and the 15-page handout `Cyclara_handout_v0.8.0.pdf`. Checksums: `docs/evidence/p13_installers/*.sha256`.
The PC was not connected to the session, so nothing was written to E:.

## Next

Open a real long Arbin or Neware export (several hundred thousand rows) and a real multi-plateau
material in the app and compare the plateau table with what you read from the curves by hand; install
from the rebuilt installers on a Windows PC and a Mac. Then batch mode and impedance.
