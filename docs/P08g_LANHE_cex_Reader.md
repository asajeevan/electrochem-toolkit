# P08g: LANHE (LAND) `.cex` files, read natively

Status, 20 October 2026: **implemented and software-tested; verified on one real file by four statements inside that file; not yet compared with LANHE's own Excel export of the same file.** Reader: `electrochem/readers/lanhe_cex.py` (`lanhe-cex` 1.0.0). Tests: `tests/test_readers_cex.py` (28 tests on synthetic files; each of 26 deliberate faults put into the reader made them fail), `tests/test_degenerate_pairs.py` (each of 14 deliberate faults in the pairing rule, the figure fixes and the app wording made it or the app test fail). The real file is a user's and private: it and every value from it stay out of the repository; its regression check lives beside it.

## 1. Why a native reader

The `.cex` is the binary file LANHE's battery testers (sold by Wuhan LAND) write as a test runs. LANHE publishes no description of it. Until 0.8.0 Cyclara refused it with an instruction to export Excel, which its `landt-xlsx` profile reads. A user's real `.cex` (private; rest, constant-current and constant-voltage steps) arrived on 20 October 2026, and the instruction was to read it in Cyclara directly.

Sources. No published specification was found. One open project decodes the format for per-cycle capacities (`culture-medium/battery-data-tool`, `land_extract.py`, v0.5.7, inspected at commit 1037eb0): it carries no licence, so none of its code is used; its description of the header, the unit signatures and the 16-byte record helped locate fields, and every fact below was established again on the real file. That project reads capacity and energy only; it does not decode voltage, current or time, and it refuses the constant-voltage step type found here.

## 2. The format, as read

Little-endian throughout; offsets in bytes.

| Where | What | Status |
|---|---|---|
| header 0 to 3 | magic `10 11 09 88` | seen; checked on every file |
| header 4 to 7 | layout code `07 00 04 00` (16-byte records with float32 counters) | the only layout read; others refused |
| header 16 to 19 | test start, Unix seconds (uint32) | equals the first step's start unit |
| header 24 to 27 | range codes (two uint16): voltage `0xE005`, current `0xC00A` | scales below; other codes see section 3 |
| header 28 to 31 | active mass, g (float32) | another project's reading; 0 in the real file (not set); offered, never applied |
| units after the header | 16 bytes each, told apart by the first word | |
| `FFFFAAAA` ... `FFFFBBBB` | a block: type in the low 16 bits of word 1, payload length in the high 16, then the payload, then an end unit repeating words 1 to 3 | framing checked; types 0xAA, 0x55, 0x78 and 0x13 (step plan) seen; skipped |
| `FFFFCCCC`/`FFFFCCCD`, kind 0x22 | step start: word 1 high 16 bits the tester's step number (bit 15 set); word 2 the step type (low byte), a flag byte, the setpoint in counts (high 16 bits); word 3 the start, Unix seconds | read |
| kind 0x44 | cycle marker: direction flag; the tester's cycle number (from 0) and step number | listed per step, not used |
| kind 0x33 | status event: code 0x0201 at the start, 0x0101 at the end, 0x0401 with a step number | other codes refused |
| kind 0x88 | once, before the step plan | listed, not interpreted |
| kinds 0xB1, 0xB2 | retention references (another project's reading) | skipped with a note; not seen here |
| any other unit | data record: `uint32` time in 0.01 s since the test start; `int16` voltage counts; `int16` current counts (charge positive); `float32` capacity counter, Ah; `float32` energy counter, Wh | read |

Step types: `0x70` rest, `0x03` constant-current charge, `0x02` constant-current discharge, `0x05` constant-voltage charge. Any other type is refused, naming it.

Scales: full scale is reached at `0x7E00` = 32 256 counts. Voltage: 5 V / 32 256 per count. Current: 1 mA / 32 256 per count.

Counters: they restart at zero with each step, except that a step continuing the step before it in the same direction carries them on (the constant-voltage step after the constant-current one). A step's first increment includes the charge passed between the previous step's last record and its own first record (a fraction of a second in the real file), so the counter is the tester's charge, and the trapezoid of the logged current misses those intervals (a few parts in 100 000 there).

## 3. Evidence for each fact, and the checks made on every file

Established on the real file from four independent statements it makes in physical units, none of which the decoding assumed:

1. **Time unit.** The step-start units carry the tester's clock in whole seconds. The first record of every step follows its step's start by less than a second, over several hours: record time against clock time has a slope of 1 to within a few parts per million. A 0.01 s unit is the only one that fits.
2. **Current scale.** Over the intervals of each current-carrying step after its first, the trapezoid of the decoded current equals the increments of the float32 capacity counter (in Ah) to within 0.01 % on every step with 1 mA / 32 256 per count.
3. **Voltage scale.** On the same intervals, the trapezoid of decoded voltage times current, divided by the current's own ratio, reproduces the float32 energy counter (in Wh) to within 0.001 % with 5 V / 32 256 per count, over steps spanning very different voltages (so no offset).
4. **The step plan.** The plan block holds the programmed current (in A) and voltage limits and setpoints (in V) as float32. Under these scales the setpoint counts in the step-start units equal them to the rounding of one count; each constant-current step ends at the first record past its programmed voltage limit; the constant-voltage step lasts exactly its programmed time; and a step that began above its own voltage limit ended at its first check, after one recorded interval.

The capacity counter could in principle be in mAh and the current scale a thousand times smaller; the programmed current in the plan (which would then have to be in mA too, an implausibly small current for a 1 mA channel), the range code and the other project's reading (verified there against LANHE's exports) all say Ah.

Every file opened is checked the same way, and the reader refuses rather than reads when a check fails:

| Check | Rule | Refusal code |
|---|---|---|
| clock | record time against the step-start clock over at least a minute: slope within 1 % of 1; an offset above 2 s is warned (a clock change or an unmarked pause) | `cex_time_base` |
| current | trapezoid of the decoded current against the capacity counter, constant-current steps, intervals after each step's first, at least 20: within 0.2 % (1 % when only constant-voltage steps qualify) | `cex_scale_check` |
| voltage | the same for voltage times current against the energy counter, steps whose voltage stays positive, normalised by the current's ratio | `cex_scale_check` |
| direction | the net current of every step agrees with its step type | `sign_contradicts_step_type` |
| counters | finite; never decreasing inside a step; each step starts at zero or carries the step before it (anything else warned and read as a restart) | `cex_counter_decreases`, `cex_counter_invalid` |
| structure | blocks end where their length says; no unknown unit; no record before the first step start; time never decreasing | `cex_block`, `cex_unit`, `cex_records_before_step`, `cex_time_backwards` |

Range codes. `0xE005` (5 V) and `0xC00A` (1 mA) are verified. Another code of the same family is decoded by the family's rule (voltage `0xE0nn`: nn V; current `0xC0nn`: nn x 0.1 mA) **only when this file's own counters confirm the scale it gives** within the tolerance above, and the import says so (`cex_range_confirmed`); a file that carries too little current to confirm it is refused (`cex_range_unverified`). A code outside both families is refused.

## 4. What Cyclara does with it

The engine receives the same Table as from any reader: time (s), current (A, charge positive), voltage (V), the executed step number (1, 2, 3, ... in the order the steps ran, so every boundary shows even when a program repeats a step), the mode (1 constant current, 2 constant voltage, 3 rest) and the charge increments from the counter. No native cycle number is passed: Cyclara pairs branches itself (M01 section 6), and the tester's cycle markers are listed per step. The tester's step table is rebuilt from the file and exported as `instrument_steps.csv` (step, tester's step number, type, setpoint, start on the tester's clock, records, first and last time, voltage at both ends, how the counter started, counter values at the end, notes). `settings.json` carries the reader, its scales and every check under `import`.

Because the step types name the direction and the current's sign agrees on every step, the app answers "which current direction charges the cell" from the import and shows why; the configuration (cell voltage or half-cell) and the mass are still asked.

## 5. Found while checking the outputs of the real file

- **A step that ended at once.** A charge step to a voltage limit, started on a cell already above that limit, ran for one recorded interval (two records) and carried a few thousandths of a per cent of the charge of the long discharge after it. Charge-first pairing put the two together: a coulombic efficiency of millions of per cent and a hysteresis of more than a volt. M01 section 6 now withholds the efficiency, the energy efficiency and the hysteresis of such a pair, keeps its capacities and its retention, and says why in the cycle's note; the app asks whether each cycle starts with a charge or a discharge when a file opens with such a branch.
- **The last branch.** The file ends at the end of a constant-voltage step that ran its programmed time, followed by the tester's end-of-test event. M01 treats a branch that reaches the end of the data as interrupted, so the only real cycle (the discharge and the charge after it, with discharge-first pairing) has no coulombic efficiency in Cyclara. Whether the end-of-test event can be taken as "the run ended as programmed" is not established (a run stopped by hand may write the same event), so the rule is unchanged; the branch capacities are given.
- **Figures.** The dQ/dE map's two panels share a cycle axis, but each set it to its own cycles, so when the charge curves started a cycle later than the discharge curves the charge panel showed nothing; both now span the cycles of either. A single cycle was labelled 1.50, 1.75, ... in the map and the surfaces; now its own number. The summary figure's bin-width note could sit over a curve; it now takes a free corner or a band below the data. Figures and the app drew a hysteresis computed from the two averages even where the cycle's own value was withheld; they now draw the cycle's value.

## 6. Not verified, and what would verify it

- **LANHE's own export of the same file.** Exporting this `.cex` from LANHE's software to Excel (its Record, Step and Cycle sheets) and comparing it row by row with Cyclara's reading is the independent check still missing. The four internal statements above make a misread scale very unlikely; the export would also settle the tester's own cycle numbering and how it names the constant-voltage step.
- **Other files.** Other channels (other range codes), other layouts (`01 00 04 00`, and `02 01 01 00` with counters instead of float32 values), constant-voltage discharge, pauses and resumes, retention references, temperature channels, and files copied while the test was running (read with a warning; synthetic only so far).
- **The active-mass field** has not been seen set in a real file.

## 7. Refusal messages

Every refusal names what was found (the code, the offset or the step) and ends with the remedy: export the run to Excel from the tester's software, which Cyclara reads (`landt-xlsx`), and send the `.cex` with its export so the reader can be extended on evidence.
