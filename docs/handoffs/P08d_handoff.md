# P08d: built-in import profiles checked against real instrument files. Handoff

Date: 2026-10-20. Status: **implemented and tested on shipped real files** for the
dialects marked verified in `docs/P08d_Instrument_Compatibility_Matrix.md`; the rest are
recognition-only, verified on inspected files only, or not supported, as the matrix says.

## What changed

- `data/public/<vendor>/` for arbin, maccor, neware, basytec, novonix, pec and landt:
  21 real export files (16 readable, 3 binary examples, 2 rest-only), each with
  `ATTRIBUTION.md`, `manifest.json` (SHA-256 of the shipped file and of its source) and
  the source repository's licence text. Sources: beep and battery-data-toolkit
  (Apache-2.0), PyProBE (BSD-3-Clause), galv-harvester (BSD-2-Clause), cellpy and navani
  (MIT). Three files are truncated or derived (Maccor first cycle, PEC first cycle, two
  row ranges of a 50 MB Neware workbook); the rest are byte-for-byte copies.
- `electrochem/readers/builtin.py`: 16 profiles, each with evidence naming the real
  file it was checked against and what it showed. Corrected: `arbin-csv` (the counter
  resets per cycle, not over the test), `neware-xlsx` (the real record sheet has signed
  current, `Total Time` as an Excel time cell and `Cycle Index`/`Step Index`; the old
  profile's `Status`, `Record ID` and unsigned current were invented), `maccor-txt` (now
  the real 12-line-header dialect, whose `TestTime` is in minutes and whose single
  counter is used). Added: `arbin-xlsx`, `arbin-mits8-csv`, `arbin-res-table-csv`,
  `neware-csv`, `maccor-export-sec`, `maccor-export-min`, `maccor-export-clock`,
  `maccor-export-signed`, `basytec-txt`, `novonix-csv`, `pec-csv`, `pec-csv-clock`,
  `landt-xlsx`. Python names `ARBIN_CSV`, `NEWARE_XLSX`, `MACCOR_TXT` kept.
- Reader changes, each with a test (matrix section 6; failure codes in P08a 3.5a):
  `cells.py` (new; clock durations and Excel time cells), Excel header located per
  sheet, empty trailing row fields, empty step types, throughput counters, capacity
  semantics checked for consistency, interleaved tables refused, headerless sheets
  warned, voltage-trend sign check, counter check without sustained current,
  largest-table proposal, profile claiming by kind plus sniff plus bindings, no mode
  array from a direction-only vocabulary. Typed profile API unchanged; engine
  untouched; readers still import no engine module.
- Tests: `tests/test_readers_real_files.py` (new, 120 tests); 10 tests added to
  `tests/test_readers_robustness.py` and 1 to `tests/test_readers_import.py`; the
  synthetic Neware and Maccor fixtures rewritten to the real layouts, and the tests that
  encoded the invented layouts updated (`test_readers_import.py`,
  `test_readers_robustness.py`).
- Documents: `docs/P08d_Instrument_Compatibility_Matrix.md` (new); dated corrections
  added to `docs/P08_Multi_Instrument_Import_Specification.md`; new and changed codes in
  `docs/P08a_Import_Failure_Mode_Register.md`; `--profile` help in `analyze.py`.

## Evidence

- Reader suites (`test_readers_real_files`, `_workflow`, `_import`, `_robustness`,
  `_fuzz`): 288 passed. Full suite (`python -m pytest -q tests -p no:cacheprovider -x`,
  Python 3.13): `481 passed, 2 skipped, 56 subtests passed in 351.38s (0:05:51)`.
- The independent checks are physical where possible: elapsed test time against the
  wall clock in the same file; voltage rising under charge-positive current; the
  instrument counter against the trapezoidal integral; Landt's own Cycle sheet (30
  cycles, 1.6 % worst); battetl's StatisticByCycle and `[STATS]` files (inspected).
- Findings that only real files could give: Arbin counters reset per cycle; Maccor's
  12-line-header export writes minutes under `TestTime`; Maccor's single `Amp-hr`
  restarts at every step, CC to CV included, in three sites' files; Neware's Excel
  `Total Time` switches from a time of day to a 1900 date at 24 h and was read
  continuous over 6.5 days; Neware's CSV clock has 1 s resolution; Neware's old CSV
  interleaves three tables; two corpus examples (navani's Maccor file, datalab's Ivium
  file) are synthetic and were neither shipped nor used as evidence.
- A claim corrected before it was written down: an apparent one-hour daylight-saving
  jump in the Arbin workbook's wall clock came from the test machine's time zone, not
  the file; the tests now read wall clocks without a time zone.

## Decisions made (reversible)

1. A capacity declaration is accepted when the file does not contradict it, and
   reported verified only when the file leaves no other behaviour open.
2. Arbin profiles declare cycle-cumulative (measured on multi-cycle files), not
   test-cumulative.
3. Maccor profiles keep `current_sign="detect"`: TRI files are signed, Birmingham and
   KIT files unsigned. Rest-only files are still refused (`ambiguous_sign`), as the
   existing test requires.
4. A direction-only step vocabulary builds no mode array, so no CC/CV split is shown
   for Maccor, BaSyTec, Landt or the observed Neware vocabulary, instead of a 0 % CV
   share.
5. BaSyTec and Novonix counters are not bound (no discharge in the files); capacity is
   integrated. Landt's counter is not bound (no step column).
6. The Landt workbook is shipped whole (2.4 MB) for its Cycle sheet.
7. Headerless continuation sheets are warned about, not appended (no real example).
8. No binary reader integrated; NewareNDA needs pandas (the user's decision), fastnda
   needs polars, cellpy's `.res` path needs ODBC or mdbtools; access-parser is the one
   pure-Python `.res` candidate and is untested here.

## What remains unverified

Matrix section 7: Arbin underscore CSV with cycling data; workbooks split across
sheets; other Neware Excel variants and Chinese-locale headers; BaSyTec and Novonix
discharge; PEC clock dialect and Maccor `Test (Min)` under current; `maccor-export-signed`
on a shipped file; every binary format; Digatron, Gamry cycling, Ivium and any
instrument not listed. The CC-CV pairing of the TRI fast-charge protocol (a rest inside
the charge) gives cycle efficiencies above 100 % in the engine's pairing: an engine
matter for a later package, not an import fault.

## Next actions

- Obtain one multi-cycle Arbin underscore CSV and one multi-sheet Landt and Arbin
  workbook (the zenodo corpus in P08 section 7 lists Arbin, Digatron, Basytec and Landt
  raw files under CC BY 4.0) and add them as rows here.
- Decide on pandas (NewareNDA) or polars (fastnda) for Neware binaries, or a numpy
  port validated against NewareNDA's shipped reference for `test.nda`.
- Evaluate access-parser on `arbin/arbin_example.res` in a sandbox, against an Arbin
  text export of the same test once one is available.
