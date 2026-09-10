# P03 text import — version 0.1.0

**Update:** the text profile described here is unchanged. Native support and explicit settings linkage are now implemented separately; see `p03_native/README.md`. Earlier next-work statements below describe the text-only handoff.

This is the first implemented part of P03. It imports bounded EC-Lab/BT-Lab tab-delimited text, preserves source bytes and lexical records, and supports reviewed normalization into P01 projects. Native MPR remains an evaluated candidate path, not an enabled application importer.

## Run

Extract the source bundle and open a terminal at its root. Python 3.11/3.12 is the declared core target; this package was tested only on Linux Python 3.12.14.

```sh
python -m pip install -r electrochem_core/requirements-lock.txt
python -m eclab_import p03_import/examples/synthetic.mpt
python -m eclab_import p03_import/examples/synthetic.mpt --mapping p03_import/examples/mapping.json --output reviewed-example.ecproj
python -m unittest discover -s p03_import/tests -v
python p03_import/public_checks.py
```

The first command installs dependencies; subsequent import and verification are offline. Choose a new output path each time: saving refuses to overwrite. A completed example snapshot is also included. The CLI returns exit code 2 on import/mapping/save errors. It does not modify its input.

Inspect lists original column indices, names and unit suffixes. Mapping JSON specifies indices and the researcher's evidence for them. The example deliberately leaves potential role, cell configuration and current polarity unresolved. Set a current multiplier only from a documented convention. Select terminal potential only with named sensing nodes and justified current direction; the channel name Ewe is insufficient. Do not map control/setpoint current as measured current. Angle-bracketed averaged signals retain their original labels; their temporal meaning still requires review.

For legacy text use `--encoding cp1252` or `--encoding iso-8859-1` only when verified. Decimal comma requires `--decimal ,`. Explicit `--headerless` permits a table whose first line holds columns. `--missing-terminal-empty-field` permits precisely one absent terminal field when the final column name is empty. These decisions are saved in import provenance; there is no automatic fallback to another encoding, decimal convention or row-repair policy.

For reusable code import `eclab_import.text` with the project root and `electrochem_core` on Python's module search path, or install the core into the environment. `parse(bytes, filename, Options(...))` returns immutable lexical records. `project_from_text(parsed, bytes, Mapping(...))` returns a P01 Project and source blobs for the shared archive writer. No second archive implementation was introduced.

## Parser contract

- Accept exact `EC-Lab ASCII FILE` or `BT-Lab ASCII FILE` signatures and an integer header-line declaration. The declared final header line supplies tab-delimited column names. Headerless tables require explicit selection.
- Preserve every original byte, including encoding/BOM/newlines; duplicate and empty column names; original unit suffixes; header text with physical line numbers; all lexical row fields, native flags and counters. The original bytes are authoritative. The lexical view does not retain line terminators separately.
- Rows have zero-based measurement indices plus independent one-based physical line references. Reject malformed width, blank body rows and NUL; never silently skip a row. An explicitly accepted missing final empty field is represented by None in P01 while the exact shorter field tuple remains in the import record.
- Normalize selected time/current/potential columns only. Use declared units and numeric decimal convention. Empty fields are missing; malformed, nonfinite, overflowing or underflowing values are invalid. Neither becomes zero. Mixed decimal/grouping conventions are not guessed.
- All adjacent intervals remain unresolved with no interpolation model. The `unreviewed` block label is a placeholder, not evidence of continuity. Preserve duplicate/reset times and acquisition order. P04 must establish blocks, valid flags, step semantics, support and segmentation before integration.
- Retain header metadata as unconfirmed source context. No automatic mass, area, reference electrode, date locale, timezone or charge/discharge mapping. Absolute-time strings remain raw and are invalid in a numeric-seconds channel until a dedicated reviewed timestamp path exists.
- Recognize EC/BT-LAB settings signatures and expose MPS text as context only. It cannot become measurement observations. Cross-file settings linkage is not implemented.
- The snapshot embeds the original file plus an import JSON source containing options, mapping, header/row references and parser version. Reopening preserves both and the P01 scientific-input digest. The importer reparses bytes before projection to detect mismatched/tampered parsed records.

## Scope and evidence

23 new tests pass. Public verification covers 15 measurement exports (31,865 rows) and one settings file. Nine selected time values are deliberately invalid: one `XXX` token and eight absolute timestamps. This is expected preserved behavior, not successful timestamp conversion. Numerical conversion checks compare against Decimal arithmetic using explicit public-fixture scales, with a binary arithmetic bound of max(1e-15 SI units, 3e-16 times magnitude). This bound does not apply to instrument or model uncertainty.

Each public file's exact hash, source revision, options and expected invalid fields are in `public_data/manifest.json`; observed results are in `evidence/public-compatibility.json`. Fixture bytes are unmodified and retain upstream notices. They cover varied tables, not validated CV/EIS analysis. Public files can be truncated/edited examples and are not a substitute for the user's representative measurements or the instrument's output settings.

The separate `native_probe.py` evaluated an external Galvani checkout at the recorded revision. It requires NumPy and that external checkout, neither added as an importer dependency. To reproduce it: `python p03_import/native_probe.py PATH_TO_GALVANI_CHECKOUT`. See the report for its retained failures and exclusions. No Galvani source code is bundled or copied.

## Remaining P03 work

Native MPR integration, full settings/technique decoding, cross-file linkage, synchronized absolute-time parsing, additional locales/layouts and format-version coverage remain open. Inputs are capped at 10 MiB for this in-memory text implementation. There is no streaming, GUI, parser performance claim, Windows execution certification or hostile-input resource certification. All P01 archive limits still apply. Rejected inputs remain untouched and can be reviewed externally; no partial import is silently saved on a layout failure.

Next is P03 native-adapter and compatibility work, followed by P04 segmentation. Do not treat successful import as permission to integrate unresolved intervals.
