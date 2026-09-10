# M01 verification and handoff

10 September 2026 | P00 cycling subset | Specification 0.1

## Delivered

- `M01_Cycling_Method_Specification.md`: ten method cards, shared measurement model, units, interval rules, sign conventions, pairing/tail policies, uncertainty and reproducibility requirements.
- `Cycling_Source_Register.md`: exact inspected sections, source identities, access limits, detected source discrepancy, and evidence mapping.
- `cycling_reference_checks.py`: standalone Python standard-library reference audit, with independently derived expected quantities. This is not the production numerical engine.
- `cycling_reference_results.json`: actual machine-readable results and script hash.

## Observed verification

Executed with Python 3.12.14: `python3 cycling_reference_checks.py`.

Final outcome: **14/14 reference checks passed**, plus a separate composite-midpoint cross-check of the varying-current/varying-voltage energy example.

| Case | Quantity checked | Final expected value |
|---|---|---|
| R01 | Constant-current charge | 3.6 C = 1 mAh |
| R02 | Active-mass normalization | 100 mAh/g |
| R03 | Linear current, nonuniform samples | 2 C |
| R04 | Work at 3 V | 0.003 Wh |
| R05 | U=2+t V, I=1+t A, 0–2 s | 38/3 J |
| R06 | Opposite-direction branch throughput | 20 C, despite zero net charge |
| R07 | CC plus linear constant-voltage tail | 3.9 C |
| R08 | Energy efficiency at unequal directional voltages | 91.875%, with CE=98% |
| R09 | Selected-reference retention | 90% |
| R10 | Theoretical capacity unit consistency | Approximately 115.38437 mAh/g |
| R11 | Area conversion | 1 mAh/cm² |
| R12 | 0.5C on a 2 mAh reference | 0.001 A |
| R13 | Independent 1% charge and 2% mass uncertainty | Relative standard uncertainty √5/100 |
| R14 | Common-mass contribution to retention variance | Exactly zero; other error contributions remain |

Most comparisons use exact rational arithmetic, so no tolerance is needed for those constructed inputs. R13 uses 1e-15 absolute tolerance on a dimensionless floating-point quantity. This is an arithmetic tolerance, not experimental accuracy.

For R05, independent composite midpoint integration with 10,000 intervals gave 12.66666666 J versus the analytic 12.666666666666666 J. Absolute error was 6.666665441912301e-9 J, inside the derived 2/(3N²) truncation error plus 1e-12 J rounding allowance. The candidate product-interpolation formula and this independent quadrature agree with the primitive integral. No production integration implementation was tested.

## Failure discovered and corrected

The initial R05 expected value was mistakenly entered as 50/3 J. The exact product-interpolation calculation and independent midpoint integration both disagreed with it. The first audit returned 13/14 passing reference checks and a failed midpoint comparison (roughly 4 J discrepancy).

Independent expansion gives UI=2+3t+t², whose integral on [0,2] is 4+6+8/3=38/3 J. The endpoint-power trapezoid is 14 J, rather than the initially written 18 J; its excess remains 4/3 J. Corrected the target and explanatory text. **No tolerance was relaxed and no integration expression was changed to hide the discrepancy.** The second audit passed.

## Scientific clarifications completed

1. Separate instrument-reported, reconstructed measured, and setpoint-estimated charge. Manufacturer descriptions establish that internal calculations and saved observations can have different time resolution; user-file behavior still needs verification.
2. Define terminal energy with an explicit passive sign convention. Preserve the distinction between independently linear voltage/current and linearly interpolated sampled power.
3. Define temporal support as explicit intervals. Unknown step endpoints or gaps cannot acquire charge through automatic interpolation.
4. Define charge/discharge pairing separately from electrochemical polarity, with documented treatment of first discharge, formation, partial branches, and constant-voltage tails.
5. Require covariance for shared measurement errors and avoid counting common-mass uncertainty twice in retention/CE.
6. Record the apparent CE-to-ppm conversion error in the BioLogic glossary. This does not invalidate the independently checked elementary equations.

## Limits and release gates

- No user EC-Lab measurements, native/text pairs, parser, segmentation engine, GUI, or Windows build were tested.
- Invalid-input and incomplete-model behaviors are specified in M01, but not yet exercised against application code.
- The supplied textbook was read selectively, not cover to cover. The supplied ChemTexts article was inspected for scope and early assumptions; its complete CV derivations are deferred.
- Correction searches did not establish a complete errata history for either supplied publication. No absence-of-corrections claim is made.
- Counter reset/endpoint semantics, synchronization, actual calibration uncertainty and recording policies remain instrument-specific verification gates.
- Exact rational identities, numerical quadrature comparisons and experimental validation are different evidence classes. These checks support the proposed numerical contract; they do not establish experimental accuracy.

## Next package

Proceed to **P01: units, measurement conventions and shared data model**, with P02 fixture expansion depending on it.

Concrete next deliverable: versioned schema definitions for immutable sources, normalized observations, interval support, metadata revisions, branch/pair identifiers, result status, provenance and uncertainty; explicit unit conversions; meaningful checks for dimensional mistakes and preservation of unresolved metadata. Evaluate candidate dependencies before committing to them. Preserve the source quantities and diagnostics required by M01.

Then extend P02 into frozen synthetic datasets and negative cases before implementing P03/P04/P05. Obtain one representative GCPL .mpr/.mpt pair and settings when available; this is a real-data gate, not a blocker for P01.
