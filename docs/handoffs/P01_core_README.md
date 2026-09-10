# Electrochemistry research core — P01 v0.1.0

An offline Python foundation for explicit measurement conventions, units, provenance and small reproducible project snapshots. This is a cycling-focused data contract, not yet an EC-Lab importer or calculation application.

## Run

Extract the source bundle and open a terminal in `electrochem_core`. Use Python 3.11 or 3.12 (only Linux Python 3.12.14 has been tested). A virtual environment is recommended. On Windows, `py -3.12` can be used in place of `python` if that interpreter is installed.

```sh
python -m pip install -r requirements-lock.txt
python -m unittest discover -s tests -v
python -m examples.inspect_project
```

Installing dependencies requires access to package files; subsequent core operations are offline. The dependency list pins the tested runtime packages, but is not a hash-locked, platform-complete distribution environment. Build tooling is separately declared in `pyproject.toml`; building a wheel and Windows packaging remain untested.

The example verifies a bundled synthetic snapshot and reports `unconfirmed_terminal_convention`. This is expected: the raw `Ewe/V` channel has no confirmed terminal-voltage meaning, so energy is blocked. It does not calculate a synthetic capacity or energy.

## Contents

- `electrochem/units.py`: finite scalar conversions within a closed, versioned unit registry.
- `electrochem/models.py`: immutable records, semantic checks, input fingerprints and an energy eligibility check.
- `electrochem/archive.py`: source-hash-verified, non-overwriting small project snapshots.
- `tests/test_contracts.py`: 27 software tests, including invalid inputs and independent unit expectations.
- `examples/`: synthetic original bytes embedded in a snapshot, its JSON representation, and a read-only example.
- `project.schema.json`: generated structural schema. Python validators enforce additional cross-record rules that JSON Schema alone does not express.
- `evidence/`: observed test output and environment versions.
- `docs/`: dependency decision and package handoff.

Use `Record.revised(...)` for validated changes. Pydantic's unchecked construction/copy APIs are not an approved mutation interface. Raw lexical tokens are separate from normalized SI values, and the archive retains original source bytes. Numerical code must operate on full-resolution observations, never display settings or downsampled views.

See `docs/P01_Handoff.md` for evidence, limits and the P02 handoff. No distribution license has yet been selected for this project's own code.
