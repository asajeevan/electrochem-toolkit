# P08d: instrument compatibility matrix

Status: written 20 October 2026, with `tests/test_readers_real_files.py` (120 tests on
the shipped files) and the corrected `electrochem/readers/builtin.py` (16 built-in
profiles). Extends `P08_Multi_Instrument_Import_Specification.md` and
`P08a_Import_Failure_Mode_Register.md`.

## 1. The claim, stated exactly

- **Any cycler's delimited-text or spreadsheet export can be read** through an import
  profile: a built-in one where it exists, otherwise one learned from the file through
  the proposer and the import review page.
- **Built-in profiles exist only for dialects whose real export files were read and
  checked.** Each profile's `evidence` string names the file, its source, and what the
  file showed. "Verified" in the table below means that a test in this repository
  opens a shipped real file through `workflow.open_file` (no profile named) and checks
  it independently. Where the only real files could not be shipped (licence), the row
  says "verified on inspected files only".
- **Not claimed:** that every dialect of a listed vendor is recognised (export dialogs
  let users choose columns, units and layouts), that binary formats are read, or that
  a vendor not listed is recognised automatically.

## 2. How each file was checked

Every check in `tests/test_readers_real_files.py` parses the file a second time with
`csv` or `openpyxl`, applies the unit and sign it knows for that dialect, and computes
the expected quantity with numpy; nothing is taken from the reader. Codes used in the
table:

| Code | Check (test function) |
|---|---|
| R | recognised by its columns alone: exactly one built-in profile claims it (`test_the_file_is_recognised_by_its_columns_alone`) |
| A | time, current and voltage arrays equal the independent parse: units, decimal mark, clock formats, sign (`test_the_arrays_equal_the_file_parsed_independently`) |
| W | elapsed test time equals the elapsed wall clock written in the same file, which fixes the time unit (`test_the_time_unit_is_confirmed_by_the_wall_clock_in_the_same_file`) |
| S n/m | sign convention measured: in n of m steps carrying current of one sign, the voltage rose exactly when the charge-positive current was positive (`test_charging_raises_the_voltage_in_every_step`) |
| C | capacity-counter semantics measured: "unique" when the file leaves only the declared behaviour open, "consistent" when it cannot decide (`test_the_counter_behaviour_is_measured_on_the_file`, from `capacity_semantics_consistent` in the import report) |
| I x | instrument counter against the trapezoidal integral of the current over edges inside one step, charge and discharge separately; x is the worst relative difference (`test_the_instrument_counter_agrees_with_the_integral_of_the_current`) |
| E | analysed end to end: engine branch capacities equal the independent totals to 1e-6, one branch per run of one current sign (`test_the_engine_capacities_equal_the_independent_totals`) |
| V | compared with the instrument's own cycle statistics carried by the export |

Settings for E are those of `tests/test_readers_workflow.py`:
`Settings(charge="ox", terminal_voltage=True)`.

## 3. The matrix

Licences are those of the source repositories; each vendor directory under
`data/public/` has `ATTRIBUTION.md`, `manifest.json` (SHA-256 of the shipped and the
source file) and the licence texts. "Truncated" means the first N lines kept byte for
byte; "derived" means a contiguous row range of a workbook sheet kept with its cell XML
unchanged.

| Instrument | Export dialect (profile) | File example (source, licence) | What was verified | Status | Known limitations |
|---|---|---|---|---|---|
| Arbin | MITS Pro CSV, underscore names `Test_Time(s)` (`arbin-csv`) | `arbin/arbin.csv` (galv-harvester, BSD-2-Clause) | R, A, E (no branch) | Column names verified on a real file; conventions not measurable in it | The file repeats one rest row 21 times. Sign and counter conventions are carried over from `arbin-xlsx` (same software, same names) and the multi-cycle Arbin files below. No real multi-cycle file of this dialect was available. |
| Arbin | MITS Pro Excel, sheets `Global_Info` + `Channel_<ch>_<n>` (`arbin-xlsx`) | `arbin/bs542_004_gr_li_50ua_50mv_1v_191020_Channel_11.xlsx` (navani, MIT) | R, A, W, S 3/3, C consistent (test or cycle), I 1e-4, E | **Verified on a real file** | One cycle, so test- and cycle-cumulative cannot be told apart in it. No Statistics sheet in this example. The row count at which Arbin splits sheets is unverified (P08 section 9). |
| Arbin | MITS CSV, spaced names `Test Time (s)` (`arbin-mits8-csv`) | `arbin/sample_data_arbin.csv` (PyProBE, BSD-3-Clause) | R, A, W, sign by counter identity, C consistent, I 0.25 %, E | **Verified on a real file**, a 13-row one | Two charging rows only: too few for the voltage test. Its conventions were also measured on three battetl MITS exports (34 209 to 61 699 rows, BattSoft Community License, **inspected, not shipped**): S 16/16, 5/5, 11/11; C unique (cycle-cumulative); I 8e-4; V: per-cycle counter increments equal the vendor's StatisticByCycle export to 3e-9 over 16 cycles. |
| Arbin | `.res` channel table written as CSV, names without units (`arbin-res-table-csv`) | `arbin/arbin_example.csv` (battery-data-toolkit, Apache-2.0) | R, A, W, S 6/6, C unique (cycle-cumulative), I 5e-4, E | **Verified on a real file** | A dump of the `.res` Channel_Normal_Table (TRI data), not a direct MITS Pro export; units are the `.res` schema's, confirmed by I and W. The file starts mid-cycle. The protocol splits each charge by a rest, so the engine pairs the last charge branch with the discharge (cycle efficiency above 100 %): an engine pairing matter, not an import one. |
| Arbin | `.res` binary (Access database) | `arbin/arbin_example.res` (navani, MIT) | refused with `binary_export` (`test_a_binary_instrument_file_is_refused_with_a_reason`) | **Binary, not readable** | See section 5. |
| Maccor | text export, `Test (Sec)` (`maccor-export-sec`) | `maccor/xTESLADIAG_000038con.078`, `maccor/PredictionDiagnostics_000151_test.052` (beep, Apache-2.0) | R, A, W, S 16/16 and 1/1, C unique (step-cumulative) in the 8-cycle file, I 2.5e-5, E | **Verified on real files** | Amps are signed in these files; detection decides per file. The second file starts at record 249 791 inside a discharge: only the charge passed inside the file is counted, and its cycle numbers (from 37) are kept and warned about. Test time and PC clock drift by 1.2e-4. |
| Maccor | text export, `Test (Min)` (`maccor-export-min`) | `maccor/maccor_example.001` (battery-data-toolkit, Apache-2.0) | R; import refused with `ambiguous_sign` by design; with the sign answered, W | **Recognised only** | Eight rows of rest: neither sign nor counter can be measured. Conventions carried over from `maccor-export-sec`, which differs only in the time unit. |
| Maccor | text export, clock `TestTime` `0d 00:00:5.05`, unsigned `Amps` + `State` (`maccor-export-clock`) | `maccor/maccor_001_first_cycle.txt` (cellpy, MIT; truncated to the first cycle) | R, A, W, S 3/3, C unique (step-cumulative), I 5e-6, E | **Verified on a real file** | The whole source file (6 704 rows, not shipped in full) gives S 9/9 and I 2e-5. `Cyc#` stays 0. beep's EIS file `maccor_test_file_4267-66-6519.041` has this header and is refused for its `FRA` and `P` states, which is right for an impedance test. |
| Maccor | text export with a 12-line header block, `Cycle P`, `Cap. [Ah]`, `Md` (`maccor-txt`) | `maccor/maccor_002.txt`, `maccor/maccor_two.txt` (cellpy, MIT) | `maccor_002`: R, A, W, S 4/4, C unique (step-cumulative), I 3e-6, E. `maccor_two`: R, decimal comma, W with the sign answered | **Verified on a real file** | **`TestTime` is in minutes** although its name states no unit: it advances 1.0 per 60 s of `DPT Time`, and only minutes make the counter agree with the integral (`test_maccor_kit_time_is_minutes_and_the_counter_needs_them`). Data rows end with a tab the header lacks (dropped). `maccor_two` is rest only (refused by design, `ambiguous_sign`) and ends in a line cut off mid-number (kept, its current unused). |
| Maccor | text export with units in brackets, signed `Current(A)`, no State (`maccor-export-signed`) | battetl `BG_Maccor_Testdata - 079.txt` (BattSoft Community License, **inspected, not shipped**) | on the inspected file: S 15/15, C unique (step-cumulative), I 2e-5, V: per-cycle totals equal the export's `[STATS]` AH-IN and AH-OUT to 6e-5 over 8 cycles. In the repository: a synthetic file in this layout only (`test_maccor_signed_export_profile_on_a_synthetic_file_in_its_layout`) | **Verified on inspected files only** | battetl's `ResetCap_Take11 - 074.txt`, whose schedule resets the counter inside steps, is refused with `capacity_semantics_mismatch`, as it should be. |
| Maccor | other dialects seen | PyProBE `sample_data_maccor.csv` (BSD-3); battetl `BG_Maccor_Type2 - 075.txt`; cellpy `maccor_three.txt` (MIT); navani `maccor_example.txt` (MIT) | inspected | **No built-in profile** | PyProBE's CSV has no State column and only a charge, and states no units: the proposer blocks, correctly. battetl Type2 has no units in its header: proposer. cellpy's `maccor_three.txt` was re-saved by pandas (an `Unnamed: 12` column) and writes millivolts under `Volts`: not used as evidence. navani's file is a synthetic demo (perfectly linear voltages, a clock that wraps from 11:59 to 11:00) whose counter never resets, unlike every real Maccor file; it is refused by the semantics check. |
| Neware | Excel export, `record` sheet, `Total Time` as an Excel time cell (`neware-xlsx`) | `neware/sample_data_neware_rows_2_25001.xlsx`, `neware/sample_data_neware_rows_80001_90000.xlsx` (PyProBE, BSD-3-Clause; derived) | R, A, W, S 1/1 each, C unique (step-cumulative) in the first part, I 1.3e-6 and 5e-8, E; `Total Time` continuous across 24 h (`test_neware_total_time_is_continuous_where_excel_switches_to_a_date`) | **Verified on real files** (derived parts) | The whole 789 589-row source was read through the profile (not shipped): S 21/21, I 3e-5, time continuous over 6.5 days. This export has 10 columns (no Step Type, no DataPoint); variants with mass-normalised columns (`Current(A)`, `Chg. Spec. Cap.`) and Chinese-locale headers are unverified. Durations of 59 to 61 days are made invalid, not guessed (Excel's 29 February 1900). |
| Neware | flat CSV export, one row per record, `Cumulative Time` hh:mm:ss (`neware-csv`) | `neware/neware_uio.csv` (cellpy, MIT) | R, A, W, S 16/16, C unique (step-cumulative), I 1.6e-5, E | **Verified on a real file** | The clock has 1 s resolution, so sub-second records share timestamps; the engine does not integrate the 67 zero-duration edges (1.1 uAh, 5e-5 of the discharge), and the test mirrors that. |
| Neware | hierarchical CSV (BTS 7), cycle, step and record rows interleaved | cellpy `nw_regular_export_ife_example.csv` (MIT), beep `raw/neware_test.csv` (Apache-2.0) | inspected; reader refuses with `interleaved_tables`, proposer blocks (synthetic test in `test_readers_robustness.py`) | **Not readable, by design** | Export the record level only. |
| Neware | `.nda`, `.ndax` binary | `neware/test.nda`, `neware/test.ndax` (navani, MIT) | refused with `binary_export` | **Binary, not readable** | `test.nda` is byte-identical to NewareNDA's `new_nda_file.nda`, whose decoded reference output NewareNDA ships: a ready validation case for section 5. |
| BaSyTec | result file with a `~` header block (`basytec-txt`) | `basytec/sample_data_basytec.txt` (PyProBE, BSD-3-Clause) | R, A, S 1/1, I 2.9e-4 (`Ah-Step`), E | **Verified on a real file**, charge only | No discharge in the file: negative-for-discharge is declared, not measured. The counters are not bound (their behaviour in a discharge is unobserved), so capacity is integrated. No wall-clock column. |
| Novonix | UHPC CSV with `[Summary]`, `[Protocol]`, `[Data]` (`novonix-csv`) | `novonix/sample_data_novonix.csv` (PyProBE, BSD-3-Clause) | R, A, W, S 1/1, I 2.7e-5, E | **Verified on a real file**, one charge step | The numeric Step Type code is not explained by the file and is not used; the counter is not bound. beep's `test_Nova_Form-CH01-01_short.csv` has every data line wrapped in quotes (re-saved) and was not used. |
| PEC | CSV, `Total Time (Seconds)`, mV and mA (`pec-csv`) | `pec/pec_first_cycle.csv` (cellpy, MIT; truncated after the first full cycle) | R, A, W, S 3/3, C unique (cycle-cumulative), I 8e-7, E | **Verified on a real file** | The energy columns are labelled `Charge Capacity (mWh)` in this export; the binding cannot take them because mWh is not a charge unit. |
| PEC | CSV, `Total Time (Hours in hh:mm:ss.xxx)` (`pec-csv-clock`) | `pec/Test25205.csv` (cellpy, MIT) | R, A, W; counter not compared (no current flows) | **Recognised and read; conventions not measurable** | Open-circuit storage only. Sign and counter behaviour carried over from `pec-csv` (same software, 2019). |
| Landt / LANHE | Excel, sheets `Record`, `Mode`, `Cycle` (`landt-xlsx`) | `landt/NJK_CC_156_C30_C_x30.xlsx` (navani, MIT; 2.4 MB, kept whole for its Cycle sheet) | R, A, S 60/60 runs, E, V: 30 charge and 30 discharge capacities within 1.6 % of the instrument's Cycle sheet (0.6 % median) | **Verified on a real file** | The Record sheet has no step or cycle number, so its per-state `Capacity/mAh` counter cannot be checked at boundaries and is not bound; capacity is integrated from a time printed to 0.01 h and a current printed to 0.0001 mA, which bounds the agreement. Continuation sheets without a header (P08 trap 6) are not read and are warned about (`headerless_sheet_not_read`); no real multi-sheet Landt file was available. |
| Landt | CSV | battery-data-format `data/SINTEF__LiGrR2032__2024-04-30__25degC__Landt.csv` (Apache-2.0) | inspected | **No profile** | A site-converted CSV (`test_time_s`, `current_A`, ...), not a Landt export. |
| Landt / LANHE | `.cex` binary, layout `07 00 04 00` (native reader `lanhe-cex`) | none shipped (a user's file, private, 20 October 2026); synthetic files in `tests/cex_synthetic.py` | T, A, V, S, R and the four internal statements of P08g section 3 (clock, capacity counter, energy counter, programmed setpoints): current within 0.01 %, voltage within 0.001 % | **Read natively; verified on one real file; LANHE's own export of that file not yet compared** | `docs/P08g_LANHE_cex_Reader.md`. Range codes `0xE005` (5 V) and `0xC00A` (1 mA) verified; other codes of the same families read only when the file's own counters confirm the scale. Other layouts, unknown step types (constant-voltage discharge included), pause or resume events and unknown units are refused with what was found. No published description exists; one open project decodes the format for capacities (`culture-medium/battery-data-tool`, v0.5.7) but carries no licence, so no code of it is used. Before 20 October 2026 the file reached the window as a raw `csv` error, then was refused (fixed, below). |
| Digatron | any | none | | **No real file available** | The corpus holds only a BDF conversion (`FZJ__INR21700__...Digatron.bdf.csv` in battery-data-format), not a raw export. |
| BioLogic (EC-Lab, BT-Lab) | `.mpr`, `.mpt` | `data/public/mpr`, `data/public/mpt` | the validated EC-Lab path (P03), untouched | Unchanged | Not part of P08d. |
| Gamry | `.DTA` | gamry-parser `tests/data/ccd_data.dta`, `ccd_charge_data.dta` (MIT) | inspected | **Not supported** | A charge-discharge `.DTA` holds a per-half-cycle summary (`CAPACITYCURVE`) or one `CURVE` table per segment followed by metadata lines; the generic reader reads one table per file. Needs a format-specific table extractor. |
| Ivium | text | datalab `rest_only_ivium.txt` (MIT) | inspected | **No real file available** | That file is synthetic (perfectly linear voltage, rest only). |
| Solartron, CH Instruments, Autolab, Parstat | impedance exports | impedance.py, pyimpspec examples | not applicable | Out of scope | Impedance spectra, not cycling time series; the proposer blocks them. |
| Repower, Indigo | | Battery-Data-Steward fixtures | inspected | **No real file available** | 100 to 300 byte files written by that project's authors, not instrument exports. |

Sources inspected and **not shipped** because their terms do not allow it here:
battetl (BattSoft Community License: field-of-use restriction, no sublicensing, so
not redistributable inside a GPL-3.0-or-later repository); BatteryProcessing,
VoltaiqDataFormat and cellxplorer (no licence; their data files were not opened).

## 4. What the import report now states for every file

`import_report` (and `settings.json` of an export) carries, besides the P08a fields:
`sign_vs_voltage` (voting steps, agree, disagree), `capacity_semantics_consistent`
(every counter behaviour the file leaves open), `capacity_semantics_verified` (true
only when the declared one is the only one left) and `counter_vs_integral` (or
`{"compared": false}` where no current flows). New finding codes are listed in
P08a section 3.5a.

## 5. Binary formats: the libraries evaluated

Evaluated by reading their source and packaging metadata only; none was installed or
run here (the corpus is untrusted code), so none is tested on the shipped binaries.

| Library | Licence | Last commit | Dependencies | Pure Python? | Usable from GPL-3.0-or-later? | Assessment |
|---|---|---|---|---|---|---|
| NewareNDA (d-cogswell, `.nda`, `.ndax`) | BSD-3-Clause (SES AI) | d895eb2, 11 June 2026 (v2026.06.11) | **pandas**, xmltodict | Yes: `struct`, `mmap`, `zipfile`, `xml`; no compiled code | Yes, as a dependency or vendored with its copyright and licence kept | Needs pandas, which is not a dependency of this toolkit (adding it is the user's decision). pandas is used to assemble, de-duplicate, sort and pivot the decoded records (about 30 calls); the record decoding itself is `struct`-based and could be ported to numpy, with NewareNDA's shipped reference outputs (`tests/reference*/`) as the validation cases. Not integrated. |
| fastnda (Empa fork of NewareNDA) | BSD-3-Clause (SES AI, Empa) | ea1e60f, 9 September 2026 (v1.3.1), active | numpy, **polars**, defusedxml, xmltodict, tqdm, typer, isal (x86_64, AMD64 and aarch64 only) | Its own code is Python; polars (Rust) and isal (C) are compiled but ship wheels for Windows and macOS | Yes | No compiler needed, but polars adds roughly 35 to 45 MB per platform, and isal is not installed on Apple Silicon (`arm64`). pandas only in its extras. Ships Parquet reference outputs for its test files. Not integrated. |
| access-parser (ClarotyICS, Access `.mdb`/`.accdb`, so Arbin `.res`) | Apache-2.0 | 7b73391, 21 January 2025 (v0.0.6), low activity | construct, tabulate (both pure Python, MIT) | Yes | Yes (Apache-2.0 is compatible with GPL-3.0) | The only pure-Python route to `.res` found. Its code handles Jet 3, 4, 5 and 2010 headers; both Arbin `.res` files looked at begin `Standard Jet DB` with version byte 1 (Jet 4). Its README warns it was tested on a limited set of databases. Untested on `.res` here; a future evaluation would read `Channel_Normal_Table` from `arbin/arbin_example.res` and compare it with an Arbin CSV of the same test, which this corpus does not contain. |
| cellpy `.res` loader | MIT | 29d916c, 19 October 2026 | pyodbc with the Microsoft Access ODBC driver (Windows), or the `mdb-export` command of mdbtools (Linux, macOS); sqlalchemy, pandas | No | Licence yes, packaging no | Needs a system component the installers cannot bundle. navani's `.res` route (galvani `res2sqlite`) also shells out to mdbtools. |

Decision recorded: no binary reader is integrated in P08d. `.res`, `.nda` and `.ndax` stay
refused with an instruction to export text, and the shipped examples test that refusal. The
LANHE `.cex` is the exception since 20 October 2026: it is read natively (P08g), because a
real file was decoded and its reading is checked against the tester's own counters on every
file. Since 20 October 2026 any other file with NUL bytes in its first 64 KiB, and no
UTF-16 or UTF-32 byte-order mark, is refused as `binary_content` before the layout
detection reads it as text; the detection ends a row at any line ending (a lone carriage
return included, as the reader's `splitlines()` does) and honours UTF-16 and UTF-32
byte-order marks (`tests/test_readers_unreadable.py`).

## 6. Reader changes P08d needed, each with a test

All in `electrochem/readers/`; the engine is untouched and readers still import no
engine module.

1. `cells.py` (new): clock-format durations (`hh:mm:ss` unit) and Excel time cells read
   back as elapsed seconds.
2. `reader.py`: Excel header located per sheet by `header_contains`; empty trailing
   fields beyond the header dropped; empty step-type cells treated as missing values;
   one unsigned throughput counter (`step_cumulative_capacity_ah`) given direction by
   the current; capacity semantics checked for consistency rather than equality;
   interleaved tables refused; headerless continuation sheets warned about.
3. `checks.py`: the voltage-trend sign check; the counter check skipped without
   sustained current and floored at a tenth of the throughput.
4. `propose.py`: the largest table of a workbook is the time series, found again by
   its column names; clock columns get `hh:mm:ss`; Maccor-style counters proposed as
   step throughput; a generic `Capacity` beside charge and discharge counters not
   proposed as a net counter; interleaved tables block.
5. `registry.py`: a built-in profile claims a file only if the kind matches, a sniff
   string is present, and its time, current and voltage columns resolve.
6. `bridge.py`: no mode array from a vocabulary that never names a constant-voltage
   stage.
7. `profile.py`: the `hh:mm:ss` unit; `step_cumulative_capacity_ah` and
   `cycle_cumulative_capacity_ah` force their own semantics.

The typed `ImportProfile`, `Conventions`, `Binding` and `Layout` APIs are unchanged.

## 7. What remains unverified

- Any Arbin underscore-name CSV with real cycling data (only the column names are
  verified on a real file of that dialect).
- Arbin, Neware and Landt workbooks split across several sheets (concatenation and
  the Landt headerless continuation are covered by synthetic tests only).
- Neware Excel variants other than the 10-column record sheet; Neware Chinese-locale
  headers.
- Discharge behaviour of the BaSyTec and Novonix exports (no discharge in the files).
- PEC's 2026 clock dialect under current; Maccor's `Test (Min)` dialect under current.
- Every binary format.
- Digatron, Gamry cycling, Ivium, Solartron and any instrument not in the table.

## 8. Export variants: the same instrument, another header (P08e, 20 October 2026)

Arbin's MITS, LANDdt, Neware's BTS and the others let the user choose at export time which
columns to write, in what order, in which units (A or mA, Ah or mAh, V or mV, s, min or h)
and under which sheet name. Two exports of one test from one software rarely share a header,
so recognition cannot depend on the exact header. The rules, each with a test in
`tests/test_readers_variants.py`:

1. **A column is matched by its name, the unit aside.** A binding written as `Current(mA)`
   matches a header `Current(A)`; the header's own unit is what is read. Case, spacing and
   punctuation differences in the name are ignored (`Test_Time` is `Test Time`). A column
   with no unit in its name keeps the unit the profile declares (`reader._match`).
2. **Only the time, current and voltage columns decide recognition.** Extra columns are
   ignored, optional ones (capacity counters, step and cycle numbers) are used when present
   and left out when absent, and the order never matters. Without the capacity counters the
   capacity is the trapezoid of the sampled current, and the report says so; with them, the
   instrument's counter is preferred as before (M01). The Arbin and Landt sniff strings accept
   any time unit (`Test_Time(`, `TestTime/`).
3. **Workbooks are found by content, not by sheet name**: `Channel_11_1`, `Channel_1-1`,
   `Record` or `Sheet1` all work; a `Global_Info`, `Statistics` or `Cycle` sheet with another
   header is skipped.
4. **A learned profile claims later exports by the same rule** (`registry.claims_saved`): the
   exact header fingerprint is only the fast path. A unit stated in the header is never frozen
   into a learned profile (`source_unit` stays empty), so the next export in another unit is
   read as its header says; a unit the person had to supply (`Amps` with no unit) is declared.
5. **A renamed required column asks again, from the saved profile.** The proposer attaches the
   saved profile sharing the most bound columns (`Registry.nearest`, at least one of time,
   current, voltage) as `Proposal.prior`; the review page fills in its columns, sign, step
   types, capacity semantics, cycle base, evidence and instrument name, ticks Remember, and
   asks the person to confirm and to choose the one column it could not match. Saving moves the
   profile on to the new column name.
6. **Two saved profiles claiming one file is an ambiguity, never a silent choice.**
7. **Several channels in one workbook are refused, not merged** (`sheets_not_continuous`): sheets
   with one header are read as one record only while the test clock runs on from sheet to
   sheet, which is how Arbin and Neware split a long record; a sheet whose clock starts again is
   another channel or test.

Verified on re-exports written from the shipped Arbin Excel file (subset, reorder with extra
columns, mA/mAh/min, other sheet names with a Global_Info and a Statistics sheet, CSV subset,
CSV in mA and mV) and from the shipped Landt workbook (A/mV/Ah/s, subset with extra columns,
another sheet name and order): every variant is recognised by the same profile with no
question, the time, current and voltage arrays are equal to the original's to 1e-9, and the
branch capacities are equal on the same basis. Not verified: a real second export from the
same instrument (none available); Neware and Maccor variants beyond their shipped dialects.


## 9. Large files (P08f, 20 October 2026)

A cycler export of several hundred megabytes (an Arbin CSV of millions of rows) or a workbook of
a million rows is read with memory that follows the number of rows times the number of bound
columns, not the size of the file, and gives exactly the result the reader gave before.

**What streams.**

- Text: the file is decoded in blocks of 4 MiB by an incremental decoder; the concatenated
  blocks are the text the whole-file decode gave, and each block is cut after its last line feed
  (never inside CR LF), so lines break exactly where `str.splitlines` broke them. The byte-order
  mark, NUL check (first 64 KiB) and encoding-damage check (first 20 000 characters) look at the
  same bytes and characters as before. A first pass stops at the header line; the second passes
  every row through the `csv` module once, fed line by line as it was fed before, and hashes the
  file (SHA-256) on the way.
- Workbooks: each sheet's rows come from openpyxl's read-only mode a chunk at a time. A sheet
  without the header is read only as far as the header search (100 rows) and the headerless
  check (50 rows) look; the time-span check across sheets (`sheets_not_continuous`) is kept per
  sheet while streaming. `workbook.open_workbook` sizes each sheet from parser start events: for a
  sheet that declares no dimension, openpyxl otherwise parses the whole sheet once at load time
  before the first row is read (it waits for the end of `sheetData`). The dimension found is the
  same; every workbook Excel saved declares one, so this matters for dimension-less files only
  (openpyxl's write-only output, some instrument software).
- What is kept: every numeric column a binding can use, as float64 built chunk by chunk; the
  step-type column as a list of strings that share one object per distinct value; clock-format
  columns parsed per token by `cells.parse_duration`; for the shape checks only counts (a
  histogram of row widths, rows wider than the header with and without a value beyond it,
  values under each nameless header column); the first 200 data rows (decimal mark and
  grouping, decided as before) and the unit row. Which columns to keep is found by running the
  binding loop itself against the header, for every width the header can still take.
- Numbers are converted a chunk at a time by `float()` (numpy's object-to-float64 cast), where
  the chunk provably gives the same values as the per-token rule (`reader._numbers_fast`: no
  whitespace inside a token, ASCII after the Unicode minus and decimal-mark replacements, no
  `n`, `N` or `_`). Otherwise the chunk is split into pieces of 1024 rows and a piece that still
  cannot be vouched for is read token by token by the original `_to_float`, which also counts
  the unreadable tokens (`invalid_tokens`, `column_mostly_unreadable`, `column_all_invalid`).

**Equivalence.** `tests/test_readers_reference.py` compares the reader with a reference captured
from the reader before the change (`scripts/capture_reader_reference.py`, stored in
`tests/fixtures/reader_reference/`): all 21 files under the seven vendor directories (profile
identified, table or refusal, the unsigned re-read of the two rest-only Maccor files, and the
proposal), the 14 BioLogic text exports read through the generic engine, and 299 synthetic
cases (`tests/reader_corpus.py`: line endings, encodings and byte-order marks, NUL bytes,
encoding damage, comment lines, unit rows, quoted fields, every number format, grid shapes,
clock durations, step types, workbooks with several sheets, and the 200 dialects of the fuzz
sweep). Every array is identical (NaN equal to NaN, same dtype), every finding identical in
code, severity, message, detail and order. The corpus is also read with blocks of 5 bytes and
chunks of 3 rows; nothing changes.

**Measured** on this machine (2 cores, 7 GB; peak resident memory is the reading process's own
high-water mark, VmHWM; the interpreter and imports account for about 42 MB of each figure):

| File | Rows x columns | Size | Before P08f | Streaming reader |
|---|---|---|---|---|
| Arbin CSV, synthetic (`tests/test_readers_large.py`) | 2 000 000 x 14 | 273 MiB | 3940 MB, 25.7 s | 322 MB, 11.7 s |
| the same experiment | 500 000 x 14 | 67 MiB | 1008 MB, 6.7 s | 152 MB, 2.9 s |
| Arbin workbook, no dimension declared | 200 000 x 15 | 12.5 MiB | 291 MB, 45.8 s | 118 MB, 19.8 s |
| Arbin workbook, no dimension declared | 1 000 000 x 15 | 63 MiB | not measured | 257 MB, 107.7 s |
| the same, dimension declared (stored uncompressed) | 1 000 000 x 15 | 572 MiB | refused (`file_too_large`, then 512 MiB) | 254 MB, 106.7 s |

Recognising the 2 000 000-row CSV (`Registry.identify`) takes 0.6 s, and proposing a mapping for
it as an unknown file 3.5 s.

**What openpyxl's speed means in practice.** A workbook is read at about 7 microseconds per cell
(about 107 microseconds per row of 15 columns): a full Excel sheet of a million rows takes close
to two minutes, almost all of it in openpyxl's XML parsing, whatever the reader does with the
rows. Memory stays bounded. For a large record, a CSV export of the same test reads more than ten
times faster per row (2 000 000 CSV rows in 11.7 s).

**Progress.** `read(path, profile, progress=None)` calls `progress(rows_read, bytes_read,
bytes_total)` once per chunk of 16 384 rows and once at the end (`bytes_read == bytes_total`).
For a workbook, `bytes_read` is estimated from the rows read and the dimensions the sheets
declare. The window does not use it yet (handoff P08f).

**The proposer** finds the table in the first 8 MiB of a text file (whole lines) or the first
2000 rows of each sheet (a larger sheet is sized from its declared dimension), which is also all
the registry reads to recognise a file. It measures the conventions (sign and range of the
current, counter behaviour, first cycle number, time span, step-type values) on the first
200 000 data rows. When the table is longer, `Proposal.measured` holds `rows_measured` and
`rows_total_estimate` (lines after the header of a text file, rows declared after the header of
the matching sheets), `rows` is that estimate, and a question says that the rest of the file was
not measured. A file within those limits gives exactly the proposal it gave when it was read
whole.

**Limits.** `MAX_BYTES` is 2 GiB, a guard against a wrong file rather than a memory bound. Memory
still grows with rows times bound columns (8 bytes a value), and the step-type column with 8
bytes a row plus its distinct values. A layout with `header_row` below 1 (and no
`header_contains`), a negative `unit_row` or a negative `skip_rows_after_header` is refused
(`invalid_layout`): the whole-grid reader indexed its row list with these, so `header_row=0`
took the last line as the header. A corrupt worksheet that the reader skips is no longer parsed
to its end, so damage past its first 100 rows no longer raises. The proposer's delimiter choice
counts consistent rows in the 8 MiB it reads, not in the whole file.
