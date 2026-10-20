# P08a: Import failure-mode register and the universal-import claim

Status: **implemented and tested** in `electrochem/readers/` (merged 19 October
2026; the reader tests are `tests/test_readers_*.py`). Validation of the built-in
profiles against real files from non-BioLogic instruments is recorded separately
in `docs/P08d_Instrument_Compatibility_Matrix.md` (written 20 October 2026); a
profile not shown there as verified on a shipped file is a declaration checked
only as far as that file says.

Date: 2026-10-19. Extends `P08_Multi_Instrument_Import_Specification.md`.

---

## 1. What "universal for all cyclers" can honestly mean

The request was for a tool that works for every cycler with no room for error.
Two halves, and they need different answers.

**The reachable claim.** Every battery cycler on the market can export
delimited text or a spreadsheet. A reader that handles arbitrary delimited text
and Excel, and that is told four things no file states about itself, can
therefore read any cycler's data. This is implemented and tested.

**The claim that would be false.** That the tool recognises every cycler out of
the box. Recognising an instrument means knowing its column names, and writing
those from memory for an instrument whose files have never been seen produces a
profile that fails *silently*, the single worst failure mode available, and
the one this project's standards forbid ("Do not claim universal EC-Lab
compatibility"; "Never invent citations or claim to have read inaccessible
material"). The same reasoning forbids inventing a Land or Digatron profile
from memory.

So the design inverts the usual approach. Instead of shipping guessed profiles,
the tool reads an unknown file, proposes a mapping with its reasoning shown,
states what it measured, asks only what the file genuinely cannot say, and
saves the answers against a fingerprint of the header. The second file from
that instrument needs no questions. The instrument is learned once, from
someone who has the ground truth, and the evidence is recorded in the profile.

What this means in practice:

| Situation | What happens |
|---|---|
| BioLogic `.mpt` / `.mpr` | Existing validated reader. Unchanged. |
| Arbin (CSV, Excel, .res table CSV), Neware (Excel, CSV), Maccor (five text dialects), BaSyTec, Novonix, PEC, Landt | Built-in profiles; `docs/P08d_Instrument_Compatibility_Matrix.md` says which are verified on a shipped real file and which only on inspected files or by recognition. |
| Any other cycler, text or Excel export | Proposer maps it, asks what it cannot determine, learned on confirmation. |
| A binary format with no library (`.res`, `.nda`) | Refused with a clear message: export to text first. Not silently mishandled. |

The honest summary line for the README and the paper: *any cycler's text or
spreadsheet export can be analysed; the instruments listed as verified in the
compatibility matrix are recognised automatically, and any other instrument is
learned from one file.*

---

## 2. The one property the layer is built to have

> For a file whose true capacity is known by construction, the reader either
> raises `ImportFailure` naming every problem it found, or returns a table
> whose capacity equals the constructed truth. It never returns numbers that
> are merely plausible.

A silent wrong answer is the only unacceptable outcome, because it is the only
one that cannot be detected downstream. A refusal costs the researcher five
minutes; a wrong capacity costs a retracted figure.

`tests/test_readers_fuzz.py` asserts this across 200 randomised dialects
(delimiter, decimal mark, encoding, byte-order mark, preamble length, trailing
delimiter, time unit, current unit, sign convention) plus an exhaustive sweep of
the combinations that interact. 150 of the 200 must be read correctly rather
than refused, so the property cannot be satisfied by a reader that refuses
everything.

---

## 3. The failure-mode register

46 named findings. Severity is one of:

- **refuse**: the import stops. Data would otherwise be lost or wrong.
- **warn**: the import proceeds; the warning is attached to the result and
  travels into the exported settings, not printed and forgotten.
- **note**: a decision worth recording for reproducibility.

The reader collects every finding before it decides, so a file with three
faults takes one run to diagnose, not three.

### 3.1 File and grid shape

| Code | Sev | Situation | Guard | Test |
|---|---|---|---|---|
| `empty_file` | refuse | zero bytes | size checked before reading | yes |
| `file_too_large` | refuse | beyond 2 GiB (512 MiB before P08f) | size checked before reading | yes |
| `no_data` | refuse | header, no data rows | row count | yes |
| `short_file` | refuse | fewer lines than the declared header row | line count | yes |
| `no_header` | refuse | no line contains the header markers | marker search | yes |
| `no_delimiter` | refuse | no tab, semicolon or comma on the header line | sniffer | yes |
| `missing_sheet` | refuse | a named worksheet is absent | workbook check | yes |
| `rows_wider_than_header` | refuse | fields beyond the last column name | width comparison | yes |
| `rows_narrower_than_header` | warn | interrupted final line, ragged export | missing fields become NaN and are counted | yes |
| `trailing_delimiter_in_header` | note | EC-Lab ends every header line with a tab | nameless trailing columns dropped only while every data row is narrower | yes |
| `sheets_concatenated` | note | Neware splits a long run across sheets | sheets with an identical header joined in workbook order | yes |
| `sheets_skipped` | note | a Statistics or Summary sheet | sheets with a different header excluded | yes |
| `duplicate_header_names` | note | the same name twice | recorded; binding to it refuses separately | yes |

### 3.2 Text, encoding and number formats

| Code | Sev | Situation | Guard | Test |
|---|---|---|---|---|
| `binary_content` | refuse | NUL bytes: an `.mpr`/`.res`, or UTF-16 with the BOM stripped | NUL scan before decoding, because cp1252 maps NUL to a valid character and would not notice | yes |
| `encoding_damage` | refuse | the declared encoding loses characters | replacement characters in the first 20 kB | yes |
| `byte_order_mark_overrides_profile` | note | a BOM contradicts the profile | the BOM wins: it is the file's own statement | yes |
| `decimal_mark_conflict` | refuse | `1,234.5` parsed with a decimal comma would become 1.2345 | grouping patterns detected for both conventions | yes |
| `thousands_grouping` | note | grouping separators present and removed | | no |
| `column_mostly_unreadable` | refuse | over half a column is non-numeric | fraction per column | yes |
| `column_all_invalid` | refuse | an entire column unreadable | | yes |
| `invalid_tokens` | note | scattered `XXX`, `OVERFLOW`, blanks | become NaN, counted per column; those rows are not integrated | yes |

Also handled without a finding, because they are unambiguous: UTF-8 BOM;
Unicode minus (U+2212); Fortran `D` exponents (`1.5D-03`); decimal comma with
point grouping (`1.234,5`); CRLF, LF and CR line endings; quoted fields
containing the delimiter.

Deliberately refused rather than resolved: a comma delimiter with a decimal
comma. No reader can disambiguate that file, so neither does this one.

### 3.3 Column mapping

| Code | Sev | Situation | Guard | Test |
|---|---|---|---|---|
| `missing_column` | refuse | no column for time, current or voltage | required roles | yes |
| `ambiguous_column` | refuse | two columns match one role | all matches returned, never the first by position | yes |
| `column_claimed_twice` | refuse | one column bound to two roles | claim table | yes |
| `unknown_unit` | refuse | a unit outside the closed registry | registry lookup, never a guessed factor | yes |
| `unit_dimension_mismatch` | refuse | `Current(mV)`, or `-Im(Z)/Ohm` scored as current | **every registered unit carries its physical dimension; a binding whose unit has the wrong dimension is refused** | yes |
| `unit_conflict` | refuse | the header says mA, the profile says A | both compared | yes |

The dimension gate is the structurally important one. It converts a whole class
of mis-mapping from "unlikely, given good name lists" into "impossible, given
the registry". It is what stops an impedance column becoming a current on an
EIS file, where the name alone is convincing.

A second structural guard: a header containing `control`, `setpoint`, `limit`,
`aux`, `target` or `nominal` never satisfies a measurement role implicitly. A
profile may still bind one by naming the column in full, which makes the choice
explicit and reviewable.

### 3.4 Physical and structural sanity

| Code | Sev | Situation | Guard | Test |
|---|---|---|---|---|
| `time_resets_at_every_step` | refuse | a per-step clock mapped as the test clock | refused when essentially every step boundary resets | yes |
| `time_goes_backwards` | warn | two runs concatenated; a clock correction | distinguished from the above by what *fraction* of boundaries reset | yes |
| `time_not_finite` | warn | unreadable timestamps | counted; those edges not integrated | yes |
| `time_too_short` | refuse | fewer than two readable times | | yes |
| `duplicate_timestamps` | note | consecutive rows share a time | zero-length edges contribute nothing | no |
| `sign_contradicts_step_type` | refuse | signed current disagrees with the step label | the two independent statements of direction must agree | yes |
| `ambiguous_sign` | refuse | no negative current and no usable step type | detection refuses rather than assuming | yes |
| `no_direction` | refuse | unsigned current, step type states no direction | | yes |
| `unmapped_step_type` | refuse | new firmware emits an unknown label | never silently called "other" | yes |
| `current_sign_detected` | note | what detection concluded and why | | yes |
| `capacity_semantics_mismatch` | refuse | the declared accumulator behaviour contradicts the file | measured per file | yes |
| `counter_disagrees_with_integral` | warn | the instrument's charge counter and our integral differ by >5 % | compared separately for charge and discharge | yes |
| `counter_agrees_with_integral` | note | they agree | the figure is recorded | no |
| `implausible_magnitude` | warn | current outside 1 fA to 1 kA after conversion | a mislabelled unit is the commonest real cause | yes |
| `implausible_range` | warn | voltage outside -20 V to 100 V, temperature outside -100 to 400 °C | | yes |
| `cycle_base_mismatch` | warn | the profile says cycles start at 1, the file starts at 0 | cycle labels would be off by one | yes |
| `cycle_counter_decreases` | warn | two runs concatenated | cycles must be re-indexed before pairing | no |
| `channel_column_present` | note | a Channel or Cell column | a multi-channel file must be split, which no downstream rule could detect | yes |

Charge and discharge are compared **separately** against the instrument
counter. A net comparison can be passed by two compensating errors, which is
exactly what a reversed sign produces.

The counter-versus-integral check is the only one here that works on the
researcher's own data with no known answer, so it is the one that will catch a
bad mapping in the field. On a correctly mapped file it agrees to a few parts
per million; a disagreement on constant-current data means a wrong column, unit
or sign. A disagreement confined to a sparsely sampled constant-voltage tail is
expected, and the counter is the better value there (the existing M01 decision).

### 3.5a Added in P08d, from real instrument files

Each of these was met in a real export read for the compatibility matrix
(`docs/P08d_Instrument_Compatibility_Matrix.md`); the file is named.

| Code | Sev | Situation | Guard | Test |
|---|---|---|---|---|
| `interleaved_tables` | refuse | Neware's hierarchical CSV: cycle, step and record rows in one table (cellpy `nw_regular_export_ife_example.csv`, beep `raw/neware_test.csv`) | a nameless header column filled in some rows but not all; the proposer blocks on the same test | yes |
| `trailing_delimiter_in_rows` | note | every data row ends with a tab the header lacks (Maccor, cellpy `maccor_002.txt`) | empty fields beyond the header dropped; a value there still refuses | yes |
| `step_type_missing` | warn | a row with no step type in an unsigned-current file (a last line cut off mid-number, cellpy `maccor_two.txt`) | that row's current is not used; an empty cell is missing data, not an unknown vocabulary | yes |
| `current_sign_contradicts_voltage` | warn | the charge-positive current and the voltage trend disagree over most steps | charging raises the terminal voltage; steps with one current sign vote by their end points | yes |
| `current_sign_agrees_with_voltage` | note | they agree; the vote counts travel in the report (`sign_vs_voltage`) | | yes |
| `counter_not_compared` | note | no step carries current over three or more rows (an open-circuit PEC file whose counter creeps by leakage the log cannot show) | the comparison is skipped, not failed | yes |
| `headerless_sheet_not_read` | warn | a workbook sheet with no header but record-like rows after the table's sheet (Landt continuation sheets, P08 trap 6) | rows are not appended on a guess; no real multi-sheet Landt file was available | yes |

Changed in P08d:

- `capacity_semantics_mismatch` now refuses only a declaration the file
  contradicts. The reader lists every counter behaviour the file leaves open
  (`capacity_semantics_consistent`): a counter that never falls in a one-cycle
  file is test- or cycle-cumulative, and no row decides. Before, such a file
  was reported as test-cumulative and a correct cycle-cumulative declaration
  was refused; the real multi-cycle Arbin exports reset per cycle.
  `capacity_semantics_verified` is true only when the declared behaviour is the
  only one left.
- The counter comparison divides each direction's difference by no less than a
  tenth of the throughput of both, so a direction carrying almost nothing (such
  as the single boundary increment of 2e-5 Ah in discharge seen in PyProBE's
  Arbin sample, a file that otherwise only charges) cannot warn on its own.
- A single unsigned throughput counter (BDF `step_cumulative_capacity_ah`,
  Maccor's `Amp-hr`) is turned into signed increments using the
  charge-positive current of each row.
- A time column may be declared `hh:mm:ss`, a clock-format duration (Maccor
  `0d 00:00:5.05`, Neware `00:01:00`, PEC `0:00:10.000`); Excel time cells are
  read back as elapsed seconds whether openpyxl returns a time, a time span or
  a 1900 date (Neware `Total Time` past 24 h; P08 trap 3).
- A built-in profile claims a file only when it is the same kind (text or
  workbook), one of its sniff strings is present (whole column names where
  needed) and its time, current and voltage columns resolve; two sibling
  dialects can no longer both claim one file.
- A step-type vocabulary that never names a constant-voltage stage (Maccor,
  BaSyTec, Landt, Neware as observed) produces no mode array, so no CC/CV split
  is reported for it rather than a constant-voltage share of 0 %.

### 3.5 Four codes without a direct test

`thousands_grouping`, `duplicate_timestamps`, `counter_agrees_with_integral`
and `cycle_counter_decreases`. All are notes or warnings on paths exercised
indirectly. Listed here rather than papered over.

---

## 3.6 Re-exports of a known instrument (P08e)

Recognition tolerates what an export dialog changes: column order, extra and absent optional
columns, the unit written in a header, the sheet name. A saved profile claims a later export
when its time, current and voltage columns resolve; a renamed required column opens the review
page pre-filled from that profile (`Proposal.prior`). The matrix's section 8 states the rules
and the tests. What is still refused: a unit in the header that contradicts a unit the profile
had to declare (`unit_conflict`), two saved profiles claiming one file, a required column
whose name changed (asked, not guessed), and a workbook whose same-header sheets restart the
test clock (`sheets_not_continuous`: several channels or tests in one file, which read as one
cell would double the capacity; export one channel per file).

## 3.7 Large files (P08f)

The reader streams: rows are read once, a chunk at a time, and only the columns a binding can use
are kept (matrix section 9). Every finding above keeps its code, its severity, its message and its
place in the order of findings; `tests/test_readers_reference.py` compares every one of them, for
every shipped file and a corpus of 299 synthetic cases, with a reference captured from the reader
before the change.

| Code | Sev | Situation | Guard | Test |
|---|---|---|---|---|
| `invalid_layout` | refuse | a profile layout with `header_row` below 1 (and no `header_contains`), a negative `unit_row` or a negative `skip_rows_after_header` | refused by name before reading; the whole-grid reader indexed its row list with these, so `header_row=0` silently took the last line as the header | yes |

Changed in P08f: `file_too_large` is now 2 GiB, a guard against a wrong file rather than a memory
bound (2 000 000 rows of an Arbin CSV, 273 MiB, read with a 322 MB peak).

## 4. Limits that remain, stated plainly

1. **Real-file validation is per instrument and recorded in the compatibility
   matrix** (`docs/P08d_Instrument_Compatibility_Matrix.md`, 20 October 2026).
   Every built-in profile there names the real file it was checked against;
   the matrix says which of those files are shipped and tested in the
   repository and which were only inspected.
2. **Binary formats other than `.mpr`.** Arbin `.res`, Neware `.nda`/`.ndax`
   and Maccor's binary outputs are refused with an instruction to export text.
   Adding them means adding a dependency per format, each evaluated for
   maintenance and licence first.
3. **Multi-channel files are detected, not split.** A file holding more than
   one cell is noted; splitting it is P08c.
4. **A single step boundary cannot distinguish a per-step clock from a
   concatenation.** With only one reset there is no evidence either way, so the
   reader warns rather than refusing. Documented rather than hidden.
5. **Plausibility bands are conventions, not physics.** They are wide enough to
   pass any real battery or electrolyte measurement and narrow enough to catch
   a three-order-of-magnitude unit error. They warn; they never correct.
6. **The proposer's synonym register reflects the headers in the public corpus
   and in documentation**, not an exhaustive survey. An unmatched column is
   reported as unmapped, never guessed.

---

## 5. Where it lives

`electrochem/readers/`: `profile.py` (typed profile, closed unit registry with
dimensions), `reader.py` (collect-then-refuse generic reader), `checks.py`,
`propose.py` (the proposer and the folder screen `looks_tabular`),
`registry.py` (saved profiles by header fingerprint), `builtin.py`,
`bridge.py` (`is_eclab`, `to_table`). Tests: `tests/test_readers_import.py`,
`test_readers_robustness.py`, `test_readers_fuzz.py`,
`test_readers_differential.py`, `test_readers_workflow.py`.

Five defects were found by the new tests during the prototype, all fixed. Two of
them, the impedance column scoring as current and the BOM silently unbinding the
first column, would have produced plausible wrong numbers rather than errors.
