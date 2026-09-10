# EC-Lab electrochemistry software: detailed build specification

Prepared 10 September 2026. This is a proposed development specification, not an implemented or validated application. No representative user EC-Lab files have yet been inspected. Timelines and performance limits below are planning targets, conditional on the compatibility study.

## 1. Product goal and scope

Build a research application in which a scientist imports an EC-Lab file or experiment folder and receives appropriate plots, calculated metrics, quality flags, and reproducible exports. Optimize the first release for battery research: galvanostatic cycling, CV, OCV, and impedance, followed by polymer-electrolyte and pulse-method analysis.

The main interaction should be: import files; review detected experiment and missing metadata; receive results; optionally refine a saved analysis recipe; export figures and results. Once a cell profile and recipe are saved, subsequent compatible files should run without repeated setup.

“Automatic” means all applicable, scientifically justified outputs. It does not mean assigning a diffusion coefficient, interphase mechanism, or equivalent circuit to every file. A missing active mass should block specific capacity, while absolute capacity and voltage plots remain available. Missing information should never silently become zero or a guessed physical parameter.

Start with a local application, Windows first, able to run offline and retain unpublished data on the researcher's computer. Use a local Python service and a browser interface; package a launcher so routine users do not manage Python. A hosted collaborative edition is a later deployment decision. Instrument control and live acquisition are outside the first release.

## 2. Input compatibility and parser strategy

| Input | Intended behavior | Release priority |
|---|---|---|
| `.mpt` | Import exported EC-Lab text, headers, units, and available settings | First vertical slice |
| `.mpr` | Direct import of native binary measurements and available metadata | Required before useful beta |
| `.mps` | Read settings and associate measurement files when present; identify missing companions | Beta, after compatibility study |
| Folder or ZIP | Reconstruct experiments and maintain separate cell/channel identities | Beta |
| CSV/TSV | Column mapping with explicit units, saved as an import profile | Beta |
| Arbin and other vendors | Additional adapters into the same data model | Later |

The eclabfiles documentation describes these three EC-Lab formats, identifies `.mps` as settings rather than measurement data, and states that the project is archived and superseded by the `yadg` EC-Lab extractor. Use it as historical format context, not as the default production dependency. [eclabfiles repository](https://github.com/vetschn/eclabfiles)

Evaluate a pinned release of `yadg` against actual user files. Its documented capabilities include BioLogic extraction, metadata, units, provenance, and a Python extraction interface. Availability of an extractor does not establish coverage of every EC-Lab version or technique. Keep it behind a replaceable adapter. [yadg repository](https://github.com/dgbowl/yadg)

Before committing to a parser, build a compatibility matrix by instrument, EC-Lab version, technique, file format, locale, and file size. Use matched `.mpr` and `.mpt` exports from the same run to compare independent representations. Record supported, partial, and unsupported cases. For an unsupported binary version, preserve the original and offer an EC-Lab text-export route with an explicit explanation.

Both repositories display GPL-3.0 licensing. Decide the intended distribution model and review dependency licensing before building a distributable product around a parser. Architecture alone should not be assumed to resolve license requirements. [yadg license information](https://github.com/dgbowl/yadg)

Parser requirements:

- Detect type using file contents as well as extension.
- Preserve original bytes, original headers, column names, row order, and unknown fields.
- Normalize decimal separators, encodings, and unit variants without losing the source representation.
- Distinguish recorded zero from missing values and invalid values.
- Recognize time resets, counter resets, technique changes, interrupted runs, loops, and concatenated data.
- Prevent duplicate import using a file hash, while allowing distinct analyses of one file.
- Do not silently sort acquisition data or merge files based only on filenames.
- Bound memory, processing time, archive expansion, and upload size; reject archive path traversal.

## 3. Metadata and normalized data model

Use the hierarchy Project → Cell → Experiment → Technique segment → Cycle/step/spectrum → Analysis run → Artifact.

Separate three layers: immutable source files, normalized observations, and derived results. A changed mass or recipe creates a new analysis result, without editing the source.

Time-series observations should carry source file hash and row index, segment identifier, local elapsed time in seconds, absolute time when available, current in amperes, named potential channels in volts, temperature in kelvin when available, instrument flags, native cycle identifiers, derived cycle identifiers, and charge counters if recorded. Preserve individual working, counter, and reference-related potential channels; do not assume `Ewe` always represents full-cell voltage.

Impedance observations additionally require spectrum identifier, frequency in hertz, real and imaginary impedance in ohms, DC operating condition when known, excitation amplitude when known, and acquisition context. Explicitly map whether the source column contains imaginary impedance or its negative.

Cell profiles should support:

- Cell ID, material, positive and negative electrode descriptions, electrolyte, and configuration.
- Two-electrode, three-electrode, blocking-electrode, and symmetric-cell configurations.
- Active-material mass, composite mass, active fraction, area, and thickness as distinct quantities.
- Both electrode masses when relevant, and the selected denominator for each normalized result.
- Reference electrode and potential scale, polarity convention, temperature, pressure if known.
- Nominal capacity or theoretical capacity basis for C-rate; formula and electron count when supplied.
- Replicate group, batch, formation protocol, test purpose, and free-text notes.

Each metadata value needs a unit, origin (file, user, or calculation), and confirmation state. Display imported values as available metadata, not as guaranteed correct specimen information. For profiles without mass, continue with unnormalized measurements.

## 4. Analysis modules and release order

### A. Galvanostatic cycling: first priority

Automatic plots: voltage and current versus time; selected-cycle voltage versus capacity; charge/discharge capacity versus cycle; coulombic efficiency; retention; mean charge/discharge voltage; energy and energy efficiency where cell voltage is identified; rate-step comparison.

Segmentation should use native technique, step and loop metadata first, with current and potential behavior as a documented fallback. Recognize rest, constant-current, constant-voltage, formation, incomplete half-cycles, and partial cycling. Store native cycle numbers separately from reconstructed cycle numbers. Allow manual boundary correction and reuse it through a recipe.

Integrate within valid contiguous segments. Do not bridge a time reset, unrecorded gap, or current reversal. Compare integrated charge against recorded instrument counters when available and explain discrepancies. Explicitly configure whether constant-voltage tails contribute to capacity. Do not globally infer “charge” from positive current for every electrode experiment; establish a cell convention.

Reference definitions for implementation:

- Capacity magnitude: Q in mAh = (1000/3600) × integral of |I| dt, with I in A and t in s, evaluated within an identified unidirectional charge or discharge segment.
- Specific capacity: q = Q/m, with active mass m in grams and denominator identified.
- Areal capacity: Q/A, with area in cm².
- Coulombic efficiency: 100 × Q_discharge/Q_charge for explicitly paired steps or cycles. Zero or absent denominators yield unavailable, not infinity.
- Retention: 100 × Q_discharge,n/Q_discharge,reference. The reference cycle is visible and selectable; formation exclusions are recorded.
- For identified full-cell voltage and directional energy flow: energy magnitude in Wh = |integral of V I dt|/3600. Split direction-changing segments; do not hide reversals with a global absolute value.
- Average voltage: energy in Wh divided by capacity in Ah for the same segment.
- Specific energy: Wh divided by the declared mass in kg. Positive-electrode-based energy must be labeled as such and must not appear as packaged-cell energy density.

### B. Differential analysis

Produce dQ/dV versus voltage and dV/dQ versus capacity for eligible branches, with optional peak tracking. Separate charge/discharge and monotonic branches. Exclude or separately handle constant-voltage segments. Near-zero denominators and repeated potential values require explicit handling.

Retain raw curves and provide derivative processing settings: interpolation grid, smoothing algorithm, polynomial order, window, and edge handling. Compare peak locations and areas across reasonable settings. Display derivative uncertainty or sensitivity where feasible, rather than presenting every small feature as a redox event.

SciPy provides a Savitzky–Golay implementation with explicit window, order, derivative, and spacing parameters. For derivative use, resample appropriately or use a method supporting the actual nonuniform independent-variable spacing. [SciPy documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_filter.html)

### C. Cyclic voltammetry

Automatic outputs: current versus potential, normalized current when metadata permit, cycle overlays, candidate oxidation/reduction peaks, peak potentials and currents, peak separation for approved pairs, integrated branch charge, and cycle evolution.

The system must show peak candidates, integration boundaries, and baseline. Multiple peaks should not be paired solely by nearest distance. Derive charge by time integration; any potential-domain integration must use the correct signed local scan rate and branch conventions.

Later add scan-rate series, peak current versus square root of scan rate, log–log fits, and selected kinetic models. A scan-rate exponent is a fitted descriptor, not a unique proof of mechanism. Diffusion-model outputs require the chosen model, concentration, area, temperature, electron count, and applicability checks. Do not enable these models indiscriminately for porous composite electrodes.

### D. Electrochemical impedance

Initial outputs: Nyquist with equal axis scaling, Bode magnitude and phase, frequency-colored spectra, operating-condition overlays, repeated-spectrum comparison, and recorded data-quality flags.

Fitting workflow: validate spectrum → select approved model or saved recipe → choose frequency range and weighting → fit with bounds and multiple initial guesses → inspect residuals and identifiability → report estimates and limitations.

Evaluate `impedance.py` for fitting and Lin-KK screening. Its documentation describes circuit analysis and validation. Lin-KK checks consistency with Kramers–Kronig behavior; a passing result should not be advertised as independent proof of all experimental validity conditions. [impedance.py](https://impedancepy.readthedocs.io/en/latest/) and [validation documentation](https://impedancepy.readthedocs.io/en/latest/validation.html)

Require circuit, parameter units, bounds, starting values, weighting, residuals versus frequency, and failed-fit status in exports. Report fit uncertainty with its method and assumptions, and flag poorly constrained or strongly correlated parameters. A CPE coefficient must not be labeled as ordinary capacitance; any effective-capacitance conversion must declare its formula and circuit assumptions.

Do not automatically name every arc “charge-transfer resistance,” remove inductive points, or pick a physical mechanism solely from lowest fit error. Reference-electrode configuration and full-cell contributions matter. DRT belongs in a later release with regularization sensitivity and validation.

### E. Solid polymer electrolyte and symmetric-cell workflows

Add a conductivity recipe using sigma = L/(R_b A), with thickness L and effective electrode overlap area A in consistent units and an explicitly justified bulk resistance R_b. Using cm and cm² gives S/cm. Flag thickness, contact, geometry, and resistance-assignment uncertainty.

Provide conductivity versus temperature and optional Arrhenius/VTF fits, with fit-range selection and residual inspection. Require measured temperature metadata rather than extracting temperature from a filename without confirmation. Treat heating/cooling branches separately. Activation-energy output must match the chosen equation and logarithm convention.

For symmetric cells, report polarization versus time and current density plus step summaries. Do not divide the total impedance by two without an explicit model assuming equivalent interfaces. Add transference-number workflows only after independently validating the selected formula, prerequisites, and before/after impedance treatment.

### F. Pulse, hold, and relaxation methods

OCV: potential versus time, drift, relaxation duration, and user-defined stabilization criteria; operational stabilization is not proof of thermodynamic equilibrium.

CA/CP: current or potential versus time, integrated charge, step changes, and selected fit windows. GITT/PITT: first provide pulse segmentation, transient plots, relaxation flags, and fitted-window diagnostics. Add model-dependent diffusion estimates only in a later validated release, with geometry, length scale, thermodynamic assumptions, ohmic-drop treatment, and fit windows exposed. Suppress the coefficient when required inputs or model conditions are absent.

## 5. Calculation workspace

Include a unit-aware calculator connected to each cell profile:

- Theoretical capacity q_th = nF/(3.6M) in mAh/g, with M in g/mol and documented electron count n.
- Active mass from composite mass × active fraction; do not confuse wt% with a fraction.
- Electrode area from diameter, active loading in mg/cm², and current density in mA/cm².
- Applied current from the selected nominal/theoretical capacity and C-rate. Store which capacity defines 1C.
- Practical utilization relative to the declared theoretical capacity.
- Nominal N/P capacity ratio, with separate electrode mass and usable specific-capacity inputs and a clear warning if the inputs use incomparable conditions.
- Electrolyte amount per capacity and related preparation calculations when sufficient metadata are present.

Display formula, inputs, units, denominator, and provenance beside each output. Zero, negative, missing, and dimensionally inconsistent inputs require meaningful validation. Potential-reference conversion requires an explicit reference and conditions.

## 6. Automation rules and reproducibility

Each result has one status: ready; provisional with a named assumption; needs metadata; not applicable; or failed validation. The dashboard should explain exactly what is missing and offer the smallest correction. Reusable lab recipes should preserve electrode convention, cycle rules, reference cycle, normalization basis, approved circuit, fit windows, and plot styles.

Every result must retain the source hashes, source row ranges, metadata revision, parser version, calculation version, recipe, filters, units, fit configuration, random seed if used, and creation time. Exclusions remain visible in an audit trail. A manual change invalidates dependent results and triggers recalculation only where needed.

An optional AI layer can later help users navigate, describe plots, or select an existing recipe. Numerical results must come from tested deterministic functions. Any generated explanation must identify the underlying results and avoid asserting an unmeasured mechanism. No external AI service is necessary for the core workflow.

## 7. User interface

Six main views:

1. Projects: recent cells, experiment folders, import status, search, tags.
2. Import review: detected technique, file compatibility, metadata, preview, unresolved boundaries.
3. Results: appropriate plots and metric cards, quality status, selected cycles.
4. Analysis: derivative settings, fit windows, models, baseline, raw/processed comparison.
5. Compare: explicitly selected compatible cells and conditions, replicate statistics.
6. Export: figures, tabular results, report, complete reproducible project.

For comparisons, require compatible voltage references, normalization bases, temperatures and protocols, or label the differences. Replicate statistics must count independent cells, not cycles within one cell as independent replicates. Display individual results alongside group summaries and define error bars.

Figure controls: single/double-column dimensions, font, line width, colorblind-friendly palette, axis units, cycle colors, editable legend, panel layout, and saved journal styles. Keep linked highlighting between table rows and curve regions.

Exports: vector SVG/PDF figures; PNG/TIFF where needed; CSV metrics and curve data; Excel summary within format limits; HTML/PDF analysis report; project archive containing original files, metadata, recipes, versions and results. Include an exported plotting specification or script so figures can be regenerated. Validate vector exports and preserve meaningful extrema when display reduction is used.

## 8. Proposed architecture

Use one reusable scientific engine behind both the interface and a command-line batch runner.

| Layer | Proposed technology | Purpose |
|---|---|---|
| Scientific engine | Python, NumPy, SciPy | Segmentation, integration, derivatives, regression |
| Data tables | pandas initially, Arrow/Parquet for storage | Typed, efficient analysis and persistence |
| EC-Lab adapter | Pinned, tested yadg candidate | Binary/text import through a stable internal interface |
| Units and schemas | Pint and Pydantic candidates | Explicit units and input validation |
| EIS adapter | impedance.py candidate | Model fitting and validation |
| Local API | FastAPI candidate | UI-to-engine operations |
| Interface | React/TypeScript and Plotly candidates | Responsive plots, controls, project navigation |
| Publication export | Matplotlib candidate | Deterministic vector figures |
| Project index | SQLite | Cells, recipes, result references, job state |
| Background jobs | Local worker processes | Cancellation, memory isolation, UI responsiveness |
| Verification | pytest and browser tests | Numerical and user-workflow regression checks |

These are proposed choices, not a claim that integration has already been demonstrated. Verify supported versions and licenses during the technical spike. Avoid a separate scientific implementation in JavaScript: it would create two calculation paths to maintain.

Organize source into importers, schema, segmentation, analyses, calculators, validation, plotting, reports, API, UI, and test fixtures. An analysis plugin should declare required observations and metadata, applicability rules, numerical routine, output schema, and diagnostics.

Jobs need queued/running/completed/failed/cancelled states, persistent progress, actionable errors, and restart recovery. Cache using file hash + metadata revision + recipe + engine version. Do not calculate on display-downsampled data. Chunk large imports and isolate expensive fits.

A local service should bind to loopback, protect requests from unrelated browser origins, and avoid exposing arbitrary filesystem access. Default to no telemetry or cloud transfer. Never overwrite measurement files. These are implementation requirements, not extra user approval steps.

## 9. Validation and acceptance criteria

Obtain a representative corpus of approximately 20–30 experiments with paired native/text exports where possible. Include GCPL, CV, PEIS/GEIS, OCV, linked protocols, constant-voltage tails, incomplete runs, locale differences, multiple instrument/software versions, and a large file. The exact count matters less than coverage.

Validation has four independent layers:

1. Parser fidelity: row counts, time bases, units, flags and selected raw values against paired exports and source inspection. No unexplained row loss or silent sign changes.
2. Analytic reference cases: constant-current capacity, variable-current integration, known capacitor behavior, simple resistor/RC spectra, time resets, and invalid metadata. Example: 1 mA for 3600 s must yield 1 mAh within floating-point tolerance.
3. Real scientific comparisons: cycle assignments and metrics compared against documented EC-Lab settings and independent calculations; equivalent-circuit comparisons use identical model, weighting and bounds. Any disagreement must be explained rather than hidden behind tolerance.
4. End-to-end use: import → edit mass → verify dependent recalculation → compare → export → reopen → reproduce.

Proposed numerical gates: analytic integrations relative error below 1e-6 where the input construction permits; complete clean-cycle capacity agreement within 0.1% against an equivalent independent calculation, with exceptions investigated. Parser differences must use field-specific precision tolerances, not an arbitrary universal percentage. Diffusion and fitting modules require separate model-specific gates before release.

Additional required cases: current-direction ambiguity, first-step discharge, repeated timestamps, counter rollover/reset, duplicated files, missing mass, zero charge denominator, EIS imaginary-sign conventions, inductive spectra, failed fits, short/noisy derivative traces, and replicate grouping errors.

Benchmark on a declared Windows laptop configuration, provisionally 4 CPU cores and 16 GB RAM. Initial targets: preview a supported one-million-row file within 10 seconds; complete routine cycling analysis within 30 seconds; handle a 100-file batch with progress and bounded memory. Measure first, then revise targets transparently. Advanced fits have separate cancellation and time budgets.

## 10. Milestones, staffing and dependencies

Assume one experienced developer working full time, with regular electrochemist review and sample files available. Estimates are effort ranges, not delivery guarantees.

| Phase | Estimated duration | Concrete exit condition |
|---|---|---|
| 0. Compatibility and design spike | 1–2 weeks | Representative files collected; parser and license strategy chosen; normalized schema and acceptance cases agreed |
| 1. First vertical slice | 2–3 weeks | MPT GCPL import → segmentation → plots/metrics → CSV/SVG export, numerically checked |
| 2. Useful battery beta | 3–5 weeks | Tested MPR import, batch handling, CV, EIS plots, saved profiles and projects, reproducible exports |
| 3. Research workflows | 3–5 weeks | Derivatives, EIS fits and diagnostics, conductivity recipes, comparisons and report generation |
| 4. Release hardening | 2–3 weeks | Windows installer, offline/recovery checks, performance benchmarks, documentation and user trial |
| Later research modules | Separate estimate | GITT/PITT diffusion, DRT, advanced kinetics, other vendors, cloud collaboration |

The first useful beta is approximately 6–10 weeks under those assumptions; the described dependable research release is approximately 11–18 weeks. Unknown binary variants or sparse validation data can extend this. Budget effort for scientific review and user testing, not only interface construction.

Suggested responsibility split: developer owns architecture and tests; electrochemist approves method definitions, real-data annotations and fit interpretation; two or three pilot researchers test whether an unfamiliar file can be processed without assistance. These are proposed roles, not a request to delegate the current task.

## 11. First development backlog

1. Collect representative `.mpr`, matching `.mpt`, and available `.mps` files plus expected outputs.
2. Write the compatibility matrix and define active-mass, potential and charge-direction conventions.
3. Test candidate parsers on the corpus and document unsupported variants.
4. Implement immutable import plus unit-normalized schema and source-row traceability.
5. Implement and validate one complete GCPL workflow before broadening technique coverage.
6. Add the interface with an import review and immediate valid plots.
7. Add direct binary import, project persistence, batch jobs and export reproducibility.
8. Add CV and EIS visualization, then introduce derivative and fitting tools behind validated recipes.
9. Pilot on actual battery, polymer-electrolyte, symmetric and blocking-cell experiments.
10. Package and document the supported release; publish a known-limitations and compatibility table.

## 12. Decisions and inputs for implementation

Default assumptions in this plan: battery research first; Windows first; offline core; one-user projects initially; direct native EC-Lab import required for beta; model-based outputs remain reviewable; no automatic physical-mechanism claims.

To begin implementation efficiently, request one complete GCPL example, one CV example and one PEIS example, preferably as native/text pairs, together with cell configuration, active mass, area, and one trusted existing plot or metric table. More techniques can be added progressively. These inputs are not needed to understand or approve this plan, but are necessary to establish actual parser compatibility and scientific correctness.

The defining product capability should be reproducible conversion of a complete experiment folder into defensible results: readable plots, explicit calculation definitions, and clear identification of outputs that need researcher input.
