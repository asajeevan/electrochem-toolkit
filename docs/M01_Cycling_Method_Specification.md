# M01 — Battery cycling: scientific and numerical contract

Version 0.1 | 10 September 2026 | P00 cycling subset

**Deliverable status:** specification established for P01/P02 development, with explicit instrument-specific gates. This is not a cycling engine or an experimentally validated method implementation. Sources and access limitations are in `Cycling_Source_Register.md`; executable arithmetic checks are in `cycling_reference_checks.py`.

## 1. Purpose and scope

Reduce recorded time, current, and potential observations to traceable charge, directional capacity, terminal energy, paired-cycle ratios, and explicitly normalized quantities. First support battery CC and CC–constant-voltage sequences with rests. Here `constant_voltage` is the full control-mode name; reserve `cyclic_voltammetry` for the technique to avoid “CV” ambiguity.

These are measured-signal descriptors. They do not identify individual reactions, lithium inventory loss, active-material loss, or thermodynamic stored energy. Total integrated current includes whatever contributions were measured; no automatic background subtraction or assignment to a single faradaic process [C01].

## 2. Measurement model and shared requirements

All method rows in section 4 inherit this section, the numerical procedures in section 5, and uncertainty in section 7.

| Symbol | Meaning | Internal unit / display |
|---|---|---|
| t, Δt | Local elapsed time and supported interval duration | s / s, min, h |
| I_raw, I | Original current and explicitly mapped current | A / mA, µA |
| s_I | Documented polarity multiplier, +1 or −1; I=s_I I_raw | dimensionless |
| U | Terminal voltage with named positive and negative sensing nodes | V |
| E | Electrode potential versus a named reference | V; reference label mandatory |
| Q_s | Signed integrated electrical charge | C / mAh, Ah |
| Q_b | Nonnegative charge magnitude for one directional branch | C / mAh, Ah |
| W_s, W_in, W_out | Signed terminal work, absorbed and delivered energy magnitudes | J / Wh, mWh |
| m_b, A_g | Selected mass basis; geometric electrode area | kg, m² / g, mg, cm² |
| q_b, q_A | Mass-specific and areal charge | C/kg, C/m² / mAh/g, mAh/cm² |
| n, F, M | Electrons per formula unit, Faraday constant, molar mass | 1, C/mol, kg/mol |
| r | Applied current divided by reference capacity in Ah | h⁻¹, displayed as C-rate |
| u(x), Σ, J_f | Standard uncertainty, covariance matrix, gradient of output function | units follow x and output |

Conversions: 1 mAh=3.6 C; 1 Ah=3600 C; 1 Wh=3600 J; 1 mg=10⁻⁶ kg; 1 cm²=10⁻⁴ m². Thus q[mAh/g]=q[C/kg]/3600, and q_A[mAh/cm²]=q_A[C/m²]/36000. No hidden denominator conversions.

Every observation retains source identity/hash, row reference, column name/unit, acquisition order, native step/cycle flags, validity flags, and original timestamp. Absolute time is optional and never fabricated from local elapsed time. Metadata include origin, revision, and confirmation state.

Required segmentation input: technique, cell/channel identity, current-direction branches, control steps, continuity blocks, and termination/completeness evidence. Method M01 does not infer these silently. A control change does not necessarily end a directional branch; a CC step followed by a constant-voltage tail can belong to one charge branch.

### Cell configuration and interpretation

| Configuration | Permitted M01 interpretation |
|---|---|
| Two-electrode full cell | Capacity and terminal energy after polarity/wiring confirmation |
| Two-electrode metal half-cell | Passed charge and selected material normalization; energy only as measured test-cell terminal energy, explicitly including the metal electrode |
| Three-electrode measurement | Electrode-potential curves; terminal energy only with a terminal voltage measurement or synchronized, compatible electrode potentials whose difference is explicitly constructed |
| Symmetric cell | Directional charge/polarization descriptors; no automatic battery CE or useful storage-energy interpretation |
| Blocking-electrode cell | Passed charge and polarization descriptors; no automatic battery-capacity interpretation |
| Unknown | Raw channel plots and signed-charge results if time/current units and continuity are known; named charge/discharge and energy remain gated |

Electrode oxidation/reduction polarity and full-cell charge/discharge labels are separate metadata. Do not infer them from a material name, positive current, voltage slope, or “Ewe.” Under the terminal passive convention, I enters the positive sensing terminal and U is its potential minus the other terminal; P=UI>0 is absorbed power. Record any sign mapping separately from raw observations.

No diffusion geometry, equilibrium, constant resistance, or single-reaction assumption is required for integrating terminal signals. Geometric area is required only for areal normalization, and need not equal electrochemically active area. Temporal support and channel synchronization are the relevant integration boundary conditions.

## 3. Three charge paths, kept distinct

1. **Instrument-reported charge:** preserve counters, their units, source rows, reset semantics, and native pairing. A mapped counter difference is usable only when its origin, direction and reset behavior are known. An absolute counter endpoint is not necessarily the branch increment.
2. **Reconstructed measured charge:** integrate stored current on eligible intervals, using the procedure below.
3. **Setpoint-estimated charge:** optional later estimate from the programmed current and duration. It must never replace measured charge or fill a missing interval without an explicit, separate model result.

BioLogic describes different calculation and recording time bases [C03,C04]. Therefore saved samples may not contain all information used for the hardware counter. Neither path automatically overrides the other. Compare matching temporal support, normalization, direction, and CC/tail coverage; preserve the difference and investigate flags, rounding, sampling, current offsets, resets and software settings. Do not claim exact EC-Lab reproduction without version-specific evidence.

## 4. Method cards

| ID / purpose | Equation and required additions | Regime, failure rules, numerical reference |
|---|---|---|
| M01.01 Signed charge | Q_s=∫I dt, using valid measured intervals [C01,C02] | Known time/current units; no mass required. Report observed-interval charge if coverage is incomplete. R01, R03, R06 |
| M01.02 Directional capacity | Q_b=∫|I|dt=|Q_s| only on a sign-consistent branch; Q_mAh=Q_b/3.6 | Named charging/discharging requires a confirmed mapping. Reversals are split or unresolved, never hidden by net absolute value. Not automatically rated capacity. R01,R06 |
| M01.03 Mass/area normalization | q_b=Q_b/m_b; q_A=Q_b/A_g | m_b or A_g finite and >0, with named electrode/basis. Active, composite and complete-cell masses are distinct. Without them return unnormalized charge. R02,R11 |
| M01.04 Terminal energy | W_s=∫UI dt; W_in=∫max(UI,0)dt; W_out=−∫min(UI,0)dt [C02; directional split is this project's convention] | Synchronized terminal voltage and passive current convention. Split all supported power sign changes. Electrode potential alone is insufficient. R04,R05,R07 |
| M01.05 Mean voltage / specific energy | Mean directional terminal-voltage magnitude=W_direction/Q_direction in J/C; specific energy=(W_direction/3600)/m_b in Wh/kg | Both integrals use exactly the same eligible support and physical direction; Q>0. A time-averaged voltage is not substituted. For usual positive U/sign-consistent branches this equals charge-weighted U. Mixed-polarity branches require separate reports. R04,R05 |
| M01.06 Paired-cycle CE | CE[%]=100 Q_dis/Q_ch [C02] | Explicit pair IDs, policy and complete compatible portions; denominator >0. Partial-pair ratio may be separately requested and labeled, never ordinary full-cycle CE. No clipping above 100%. R08 |
| M01.07 Retention | Retention_n[%]=100 Q_dis,n/Q_dis,ref | Explicit reference branch/cycle and protocol-comparability declaration, denominator >0. Rate changes are labeled; ratio alone is not intrinsic degradation. Reference is never silently switched after exclusions. R09 |
| M01.08 Energy efficiency | η_W[%]=100 W_out/W_in | Named complete paired process including declared holds/rest treatment; W_in>0. Different starting/ending states constrain interpretation. No thermodynamic efficiency claim. R08 |
| M01.09 Theoretical capacity / utilization | q_th[C/kg]=nF/M; q_th[mAh/g]=nF/(3600M_kg/mol); utilization[%]=100q_measured/q_th [C01; normalization derived here] | n, composition, molar mass and matching measured-material basis explicitly supplied; finite positive inputs. No claim all n electrons are experimentally accessible. R10 |
| M01.10 C-rate | r[h⁻¹]=|I_A|/Q_reference,Ah; setpoint |I_A|=r Q_reference,Ah | Reference capacity's value and nominal/measured/theoretical origin required. A variable-current tail has a variable C-rate; do not label its whole duration with the preceding CC rate. R12 |

F=96485.33212 C/mol is the rounded constant used in these fixtures, not an independently measured parameter. Constants will receive versioned provenance in P01. All ratios are dimensionless internally; percent is ×100. If ever needed, a dimensionless ratio expressed in ppm is ×10⁶; inefficiency in ppm is (1−CE_fraction)×10⁶, a different output. See source discrepancy C02-D1.

## 5. Numerical procedure and processing contract

### 5.1 Eligible intervals

Keep acquisition order. Work with intervals connecting observations, not only lists of selected rows. Each interval records its two source rows, support, inclusion/exclusion reason and reconstruction model. A row may bound two intervals without its duration being counted twice.

- Reject nonfinite times/currents in the affected interval. Missing voltage blocks energy there, not charge.
- Require Δt>0 inside a continuous block. Preserve duplicates; a same-time pair with different values may encode a step discontinuity, but its left/right meaning requires evidence. Never average conflicting duplicates automatically.
- A reset starts another local time block. Never sort to “repair” it. Blocks may be aggregated only when explicit provenance establishes nonoverlapping support within the same branch; unknown elapsed intervals remain excluded.
- A long Δt is not automatically a gap: event-based recording can be sparse. Use known acquisition settings, instrument flags, and reviewed continuity evidence. An unresolved interval is excluded; no universal seconds threshold is a scientific default.
- At a step boundary require left/right sample semantics or an explicitly justified endpoint model. If not known, calculate supported interiors only and mark the complete branch unavailable. Do not silently extrapolate from the first observation back to a programmed start.
- A smooth, resolved current zero crossing may be split using the chosen interpolation model. A programmed discontinuity or unexplained reversal cannot be converted into a smooth ramp just because adjacent samples have opposite signs.
- A declared near-zero-current threshold can guide segmentation, but does not zero out measured current. Instrument rest flags and current validity must be considered. Genuine recorded leakage contributes to measured throughput; open-circuit placeholder currents are not leakage measurements.

Report support intervals, supported duration, excluded/unknown duration when measurable, and branch termination status. A “complete recorded branch” is not necessarily a full state-of-charge excursion. Do not report percentage coverage if the intended duration is unknown.

### 5.2 Integration choices

Default candidate for continuous point samples: **piecewise-linear measured current**. On an eligible interval of width h, Q_k=h(I_0+I_1)/2. Summation should use a numerically stable accumulator, with tolerances linked to floating-point scale and fixture construction. This is trapezoidal quadrature with actual times [C05], not a guarantee that between-sample current was linear.

If acquisition explicitly supplies an interval mean current with known support, Q_k=I_mean h. Do not apply the point-sample rule to interval averages. Confirm semantics in P03 before enabling this alternative.

For energy with independently linear, synchronized U and I within the same supported interval, define ΔU=U_1−U_0, ΔI=I_1−I_0 and x=(t−t_0)/h. Integrating (U_0+ΔU x)(I_0+ΔI x) from x=0 to 1 gives:

**M01.N1:** W_k=h[U_0I_0+(U_0ΔI+I_0ΔU)/2+ΔUΔI/3].

This is an exact integral of the selected interpolation model, not of the unknown true signal. Split supported zeros of U or I before assigning absorbed/delivered energy. If using linear interpolation of sampled power P=UI instead, the trapezoidal result differs by hΔUΔI/6; store that alternative as a distinct method. Neither convention may be silently exchanged to match EC-Lab. R05 verifies this distinction with an independent polynomial integral.

For a constant U or constant I interval these energy rules coincide. A mean current multiplied by a mean voltage does not generally give mean power; interval-mean energy requires measured mean power or a justified covariance model.

### 5.3 Processing defaults and evidence

No smoothing, resampling, baseline correction, or display downsampling in core cycling calculations. Explicit exclusions retain reasons; an offset correction creates a separate processed result. Plot simplification can change only displayed points. Sensitivity to sampling/interpolation is reported separately from measurement uncertainty unless a defensible uncertainty model combines them.

Do not replace unequal step sampling by an assumed uniform grid. For synthetic smooth signals, assess numerical convergence against the analytic integral; for experimental signals, a convergence study on recorded samples cannot recreate information never recorded.

## 6. Branch pairing, formation, tails and plots

Default battery recipe: one charge branch followed by its associated discharge branch, allowing documented rests and same-direction CC/constant-voltage substeps. Record pair membership explicitly; never pair by row-number parity or native cycle number alone.

A first discharge has no preceding charge within the file and is unpaired under this recipe. Retain its capacity. A user-approved discharge-then-charge protocol may use a different named grouping, but keep the numerator and denominator labels explicit. Negative-electrode insertion/extraction efficiency is a separate named return/input ratio and must not be mislabeled by forcing full-cell terminology.

Tail policy: include the complete recorded same-direction constant-voltage tail in total branch capacity by default once branch grouping is established. Always preserve Q_CC, Q_constant_voltage, and Q_total separately. A CC-only analysis must explicitly select that policy for paired portions and reference comparisons. Interrupted tails make the complete branch incomplete.

Formation is an explicit protocol/user tag. Retain formation data; exclusion applies to a declared summary, not to raw records. Require an explicit retention reference or an accepted recipe rule selecting the first eligible post-formation discharge, with the resolved ID saved. No background selection of the best cycle.

Baseline plots: native-named voltage/potential and current against time; directional voltage/potential against observed capacity; separate branch/cycle capacity; eligible CE/retention; eligible terminal energy and mean voltage. Show gaps and partial branches visibly. Reset the capacity axis at branch start only when the origin is supported; otherwise label it “capacity accumulated over recorded intervals.”

## 7. Uncertainty and validity

First-order propagation uses u_y²=J_f Σ J_fᵀ with covariance retained [C06]. For a smooth fixed-interval charge integral with exact times, Q=aᵀI and u_Q²=aᵀΣ_I a. The trapezoidal weights are a_0=h_0/2, a_last=h_last/2 and a_k=(h_(k−1)+h_k)/2 internally. If timestamps/timebase are uncertain, include their derivatives and covariance too.

For q=Q/m: u_q²=u_Q²/m²+Q²u_m²/m⁴−2Q cov(Q,m)/m³. For a ratio y=A/B: u_y²=u_A²/B²+A²u_B²/B⁴−2A cov(A,B)/B³. Multiply standard uncertainty by 100 when reporting a percentage.

An uncertain common mass correlates all mass-normalized capacities of one electrode. It cancels algebraically in same-mass CE/retention ratios; do not count that error twice. A common current gain can also cancel in a ratio, whereas separate range gains or offsets may not. Counter and reconstructed charge share measurements and are not independent replicates.

Unknown uncertainty is `not_evaluated`, never zero. Separate instrument calibration/offset/timebase, numerical reconstruction sensitivity, fit uncertainty (none in the core), and between-cell variability. Repeated cycles are not independent cells. Boundary selection, sign splitting near noise, and nonlinear ratios near zero may require sensitivity or simulation rather than a linear uncertainty formula. R13,R14 check two shared-error cases.

Core failure diagnostics: missing_unit, ambiguous_current_convention, missing_terminal_voltage, unsynchronized_channels, time_reset, unresolved_interval, conflicting_duplicate_time, unknown_counter_semantics, incomplete_branch, missing_pair, invalid_denominator, incompatible_reference, missing_mass, missing_area. Each diagnostic identifies affected results; it does not disable unrelated valid plots.

## 8. Reproducibility, acceptance and handoff

Each result retains method ID/version, source hashes/row intervals, parser and schema versions, source versus mapped current, metadata revision, pair IDs, support/completeness, integration model, settings, exclusions, units/basis, counter/reconstruction origin, uncertainty status and dependencies. Editing mass invalidates normalized quantities; editing interval support invalidates dependent integrals/ratios; editing plot colors does neither.

P00 cycling closure for this turn: equations, conventions, processing rules, source traceability and arithmetic cases are recorded. **Permitted next work: P01 schema/unit/convention implementation and full P02 independent fixtures.** M01 numerical routines may be implemented after those contracts and tests exist. Instrument-specific semantics remain P03/P04 gates, with partial output behavior already specified here.

Evidence now: source sections inspected; R01–R14 reference checks executed, as recorded in JSON. The script is a reference audit, not the production engine; diagnostic cases below are specifications only.

| Required later acceptance case | Expected behavior; not yet tested in application code |
|---|---|
| Missing mass; zero/negative mass | Keep absolute charge; gate/reject normalization |
| First-step discharge; missing charge | Keep discharge; no default CE |
| Time reset; unknown gap | No cross-boundary integration; incomplete support surfaced |
| Conflicting repeated timestamp | Preserve rows, require boundary interpretation |
| Same-time documented step endpoints | Use correct side for each interval; no double counting |
| Partial tail; incomplete final branch | Partial capacity labeled; default full-cycle ratio unavailable |
| Instrument counter reset | No wrap/reset correction until mapping is justified |
| Unknown Ewe role; unsynchronized potentials | Potential plots retained; terminal energy gated |
| Display downsampling / reopen / metadata edit | Full-resolution results preserved, reproduced or correctly invalidated |
| Matched MPR/MPT with EC-Lab settings | Declared parser matrix, pairing checks and explained counter discrepancies |

No native-file compatibility, real-data segmentation, end-to-end application tests, Windows packaging, or experimental validation has occurred in this package.
