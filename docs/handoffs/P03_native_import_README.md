# P03 native adapter and settings linkage

Adapter 0.1.0; import package 0.2.0; P01 schema unchanged. This adds a bounded optional MPR path to the existing text-import CLI. It is a research implementation, with a pinned reader and a declared compatibility corpus.

## Run

Extract the source bundle and use a terminal at its root. Install the base requirements and, for native decoding, the optional pinned reader:

```sh
python -m pip install -r electrochem_core/requirements-lock.txt
python -m pip install -r p03_native/requirements-native.txt
python -m eclab_import p03_native/public_data/bio_logic5.mpr --native
python -m eclab_import p03_native/public_data/bio_logic5.mpr --native --mapping p03_native/examples/mapping.json --output reviewed-native.ecproj
python -m unittest discover -s p03_native/tests -v
python p03_native/verify_public.py
```

The optional install requires Git and access to the pinned repository/package files; it is not a prepared offline installer. Import and project reopening are offline after installation. Do not run with Python `-O`: the pinned reader uses assertions for format checks and the adapter explicitly rejects optimized execution. Tests were executed with the exact external checkout on Python's module path and installed NumPy 2.3.5; installation through the requirements file and Windows execution were not tested.

The inspect command prints backend field labels, indices, dtype/offset information, encoded column IDs and module descriptors. Mapping indices refer to decoded physical fields. The stored source's neutral names `encoded_field_N` do not pretend that textual labels were present in the binary. Select current only if an appropriate measured-current field exists. Some public files have charge-increment fields but no directly decoded current field; the adapter does not invent current from those counters.

To link settings while saving, add `--settings FILE.mps --link-evidence "reason for associating these settings"`. Use `--settings-encoding cp1252` when verified. The CLI links the settings to its imported experiment; the reusable `link_settings` API requires explicit existing experiment IDs. A synthetic context-link example snapshot is included. Its synthetic MPS is deliberately **not** represented as the original settings for the public MPR.

Reopening `.ecproj` uses the P01 archive loader and requires no Galvani installation or original source path. It reproduces stored observations and provenance; re-decoding binary bytes requires the pinned native environment.

## Native import contract

Purpose: decode supported MPR scalar fields while retaining every source byte and keeping measurement interpretation reviewable. There is no electrochemical model or integration in this adapter.

1. Verify the optional backend's source fingerprints and NumPy version. The evaluated backend is Galvani commit `d4a5f444b16eae57d2edfad6df774ead95c92fd6`; NumPy is 2.3.5. Unknown source revisions fail explicitly instead of silently changing decoding.
2. Write the supplied bytes to a private temporary directory with a fixed filename for the backend. This prevents implicit discovery of neighboring LOOP/MPL files and avoids the pinned backend's path-variable fallback issue for in-memory streams. No original experiment file is modified or moved.
3. Decode with unknown-column guessing disabled. Validate module payload bounds/hashes, declared record count, contiguous scalar fields and exact array/source byte agreement. Reject unsupported/truncated layouts. Temporary copies are removed when decoding exits.
4. Preserve the complete MPR plus module offsets, lengths, versions, raw name/date bytes and payload hashes; ordered encoded column IDs; backend physical-field labels, dtypes, offsets, widths and interpreted units; packed flag masks; and backend loop-index interpretation. Settings/log/loop bytes remain authoritative. Module contents are not fully semantically decoded here. Packed flags mean encoded IDs and physical fields are not necessarily one-to-one.
5. Each P01 RawRow contains **hexadecimal original field bytes**, explicitly labeled as such in the embedded native-import context. For row k and field f, its byte range starts at `data_offset + k*record_width + field_offset[f]` and has the declared field width. Decoded scalar strings are separate backend interpretations, not original text tokens. Reconstructing all field bytes reproduces each record exactly.
6. Normalize only reviewed time/current/potential fields to SI, applying an optional explicitly confirmed current multiplier. A missing current mapping stays absent. Nonfinite/unrepresentable decoded values become invalid samples with raw bytes retained. Potential role defaults to unresolved; no timezone, reference electrode or terminal wiring is inferred.
7. All integration intervals remain unresolved. Native loop indices and flags are preserved evidence for future P04 work, not ready-made cycle/branch/completeness decisions. No inferred chronology, resampling, integration, mass normalization or uncertainty calculation occurs.

Geometry and electrochemical boundary conditions are not applicable to byte decoding. Time support, cell configuration, wiring, geometry and normalization become required where later methods depend on them. Measurement uncertainty remains not evaluated; decoded-bit agreement does not establish calibration accuracy.

## Explicit settings linkage

`link_settings` verifies existing source payloads, parses the settings signature, validates target experiment IDs and stores the original MPS plus a provenance record. It creates a metadata revision and conservatively changes the scientific input digest. Existing observations and denominator metadata stay unchanged. Linking identical context twice is idempotent. No mass, area, technique parameters, file ordering or historical association is inferred from filename similarity or header values.

MPR and MPS metadata can conflict. Both raw sources and the explicit association remain visible; conflict resolution/semantic parameter comparison is future work. Arbitrary file paths in a settings header are never followed.

## Verification and limits

19 tests pass, including malformed native input, unknown data version/column ID, nonfinite values, provenance tampering, backend/version gates, sidecar isolation, explicit linkage, source corruption, idempotence, backend-independent reopening and unchanged text CLI export. The six-file corpus covers 11,220 records across observed data-module versions 0, 2 and 3. Its scalar audit uses Python `struct` independently of NumPy's value decoding but uses the backend's dtype/offset descriptions; it does not independently establish every undocumented binary layout. Export comparisons provide separate evidence and retain failures.

Limits: 10 MiB input, 100,000 decoded records, 128 physical fields, one data module and contiguous scalar fields. These are software bounds, not performance certification. No live acquisition/implicit sidecars, full parameter decoder, automatic folder linking, absolute-time conversion, universal MPR compatibility or Windows validation is provided. P01's 50 MiB snapshot cap and filesystem requirements still apply. Source fingerprints may reject installations with changed source bytes, including different line endings; portability of that installation path remains to be tested.

Read the root `P03_Native_Implementation_and_Verification.md` and `ADR-003_Native_Backend.md` for the precise evidence and open compatibility gates. P04 segmentation may now proceed against these bounded import contracts and the frozen P02 cases. Release and user-specific compatibility remain open.
