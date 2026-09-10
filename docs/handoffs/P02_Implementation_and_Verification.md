# P02 — cycling reference fixtures and verification

Version 0.1.0 · 2026-09-10

**Delivered:** 21 frozen synthetic observation fixtures, one policy fixture, explicit independent expectations, a SHA-256 fixture manifest, an executable audit and machine-readable evidence. Status: cycling baseline implemented and reference-audited; P01 interoperability software-tested. No experimental validation or production cycling calculation is claimed.

## What changed and why

P02 turns M01's method and failure rules into concrete datasets that can challenge the later importer, segmentation and cycling engine. P01 code and the M01 contract are unchanged. The bundle includes both so the audit can run after extraction.

The corpus covers constant and varying current, nonuniform sampling, CC/constant-voltage tails, measured rest current, current/power reversals, unexplained gaps, local-clock resets, duplicate boundary timestamps, incomplete branches, first-step discharge, missing current/voltage, unresolved Ewe, counter resets, explicit pairs, polarity conversion and display downsampling. Normalization variants distinguish active material, composite and whole-cell mass, and geometric area. Separate policy expectations cover formation, retention references, CE above unity and common-mass cancellation.

Source basis: the inspected local `M01_Cycling_Method_Specification.md` v0.1 and its scoped `Cycling_Source_Register.md`, plus the earlier independent arithmetic audit. No additional scientific source or attached PDF was newly inspected for this package; no citation-access claim has been extended. No external dependency was added.

## Observed verification

**21 observation fixtures; 268 checks passed** on Linux, Python 3.12.14. These checks include:

- Frozen fixture hashes and exact rational expectations for charge, directional throughput, terminal energy and supported duration.
- Independent midpoint/Simpson quadrature, with current/voltage roots split before directional assignment.
- P01 projection, raw-token preservation and source-verified reopening for every observation fixture. Temporary archives remain byte-identical after reading.
- Rejection of attempts to declare reset-crossing or same-time edges supported, and missing/invalid normalization metadata handling.
- CC/tail components, explicit-pair CE and energy ratio, retention-reference arithmetic and common-mass cancellation.
- Detection of deliberate wrong alternatives: bridging a gap, using abs(net charge) as throughput, replacing the declared energy model with endpoint-power trapezoids, and integrating only display endpoints.

The corrected M01 benchmark is preserved explicitly: for I=1+t A and U=2+t V over 0–2 s, energy is 38/3 J. Endpoint-power trapezoids give 14 J, a different interpolation result. The earlier erroneous draft value 50/3 J is not reinstated. No reference discrepancy occurred in this package's executed audits, and no tolerance was relaxed.

Frozen expected numbers come from written geometric/analytic derivations. Verification uses exact fractions and a quadrature route independent of M01.N1's coefficient formula. This is stronger than generating expectations with the future production routine, but it is not external experimental validation or an independent-person review.

## Limits

P02 supplies acceptance data; it does not implement the production rules named in each fixture's `blocked_outputs`. Only identified P01 data-contract gates are currently exercised against application code. A future analysis runner must consume these fixtures and compare actual numerical outputs, applicability states, support, normalization and provenance against the frozen contract. Policy-only expectations must not be counted as already-passed production tests.

The fixtures are synthetic JSON/TSV representations, not native MPR or MPT files. No EC-Lab parser, automatic segmentation or counter-reconciliation algorithm has been validated. Physical uncertainty is not evaluated; exact synthetic arithmetic does not justify zero experimental uncertainty. The common-mass example demonstrates cancellation of that contribution only.

This is the first cycling corpus, not all of P02 for future electrochemical methods. Interval-mean acquisition, asynchronous channels, noisy/threshold-sensitive boundaries, nonlinear-signal sampling convergence, extreme dynamic range, long-sum floating-point behavior and larger randomized corpora remain extensions before claiming those capabilities. EIS, CV, conductivity and transport methods require their own reviewed references and fixtures.

Windows execution, offline dependency distribution and large-data performance remain untested. P01's existing snapshot and schema limitations still apply.

## Handoff: P03 EC-Lab import

Begin with a bounded MPT reader and a compatibility matrix grounded in official format documentation and representative files. Preserve bytes, lexical columns/units/flags, row provenance and technique/settings context. Keep counter values separate from reconstructed current integration. Compare native MPR and matching full-resolution MPT through an independently evaluated native-file reader; do not infer universal compatibility from either parser's advertised support.

Useful next input is one cycling `.mpr` plus its matching full-resolution `.mpt`, optional `.mps`, EC-Lab/instrument version and declared cell/current/voltage conventions. Their absence does not block parser contract work or clearly labeled synthetic-format tests, but does block an experimental compatibility claim. Segmentation and production cycling follow P03/P04, using this corpus as frozen acceptance input.
