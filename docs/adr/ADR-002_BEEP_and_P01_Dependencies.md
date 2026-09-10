# ADR-002 — BEEP review and P01 dependency choices

Date: 2026-09-10. Decision implemented for the P01 foundation; broader application dependencies remain open.

## Bounded BEEP review

Inspected the TRI-AMDD/BEEP source checkout at `f2b984e4bbf54554d9514c1defc81d09ac2a3dee` (2026-02-07, “Update README.md”). This was a source review; BEEP was not installed or runtime-tested in this review. Its supplied SoftwareX paper, Herring et al. (2020), DOI 10.1016/j.softx.2020.100506, was previously inspected only at pp. 1–2. The paper is historical context, not evidence of current implementation behavior.

| Inspected source | Finding and implication |
|---|---|
| [Base structure](https://github.com/TRI-AMDD/beep/blob/f2b984e4bbf54554d9514c1defc81d09ac2a3dee/beep/structure/base.py) | Separates raw data from structured/interpolated outputs. Adopt that conceptual separation. Its optional missing-column imputation uses NaN, not zero. File-path schema resolution does not alone provide a self-contained scientific provenance contract. |
| [Validator](https://github.com/TRI-AMDD/beep/blob/f2b984e4bbf54554d9514c1defc81d09ac2a3dee/beep/structure/validate.py) | Dataframe schema checks include types and limits. These do not substitute for explicit dimensions, wiring conventions, interval support and method applicability. |
| [BioLogic reader](https://github.com/TRI-AMDD/beep/blob/f2b984e4bbf54554d9514c1defc81d09ac2a3dee/beep/structure/biologic.py) | The inspected file-type path accepts CSV and TXT with distinct delimiters/encodings and detects an Ecell/V header. This path does not establish native MPR compatibility. Representative matching files are still required. |
| [Requirements](https://github.com/TRI-AMDD/beep/blob/f2b984e4bbf54554d9514c1defc81d09ac2a3dee/requirements.txt) and [project configuration](https://github.com/TRI-AMDD/beep/blob/f2b984e4bbf54554d9514c1defc81d09ac2a3dee/pyproject.toml) | Dependency surface extends into scientific arrays, dataframes, machine learning and cloud logging/storage. Importing the whole package is not justified for the small P01 contract. The two files serve different constraint roles; no complete compatible environment was tested. |
| [License](https://github.com/TRI-AMDD/beep/blob/f2b984e4bbf54554d9514c1defc81d09ac2a3dee/LICENSE) | Apache-2.0. No BEEP code has been copied and no BEEP runtime dependency was introduced. |

A recent checkout date does not certify long-term maintenance or platform support. Retain BEEP as a comparison and potential future adapter candidate. This complements ADR-001's PyProBE review; it does not override its evidence or turn either package into an accepted dependency.

## Implemented choices

1. **Pydantic 2.13.5** for typed records, serialization and validation. Inspected official [models](https://docs.pydantic.dev/latest/concepts/models/) and [strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/) documentation. Strict input handling, tuple-based nested records and validated revisions address coercion and shallow-immutability risks. Cross-record scientific requirements remain our code's responsibility. Runtime test environment is recorded separately.
2. **A closed unit registry** for the present quantities. It rejects unknown mappings and incompatible dimensions; raw unknown units are still preserved. Temperature differences and absolute temperatures are distinct. This is not a general unit algebra system. Expansion requires explicit review and tests; Pint remains a future evaluation candidate.
3. **Standard-library snapshots and tests.** No GUI, dataframe, network or numerical-fitting dependency is required for this foundation. Polars evaluation is deferred until P03's full-resolution table storage and parser work, with performance measured against real workloads.

Installed distribution metadata inspected in this runtime: Pydantic 2.13.5, pydantic-core 2.46.5, annotated-types 0.8.0 and typing-inspection 0.4.4 declare MIT; typing-extensions 4.16.0 declares PSF-2.0. These observations inform dependency selection, not a legal opinion or completed release license audit. Runtime versions are pinned in `requirements-lock.txt`; dependency hashes, offline wheels, build tooling, complete transitive notices and Windows compatibility remain release work.
