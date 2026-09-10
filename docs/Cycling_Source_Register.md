# Cycling source register

Revision 0.1 | Inspected 10 September 2026 | Scope: M01, not a full electrochemistry literature review

The identifiers C01–C06 are new and do not overwrite S01–S19 in the earlier theory document. “Inspected” below means the specified material was actually accessed, not that the complete work was read. Numerical reconstruction and software policies in M01 are explicitly project derivations/decisions, not quotations from these sources.

## C01 — Current, charge and nonfaradaic contributions

Allen J. Bard, Larry R. Faulkner and Henry S. White, *Electrochemical Methods: Fundamentals and Applications*, third edition, Wiley, 2022. User-supplied PDF, 1107 PDF pages.

- Inspected text: printed pp. 7–8 (PDF pp. 63–64), §1.1.5, equations 1.1.12–1.1.15; printed pp. 295–296 (PDF pp. 351–352), §6.6.1 and beginning of §6.6.2, equations 6.6.1–6.6.6.
- Visually checked the rendered equations on PDF pp. 64 and 351 to resolve extraction/layout risk.
- Supports current as time derivative of charge and the distinction between integrated measured charge and a particular reaction contribution. The chronocoulometry discussion is evidence that total charge can have additional contributions; its solution-phase diffusion model is not imported into battery cycling.
- Project-derived use: theoretical charge per mass from nF/M. Explicit electronic stoichiometry and composition remain inputs.
- File SHA-256: `c8f275c377e9fa981b6b4e69a63aa20b675acb846fe516531837cef93a96fb44`.
- Source identity: `libfile_430c6b1487488191ba663c27bcc64dd8`.
- Update check: a targeted errata search did not resolve an authoritative errata list. Do not claim that no corrections exist. Selected elementary relations were also checked algebraically and against C02. Book-wide review remains outside this package.

## C02 — Battery descriptor definitions and an identified source error

BioLogic, [Battery science: Interactive glossary of terms](https://www.biologic.net/topics/interactive-battery-science-glossary-of-terms/). Page states updated 15 November 2024.

- Inspected entries: capacity, charge, charge profile, CE, C-rate, cycle, current, electrodes, energy and specific energy. Supports the basic descriptor definitions used by M01.
- The glossary distinguishes electrochemical current polarity from battery operation; its charge-positive example is not treated as a universal mapping for any EC-Lab electrode setup.
- **C02-D1:** its displayed CE-to-ppm expression divides by 1,000,000. For a dimensionless fraction, the numerical value in ppm must multiply by 1,000,000. M01 defines percent/ppm independently and distinguishes CE from inefficiency.
- The variable-current/voltage energy integral is used; isolated constant-signal product expressions do not justify multiplying unrelated means.
- No full-page endorsement: other glossary statements and examples were not independently validated. No correction notice for C02-D1 was established in this review.

## C03 — Instrument quantities versus saved observations

BioLogic, [Data of interest – work more efficiently](https://www.biologic.net/topics/data-of-interest-getting-the-most-out-of-your-blue-box/). Page states updated 18 November 2024.

Inspected “Accuracy and autonomy,” the variable-process table and cycle-processing discussion. It distinguishes the instrument calculation time base from the recording rate and describes per-cycle charge counters. This supports retaining instrument and reconstructed quantities independently. It does not establish counter fields, endpoint semantics or timing for every instrument/firmware/technique. TN38 is referenced by the page but was not obtained; record it as identified only. Do not use its abbreviated constant-power energy table as a universal integration algorithm.

## C04 — Recording information loss, corroborating manufacturer context

BioLogic, [What is a battery cycler?](https://www.biologic.net/topics/what-is-a-battery-cycler/). Page states updated 6 June 2025.

Inspected “Value of interest calculation” and surrounding analysis discussion. Describes hardware calculation before software sampling. Use only as corroboration of recording information loss, not as an accuracy guarantee for a user's instrument or a fixed internal sampling rate for all devices. The difference in example time bases between C03 and C04 reinforces the need for device-specific verification.

## C05 — Numerical integration interface

[SciPy integrate.trapezoid documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.trapezoid.html), fetched page identifies SciPy 1.18.0.

Inspected API definition, treatment of supplied coordinates, and decreasing-coordinate example. The function processes coordinates in their supplied order without sorting. It does not validate electrochemical continuity. M01's segmentation/gap rules must run before integration. This review does not select or install that SciPy release; the reference-audit script uses only Python's standard library. The product-of-linear-signals energy expression is independently derived in M01 rather than attributed to SciPy.

## C06 — Measurement uncertainty

NIST, [Technical Note 1297, Appendix A: Law of Propagation of Uncertainty](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-law-propagation-uncertainty). Page states updated 11 September 2025.

Inspected A.1–A.3, especially equation A-3 and its first-order approximation/covariance qualification. M01 applies this to integrated charge and ratios; the explicit ratio gradients and common-mass cancellation are derived here. No uncertainty is invented when measurement information is absent. This source does not supply an EC-Lab calibration budget.

## C07 — Supplied voltammetry article, reserved for a later package

Rafael A. L. Chioquetti, João V. S. Vital and Silvia H. P. Serrano, [Understanding the mathematics of voltammetry: a step-by-step guide](https://link.springer.com/article/10.1007/s40828-026-00224-y), *ChemTexts* 12, 14 (2026), DOI 10.1007/s40828-026-00224-y.

- User-supplied PDF: 31 pages. Inspected abstract/introduction and geometry/diffusion assumptions on PDF pp. 1–4; publisher page accessed for identity and an update check.
- Relevant scope: reversible macroelectrode response, semi-infinite diffusion, with explicitly stated geometry and boundary assumptions. Assigned to P00-CV/P07 and future pulse-method review.
- Not used to justify cycling metrics or approved as a validated CV implementation. The later mathematical derivations, fractional-calculus treatment, and kinetic extension have not been fully reviewed here.
- A “Correction” text search on the publisher page found no match; the targeted correction search was inconclusive. This is not evidence that no update exists.
- File SHA-256: `a029d9673c625eeab81a3e61141e5ff074dfae7872fd22bea8fa474a8bf31270`.
- Source identity: `libfile_6737c8bdaa5c819197905606e6a6819f`.

## Equation-to-evidence and remaining gates

| Contract | Evidence / independent work | Remaining gate |
|---|---|---|
| Q=∫I dt; nF/M | C01,C02; arithmetic references | P01 units; P03 observation semantics |
| Capacity, CE, C-rate, energy | C02; explicit project pairing/sign definitions | Real files and protocol annotations |
| Area normalization and retention | Dimensional definition and explicit ratio convention; R09,R11 | Metadata basis and reference approval |
| Point-sample quadrature | C05 and independent polynomial derivation | Sampling suitability and production tests |
| Product interpolation for energy | M01.N1 derivation; exact primitive and composite midpoint check | Channel synchronization and numerical implementation |
| Counter comparison | C03,C04 | Instrument/version-specific documentation and matched exports |
| Uncertainty | C06; explicit gradients and algebraic cancellation | Real calibration, timestamps, offsets, covariance |
| CV model theory | C07 scoped reading only | Full method/derivation/correction review; independent models |

No inaccessible reference is treated as read. No unknown counter convention, publication correction status, native file compatibility or instrument calibration has been inferred.
