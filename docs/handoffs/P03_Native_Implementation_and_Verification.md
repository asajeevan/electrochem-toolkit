# P03 — native import and explicit metadata linkage

2026-09-10 · Native adapter 0.1.0 · Import package 0.2.0

**Implemented:** a bounded optional MPR adapter, native CLI review/project saving and explicit MPS context linkage. **Verified:** source/record preservation, failure handling and reopening on the stated public corpus. User-specific experimental validation, complete MPR/MPT equivalence and Windows execution remain unverified.

## What changed

The application can now inspect native MPR files and save reviewed time/current/potential channels into the existing project format. It retains original binary bytes, module descriptors, ordered encoded IDs, physical-field locations/dtypes, packed flag descriptions and separate decoded observations. Binary RawRow values are explicitly labeled hexadecimal source bytes, not invented original text.

The optional backend is pinned to an evaluated Galvani revision and NumPy 2.3.5. Unknown column guessing is disabled. Isolated decoding prevents nearby files from silently changing an import. Original files are unchanged. Saved projects can reopen without the native backend or original file paths because source bytes, observations and import settings are embedded.

Explicit MPS linkage retains the settings file and a researcher-supplied association reason. It checks target experiments, creates a metadata revision and invalidates the scientific input fingerprint conservatively. It does not infer mass, area, technique chronology or a match from filenames. The demonstration links synthetic settings solely to exercise the workflow; it is not an asserted historical association with the public binary.

## Observed verification

| Check | Evidence |
|---|---|
| Native/linkage tests | 19/19 passed |
| Existing text-import regression | 23/23 passed; text CLI export also executed in a subprocess without the native checkout on its module path |
| Public native corpus | Six files, 11,220 records; data-module versions 0, 2 and 3 observed |
| Raw-record verification | All audited record bytes reproduced from stored field hex; module payloads/source hashes preserved |
| Scalar decoding cross-check | 81,639 values compared with Python struct decoding using the recorded dtype/offset descriptions |
| Project reopening | All six public projects saved/reopened; source blobs and project records matched; reopening did not modify archives |
| CLI demonstration | Native mapping, explicit synthetic MPS linkage and project saving executed |
| Platform | Linux Python 3.12.14; no Windows execution or requirements-file installation test |

P01 source and P02 fixture expectations were unchanged; their earlier evidence is retained without claiming a fresh rerun this turn. The struct audit verifies adapter handling independently of NumPy's scalar conversion, but shares the backend's layout descriptions. It cannot alone prove the interpretation of undocumented column IDs. Native/text comparisons are separate and have not all passed.

## Export discrepancies and revised evidence

The comparison now covers common field labels in six candidate MPR/MPT pairs. Exact per-field statistics, invalid tokens, counts and maximum errors are in `p03_native/evidence/public-verification.json`.

- The earlier four equal-count candidates retain their scoped evidence. The invalid `XXX` time token in `bio_logic5.mpt` remains uncorrected and excluded from its numerical time comparison.
- The 958 exported timestamps of `bio_logic6` correspond to the first 958 of its 2,331 native records at the export's printed precision. Control potential, measured potential, cycle number and the common charge counter also meet that bound on this prefix. Current has 37 strict decimal-bound failures, all of which round-trip to the same binary float. This supports a prefix relationship for these fields; why the export is shorter remains unknown. No automatic pairing or full-coverage equivalence is inferred.
- Across the expanded comparison, **415 values fail the original half-last-printed-digit bound**. Of these, **362 round-trip to the same binary value**. The remaining **53**, all in the formation fixture, differ after decimal parsing by at most **four binary64 units in the last place**. They include time, charge and energy fields. Their original-unit errors are retained individually; small error is not relabeled as a passed strict check. The export rounding/conversion history is unconfirmed, so no full equivalence or instrument-calibration conclusion follows.

The previous 320 charge-field failures are a subset of this expanded comparison and have not been erased. An early exploratory prefix calculation compared two decimal renderings and overstated failures; the final calculation compares exported decimals with the exact binary floating-point value. That is a correction to the audit representation, not a tolerance change. The public comparison also initially stopped on the formation export's trailing empty header field; its already documented explicit import profile was then applied. One mutation test initially assumed the selected fixture used data version 0; inspection showed version 2, and the test was corrected to mutate its 16-bit column ID. No parser rejection was weakened.

## Decisions and limits

ADR-003 records the optional backend decision, exact source pin, licensing observations and sidecar isolation. No backend implementation was copied. The application distribution license remains unresolved; optional dependency loading does not negate license obligations. The Codeberg upstream was inaccessible, so the evaluated revision is not advertised as the latest.

Supported operation is bounded to one data module, contiguous numerical scalar fields, 10 MiB input, 100,000 records and 128 physical fields. Full settings/log semantics, live acquisition sidecars, absolute-time interpretation, additional layouts/versions, automatic experiment-folder linking and release packaging remain future work. All native intervals remain unresolved until P04. Measurement uncertainty is not evaluated.

## Handoff

Proceed to **P04: reviewed technique, step, branch and cycle segmentation**, using P02's frozen expectations and preserving explicit interval support. The baseline import paths are now implemented for the declared profiles. Keep P03 compatibility expansion and native/text discrepancy investigations open alongside that work.

A user native cycling file with matching full-resolution text export, optional settings, instrument/software versions and declared cell/channel conventions remains necessary before claiming user-specific compatibility or experimentally validated cycling outputs. Do not silently equate the presence of a native reader with universal EC-Lab support.
