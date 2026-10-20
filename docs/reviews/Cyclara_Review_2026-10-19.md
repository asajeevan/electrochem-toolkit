# Cyclara: independent review of 19 October 2026, and what was done about it

The app was called Electrochem Studio when this review was made; it is now Cyclara. The review was made by a separate agent that had not written the code, on the code as it stood at 16:54 that day. It read the source, ran the app offscreen in both themes at 1600 × 1000 and at the then minimum size of 1100 × 700, and wrote one reproduction script per defect (r01 to r29). Files: the public `020-formation_CB5` export and binary, public CV, EIS and CA files, the public `bio_logic` files, and the author's own long cycling file (more than 100 cycles), read in place and never copied. That file is private: none of its values appear below.

Severity labels are the reviewer's: wrong-result, data-loss, broken, confusing, cosmetic. Part 1 lists every finding with its fix and the regression test that fails if the fix is removed (all in `tests/test_review_fixes.py`, whose test names carry the reproduction-script numbers). Part 2 is the reviewer's text, unchanged except for the private file's values.

## 1. Findings, fixes and tests

| # | Finding (class) | What changed | Regression test |
|---|---|---|---|
| 1 | Crash (segmentation fault) opening more files while one is shown: Python's cyclic garbage collector ran on a worker thread while the GUI thread deleted inspector widgets (broken) | Automatic collection is off; a timer on the GUI thread collects every 0.5 s. Inspector widgets are blocked from signals, taken out and deleted later, never inside their own signal | `r10`; 20 repeated rounds of the reproduction without a crash |
| 2 | Area given, no mass: capacities in mAh labelled mAh cm⁻² in views, figures and the Origin script (wrong-result) | One decision, `cycling.capacity_basis` (specific, areal or absolute), now picks both the label and the value everywhere | `r01` |
| 3 | Exported efficiency axis dropped points above about 100 % (wrong-result) | `plotting.ce_limits` always includes every point; the figure checker gained "data inside the axes" | `r02_every_efficiency_point…` |
| 4 | Cycle order never asked; discharge-first protocols paired a charge with the next cycle's discharge (wrong-result) | Asked whenever the file, with the direction given, starts with a discharge; efficiency stays Q_discharge / Q_charge of the same cycle | `r02_the_cycle_order…` |
| 5 | No step (Ns) column: a current reversal stayed inside one branch, netting the charges (wrong-result) | Without Ns, a branch ends wherever the measured current changes sign, and the diagnostics say so | `r13` |
| 6 | Three-electrode files always used Ecell/V, even for a half-cell answer (wrong-result risk) | The potential column follows the answer: Ewe/V (working electrode against the reference) for a half-cell, Ecell/V for a full cell | `r15` |
| 7 | Two exports started before either wrote went to one folder (data-loss) | The folder is created when its name is chosen | `r04_r18` |
| 8 | Undo raised an error after a file was closed and reopened (broken) | Records compare by identity | `r17` |
| 9 | Old values shown unmarked while new answers were analysed (confusing) | "Updating for your last answer" beside the views; values marked provisional | `r21` |
| 10 | Text being typed in a field wiped when an analysis returned (data-loss: input) | Drafts, cursor and focus survive a rebuild; nothing half-typed is committed | `r06` |
| 11 | Keyboard browsing changed the selection; removing the focused cycle desynchronised the focus (broken) | Moving the focus never changes the selection (a focused cycle outside it is drawn dashed and not exported); removing it moves the focus and tells the window | `r03_r27`, `r03_removing…` |
| 12 | Figure checker passed broken figures; exported superscripts were 4.9 pt (broken) | Checker: lowercase panel letters, legends and text clear of lines, points, bands and bars, data inside the axes, tick weights, glyph sizes measured; superscripts raised per journal (Nature 5 pt, Elsevier 6 pt) | `r12` (both) |
| 13 | Figures view re-ticked unticked figures (confusing) | Ticks kept per file | `r05` |
| 14 | After switching to an unreadable file the previous figure stayed on the sheet (confusing) | The sheet is cleared and the list says why | `r20` |
| 15 | "1e400" accepted as an infinite mass (wrong-result on hostile input) | Non-finite numbers refused in every field | `r07_r11` |
| 16 | EC-Lab's empty-field default of 0.001 mg offered as an answer (confusing) | Never offered; specific capacities above 5000 mAh g⁻¹ flagged | `r28`, `r16_r28` |
| 17 | One undo stack for all files undid a step in a file not on screen (confusing) | Undo brings its file forward and says so | `r09` |
| 18 | Restored answers could not be undone (confusing) | One undoable step, with a lasting notice and Keep or Clear | `r08` |
| 19 | Withheld values gave the wrong reason (confusing) | Reasons name the real cause: a reference cycle that is not complete, a C-rate that needs molar mass and electrons | `r22` |
| 20 | The same data gave opposite evidence for the potential question in .mpt and .mpr (confusing) | The column name is no longer presented as evidence; the card says the .mpr names the column Ewe/V whatever the set-up | `r14` |
| 21 | Opening a folder hid .mpt files sharing an .mpr's name prefix (confusing) | An export is recognised by its header ("Saved on: File: X.mpr") or an exact name; skipped files are reported | `r19_r29` |
| 22 | Unsupported inputs gave no feedback or raw error codes (confusing) | Every refusal in words: .csv, empty folder, settings-only folder, empty or malformed file | `r25` |
| 23 | A huge range in the cycle box froze the window (broken on hostile input) | Ranges are clamped to the file's cycles before expansion | `r07_r11` |
| 24 | Tab did not reach the questions second (accessibility) | Tab goes from the files to the questions, then the views | `r24` |
| 25 | Theme switch left light-theme icons on a dark bar (cosmetic, accessibility) | Every drawn icon is redrawn in the new theme's colours | `r23` |
| 26 | Labels cut off at the minimum size (cosmetic) | First fixed only in part; redone: the window now works from 1024 × 600 (see U02, section 9) | `finding26…` at 1024 × 600, 1280 × 640 and 1480 × 920 |
| 27 | Small label and state faults (confusing) | "Optional" instead of "Answered"; plurals; integer cycle ticks; unknown cycles reported; legends and reference in titles; Data rows 1-based; no command-line flags in the window; durations under an hour in minutes | `r26` |
| 28 | Export failed silently when a file had the folder's name (broken, edge case) | The next free name is used | `r04_r18` |
| 29 | A header mass in grams was always reported as different (confusing) | Units converted before comparing | `r16_r28` |
| 30 | A test could pass before a job's result arrived (flaky test) | The test pump waits for a quiet period of at least three passes and checks again after a last pass, since a result arriving during a long pass can start the next job (the screenshot script had shown the same race) | the pump in both GUI test files and in `scripts/studio_images.py` |
| 31 | Opening an .mpr parsed the whole sibling .mpt for its header (performance) | Only the header block is read | `r19_r29` (a 60 MB export is read in under 0.5 s) |

Wrong-result findings: 2, 3, 4, 5, 6 and 15. Each could have put a wrong number or a wrong figure into a paper, and each now has a test with a known answer.

**Mutation check of these tests.** A second agent, which had written neither the code nor the tests, made 88 mutations on a frozen copy, each undoing a fix or a part of one, and ran the test named for it. 78 failed as they should. The 10 that survived were parts no test looked at: the Origin table's basis (finding 2), opening an .mpr without parsing its export's rows (31), the strip's own arrow keys (11), values marked provisional while updating (9), the Capacity legend, the reference in the Voltage title and "1 branch" (27), the reading screen handing over by itself, a step it never took, and a drop over a plot. The tests were strengthened with the agent's checked assertions (`test_r01_the_origin_tables…` is new) and the survivors were run again: 9 of the 10 are now caught. The drop over a plot cannot be observed offscreen, where Qt hands a drag that a child ignores up to the window either way. Two tests that had caught their mutants only by chance now assert what they protect: the message after undoing a step of a closed file (finding 8) and a 1 s bound on cutting the launch sequence short. The check also found that the reading screen called EC-Lab's 0.001 mg default "offered, not applied"; it now says the default is not offered.

## 2. The reviewer's report

**What was reviewed.** The code as it stood when the review began: `electrochem/studio/*.py` (app.py 16:52, views/theme 16:48, inspector 16:44, strip/tables 16:41, model/worker 16:25), `electrochem/workflow.py` (16:15) and `electrochem/plotting.py` (16:54). Three new modules and an assets folder appeared mid-review (`brand.py`, `motion.py`, `platform_support.py`, `studio/assets/`, 17:32 to 17:37). `app.py` did not import them, so they were not reviewed.

**How.** Offscreen, light and dark themes, 1600 × 1000 and the 1100 × 700 minimum size. Files: public CB5 (.mpt and .mpr); public CV, EIS and CA files; public bio_logic1/2/4/5/6; the author's private cycling file. One reproduction script per defect.

### Defects, most severe first

1. **Crash (segmentation fault) when more files are opened while one is shown [broken].** GUI thread in `Inspector._attach` (`setWidget`) deleting the previous container while a worker thread runs the cyclic garbage collector inside `eclab_import/native.py`. Inspector widgets sit in reference cycles (`lambda ed=ed`, `commit(ed=ed, err=err)`, `lambda sp=sp`). r10 crashed in 3 of 3 processes; with `gc.disable()` 15 of 15 rounds survived. Should: never crash; break the cycles or delete widgets explicitly, and keep garbage collection off worker threads.
2. **Area and no mass: capacities in mAh labelled mAh cm⁻² [wrong-result].** CB5, positive charges, full cell, area 2 cm²: Capacity view, Overview capacity panel, readout, strip tooltip, Inspector summary and Cycle card, exported `fig2_capacity_efficiency`, summary panel b and the Origin script show areal labels over mAh values (50.85 and 49.65; true areal 25.42 and 24.82). Profiles and dQ/dE divide by the area correctly. Cause: label functions pick the areal label whenever an area is set; the value code chooses only between `*_specific_mAh_g` and `*_capacity_mAh`.
3. **Exported capacity/efficiency figure silently drops CE points above about 100 % [wrong-result].** CE axis `(lo, 100 + 0.08*(100 - lo))` with `lo` from the 1st percentile; points above the top are not drawn; `check_figure` passes. Same in summary panel b and the Origin script.
4. **Cycle order never asked; silently charge-first [wrong-result].** A discharge-first protocol pairs charge n with discharge n+1. CB5 with "Negative current charges": cycle 1 unpaired, cycle 2 = branches 2+3 at 100.76 %, cycle 3 unpaired; the inspector shows "First discharge" and "First-cycle CE" from cycle 2. Should: ask or expose which branch starts a cycle, and name the cycle each summary value comes from.
5. **No step (Ns) column: one branch across a current reversal [wrong-result].** `bio_logic1.mpr`: 1.4390 mAh negative and 2.5975 mAh positive become one "discharge" branch of 1.1585 mAh. Should: split at sign changes when there is no step column, or refuse the file.
6. **Three-electrode files always analysed on Ecell/V, even after "Half-cell vs. Li⁺/Li" [wrong-result risk].** `POTENTIAL_NAMES` prefers `Ecell/V` over `Ewe/V`; no column choice. Should: use Ewe for half-cell answers, or ask.
7. **Two exports requested before either starts writing go to the same folder [data-loss].** The name is chosen on the GUI thread, the folder created only once the worker holds `RENDER_LOCK`. Should: create the folder when its name is chosen.
8. **Undo and redo raise ValueError after a file is closed and reopened [broken].** `Record` is a dataclass, so `rec not in self.records` compares field by field down to numpy arrays. Should: compare by identity (`eq=False`).
9. **Old values stay on screen, unmarked, while new answers are analysed [confusing].** About 1 s on the author's long file; only the pill says "Analysing". Should: mark results as stale until the matching run arrives.
10. **Text being typed in the inspector is wiped when an analysis returns [data-loss: user input].** Should: update cards in place; never replace a field that has focus or uncommitted text.
11. **Keyboard navigation changes the plotted selection; deselecting the focused cycle desynchronises focus [broken].** (a) Strip Left/Right/Home/End and Cycles-table Up/Down add visited cycles to the selection. (b) Clicking the focused cycle to remove it moves the strip's focus without telling the app; "]" then does nothing.
12. **`check_figure` false passes, and 4.9 pt superscripts in every exported figure [broken].** Passes: uppercase panel letter; legend over scatter, fill_between or a figure legend; text across a curve; data outside the axis limits; 0.1 pt ticks. Superscripts "⁻¹" are 0.7 × 7 = 4.9 pt, below Nature's 5 pt and below the 6 pt cited for Elsevier; the checker reports "6.5 to 7 pt".
13. **Figures view re-ticks unticked figures [confusing].** Should: keep the user's ticks per record.
14. **After switching to an unreadable file, the Figures view still shows the previous file's figure and "All 10 checks pass" [confusing].** List items say "(needs an answer)".
15. **A mass of "1e400" is accepted as infinity [wrong-result on hostile input].** Area, molar mass and electrons have the same gap.
16. **EC-Lab's untouched 0.001 mg header value offered as a one-click answer [confusing].** One click gives 50,849,834.86 mAh g⁻¹ and "Ready to export". Should: flag the default and physically implausible specific capacities.
17. **One undo stack for all files: Ctrl+Z reverts an answer in a file that is not on screen [confusing].** Should: per-file undo, or switch to the file whose step is undone.
18. **Restored answers cannot be undone, although the status bar says they can [confusing].** Should: one undoable step and a lasting notice.
19. **Withheld values give the wrong reason [confusing].** (a) A retention reference cycle that does not exist is accepted silently; retention then reads "not defined for this cycle". (b) C-rate without molar mass and electrons says "not defined for this cycle".
20. **Same measurement, opposite evidence for "What does the potential column measure?" [confusing].** CB5 .mpt has `Ecell/V` ("as in a full cell"); the .mpr of the same data has `Ewe/V` ("as in a half-cell"). Should: do not present the .mpr column name as evidence.
21. **Opening a folder hides .mpt files whose names start with an .mpr's name [confusing].** cell1.mpr hides cell10.mpt and cell11.mpt (`startswith`). Should: match only exports of the same run, and report anything skipped.
22. **Unsupported inputs give no feedback or raw codes; unreadable files show empty axes [confusing].** .csv, empty folder or .mps-only folder: nothing happens. Empty .mpt: "ImportFailure: empty_file: …". Headerless table: "requires explicit selection" with no such selection offered. Unreadable file: empty 0 to 1 axes.
23. **A large range in the cycle box freezes the window [broken on hostile input].** "1:20000000" takes 2.0 s and about 800 MB. Should: clamp each range to the file's cycles before expanding.
24. **Tab order does not reach the questions second [accessibility].** Actual: files, an empty scroll-area stop, view switcher, every plot, cycle box, strip, results, Presets, then questions.
25. **Theme switch light to dark leaves light-theme icons [cosmetic; accessibility].** Toolbar icons 2.09:1; Figures view export icon 1.22:1.
26. **At 1100 × 700, labels are clipped [cosmetic].** "Figures" button cut off; axis titles "E (%)" and "nAh g⁻¹)"; strip hint cut off; "Ctrl K" touches the pill; zoom buttons "…".
27. **Small label and state faults.** "Optional details" says "Answered" when nothing is given. Before the direction is answered the strip says "Cycles appear here once the file is read" and the Cycles table is blank. Cycle-number axes tick 1.0, 1.2, 1.4. "1, 2, 999" drops 999 silently. Capacity and Voltage views have no charge/discharge legend. Voltage view's y label omits the reference. "1 branches". Data view "Row" axis 0-based, readout 1-based. GUI messages use command-line flags. Runs under 30 min show "0 h".
28. **Export fails silently when a file named `<stem>_analysis` exists [broken; edge case].** NotADirectoryError on the GUI thread.
29. **A header mass declared in grams is always reported as different [confusing].** `mass_warnings` compares g with mg.
30. **Flaky test [low].** `pump()` checks the thread count after its last `processEvents()`, so it can return before a finished job's result is delivered.
31. **Opening an .mpr parses the whole sibling .mpt for its header [performance].** 2.6 to 3.3 s on a 31 MB .mpt; reading the header alone takes 0.4 ms.

### Checked and found correct

- Numbers (the author's file): every inspector value, Cycle card value, table cell, readout and strip value compared matches `analyse_file`; profile and dQ/dE curves are the engine's arrays.
- Axes: all 17 plot widgets use the workaround axis; no tick labels rescaled.
- Export: PDFs exactly 89.0 and 183.0 mm wide; PNGs 600 dpi at the same size; preview size equals export size; `settings.json` records checks and cycles; a second sequential export goes to `_analysis_2`.
- Refusals: CV, EIS, CA and four bio_logic files refused in plain words; "Already open"; "999" alone refused with a message; undo after closing says the step was dropped.
- Answers: mass 0 or negative refused; "1,5" gives 1.5; "1.500,5" refused; half-cell without reference keeps the question open; full/half switching keeps the reference; answers in odd orders or during an analysis apply correctly.
- Interaction and appearance: strip drag, Ctrl+drag, double-click work; typing does not trigger single-key shortcuts; dark theme correct at start; text and pill contrast at least 4.5:1.
- The checker does catch: oversize text; wrong width; legend over line data including a straight segment; overlapping labels; light colours (warning); legend overflow with every cycle shown.

### Notes

- The author's file was read in place and never copied into the repository; an export of it in the reviewer's scratch folder was deleted.
- Hostile-file tests appended tracebacks to `~/.electrochem-toolkit-errors.log`.
- Every QSettings store created was cleared.
