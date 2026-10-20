# U02: Cyclara, the cycling desktop app, and journal-checked figures

Version 0.2 | 19 October 2026 | Package 12 (interface), cycling slice, and package 6 figures | Builds on U01 and ADR-005

Status: **implemented; software-tested offscreen on Linux; reviewed independently, with every finding fixed and covered by a regression test** (sections 8 and 11). Not yet run by a user on Windows or macOS, not tested with a screen reader, no installer (the setup scripts build a shortcut on Windows and an app bundle on macOS).

## 1. Where this starts

The P12a app (U01, ADR-005) built the interface technology, the principles and the CV views on branch `p12-desktop-app`; its notes list cycling views as not built. Its git bundle was not on the computer this work could reach, so this slice was built on the toolkit the author runs (0.5.0, the cycling engine with the tkinter window) using the same stack (PySide6 6.12.0, pyqtgraph 0.14.0), the same tokens, the same rules (U01 sections 2.3, 3, 5, 6) and the same names where they overlap, so the two can be merged. Nothing in P12a was redone or changed.

## 2. Research added to U01

| Question | Source opened | What was taken |
|---|---|---|
| Journal figure rules today | nature.com/documents/nature-final-artwork.pdf; research-figure-guide.nature.com/figures/building-and-exporting-figure-panels | 89, 120, 136, 183 mm; text 5 to 7 pt; panel labels 8 pt bold lowercase; 170 mm maximum height with legend; editable text; no outlined fonts; RGB; avoid red/green and rainbow |
| Elsevier sizes | elsevier.com artwork sizing page | 90, 140, 190 mm; 7 pt text, 6 pt sub- and superscripts. Height and panel-label style are not stated there and are not claimed |
| ACS, RSC | only secondary summaries found | not offered as presets; a custom width is the route |
| How battery-data tools select cycles | docs.ionworks.com/data/visualizing | cycle filter expressions (`0:50, 100:110`, last N), colour by cycle on a colour-blind-safe ramp, retention relative to a reference cycle. Adopted as the cycle strip's expression box |
| Fonts that can ship | Debian fonts-inter copyright (OFL-1.1) | Inter bundled unmodified with OFL.txt; tabular figures (`tnum`) for every number |
| Logical sizes of common screens | Windows display-scaling defaults (125 % on 15-inch 1080p laptops, 150 % on 13 to 14-inch); macOS "looks like" resolutions | a 1920 × 1080 screen at 150 % is 1280 × 720 points, about 1280 × 640 inside a window frame: the window's minimum became 1024 × 600 (section 9) |

## 3. Decisions

1. **One workflow for the app and the command line** (`electrochem/workflow.py`): open_file, analyse_file, figure_builders, export. On the author's long cycling file the command line, rewritten on the workflow layer, writes every table, `summary.json`, `metadata.json` and the Origin folder byte for byte as 0.5.0 did (`settings.json` gains `figure_style` and `figure_checks`).
2. **The figure preview is the export.** Both call `figure_builders` with the same options; the layout is computed once and frozen before letters are placed and before saving.
3. **Figures are saved at their exact width.** No tight bounding box: an 89 mm figure is 89.00 mm in the PDF (252.28 pt).
4. **Every figure is checked after drawing** (`plotting.check_figure`, twelve checks) and the result is stored with it. The checker is itself tested against figures broken on purpose.
5. **A cycle colour ramp chosen by measurement.** Violet, blue, teal: minimum CIELAB distance between neighbouring cycles 13.3 for seven cycles (7.4 for the 0.5 blue ramp) with every step at 3.4:1 or more on white. The dark theme keeps the hue order with raised lightness, so a cycle keeps its identity across themes.
6. **The cycle strip** (overview, legend and selector in one band) drives every view and the cycles in the exported figures; `settings.json` records them. Moving the focus never changes the selection.
7. **Axes that cannot rescale.** pyqtgraph 0.14 keeps an SI-prefix scale computed while the prefix is switched off (section 10); every plot uses `theme.plain_axes()`.
8. **Answers are remembered per file content** (SHA-256), never per path; the restoration is one undoable step, announced, with Keep or Clear.
9. **One capacity basis.** `cycling.capacity_basis` (specific with a mass, areal with only an area, absolute otherwise) chooses the label and the value in every view, table, figure and the Origin script.
10. **The potential column follows the answer.** A half-cell answer uses the working-electrode column (Ewe/V), a full-cell answer the cell voltage (Ecell/V, or Ewe − Ece derived and labelled as such). A file with one potential column is analysed on it either way.
11. **Questions only the researcher can answer**: the charging direction; the cycle order, asked whenever the file starts with a discharge; what the potential column measures; the active-material mass, or "No mass" (capacities then stay in mAh, or per cm² with an area). EC-Lab's empty-field default of 0.001 mg is never offered.
12. The inspector, the readiness pill, undo, the activity log, withheld values with reasons and the keyboard order follow U01.
13. **Files from other cyclers go through the import review page** (`studio/mapping.py`, 0.7.0). An EC-Lab file is recognised by its signature (`readers.is_eclab`) and keeps the validated path; any other text or spreadsheet export is matched against the built-in and saved profiles by its header fingerprint, and a file no profile recognises opens the review page in place of the plots: the first rows in a grid, the proposer's column roles and units (a column with a unit in its name keeps it; one without asks), the conventions no file states about itself (current sign, step-type meanings, what the capacity columns accumulate, cycle base, a line of evidence), then *Check*, which reads the whole file with those settings in the worker and reports the counter-versus-integral agreement; only a passing check with an unchanged profile unlocks *Use these settings*. Saving writes the profile against the header fingerprint, so the next file from that instrument opens straight through, and the reading screen names the profile. The charging-direction question is answered from the profile (the current is charge-positive after import) and the inspector says so, with the profile's evidence. Diagnostics carry every import finding and the agreement figures. Nothing is calculated before the check passes. Because export dialogs change the header from one export to the next (Arbin, Landt: columns ticked, order, units, sheet name), recognition depends only on the time, current and voltage columns, units aside; a learned profile claims later exports by the same rule, and a renamed required column reopens the page pre-filled from the saved profile (`docs/P08d_Instrument_Compatibility_Matrix.md` section 8, `tests/test_readers_variants.py`).
14. **Every number explained in the app, and the citation one click away** (`electrochem/methods_text.py`, `electrochem/citation.py`, `studio/help_dialogs.py`, 0.8.0). Help > *How the numbers are calculated* lists one topic per quantity (branches and pairing; charge and capacity; energy and average potential; mid-capacity potential and hysteresis; efficiency, retention and fade; dQ/dE; peaks, pairs and several plateaus; the dQ/dE evolution map and surface; C-rate and degree of reaction; mass, area and basis; rests; what is not calculated), each in plain words and then in full: equation, symbols, units, sign convention, what the file must contain, the numerical procedure, the settings that change it, when it is not produced, where it appears in the tables, and the M01 card. *For this file* substitutes the open file's answers and a few of its own numbers (the charge path used, the basis, the reference cycle, the fade's fit range, a cycle's average potentials), and follows the answers while the window is open. *Copy a methods paragraph* writes a paragraph for a manuscript from the same settings, ending with the reference. The texts are tied to the code: `tests/test_methods_text.py` reads the prominence threshold, the peak limit and the Faraday constant from the functions that use them, checks every column named against the result dataclasses, and runs the three-plateau example quoted in the text (3.373 V) through `cycling.integrate`. Help > *Cite Cyclara* offers the reference, BibTeX, `CITATION.cff` and a methods sentence, all generated by `electrochem.citation` from `__version__`, `__released__`, the author and the URL; the committed `CITATION.cff` must equal the generated one (a test), `python -m electrochem.citation --write` regenerates it, and `python -m electrochem.analyze --cite` prints it. The About window has a *How to cite* button.
15. **Several plateaus: peaks are paired and tracked, nothing is called irreversible** (`differential.py` P14, `docs/handoffs/P14_Plateaus_and_Evolution_Handoff.md`, M01 sections 9 and 10, 0.8.0). For every cycle, each dQ/dE peak gets the capacity under it (valley to valley on the grid, in the file's basis, with its share of the branch outside constant-voltage stages), its partner in the opposite branch of the same cycle (the nearest within `peak_pair_window_mV`, 200 mV by default, greedy, each peak once) with the separation and an apparent mid-point, or the status *unpaired: no counterpart within 200 mV in the discharge of the same cycle*, and its presence across cycles (*seen in cycles a-b*, *first cycle only*, *appears from cycle k*). The branch's average potential stays energy / charge, the capacity-weighted mean of the plateau potentials; no other mean is formed from peak potentials. The window shows the focused cycle's pairs and unpaired peaks in the inspector in the same words, an Evolution view (every cycle's dQ/dE as a colour map with a readout, or a waterfall) draws the grid of figures 6 and 7 (`fig6_dqde_map`, `fig7_dqde_surface`, two 3D panels), and the twelve figure checks were extended to 3D axes and colour maps. Verified on a synthetic cell with plateaus known by construction (three reversible at 60 mV hysteresis, one in the first charge only, one from cycle 3): peak potentials within half a bin, separations 60.0 mV, the capacity under each peak within 2 % of the plateau capacity, the branch mean within 1.3 µV of ∫E dQ / Q (`tests/test_plateaus.py`, 18 tests; `tests/test_evolution_view.py`, 5; 14 figure tests; the inspector test in `tests/test_studio.py`).
16. **Large files** (P08f, 0.8.0; `docs/handoffs/P08f_Large_Files_Handoff.md`). EC-Lab text and binary files are read through numpy fast paths that reproduce the strict P03 importers bit for bit on every public file and step aside for anything unusual (`table.py`, `tests/test_table_fast_path.py`): a 1 000 000-row export in 2.7 s instead of 33 s and 2.1 GB. Segmentation is vectorised with the row-by-row rules kept as the test's reference (`tests/test_segment_speed.py`): 2 000 000 rows in 0.17 s instead of 8 s. Other cyclers' text and workbook exports are streamed through the generic reader with a progress callback and a 2 GiB limit, checked against a frozen reference of every public file (`tests/fixtures/reader_reference/`, `tests/test_readers_reference.py`, `tests/test_readers_large.py`).

## 4. Changes to scientific code

| Change | Why | Effect |
|---|---|---|
| dQ/dE grid kept inside the measured potential range (`differential.curve`) | the grid ran one step past the last measured potential; the clamped capacity there gave a fabricated dQ/dE near zero, visible as a horizontal line at the upper limit in every charge curve of the author's figure | `dqde_curves.csv` loses that point. Peak potentials are unchanged (to 1e-13 V). **Peak prominences and widths change** where the fabricated point had served as the lowest contour: on the author's file, for the upper charge peaks, prominence fell by up to 1.8 times and width at half prominence by up to 4.5 times. The 0.5 values for those peaks were artefacts; any table built from them should be regenerated |
| Without a step (Ns) column a branch ends wherever the measured current changes sign (`segment._runs`) | a reversal inside one "branch" netted the two charges (review finding 5) | such files now give one branch per direction; a note says how branches were found |
| Potential column chosen by the configuration answer (`table.with_potential`) | three-electrode files were always analysed on the cell voltage (review finding 6) | half-cell answers use Ewe/V |
| One capacity basis (`cycling.capacity_basis`, `cycle_capacity`) | areal labels over mAh values (review finding 2) | values and labels agree everywhere |
| Efficiency axis always contains every point (`plotting.ce_limits`) | points above about 100 % were cut off (review finding 3) | no point is lost; the checker verifies it |
| Superscripts raised to the journal minimum | Matplotlib draws them at 0.7 of the text: 4.9 pt for 7 pt text | Nature 5 pt, Elsevier 6 pt, measured in the checker |
| Axis label order "Potential vs. Li⁺/Li (V)" | quantity, reference, then unit | labels only |
| Type sizes 7 pt maximum; panel letters 8 pt | 0.5 used 7.5 pt axis labels and 9 pt letters, outside Nature's rules | figures only |

Efficiency is still Q_discharge / Q_charge of the same cycle (M01.06), never clipped, whichever branch starts the cycle.

## 5. A finding in the author's data (diagnostic, not interpretation)

A new rule flags a branch whose charge exceeds three times the median of its direction, with its numbers. It fires on the author's long cycling file: the final charge branch runs for days at a small current without reaching the upper potential limit and passes many times the median charge before the data end. The app states the numbers and names no cause. (The values are in the author's own notes, not here: the file is private.)

## 6. Name, mark and motion

**Name.** Cyclara: cycle and clarity. Tagline "Every cycle, clearly." The command-line engine keeps its name, electrochem-toolkit.

**Mark.** A "cycle reactor": thirty radial bars sweep anticlockwise round a glowing core the way a pen writes a C, each a little shorter than the one before, as capacity fades from cycle to cycle, coloured along the app's cycle ramp. It is the cycle strip bent into a ring. One parametric function (`brand.draw_mark`) draws the icons (.ico for Windows, .icns for macOS, PNG and SVG) and every frame of the launch sequence, so they cannot disagree.

**Motion rules** (`motion.py`): theatre at the threshold, calm at the bench. The cinematic moments are the launch, reading a file, the moment every answer is in, an export and the theme switch; the surfaces where numbers are read never move by themselves. Everything is short and can be cut short by a click or a key.

| Moment | What happens | Length |
|---|---|---|
| Launch | the ring traces, the cycles fire, the core lights, the name resolves; drawn inside the window, so it behaves the same on Windows and macOS | 1.5 s; any click or key skips it; View > Motion turns it off |
| Reading a file | the reactor spins while lines type themselves as each real step completes (rows read, columns found, branches segmented, cycles paired), with the elapsed time. Nothing is invented: a line is written only when its step has happened | as long as the reading |
| Page and view changes | cross-fade of a snapshot with a 10-point rise | 0.2 s |
| First results | each curve traces in once | 0.7 s |
| Every answer in | a sweep across the pill and a ring from it | 0.65 s |
| Export done | a ring from the Export button | 0.7 s |
| Theme switch | the old look is held as a picture while the new theme is applied underneath, then a widening circle from the switch, edged in teal, uncovers it; the circle starts at the first frame painted after the restyle and repaints only the band it uncovers | 0.56 s |
| Files dragged over | a scanning frame names what will open; drops are always copies, so a file manager can never delete the source | while dragging |

Reduced motion (the operating system's setting, or View > Motion) replaces movement by quick fades and skips the launch; No motion removes both.

## 7. Windows and macOS

- **Type size.** Qt counts points at 96 per inch on Windows and 72 on macOS; `platform_support.font_scale()` makes the app's type the same physical size on both, including sizes written inline in style sheets (`theme.css`).
- **Menus.** In the system menu bar on macOS, in the top bar on Windows and Linux. Only About and Quit carry menu roles, so nothing moves to the macOS application menu because of its wording. Shortcuts are shown as the platform writes them (Ctrl+K, ⌘K).
- **Window frame and taskbar.** With Qt 6.8 or later the frame follows the app's theme on Windows 11 and macOS; on Windows the process has its own AppUserModelID, so the taskbar shows the Cyclara icon instead of Python's.
- **Setup from the source folder.** `Setup.bat` creates the environment, runs the self-tests and puts Cyclara shortcuts (with the icon) on the Desktop and in the Start menu. `Setup (Mac).command` does the same and builds `Cyclara.app` (macOS 12 or later; an older Qt release is installed automatically below macOS 14).
- **One-click installers (0.7.0).** `installer/build.py` builds `Cyclara-<version>-Setup.exe` (NSIS 3, per user, no administrator prompt, Start menu and Desktop shortcuts, "Open with" registration, uninstaller) and `Cyclara-<version>-macOS-{AppleSilicon,Intel}.zip` (`Cyclara.app`), each carrying a relocatable CPython 3.12.15 (python-build-standalone, checksummed), the pinned wheels for the target platform and the toolkit. On Windows `Cyclara.exe` (`installer/windows/launcher.c`) hosts `python312.dll` in its own process, so the window, the taskbar and a pinned shortcut belong to Cyclara.exe; on macOS the interpreter binary sits in `Contents/MacOS`, so the Dock and the application menu read Cyclara. Both run Python isolated (`-I -X utf8`) and keep a log where a window program would otherwise lose its tracebacks (`platform_support.keep_a_log`; Help > Show the error log opens it). `installer/README.md` has the layout, what each build checks and what cannot be checked without the real operating system. Neither is code-signed: SmartScreen's "Run anyway" and Gatekeeper's "Open Anyway" are documented one-time steps.
- **Help > Check this installation** runs the shipped self-tests with the installed interpreter in a separate process and reports the outcome in words; the same tests the author runs.
- **Reduce motion** is read from the operating system on both (Windows client-area animations, macOS Reduce motion).

## 8. Verification

| What | How | Result |
|---|---|---|
| The whole suite | `pytest tests` offscreen on Linux, Python 3.13 | 171 tests (56 subtests) pass, 2026-10-19; 498 tests (2 skipped) on 2026-10-20 with the readers, the real-file and export-variant checks, the installer, the self-check and the Origin-link tests; **925 passed, 2 skipped** later on 2026-10-20 with the plateau, evolution, reader-reference, large-file, fast-path, segmentation, methods-text and citation tests (7 min 51 s); the 268 P02 reference checks pass |
| Review fixes | one regression test per finding (section 11); a separate agent's mutation check: 78 of 88 mutants caught, the 10 survivors were parts no test looked at; tests strengthened, and 9 of those 10 are now caught (a drop over a plot cannot be observed offscreen) | all pass |
| Synthetic file with a known answer | `data/demo/cyclara_demo_synthetic.mpt` (50 cycles, CC-CV charge, rests; each step's last point at its limit, as an instrument records it) against the per-cycle sums written by its generator | charge, discharge and efficiency agree to 1e-9 relative; every interval integrated |
| Figures | every figure for six configurations (CB5 with mass; CB5 areal; CB5 discharge-first; the synthetic file with and without mass; the author's file) in both journals: 72 figures | all twelve checks pass, no warnings |
| Small windows | every view at 1024 × 600, 1280 × 640 and 1480 × 920: whole view-button names, no overlap in the top bar, every axis title within its axis, no widget squeezed below its minimum width; screenshots reviewed at those sizes and at 1920 × 1010 | pass |
| Theme switch | timed with a file open: the circle starts after the restyle and finishes 0.56 s later; no overlay with motion off | pass |
| Speed | a theme switch re-polished every window the tests had left alive (181 s in one test): test windows are now deleted, and the app no longer re-sets its style on each switch | the GUI tests run in about 4 minutes instead of 7 |
| The Windows build | the staged tree under Wine 9: the real `Cyclara.exe`, the real Windows CPython 3.12.15 and the real win_amd64 wheels; imports, then `scripts/studio_images.py` renders every view of the demonstration file through the whole app, then the whole test suite with the bundled interpreter: 493 passed, 3 skipped for 0.7.0 and **920 passed, 3 skipped** for 0.8.0, 12 min 52 s (`installer/winetest/run.sh`, `docs/evidence/p13_installers/`); PE import closure of all binaries; byte-code and the pure-Python import under the Linux build of the same CPython release; the installer itself installed and uninstalled silently under 32-bit Wine, the installed tree byte-identical to the stage; 0.8.0 also installed over the morning's 0.7.0 with no file of 0.7.0 left behind | pass, 2026-10-20 |

Not verified: a user on a Windows PC or a Mac (the installer's own pages, shortcuts and SmartScreen prompt; Gatekeeper and the bundle's attribution on macOS; the Intel macOS build at all), a screen reader, a 4K screen at 200 %, Origin 2021 to 2025 building the project from this version.

## 9. Small screens

A 14-inch laptop with a 1920 × 1080 screen at Windows' default 150 % has 1280 × 720 points, about 1280 × 640 inside the frame; an older 13-inch MacBook has about 1280 × 690. The 0.6 draft needed 1100 × 700 and opened at 1480 × 920 regardless, so on these screens part of the window lay under the taskbar. Now:

- **Size.** Minimum 1024 × 600. The window opens at 1480 × 920 where that fits with room around it, otherwise maximised; it remembers its size, place and maximised state.
- **Side panels.** The file list appears when two or more files are open, or with one file from 1680 points wide. The inspector keeps its width; on the Figures page below 1200 points it gives way to the preview, and the pill brings it back.
- **The tables** fold to their tab row below 760 points of height and unfold when the window grows again, unless you folded them yourself (the chevron or Ctrl+J).
- **The Overview** arranges its four panels for the room: 2 × 2 when each row can be at least 250 points high, one row of four on a short, wide area, and the two main panels (profiles; capacity and efficiency) when neither fits. When both fit, the arrangement whose panels are nearer a 1.4 width-to-height ratio wins.
- **Axis titles** are given as variants from the fullest to the shortest ("Specific capacity (mAh g⁻¹)", "Capacity (mAh g⁻¹)", "Q (mAh g⁻¹)") and each axis shows the longest that fits along it, chosen again on every resize and centred on the axis. A unit is never dropped from a capacity, potential or efficiency title.
- **Pages** set the minimum width only while shown (the Figures page and the reading screen used to hold a narrow window at their width while hidden); the Figures page and the reading screen have narrow layouts.

## 10. The pyqtgraph defect

`AxisItem.updateAutoSIPrefix` in pyqtgraph 0.14.0 computes a scale whenever the axis label is visible, whether or not `autoSIPrefix` is enabled, and `setRange` recomputes it only when the flag is on. An axis that once showed 0.3 to 0.55 (capacity in mAh before the mass was given) kept a ×1000 scale; with the flag off, the "(x0.001)" note that would reveal it is suppressed. Ticks of 60 and 80 mAh g⁻¹ read 60000 and 80000. Reproduced in `tests/test_studio.py::test_axis_ticks_are_never_rescaled`, which fails on stock axes and passes on `plain_axes()`.

**The P12a CV app may be affected**: U01 lists "automatic SI prefixes on axes" as fixed; if that fix is `enableAutoSIPrefix(False)`, it carries this defect. The same test applies there.

Also in pyqtgraph: an axis title is centred only when the axis is resized, so a title changed without a resize stays where the old one was centred. `theme.fit_titles` re-centres after each change.

## 11. Independent review

A separate agent reviewed the app on 19 October 2026 and reported 31 findings: six wrong results, one crash, two losses of data or input, and confusing or cosmetic faults. All are fixed, each with a regression test. A second agent then removed the fixes one at a time (88 mutations): the tests caught 78, the gaps it found were closed, and 9 of the 10 survivors are now caught; the tenth, a drop over a plot, cannot be observed offscreen. The findings, the fixes and the tests are listed in `docs/reviews/Cyclara_Review_2026-10-19.md`, with the reviewer's report.

## 12. Limits

- Not run on Windows or macOS by a user; not tested with NVDA, Narrator or VoiceOver. The installers exist (section 7) but are unsigned and have only been exercised under Wine and by static checks.
- With the source-folder setup on macOS the bold application name in the menu bar is the Python program's ("Python"), because that bundle starts a Python outside itself. The one-click bundle keeps the interpreter inside `Contents/MacOS`, which is what should make the name Cyclara; this is to be confirmed on a Mac.
- Files from other cyclers: every text or spreadsheet export can be mapped through the review page; which instruments are recognised without it, and on what evidence, is in `docs/P08d_Instrument_Compatibility_Matrix.md`. Binary formats other than `.mpr` are refused.
- True size relies on the size the screen reports; the app says so and asks for one ruler check.
- Opening a 75,000-row .mpr takes about 7 s (the native reader); answers re-analyse in about 0.5 s; a theme switch takes about 2 s on the test machine, hidden behind the circle.
- Only cycling files are analysed; CV, EIS and CA files are refused by the engine with their technique named.
- Not built: batch recipes, exclusion masks, analysis history, merging with the P12a CV app.
