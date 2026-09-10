# P03 — text import implementation and native compatibility review

Version 0.1.0 · 2026-09-10

**Delivered:** an executable EC-Lab/BT-Lab text importer, review CLI, reusable API, a source-preserving P01 project export, synthetic tests, a public compatibility corpus and a bounded native-file comparison. **P03 text subset is implemented and software-tested; the full P03 package remains open.**

## What now works

The importer reads declared-header tab-separated exports, or explicitly selected headerless tables; preserves original bytes, header/column text, flags, counters and row references; and normalizes reviewed time/current/potential columns with explicit units and decimal convention. Encoding failures, malformed rows and unsupported native files produce clear errors. Blank, invalid and zero values remain distinct.

A minimal command-line interface lists columns for review and accepts a mapping file to save a P01 `.ecproj` snapshot. The snapshot includes the original source and import settings/line provenance. The existing shared P01 archive implementation handles reopening; no second archive engine was added. A working synthetic example, mapping and snapshot are included.

Settings files are recognized as context, not measurement data. All integration intervals remain unresolved. No technique segmentation, current-direction interpretation, source-flag validity interpretation or absolute-time timezone is silently inferred.

## Evidence observed

| Verification level | Result |
|---|---|
| New software tests | 23/23 passed, including failure, encoding, decimal, time, mapping, source-tampering and reopening cases |
| Public text compatibility | 15 measurement exports, 31,865 rows, plus one MPS settings file; all completed declared lexical/conversion/reopening checks |
| Known unsupported time values | One `XXX` token and eight absolute timestamps preserved as invalid numeric-seconds samples; never coerced to zero |
| Prior-package regression | P01: 27/27 tests passed. P02: 21 observation fixtures and 268 checks passed |
| CLI | Synthetic inspect/mapping/export command executed successfully; new output archive created |
| Environment | Linux Python 3.12.14; exact dependency versions recorded in evidence. Windows untested |

Public examples include CV/EIS tables, but successful table import does not validate those techniques' interpretation or analysis. No user experimental file, full-resolution export setting or trusted EC-Lab calculation output has been supplied for project-specific validation.

## Native MPR comparison: retain the discrepancies

Galvani was executed from an external pinned checkout to examine five same-stem MPR/MPT candidates. It has not been integrated into the application.

- Four candidates had equal row counts. Checked flags matched exactly. Compared numeric fields and counts are enumerated individually in `evidence/native-comparison.json`; absent binary columns were not invented or compared.
- One candidate, `bio_logic5`, contains the invalid exported time token `XXX`. That row's time comparison was withheld; the token remains preserved.
- `bio_logic6` has 958 text rows versus 2,331 binary records. Pointwise comparison was withheld. The reason for differing coverage is unresolved; filename similarity is insufficient evidence for forced alignment.
- Across charge-increment fields in the aligned candidates, **320 values exceeded a strict half-last-printed-digit decimal bound**. All 320 parse back to exactly the same binary floating-point value as the native reader. The largest recorded charge-field absolute difference was approximately 5.45e-19 mAh. This is consistent with decimal formatting at very high precision; the original export formatting algorithm was not established. The strict-bound failures remain failures in the report. Binary round-trip agreement is a separate observation, not a widened tolerance or proof of complete native compatibility.

Initial probe execution stopped on `XXX` and unequal row counts. The evaluation harness was corrected to report these explicitly and withhold affected comparisons; no data were repaired. Initial public decimal-dot profiles marked comma-formatted numbers invalid; after inspecting those files, three explicit profiles were changed to decimal comma and their expected invalid counts were fixed. The parser did not auto-detect or silently rewrite the values. An initial P01 regression command used the wrong working directory; rerunning from its source root passed all 27 tests.

## Sources and decisions

The manufacturer manual's historical text-export section, exact public fixture revisions, Galvani licensing/API/tests, eclabfiles archival notice and yadg development API/project metadata were inspected. Links and access scope are recorded in `p03_import/Sources_and_Native_Adapter_Review.md`. The latter distinguishes runtime evaluation from documentation-only review. No current universal format specification or universal EC-Lab compatibility is claimed.

The text importer adds no runtime dependency. Galvani is a native-reader candidate supported by scoped execution evidence; yadg remains a broader metadata candidate awaiting a pinned-runtime evaluation. Neither was adopted. P01 code and scientific decisions were preserved.

## Limits and next action

This is an in-memory 10 MiB text profile with explicitly supported signatures/layouts, not a streaming importer. MPS linkage, automatic technique metadata extraction, absolute timestamp interpretation, alternative delimiters/locales, full native metadata preservation and current-version compatibility remain open. Numeric SI conversion retains source strings because binary floating-point conversion is not itself lossless.

Next continue **P03 native-adapter acceptance and metadata linkage**, rather than declaring import complete and skipping to P04. Inspect current upstream candidates, define preservation of binary modules/column identifiers/flags and failure behavior, and reconcile paired-file coverage before integration. A user cycling `.mpr` with its matching full-resolution `.mpt`, optional `.mps`, instrument/software version and confirmed conventions is still needed for user-specific compatibility. Public/synthetic work can continue without it.

Once import contracts are sufficiently verified, P04 will establish technique/step/branch/cycle support and feed the frozen P02 fixtures into the eventual cycling engine. There is still no production cycling calculator or complete plotting application.
