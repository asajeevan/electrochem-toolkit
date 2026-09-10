# Status

Updated 2026-09-10. Repository revision 0.2.0. Supersedes status revisions 0.1 to 0.7 of the earlier bundle deliveries; their detailed evidence is kept under `docs/handoffs/` and `docs/evidence/`.

## Decision: free and open

The toolkit is released under GPL-3.0-or-later. It is built first as a working tool for the author's own measurements and published so others can use and inspect it. There is no commercial layer, so the GPL licence of the optional Galvani reader is compatible and no independent MPR decoder is planned.

## Next task

**P04 reviewed segmentation.** Build continuity blocks, technique and step boundaries, directional branches and explicit cycle pairing on top of the imported observations. Use the native `Ns`, cycle number and direction columns as primary evidence and current behaviour as documented fallback. Distinguish recorded rests from missing current, smooth zero crossings from unexplained reversals, and complete constant-current or constant-voltage branches from interrupted runs. Every interval that stays unsupported needs a stated reason. Acceptance: the frozen cases in `reference/fixtures/` (expected support, unavailable outputs and independent integrals).

After P04: P05 capacity, efficiency, retention and energy under M01; P06 calculators with explicit denominators; then the first import-to-export workflow on the author's own GCPL files.

## Completed

| Package | Result | Evidence |
|---|---|---|
| P00 | M01 cycling contract; 14 arithmetic checks plus independent 38/3 J energy quadrature | `docs/M01_Cycling_Method_Specification.md`, `docs/handoffs/M01_Verification_and_Handoff.md` |
| P01 | Records, closed unit registry, metadata revisions, source-preserving snapshots; 27 tests | `tests/test_contracts.py`, `docs/handoffs/P01_*` |
| P02 | 21 frozen observation fixtures plus one policy fixture; 268 exact checks | `reference/`, `docs/handoffs/P02_*` |
| P03 text | `.mpt` importer and CLI; 23 tests; 15 public exports, 31,865 rows | `eclab_import/text.py`, `docs/handoffs/P03_Implementation_and_Verification.md` |
| P03 native | Optional pinned Galvani adapter, binary provenance, MPS linkage; 19 tests; six MPR files, 11,220 records | `eclab_import/native.py`, `docs/handoffs/P03_Native_Implementation_and_Verification.md`, `docs/adr/ADR-003_Native_Backend.md` |

All 69 tests and the 268 reference checks were rerun on 2026-09-10 (Linux, Python 3.12.3) after the repository reorganisation.

## Fixed conventions

- Original bytes, normalised observations and derived results stay separate. Source hashes, row references, flags, revisions and processing settings are preserved.
- Never infer mass, area, current direction, reference electrode or geometry. `Ewe` is not terminal voltage until confirmed.
- All imported intervals are unresolved until P04 establishes continuity. No integration before that.
- Pydantic 2.13.5 for validation; Galvani revision d4a5f44 plus NumPy 2.3.5 for the optional native path, with source fingerprint and version gates.
- Unknown uncertainty is not zero. Cycles are not independent replicates.

## Known limits

- Text import is bounded to declared profiles; 10 MiB input. Native import: 100,000 records, 128 fields, one data module. Snapshots: 50 MiB uncompressed.
- Native versus text comparison across six public files shows 415 last-digit differences: 362 round-trip to the same binary value, 53 differ by at most four ULP after decimal parsing. This is export rounding, not an import defect. The native record is treated as the primary source where both exist.
- No user-specific experimental validation yet. It needs one cycling MPR with its matching full-resolution MPT, optional MPS, cell configuration, current convention, potential-channel meaning, normalisation basis and a trusted EC-Lab result for comparison.
- Windows execution untested.

## Parked

MPS chronology and conflict resolution, GITT and PITT, transference-number workflows, the uncertainty framework, DRT, other vendors, streaming import, schema migration, interface and installer. The build plan in `docs/` still describes them; they are not scheduled.
