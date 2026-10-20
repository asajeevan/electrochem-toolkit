# P08: multi-instrument import. Specification, decisions and implementation method

Status: **implemented** in `electrochem/readers/` (P08a, the generic layer, the typed
profile, the proposer, the registry and the import review page in Cyclara) on
19 October 2026, merged with 160 reader tests. P08b (built-in profiles checked on
real files) and P08d (the compatibility matrix) are recorded in
`docs/P08d_Instrument_Compatibility_Matrix.md` when that file exists. This text is
the specification as written before implementation; where the two differ, the code
and its tests are the record. Written 19 October 2026.

**Corrections from P08d (20 October 2026), measured on real files** (details in
`docs/P08d_Instrument_Compatibility_Matrix.md`): Arbin's charge and discharge
counters reset at each **cycle** in every multi-cycle Arbin export read (the single
file behind "cumulative over the test" in section 2 had one cycle, which cannot
distinguish the two); Maccor writes at least five text dialects, and in one of them
(the 12-line header block) the unlabelled `TestTime` is in **minutes**; Neware's
flat CSV writes `Cumulative Time` as hh:mm:ss at 1 s resolution, and its older
hierarchical CSV interleaves cycle, step and record rows and is refused.

---

## 0. The question

The toolkit reads BioLogic EC-Lab files. What should it do when the data comes
from another cycler, or arrives as a text file or an Excel sheet from someone
else's instrument?

Two things were researched before designing: the state of the open-source
parser ecosystem, and the actual byte-level structure of the vendor exports.
Both were done against real files and real source code, not from
recollection. Section 9 lists what could not be verified.

---

## 1. This is additive, not a rewrite

Every reader in the toolkit already ends at one object: the measurement table
holding SI arrays (time, current, potential, step, mode, direction flag, error
flag, cycle, instrument charge, per-row increment, temperature). Segmentation,
the cycling engine, the CV engine, differential capacity, the figures and the
Origin export work only on that object. None of them has seen a BioLogic file.

Supporting another instrument is therefore one function, bytes to table, and no
change anywhere downstream. The size of the work is set by the conventions, not
by the parsing.

**Architectural rule to enforce mechanically:** readers must not import the
engine and the engine must not import readers. A test asserting the module
graph keeps the blast radius of a new instrument at zero.

---

## 2. What actually differs between instruments

Verified by opening real export files from Arbin, Neware, Maccor and Land, and
by reading the source of the parsers that handle them. Sources in section 10.

| | Arbin | Neware | Maccor | Land | BioLogic |
|---|---|---|---|---|---|
| Current signed | yes, + = charge | yes, + = charge | **export-dependent** | yes, + = charge | yes |
| Direction source | current sign only (no status column exists) | `Status` / `Step Type` | `State` (C/D/R), or sign | `State` (R, C_CC, D_CC) | `ox/red` plus sign |
| Capacity counter | `Charge_Capacity` + `Discharge_Capacity`, **cumulative over the test** in the file measured | split columns, **reset every step** | single `Amp-hr`, **resets every step** | single `Capacity/mAh`, **resets at every state change** | `dq`, a true **per-row increment** |
| Time | `Test_Time(s)` seconds | step time only in the binary; Excel `Total Time` as a clock value | seconds, several header spellings | **hours** | seconds |
| Header row | fixed | fixed | **1, 2, 3 or 12 preamble lines** | sometimes inside the data region | declared in line 2 |
| Column naming | **three incompatible families** | at least three variants | at least three variants | several layouts | stable |

Seven traps worth writing into the code as named cases:

1. **`"cc_discharge".endswith("charge")` is true.** A direction test written
   that way marks every discharge as charge. This was a real defect in the
   prototype, caught by a cross-dialect test.
2. **Arbin's only underscore-free header** is `Internal Resistance(Ohm)`, in an
   otherwise underscore-joined set. A parser keyed on the consistent spelling
   silently misses it.
3. **Neware Excel `Total Time` rolls over into a datetime past 24 h**, so a row
   reads `1900-01-01 07:08:01.5` meaning 31 h 08 m. Parsed as a clock time it
   silently loses whole days.
4. **Neware unit labels cannot be trusted**: a maintainer of another tool
   records a machine whose column says mAh and whose values are Ah.
5. **Maccor's current may be unsigned**, with direction only in `State`. Two
   existing libraries disagree about which to assume. Neither assumption is safe.
6. **Land continuation sheets carry no header row**; a reader that assumes one
   drops the first data row of every continuation sheet.
7. **Capacity semantics are the silent killer.** Getting step-cumulative versus
   test-cumulative wrong does not raise; it changes every capacity in the
   dataset. One mature library carries an explicit enum for this with that exact
   warning attached, which is independent confirmation that this is the field
   that matters most.

---

## 3. Decision: adopt the Battery Data Format vocabulary

The LF Energy Battery Data Alliance publishes the **Battery Data Format (BDF)**,
an Apache-2.0 standard for cycler time-series data: 63 canonical quantities with
machine-readable names, fixed canonical units, an ontology extending BattINFO,
and a published **mapping sidecar schema** (target quantity to source column,
with `source_unit`, `scale`, `offset`, and a `source_locator` carrying
`sheet_name`, `header_row`, `skiprows` and `usecols` for spreadsheets).

That mapping sidecar is, field for field, the import profile this package would
otherwise have invented. Adopting it costs nothing and buys three things: a
reviewed vocabulary, interoperability with other people's tools, and a natural
export format so the author's data leaves the toolkit in a standard shape.

**Decisions.**

- Profile role names are BDF machine names (`test_time_second`,
  `current_ampere`, `voltage_volt`, `step_id`, `cycle_count`, `step_type`,
  `charging_capacity_ah`, ...).
- Canonical sign convention is BDF's: **charge-positive**. Every reader
  normalises to it at the boundary and records what it did.
- The toolkit gains a BDF writer so results are portable (not yet written).
- BDF is **not** adopted as a runtime dependency. It is version 0.2.0rc2, its
  own documentation warns that names may change without a major version bump,
  and its reference implementation carries rdflib, pint and an ontology
  snapshot, which is a lot of weight for an offline desktop tool.

**What BDF does not cover, and the profile must therefore add:** the current
sign convention, where direction comes from, the capacity counter's reset
behaviour, and the cycle numbering base. BDF standardises the vocabulary, not
the conventions. Those four fields are exactly the dangerous ones.

---

## 4. Decision: which third-party readers to depend on

Licence first, because it clears the field rather than narrowing it. The toolkit
is GPL-3.0-or-later, so it may depend on MIT, BSD, Apache-2.0 and GPL-3.0
libraries alike. Nothing here is blocked on licence grounds, and the GPL
libraries are the easiest fit, which is the reverse of the usual situation.

| Library | Licence | State (Oct 2026) | Decision |
|---|---|---|---|
| `datalab-org-galvani` | GPL-3.0+ | active, 0.6.0 on 2026-10-16 | **adopt** for `.mpr`, replacing the current pin |
| `galvani` (upstream) | GPL-3.0+ | **dormant**, no commit since 2025-07-30 | **migrate away** |
| `fastnda` | BSD-3 | active, Empa, used by cellpy | **adopt** for Neware `.nda`/`.ndax` |
| `NewareNDA` (d-cogswell fork) | BSD-3 | alive but slow | fallback if polars is unwanted |
| `NewareNDA` (SES original) | BSD-3 | **archived 2025-07-10** | do not use |
| `yadg` | GPL-3.0+ | active, independent `.mpr` implementation | **test-only cross-check** |
| `pyimpspec` | GPL-3.0+ | active | later, for EIS |
| `impedance.py` | MIT | repo alive, **PyPI release is from 2023** | prefer pyimpspec |
| `cellpy` | MIT | very active, 30 dependencies, needs Python 3.13 and pandas 3 | **read, do not import** |
| `navani` | MIT | active, closest drop-in | **read, do not import**: imposes its own cycle and state schema |
| BEEP, battery-data-toolkit, galv-harvester | Apache/BSD | no binary support, stalled, or server-shaped | no |

**Action item independent of this package.** The toolkit currently pins upstream
galvani at commit `d4a5f44`. Upstream has been dormant for about fifteen months.
The active fork has since fixed EC-Lab 11.50+ column IDs at or above 256,
registered two further column IDs, corrected the dtype search for unknown
columns, and changed unknown columns from an exception to a warning. Files
written by recent EC-Lab versions may therefore fail or mis-parse today. The
import name stays `galvani` while the distribution name changes, so the two
cannot be installed together.

**Arbin `.res` is the one genuine blocker.** Every library in this field without
exception shells out to mdbtools, or to pyodbc on Windows. For an offline
Windows-first tool that is a packaging decision, not a library choice, and it
should be settled before anything depends on it. The Arbin CSV and Excel exports
need none of that and cover the same data.

---

## 5. The design

### 5.1 Three layers

1. **Reader registry.** `electrochem/readers/`, the generic reader for delimited
   text and spreadsheets, dispatching on file contents (signature, header
   fingerprint), not on the extension. The registry records which profile
   produced each table.
2. **A typed import profile.** One declaration per instrument family, covering
   every delimited-text and Excel export with a single generic reader. Built-in
   profiles ship with the toolkit; user profiles live in a folder beside it
   (`~/.electrochem-toolkit/profiles`, or `ELECTROCHEM_PROFILES`).
3. **An import review step in the window.** For a file matching no profile: the
   first rows in a grid, dropdowns to assign roles and units, a switch for the
   sign convention, and a check that states what the tool would conclude
   before anything is written. Then the profile is saved against the header's
   fingerprint and the next file from that instrument opens straight through.

### 5.2 The profile, and why it is typed rather than a dictionary

```python
class Conventions(BaseModel):
    current_sign: Literal["charge_positive", "discharge_positive",
                          "unsigned", "detect"]
    direction_source: Literal["current_sign", "step_type"]
    capacity_semantics: Literal["per_row_increment", "step_cumulative",
                                "cycle_cumulative", "test_cumulative", "none"]
    cycle_base: Literal[0, 1]
    evidence: str = Field(min_length=10)
    step_type_map: dict[str, StepKind] = {}
    verify_capacity_semantics: bool = True
```

None of the first five has a default. A profile that does not state the sign
convention, the capacity semantics and who verified it **cannot be constructed**.
Cross-field validation refuses the incoherent combinations: unsigned current
with no status column, a status column with no mapping. The failure happens when
the profile is loaded, not when a number is published.

This is the single most important design decision in the package. Every other
protection is a safety net under it.

### 5.3 Conventions are claims, and claims get checked

Two of the declarations can be tested against the file itself, so they are:

- **Capacity semantics.** An accumulator that never decreases is cumulative over
  the test; one that decreases only at step boundaries resets there. Measured
  per file and compared with the declaration; a mismatch stops the import. This
  matters because the published descriptions of Arbin's behaviour disagree with
  each other and with the real file that was measured, and Arbin schedules can
  issue explicit resets. The claim is checked rather than believed.
- **Current sign, for Maccor.** `current_sign="detect"` makes the reader look:
  any negative current means the column is signed; none, with a usable status
  column, means unsigned; neither means the file cannot establish direction and
  the import stops rather than guessing.

### 5.4 One convention downstream

Whatever the instrument did, what leaves the reader is charge-positive signed
current in SI units, with the conversion recorded in the report. The engine then
has one convention to reason about. Normalising at the boundary rather than
threading a convention flag through the engine is what keeps a new instrument
from being able to change an existing number.

---

## 6. How to build this without errors

The hard part is not that the code might crash. It is that it might quietly
return the wrong number. Eight practices, in the order they pay off.

**1. Make illegal states unrepresentable.** Section 5.2. Most of the value is here.

**2. Never let a default carry scientific meaning.** The toolkit already refuses
specific capacity without a mass and efficiency without a declared charge sign.
Extend it: no declared capacity semantics means no instrument cross-check,
trapezoid only, and the report says so.

**3. Metamorphic testing.** For a real instrument file nobody knows the right
answer, which is the classic oracle problem in scientific software. The standard
answer is to test relations whose effect is known exactly even when the output
is not:

| Transform the input | The output must |
|---|---|
| multiply every current by k | multiply every capacity by k, leave voltage untouched |
| declare the opposite sign convention | mirror the current exactly, swap charge and discharge |
| express current in mA, declared | change nothing |
| express time in hours, declared | change nothing |
| write the file with a decimal comma | change nothing |
| thin the interior of a constant-current step | leave the integral unmoved |
| duplicate the run with time shifted | double the cycle count, repeat the per-cycle values |

These hold whatever the true capacity is, so they test a reader for an
instrument that has never been seen.

**4. Cross-dialect equivalence.** Write one synthetic experiment with an exact
known capacity, emit it in several vendor dialects that differ in units, sign
convention, direction source, capacity semantics, decimal separator and file
kind, and require identical arrays. A unit or sign error cannot affect all
dialects identically, so this catches what a single-instrument test cannot.

**5. Differential testing against independent implementations.** Three sources:
the toolkit's own validated EC-Lab reader, for any new generic path over the
same files; `yadg`, whose `.mpr` parser is an independent implementation; and
the public corpus below, which ships reference conversions of the raw files. Two
unrelated parsers agreeing on the same bytes is a far stronger validation than
agreement with oneself. Any disagreement is explained, never absorbed into a
tolerance.

**6. The instrument's own counters as the in-field oracle.** This is already
proven on EC-Lab: agreement with the charge counter to 1e-15 and with the
`Efficiency` column to 4e-6 %. Generalise it. Every reader reports its agreement
with whatever counters the file carries, and the review step shows that number
before a mapping is accepted. A wrong column mapping does not survive it.

**7. Property-based testing of the parser itself.** Generate files with random
delimiters, encodings, decimal separators, preamble lengths, blank lines,
truncated final lines, BOMs and line endings. The property is: parse correctly
or raise a typed failure. Never a silently truncated or misaligned table.

**8. Golden files with a hash manifest, and fuzzing for binaries.** The frozen
fixtures and SHA-256 manifest already in use, extended to one small golden file
per profile. Keep `.gitattributes` exempting fixtures from line-ending
conversion, which has already caused a failure once. For binary readers, mutate
a seed corpus and require a typed failure rather than a crash, a hang or
unbounded allocation.

Alongside those: mypy on the readers package, so the optional array fields have
to be handled; and a memory ceiling test, because the public corpus contains a
258 MB text export and the present text reader keeps every row as Python tokens.

---

## 7. There is a public test corpus, and it removes the main blocker

The Battery Data Alliance publishes, under CC BY 4.0:

- **Raw vendor files**, 19 files, 703 MB, from Arbin (`.xlsx`, `.CSV`), Neware
  (`.nda`, `.csv`), Maccor (`.csv`), Basytec (`.txt`), Digatron (`.csv`), Landt
  (`.csv`, `.txt`, `.ccs`), BioLogic (`.mpt`) and Novonix (`.csv`). Some contain
  **deliberate defects**, including outliers and non-monotonic timestamps.
  DOI 10.5281/zenodo.18986774.
- **Canonical BDF conversions of the same files**, with a `datasets.json` pairing
  each artifact to its raw source, converter and checksums.
  DOI 10.5281/zenodo.22230066.

This means readers for eight cyclers can be built and verified now, against an
independent reference conversion, without waiting for anyone to supply a file.
The deliberately broken files are ready-made tests for the continuity rules the
engine already has.

Zenodo is not reachable from the analysis sandbox. Either download the corpus on
the Windows machine, or allow `zenodo.org` under Settings, Capabilities.

---

## 8. Staged plan

Each stage has a gate. Nothing is called supported before its gate passes.

**P08a. The generic layer.** Reader registry, generic delimited-text and Excel
readers, the typed profile, the import review step, the agreement report, BDF
export. No vendor files needed.
*Gate:* the generic engine reproduces the existing validated EC-Lab reader
exactly on every public BioLogic file in `data/public`, and the full existing
suite is unchanged. **Done 19 October 2026** (BDF export not yet).

**P08b. Profiles, one instrument at a time**, in the order Arbin, Neware,
Maccor, Land, Basytec, Digatron, Novonix.
*Gate per instrument:* a real file parses; the arrays match an independent
conversion elementwise where one exists; the measured capacity semantics
match the declaration; agreement with the instrument's own counter is reported.

**P08c. Binary readers behind optional extras.** Migrate `.mpr` to the active
galvani fork; add `fastnda` for Neware. Decide the Arbin `.res` packaging
question or document that the CSV and Excel exports are the supported route.
*Gate:* the fork migration changes no number on the existing public corpus, and
the `yadg` cross-check agrees.

**P08d. Compatibility matrix in the documentation**: instrument, format, tested
with a real file or not, what works, what does not. The same discipline as "no
universal EC-Lab compatibility".

---

## 9. What could not be verified

Stated plainly, so nothing is built on it:

1. Neware Chinese-locale column headers. Searched for specifically; no reliable
   source found. Not guessed.
2. Autolab NOVA, VersaStudio `.par` and CH Instruments column header strings,
   and their imaginary-impedance sign conventions. One widely used library does
   not negate for any of them, which may be a bug in one or more cases.
3. The row threshold at which Arbin splits an Excel export across sheets. The
   `Channel_<ch>_<n>` naming is verified; the trigger is not.
4. Whether Arbin's capacity reset behaviour is schedule-configurable. One real
   file measured as test-cumulative, contradicting a published description. This
   is why it is measured per file.
5. Individual meanings of Maccor's `ES` end-of-step codes.

A warning for anyone mining existing libraries for column names: one widely used
Maccor configuration contains eight column names copy-pasted from its Arbin
loader that do not exist in Maccor files. Mapping tables must be checked against
real files, not inherited.

---

## 10. Prototype

The prototype that became `electrochem/readers/`: a typed profile, one generic
reader for delimited text and Excel, three vendor profiles written as
declarations, a synthetic experiment emitted in three dialects, and the test
battery. It proved the design twice by failing:

- The cross-dialect test caught `"cc_discharge".endswith("charge")`, which had
  silently marked every discharge as charge for both unsigned-current dialects.
  A single-instrument test would have passed.
- The known-answer test caught integration across a programmed step boundary,
  worth 1.7 % of the charge capacity on that fixture. It is why segmentation
  has to precede integration.

It also reproduces the repository's validated EC-Lab text reader exactly on all
twelve real public BioLogic files, including the decimal-comma exports, the
invalid `XXX` time token and the variable-length headers, which is the evidence
that the generic layer can be added without putting the validated path at risk.

### Sources

Research was done against real files and source code on 19 October 2026.

- Battery Data Format: github.com/battery-data-alliance/battery-data-format;
  reference implementation `batterydf` 0.2.0rc2 on PyPI; ontology snapshot read
  from the package.
- Public corpus: Zenodo DOI 10.5281/zenodo.18986774 (raw) and
  10.5281/zenodo.22230066 (canonical BDF conversions), both CC BY 4.0.
- Vendor structures: real Arbin `.res` and MITS Excel exports, Neware `.nda`,
  `.ndax` and Excel, Maccor CSV, Landt Excel, Gamry `.DTA`, ZPlot `.z`; plus the
  source of galvani, NewareNDA, navani, cellpy, BEEP and impedance.py.
- Library states: PyPI JSON API and shallow clones, 19 October 2026.
- Metamorphic testing as the standard response to the oracle problem in
  scientific software: Chen, Tse and colleagues, widely published from 2002.
