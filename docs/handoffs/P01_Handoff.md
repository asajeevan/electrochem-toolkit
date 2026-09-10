# P01 — implementation, verification and handoff

Date: 2026-09-10. Core version: 0.1.0. Status: **cycling-focused foundation implemented and software-tested**. No parser or experimental validation is claimed.

## Delivered

The source bundle `Electrochem_Core_P01.zip` contains a reusable offline Python core, tests, a synthetic project, a generated JSON schema, dependency pins, test evidence and ADR-002. It implements the data-contract prerequisites for the existing M01 cycling method, without introducing a second calculation engine.

| Contract | Implemented behavior |
|---|---|
| Units | Finite explicit conversions to SI; dimensions checked; unknown units rejected for normalization; absolute temperature and temperature differences distinguished. |
| Raw observations | Original file bytes verified by SHA-256, original column positions/names/units and lexical row tokens retained separately from normalized values. Duplicate column names and unmapped flags survive. Row indices identify measurement records, not assumed text line numbers. |
| Measurement conventions | Explicit cell configuration, channel quantity, terminal-voltage/electrode-potential role, reference context, polarity and provenance. Unresolved Ewe does not qualify for terminal energy. |
| Missing data | Null, invalid and zero remain different. Invalid raw tokens remain available for inspection. No inferred mass, geometric area or current polarity. |
| Time and segmentation records | Acquisition order, time blocks and explicit supported/excluded/unresolved adjacent intervals. Resets and duplicate times can be retained but cannot be declared supported integration intervals. Branch completeness needs evidence; cycle pairing is explicit and cannot count the same interval twice. Segmentation algorithms are not implemented. |
| Metadata and results | Immutable revisions, typed normalization basis, result status separate from evidence level, settings/exclusions/support references and uncertainty records. A scientific input digest changes on metadata revision and ignores display styling. |
| Reopening | A small `.ecproj` snapshot verifies source sizes/hashes and reconstructs records without extracting or deleting files. Existing destinations are not overwritten. |

The example intentionally preserves an unresolved potential channel and reports `unconfirmed_terminal_convention`. The eligibility check is not an energy integrator. Model validation checks declared consistency; it cannot prove that a supplied wiring description or completeness statement is experimentally true.

## Verification observed

**27/27 software tests passed** on Linux, Python 3.12.14. Exact output and installed dependency versions are included in `evidence/`. Tests include independent known unit conversions, a seconds-to-absolute-time check, rejection of a microsecond scaling error, current-polarity preservation, null versus zero, invalid values, unknown/duplicate raw columns, missing metadata, interval resets, incomplete branches, pairing conflicts, immutable revisions, normalized-result eligibility, source corruption, unexpected archive members and non-destructive reopening.

The demo reopened the bundled two-observation synthetic snapshot and verified one original source payload. Its scientific input digest was `6302f6689201bb01414b881c5e0c4c8a299583f37be82f74b211e0facb1509f6`.

These tests validate the implemented contracts. They do not establish EC-Lab parser compatibility, physical model validity, experimental accuracy, complete numerical-result reproducibility or Windows release readiness. The earlier M01 14-case arithmetic audit remains a separate evidence artifact.

## Architecture decision

The bounded BEEP source review is complete. Its separation of raw and structured data is useful, but the application retains its own scientific records. Neither BEEP nor PyProBE was added as a runtime dependency. ADR-002 records exact inspected source links, scope and licensing observations. Pydantic is pinned for records and validation; broader numerical/dataframe dependencies remain open.

## Limits and unresolved work

- P01 covers the first cycling workflow's core contract. Dedicated EIS spectra, advanced transport models and their metadata require later versioned extensions.
- No MPR/MPT parser, MPS context reader, automatic segmentation, cycling calculations, plots or researcher interface is implemented here. Raw-token parsing and correspondence to normalized values are future importer responsibilities.
- The in-memory record representation and 50 MiB uncompressed snapshot limit are for small fixtures. Large-data storage, multi-file channel reconciliation, streaming and performance remain unvalidated.
- JSON Schema captures structure; Python validation is required for all cross-record invariants.
- Scientific-input invalidation is conservative across a whole project. Selective dependency tracking, method/run fingerprints, automatic recomputation and numerical equivalence across environments remain later work. A stored result record alone is not proof of reproducibility.
- Uncertainty fields record provenance and covariance-group links; they do not propagate uncertainty or calculate covariance.
- Snapshot publication uses a same-filesystem hard link. Windows and filesystems without hard-link support have not been tested. Full crash recovery, migrations, concurrent writers and hostile-archive hardening remain P18 work; the format is not a security-certified container.
- The tested dependency list is not a full distribution lock. Windows wheels, offline installation, build reproducibility and the project's distribution license remain unresolved.

## Next package: P02

Freeze independent synthetic cycling datasets against M01 before implementing the cycling calculator. Include constant current, varying current/voltage, CC/CV tails, rests, step endpoint ambiguity, resets, unexplained gaps, duplicate timestamps, interrupted runs, incomplete pairs and normalization variants. Each case must state exact observations, interval semantics, analytic or independently calculated expectations, evidence-derived tolerances and expected blocked outputs.

Keep those frozen expectations separate from implementation logic. Carry existing M01 reference corrections forward explicitly. Representative native `.mpr` files and matching full-resolution `.mpt` exports, optional `.mps`, instrument/software version and declared cell conventions are still required for P03/P04 experimental verification, but do not block P02.
