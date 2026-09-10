# PyProBE review before P01

10 September 2026 | Decision record ADR-001 | Review scope: cycling/import architecture

## Recommendation

**Use PyProBE as a serious reuse candidate and comparison backend, but do not make its current data model or cycling calculations the authoritative core of our application.** Preserve our M01 requirements. Build the P01 measurement/provenance schema independently, with an explicit conversion boundary to PyProBE for eligible battery-cycling datasets. Test that boundary before selecting a production dependency.

PyProBE overlaps enough with our project that rebuilding every filter, plotting convenience, or analysis workflow would waste effort. However, the inspected revision has reproducible behaviors incompatible with our requirements. Some are defects; others are reasonable simplifications for a narrower use case. A replaceable adapter lets us reuse suitable work without inheriting those assumptions silently.

No application feature was implemented, dependency committed, fork created, upstream issue filed, or message sent to maintainers in this review.

## Exact source and evidence

- Repository: [ImperialCollegeLondon/PyProBE](https://github.com/ImperialCollegeLondon/PyProBE).
- Inspected checkout: [`d0ad5a9b722c3b599d30a7b61cd88f74c5207630`](https://github.com/ImperialCollegeLondon/PyProBE/tree/d0ad5a9b722c3b599d30a7b61cd88f74c5207630), commit dated 22 August 2026.
- `pyproject.toml` identifies version **2.6.0**, Python **>=3.11,<3.13**. This is the checkout's declared version, not a verified statement about the latest PyPI release.
- Read relevant source, tests, CI configuration, input documentation, unit helpers, archive code and licence. The shallow clone remained unmodified after tests.
- Ran ten upstream tests from `tests/cyclers/test_biologic.py` and `tests/analysis/test_cycling.py`: **10 passed, 4 deprecation warnings**.
- Ran five targeted probes, including both CE-option branches. Outcomes below are reproduced backend behavior, not guesses from the README.
- Environment: Python 3.12.14, Polars 1.18.0 (the declared lower bound), Pydantic 2.13.5, NumPy 2.3.5, SciPy 1.17.0. Detailed versions and source hashes are saved in `pyprobe_review_results.json`.
- Scope limitation: the normal package import requires dashboard dependencies; it failed in the partial review environment on missing Plotly. A namespace-package harness omitted the GUI-importing `__init__` and imported the unmodified backend modules. This does not certify a full installation, GUI operation, the upstream lockfile, or Windows behavior. The environment used available system scientific packages plus review-only dependencies, not a fully isolated release installation.

Reproduce the recorded probes using `pyprobe_review_checks.py /path/to/checkout` in a suitably provisioned environment. The script writes observations, not a claim that the suspect behaviors satisfy our requirements. The upstream test run is captured separately in `pyprobe_upstream_test_log.txt`.

## What is useful to reuse

| Area | Inspected capability | Recommended use |
|---|---|---|
| Data organization | Cell metadata, procedures, experiments, cycles, steps | Reuse concepts; evaluate a conversion adapter |
| Battery text import | BioLogic .mpt/.txt, Modulo Bat handling; other cycler adapters | Candidate text-processing path after our raw-file preservation and compatibility checks |
| Table processing | Polars dataframes/lazy evaluation and Parquet | Evaluate these technologies directly; PyProBE demonstrates a relevant pattern |
| Experiment context | Human/machine-readable README metadata | Inspiration for saved protocols and lab recipes |
| Filtering | Experiment, cycle, charge/discharge, rest, CC and constant-voltage accessors | Useful after explicit convention/segmentation validation |
| Plotting and exploration | Plotting integrations and Streamlit dashboard source | Candidate prototyping tools, not a verified desktop application |
| Analysis | Cycling summaries, pulse analysis, differentiation, smoothing, degradation-mode analysis | Method-by-method evaluation; advanced interpretations remain gated |
| Persistence | Cell archive with metadata, Parquet and PyProBE version | Useful starting pattern; insufficient for our full raw-source audit requirements |

Sources: [import guide](https://pyprobe.readthedocs.io/en/latest/user_guide/importing_data.html), [pinned source tree](https://github.com/ImperialCollegeLondon/PyProBE/tree/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe), and [input-format guidance](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/docs/source/user_guide/input_data_guidance.rst). Advertised performance was not benchmarked here.

## Reproduced findings

### B1. Absolute timestamp scaling in the numeric-time BioLogic path

On the repository's `Sample_data_biologic_CA1.txt`, elapsed time changed by **139.524006627 s**, but the constructed datetime changed by **0.000139 s**. The reader casts numeric seconds directly to a Polars duration before adding the acquisition start. In this environment that duration is interpreted on a microsecond scale, with integer truncation.

This affects the absolute datetime construction in the numeric-time/header branch. It is not a claim that all timestamps or the separate timestamp-string input path are wrong. The elapsed `time/s` values themselves remained intact in this probe. Misaligned absolute time would matter when synchronizing temperature or other instruments.

The existing expected last-row datetime in the upstream test encodes the same small offset, so passing that test does not establish correct physical timing. Our adapter requires equality between elapsed-time differences and absolute-time differences within declared timestamp precision. [Reader](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe/cyclers/biologic.py), [tests](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/tests/cyclers/test_biologic.py).

### B2. Missing CE result when `dchg_before_chg=False`

Calling `cycling.summary` on the same synthetic experiment with True produced a `Coulombic Efficiency` column; False produced no such column. In the False branch, a Polars expression is constructed but is not attached to the dataframe. This is a reproduced functional defect in this revision.

The True result's presence does not validate its pairing for every protocol. The function also uses a shifted charge denominator and normalizes capacity to the first observed value; those choices need alignment with our explicit pair IDs and retention reference. [Cycling implementation](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe/analysis/cycling.py).

### B3. Unit helper does not enforce physical dimensions

`Current [mA] = 1` converted through `.units.to_unit('V')` returned **`Current [V] = 0.001`**, without rejection. The helper applies unit-prefix factors rather than validating dimensional compatibility.

This is not a claim every normal unit conversion fails. It means this helper cannot serve as our dimensional validator; P01 must reject current-to-voltage conversion and distinguish charge, temperature and normalized quantities explicitly. [Unit implementation](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe/units.py).

### B4. Normalized projection loses source-specific information

A synthetic .mpt-style file with `Ewe/V` and an extra `source_flag` was read. Its standard output retained Ewe values as `Voltage [V]` but omitted both the original channel name and the extra flag column. This results from selecting recognized column importers. If both Ecell and Ewe are available, source inspection shows that first-valid mapping priority selects one generic voltage output.

The upstream original file is not overwritten by this operation, and the intermediate dataframe can still contain more columns. The risk arises if we use the normalized projection as our sole canonical dataset. Our raw/normalized layers must preserve original channels, unknown flags, units and row references independently. [BioLogic mappings](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe/cyclers/biologic.py), [projection](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe/cyclers/basecycler.py).

### B5. Modulo Bat step correction fills unrelated missing values

`BiologicMB.apply_step_correction` changed a synthetic auxiliary column from `[null, 2.0]` to `[0.0, 2.0]`. Its joined dataframe receives a general `.fill_null(0)` before correcting step numbers.

Our requirement is narrower: a missing step-offset after the join can be assigned zero where justified, but a missing measurement must remain missing. This probe establishes behavior of the step-correction helper, not the prevalence of the issue in user files. [Implementation](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe/cyclers/biologic.py).

## Additional source-inspected constraints, not runtime-tested here

- **Native binary support:** the documented BioLogic formats are .mpt and .txt, and the reader is text-based. No native .mpr or .mps settings parser was identified in the inspected code. We still need a native EC-Lab adapter.
- **Charge reconstruction:** `CapacityFromChDchMap` clips negative counter differences and constructs cumulative capacity with an offset. This is a particular counter model, not a general validation of resets/gaps. Preserve separate raw counters and document compatibility.
- **Segmentation:** without cycle metadata it warns and infers cycles from decreasing step numbers. Charge/discharge filters use current sign and a threshold relative to maximum current; CC/constant-voltage filters use value-based heuristics. These should not replace explicit native control-mode and boundary evidence.
- **Capacity summary:** directional max-minus-min is used after filtering. It needs suitable endpoints and does not itself prove completeness or account for unsupported intervals.
- **Archive loading:** `load_archive` extracts a ZIP and then calls `os.remove(path)` on the input ZIP. Do not pass a user's only archive copy through this path. This is a source-confirmed lifecycle behavior, not a runtime deletion test; our reopen operation must preserve its input.
- **Scope:** no ready-made general EIS fitting/Lin-KK, SPE conductivity, or operational transference workflow was identified in the analysis-module inventory. Pulse tools or generic differentiation do not establish these methods.

Relevant files: [column maps](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe/cyclers/column_maps.py), [filters](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe/filters.py), [cell/archive code](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyprobe/cell.py).

## Maintenance, dependencies and licensing

The repository has recent commit activity, extensive tests, examples and CI configuration. The inspected PR workflow covers Python 3.11/3.12 on Linux, Windows and macOS, including frozen/upgraded dependencies and distribution checks. This is evidence of maintenance infrastructure; recent commits alone do not establish scientific correctness, and I did not verify all remote CI outcomes. The changelog's top entry is v2.2.0 while the manifest is v2.6.0, so pin by exact revision and verify release notes rather than infer freshness from that file.

The manifest includes Polars, NumPy, Pandas, Pydantic, plotting/GUI and analysis dependencies. Streamlit and ipykernel are in core dependencies, so using the whole package adds more than a small numerical kernel. SciPy is directly imported by inspected backend code but not directly listed in its main dependency list; its resolution should be explicit in a reproducible environment. No full transitive dependency/licence audit or executable-size benchmark was performed.

The repository uses **BSD-3-Clause**. The licence permits source/binary reuse with its notice/disclaimer and non-endorsement conditions; any reused dependencies require their own review. There is no need to choose our distribution licence during this comparison. [Pinned licence](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/LICENSE), [manifest](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/pyproject.toml), [CI](https://github.com/ImperialCollegeLondon/PyProBE/blob/d0ad5a9b722c3b599d30a7b61cd88f74c5207630/.github/workflows/ci-pull-request.yml).

## Supplied software papers: scoped relevance

| Supplied paper | Material inspected in this review | Consequence |
|---|---|---|
| Jalalvand et al., MATLAB in electrochemistry: A review, Talanta 194 (2019), DOI 10.1016/j.talanta.2018.10.041 | Repository cover/title, PDF p.1 | Background reading candidate; no algorithm adopted |
| Zheng, Python for Electrochemistry: A Free and All-In-One Toolset, ECS Advances 2 (2023) 040502, DOI 10.1149/2754-2734/acff0b | Cover and abstract/introduction, PDF pp.1–2 | Ecosystem orientation; not validation of PyProBE |
| Vishart et al., pyEIA, SoftwareX 15 (2021) 100720 | PDF pp.1–2, scope/software description | CV/EIS GUI comparison candidate; its immunoassay/semicircle assumptions cannot be transferred to arbitrary battery spectra |
| Herring et al., BEEP, SoftwareX 11 (2020) 100506 | PDF pp.1–2, including validation and structuring sections | Valuable reference for separating raw data, validation, structured data and ML features; add to focused architecture comparison |

BEEP is particularly relevant to P01/P02. Its 2020 paper describes a validation-first battery-data workflow, but the present BEEP repository, dependency status and EC-Lab coverage have not been reviewed here. Do not choose a current dependency from historical paper metadata. The two previously supplied theory sources retain their earlier scoped-review status.

## Revised next action

Keep P01 as the next implementation package, **with reuse evaluation made explicit**:

1. Define our lossless source/observation/interval/metadata/result contracts. Evaluate Polars for tabular storage alongside unit and schema tools; PyProBE's use of it is a reason to test it, not automatic approval.
2. Define a narrow PyProBE bridge for supported cycling data. Retain source hashes, original columns, potential roles, sign mapping and unsupported intervals in our canonical model. Do not round-trip our sole data copy through a lossy projection.
3. Turn B1–B5 into acceptance tests for that bridge and the relevant fixes. Include archive preservation, resets, first-discharge pairing and missing metadata. Existing upstream tests remain useful but insufficient.
4. Review BEEP's current schema/validation implementation in a bounded comparison before finalizing equivalent machinery. Do not expand this into an open-ended survey of all packages.
5. Test native/text EC-Lab pairs with a separate native parser candidate when user data become available. Compare explicitly supported PyProBE results against the independently specified M01 engine behavior.

Final dependency choices remain open. The practical strategy is selective reuse with recorded scientific contracts and independent checks, rather than an unmodified PyProBE wrapper or a commitment to rebuild everything.
