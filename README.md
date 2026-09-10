# electrochem-toolkit

Traceable import, records and calculations for BioLogic EC-Lab battery measurements.

The aim is simple: import an EC-Lab file, state the measurement conventions once, and get only the plots and numbers the data can justify, with every result linked back to its source rows, units and settings. Nothing is guessed. Missing current is never treated as zero, `Ewe` is never assumed to be cell voltage, and charge is never integrated across an unexplained gap or reset.

The toolkit is written for research on organic positive electrode materials and solid polymer electrolytes, where a Li-metal half-cell, a two-electrode full cell, a three-electrode cell and a blocking-electrode cell can all record the same column names with different meanings.

**Status (September 2026): foundation only.** Import, unit handling, records and project snapshots are implemented and tested. Segmentation, capacity calculation and plotting are the next packages. There is no graphical interface yet. See [STATUS.md](STATUS.md).

## What works today

- Read EC-Lab and BT-Lab `.mpt` text exports with explicit encoding, decimal separator and column mapping, keeping the original tokens and line numbers.
- Read native `.mpr` binaries through a pinned, optional [Galvani](https://github.com/echemdata/galvani) adapter, keeping the original bytes and the decoded field layout.
- Attach an `.mps` settings file as reviewed context, without treating it as measurement data.
- Convert between units in a closed, versioned registry that rejects incompatible dimensions.
- Save a project and its source bytes as a single `.ecproj` snapshot, verify hashes, and reopen it later without the original folder or the native reader.

## What does not work yet

- No automatic step, branch or cycle segmentation (package P04, in progress).
- No capacity, efficiency, retention or energy calculation (P05, P06).
- No plots, batch processing, CV or impedance analysis, interface or installer.

## Install

Python 3.11 or 3.12. Only Linux Python 3.12 has been tested.

```sh
git clone <this repository>
cd electrochem-toolkit
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt        # core
.venv/bin/python -m pip install -r requirements-native.txt # optional MPR reader, needs git
```

On Windows replace `.venv/bin/python` with `.venv\Scripts\python.exe`.

## First run

Inspect the bundled synthetic text example. This lists columns, row count and parser details. It does not report a capacity.

```sh
.venv/bin/python -m eclab_import data/examples/synthetic.mpt
```

Save a reviewed project from it:

```sh
.venv/bin/python -m eclab_import data/examples/synthetic.mpt \
    --mapping data/examples/mapping.json --output reviewed-example.ecproj
```

Inspect a public native file (needs the optional reader):

```sh
.venv/bin/python -m eclab_import data/public/mpr/bio_logic5.mpr --native
```

The example mapping belongs to the synthetic file only. For your own measurements, inspect the columns first and write a mapping that names the time, current and potential columns and states the cell configuration and current convention. Do not reuse column indices blindly; EC-Lab column order depends on export settings.

## Run the tests

```sh
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest              # 69 tests
.venv/bin/python reference/verify.py    # 268 exact reference checks
```

## Layout

| Path | Contents |
|---|---|
| `electrochem/` | Shared records (`models.py`), unit registry (`units.py`), project snapshots (`archive.py`) |
| `eclab_import/` | Text reader, native adapter, settings linkage and the `python -m eclab_import` command |
| `tests/` | Unit tests for records, text import and native import |
| `reference/` | Frozen synthetic cycling cases with exact expected values, and the audit that checks them |
| `data/examples/` | Synthetic example files and mappings |
| `data/public/` | Public EC-Lab test files (CC-BY-4.0 and other notices retained beside each file) |
| `scripts/` | Public-corpus audits and evaluation probes; not needed to import a measurement |
| `docs/` | M01 calculation specification, build plan, decision records, handoffs and recorded evidence |

## Scientific rules that the code enforces

1. Original bytes, normalised observations and derived results are kept separate.
2. Every quantity carries an explicit unit; invalid or missing values stay invalid or missing.
3. A potential label does not establish terminal-voltage meaning; a control column is never substituted for measured current.
4. Every interval must be reviewed as continuous before it is integrated.
5. Every result records its equation, convention, denominator and inputs so it can be reproduced.

The M01 specification in `docs/` defines the cycling arithmetic: capacity as the integral of current, paired-cycle coulombic efficiency, retention against a visible reference cycle, and energy only where a terminal voltage has been confirmed.

## Roadmap

1. **P04** Segmentation from native `Ns`, cycle and direction columns, with current-based fallback and reviewable reasons for every unsupported interval.
2. **P05, P06** Capacity, efficiency, retention and energy under M01, plus basic calculators with explicit denominators.
3. First complete workflow: import, review, calculate, plot, export, reopen.
4. Nyquist and Bode plots, then conductivity and VFT/Arrhenius fits for polymer electrolytes.
5. CV branch separation and differential analysis.
6. Minimal interface and Windows packaging.

## Licence

GPL-3.0-or-later, see [LICENSE](LICENSE). The optional native reader Galvani is also GPL-3.0-or-later and is installed separately; its source is not included here. Public test files keep their own notices.

## Author

Aswadh Shyma Sajeevan. Built alongside doctoral and postdoctoral research on soft solid-state Li-organic batteries.
