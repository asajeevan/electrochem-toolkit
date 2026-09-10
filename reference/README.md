# P02 — frozen cycling reference fixtures v0.1.0

This package provides 21 synthetic observation fixtures, one policy fixture and an independent executable audit for M01. It is not a production cycling calculator or EC-Lab parser. Original scientific contracts and the unchanged P01 core accompany the source bundle.

## Run the audit

Extract the bundle. From the extracted root directory, use Python 3.11/3.12 (observed verification: Linux Python 3.12.14):

```sh
python -m pip install -r electrochem_core/requirements-lock.txt
python p02_reference/verify.py
```

The verifier checks the frozen fixture hashes, exact reference arithmetic, P01 projection and temporary snapshot reopening. It writes `p02_reference/evidence/verification.json`; it never rewrites fixture expectations. Expected output: 21 observation fixtures and 268 passed checks. These are individual assertions, not 268 independent experiments or test methods. Installation needs package files; the audit itself is offline.

`freeze_cases.py` is the authoring record. Do not run it during normal verification or use it to update expectations to match a failing implementation. A deliberate fixture revision must review derivations, update version/history and regenerate hashes separately. The hash manifest detects changes relative to the bundled manifest; it is not a signed authenticity guarantee.

## Fixture contract

Each Sxx JSON contains original lexical observations, units, acquisition order implied by row order, continuity blocks, explicitly supported adjacent edges, reasons for unsupported edges, channel roles, polarity mapping, completeness, exact expected SI quantities and a written independent derivation. Decimal strings are exact synthetic inputs; null is missing. They are not EC-Lab exports. The fifth original column preserves synthetic charge-counter tokens when present.

Edges are zero-based: edge k joins rows k and k+1. No sorting, smoothing, baseline subtraction, resampling or extrapolation is permitted. All declared supported signals use linear point-sample reconstruction; the fixture definitions provide the support evidence. They do not teach an importer to infer support from the values. Unsupported intervals are not assigned zero current. A signed integral without any eligible support is null, not zero.

Positive/negative charge fields describe current polarity and remain distinct from named charge/discharge capacities. Negative charge and delivered energy fields contain nonnegative magnitudes. Signed energy uses the passive terminal convention. S03/S04 are mathematical sign-splitting challenges; negative voltage in S04 is not a proposed ordinary battery operating protocol.

`blocked_outputs` contains required future analysis behavior, not P01's implemented diagnostic vocabulary. Similarly formation/reference selection, completeness and detailed step components are fixture instructions for later recipes. The P01 projection tests raw observations, interval support, channel roles and the explicitly constructed S19 pair; it does not encode every recipe field or claim to implement segmentation. Unknown duration in S08 means no coverage percentage can be calculated.

## Independent reference method

Frozen values are explicitly written from rectangles, triangles, polynomial antiderivatives and rational ratios. The verifier uses Python Fraction arithmetic. It evaluates linear current at the midpoint and quadratic power with Simpson's rule on subintervals split at roots of current and voltage. Simpson's rule is exact for the degree-two product of the declared linear signals. This differs from evaluating M01.N1's coefficient expression, and does not use the P01 engine to generate expected values.

The audit requires exact rational equality. Future floating-point implementations should compare each small-fixture quantity using `abs(actual-expected) <= max(1e-14, 1e-12*abs(expected))` in the stated SI unit (dimensionless for ratios). This is a provisional arithmetic allowance for this small corpus, not a universal instrument tolerance. Scientific status, missingness, support and identifiers must match exactly. Scale/large-sum validation needs additional fixtures before widening scope. No uncertainty is inferred from a passed arithmetic comparison.

## Coverage

| IDs | Challenge |
|---|---|
| S01 | Constant current; active/composite/cell mass; geometric area; missing/zero/negative mass |
| S02 | Independently varying current/voltage; corrected 38/3 J reference; alternative power interpolation |
| S03–S04 | Current zero crossing; voltage/power sign crossing |
| S05–S06 | CC and constant-voltage components; measured nonzero rest current |
| S07–S10 | Gap, reset, known same-time endpoints and unexplained boundary reversal |
| S11–S13 | Missing current, missing voltage, unresolved Ewe |
| S14–S18 | Sparse supported recording, interrupted tail, first discharge, counter reset, nonuniform samples |
| S19–S21 | Explicit complete pair, inverted raw current convention, display decimation |
| policies.json | Formation/reference selection, above-unity CE, zero denominator, configuration interpretation and common-mass cancellation |

Policy arithmetic is audited for retention, above-unity CE and shared-mass cancellation. Configuration applicability, zero-denominator output status and removal of a reference remain specified acceptance rules, not tests against a production engine. Zero/negative normalization metadata rejection is exercised against P01.

See `P02_Implementation_and_Verification.md` at the bundle root for limitations and the next package.
