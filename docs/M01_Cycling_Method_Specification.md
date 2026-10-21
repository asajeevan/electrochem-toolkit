# M01: battery cycling, scientific and numerical contract

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
- A tester that restarts from a saved state (amendment, 21 October 2026; LANHE `.cex`, P08g section 8) writes records whose time goes back to that state, and its charge counter goes back with it. The records of both passes are kept; the interval across the restart is not integrated, like any reset, so the branch is partial; the counter's step back is not a charge (its increment there is zero) and the increments recorded before the stop are kept, so the branch charge includes what the instrument's own counter left out. A pause the instrument marks (amendment, 21 October 2026) is no gap: the record time does not count it, so the interval across it is integrated as usual and the branch stays complete; but the potential relaxes while the current is off, so a branch paused inside its dQ/dE curve has none (section 9.3, item 1).
- Open question (21 October 2026): a time printed coarsely, so that consecutive rows share it (the Landt Excel export checked in P08d prints the time to 0.01 h), gives zero-duration intervals, which this section does not integrate, so every branch of such an export is partial and no cycle has an efficiency or a retention, although the time between the distinct printed times is complete. Whether intervals shared only through print resolution may be treated as supported, and how such files would be recognised, is not decided.
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

A step that ended at once (amendment, 20 October 2026; retention added 21 October 2026). A branch of at most two rows (one recorded interval, or a single record) that carries less than 0.1 % of the charge of the branch it is paired with is reported as such in the pair's note: "the charge branch k spans one recorded interval (t s) and carries x % of the charge of discharge branch m: a step that ended at once" ("is a single record" for one row). The pair keeps the capacities, energies and potentials of both branches; its coulombic efficiency, coulombic inefficiency, energy efficiency and average-voltage and mid-capacity hysteresis are not given, because a ratio of such a pair describes the step, not the cell. When the branch that ended at once is the discharge, the cycle's retention is not given either (that discharge is no measure of the cell's capacity), so the cycle takes no part in the cycle reaching 80 % or the fade line, nor its average discharge potential in the mean of the summary, nor its capacity in the first-cycle utilisation; when it is the discharge of the reference cycle, no retention is given for any cycle and the summary says to choose another reference. Both conditions are required, so a dying cell whose branches are all small, pulses of similar size, and a long branch of any charge are unaffected. Constants: `cycling.DEGENERATE_ROWS` = 2, `cycling.DEGENERATE_FRACTION` = 1e-3. Found while checking a real file, where charge-first pairing put such a step with the full branch after it and gave a coulombic efficiency of millions of per cent; a step to a voltage limit started beyond that limit ends this way. When a file opens with such a branch, the app asks which branch each cycle starts with (the same question as for a file that opens with a discharge), with the branch's duration and share of charge as evidence. Tests: `tests/test_degenerate_pairs.py`, at both edges of each condition, and for a discharge that ended at once, in an ordinary cycle and in the reference cycle.

Tail policy: include the complete recorded same-direction constant-voltage tail in total branch capacity by default once branch grouping is established. Always preserve Q_CC, Q_constant_voltage, and Q_total separately. A CC-only analysis must explicitly select that policy for paired portions and reference comparisons. Interrupted tails make the complete branch incomplete.

Summary (amendment, 21 October 2026). The summary (first cycle, retention at the last cycle, the cycle reaching 80 %, the fade line, the mean efficiencies and potentials) is formed from complete cycles only, and its note names the incomplete cycles it leaves out, wherever they lie (the first twelve, and how many in all when there are more); before, only an unfinished last cycle was named, and an interrupted cycle in the middle of a run was left out unnamed. When the reference cycle is not a complete cycle of the file, no cycle has a retention, and the note says so and asks for another reference cycle.

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

## 9. dQ/dE peaks, pairing and plateau descriptors (P14, 20 October 2026)

**Status:** implemented in `electrochem/differential.py` (`peak_search`, `peak_windows`, `peak_charges`, `pair_peaks`, `track_peaks`, `plateau_analysis`), wired into `workflow.Run.plateaus()` and the export; tested against a synthetic cell whose answers are known by construction (`tests/plateau_cell.py`, `tests/test_plateaus.py`) and smoke-tested on the demonstration file and the public formation file. Not experimentally validated: no measured cell with independently established plateau capacities has been analysed.

### 9.1 Purpose

Describe the measured dQ/dE curve of each branch when it has several plateaus (for example three or four that return on discharge and two or three that do not): where each peak sits, how much charge it holds, which charge and discharge peaks of a cycle lie close together, and in which cycles a peak is present. These are descriptors of the measured curve at the applied current, temperature and state of the cell. The software never infers a mechanism from them and never labels a peak "reversible" or "irreversible"; it states what the data show.

### 9.2 Symbols and units

| Symbol | Meaning | Unit |
|---|---|---|
| Δ | bin width of the potential grid (`dqde_mv`, default 10 mV) | V |
| E_j | grid node j of one branch, E_j = E_min,b + jΔ, inside the measured range of the branch | V |
| Q_j | branch capacity interpolated at E_j, on the capacity basis of `cycling.capacity_basis` (mAh, mAh/g or mAh/cm2) | mAh, mAh g⁻¹, mAh cm⁻² |
| y_j | (dQ/dE)_j; charge branches positive, discharge branches negative | basis per V |
| f | prominence threshold as a fraction of max_j abs(y_j) (`MIN_PROMINENCE_FRACTION`, 0.05) | 1 |
| N_max | peaks kept per branch, the most prominent (`MAX_PEAKS`, 6) | 1 |
| w | pairing and tracking window (`Settings.peak_pair_window_mV`, default 200 mV; `analyse_file(..., peak_pair_window_mV=)` overrides it in the run's copy of the settings) | mV |
| E_p,k | potential of peak k (a grid node) | V |
| Q_k | capacity under peak k | basis |
| s_k | share of the branch, 100 Q_k / Q_curve | % |
| Q_curve | capacity spanned by the dQ/dE curve, abs(Q_J − Q_0): the branch capacity outside constant-voltage stages | basis |
| ΔE_pair | separation of a pair, E_p(charge) − E_p(discharge) | mV |
| E_mid | apparent mid-point of a pair, (E_p(charge) + E_p(discharge)) / 2 | V |

### 9.3 Equations and numerical procedure

1. **dQ/dE** (unchanged from 0.7.0): within one branch, rows recorded in constant-voltage mode are removed (dE is zero there), the remaining rows are sorted by potential, Q is linearly interpolated at E_j, and y_j is `numpy.gradient(Q, E)`: (Q_(j+1) − Q_(j−1)) / (2Δ) inside, one-sided differences at the two ends. The bin width is the only smoothing. **Interrupted branches** (amendment, 21 October 2026): a branch has no dQ/dE when it has a **curve break**, an unsupported interval where the time goes back or is invalid, a current is missing or an instrument error flag is set (`segment.CURVE_BREAKS`; counted per branch as `curve_breaks`, with the reasons in `breaks_why`), or a **pause** the instrument marked inside it, however short (`Table.paused`, from a LANHE `.cex`; counted as `pauses`). Only a break or a pause between the branch's first and last row outside constant-voltage stages counts, since only those rows make the curve (a break on the interval after row k counts for first ≤ k < last, a pause before row j for first < j ≤ last): one inside a constant-voltage hold that ends the branch, or before the branch's first such row, cannot fold the curve, and the branch keeps it. The potential after a break need not continue the curve before it (a cell left without current relaxes, and the current resumes from the relaxed potential), and the stable sort then folds the two parts of Q(E) onto each other: at the restarts of the second real `.cex` this showed large false peaks (P08g section 8.3). At that file's pauses the potential relaxed by a few millivolts and the curves did not differ visibly at a 10 mV bin; for pauses the rule is a precaution, because a pause has no bound on its length and so none on the relaxation. A zero-duration interval (a time printed coarsely, as in the Landt Excel export checked, or a programmed discontinuity) loses no time and is not a break, and reaching the end of the data is not one either. A pause leaves the charge, the completeness, the efficiency and the retention of the branch as they are. The pair's note says which branch has no dQ/dE and why; figures 3, 6 and 7, the dQ/dE and Evolution views and the peak tables leave the branch out (a figure in which no branch has a curve draws the reason instead, and the dQ/dE view says it in words), and a peak whose partner branch has no curve says so (item 4). Tests: `tests/test_interrupted_branches.py`, `tests/test_readers_cex.py`, `tests/test_plateaus.py`.
2. **Peaks:** `scipy.signal.find_peaks` on abs(y_j) with prominence ≥ f · max abs(y) and width ≥ 1 node; the N_max most prominent are kept and numbered in order of potential. The number found before the cap is kept (`peaks_found`); a capped branch is marked (`capped`, `peaks_note`).
3. **Charge under a peak:** Q_k = abs(Q(E_hi,k) − Q(E_lo,k)), with Q the interpolated grid capacity of step 1 (so the shares of all peaks never exceed 100 %). Boundary rule: between two neighbouring reported peaks, the node of lowest abs(y) between them (the first such node on a tie), shared by both peaks, so windows neither overlap nor leave a gap; outside the outermost peaks, the node of lowest abs(y) between the peak and the curve end (the node nearest the peak on a tie). Capacity before the first boundary or after the last belongs to no peak and is not reported as one. s_k = 100 Q_k / Q_curve.
4. **Pairing within a cycle:** every combination of a charge peak c and a discharge peak d of the same cycle with abs(E_p,c − E_p,d) ≤ w (inclusive) is a candidate; candidates are taken in order of increasing abs(E_p,c − E_p,d) (ties: lower charge potential, then lower discharge potential) and kept when neither peak is already used. ΔE_pair = E_p,c − E_p,d; E_mid = (E_p,c + E_p,d) / 2. Pairing by proximity is a convention: it does not establish that two peaks belong to one process, and E_mid is not a formal or equilibrium potential. A peak left without a partner is `unpaired`, and its note says which of three applies: no counterpart within w in the opposite branch of the same cycle; the opposite branch of the cycle has no dQ/dE curve (item 1); the cycle has no opposite branch.
5. **Presence across cycles:** for each direction, cycles are visited in increasing order; a peak joins the track whose most recent potential is nearest, within w, greedy by smallest shift, one peak per track per cycle; a peak that joins none starts a new track; tracks survive cycles in which they have no peak. Each peak is then described by its track over the analysed cycles of its direction, the cycles in which that direction has a dQ/dE curve: "seen in cycles a-b" (ranges run through consecutive analysed cycles), "first cycle only" (in the first analysed cycle and in no later one), "appears from cycle k" (the track starts after the first analysed cycle), or "one cycle analysed". A cycle whose branch of that direction has no curve (item 1) is not an analysed cycle of it: the ranges run through it, and the column `no_curve_cycles` lists such cycles, so that "seen in cycles 1-5" with `no_curve_cycles` 2 reads as seen in cycles 1, 3, 4 and 5 and not known in cycle 2.
6. **Branch mean potential (unchanged):** Ē_b = W_b / Q_b = ∫E dQ / ∫dQ over the whole branch (M01.05), the charge-weighted mean potential. When a branch consists of plateaus i at E_i with capacities Q_i, Ē_b = Σ Q_i E_i / Σ Q_i; sloping regions enter with their own capacity. No other mean is formed from the peak potentials: averaging peak potentials, with or without weights, is not a substitute for Ē_b, and the software does not report one.

### 9.4 How several plateaus are reported

- **Each plateau's potential:** the peak potential E_p,k of its branch, a descriptor at the applied rate. A per-plateau "mean potential" is not computed: within a plateau the potential is the peak region of dQ/dE, and the branch mean of item 6 already weights every plateau by its capacity.
- **Peaks that do not return:** a charge peak with no discharge peak within w in the same cycle is reported `unpaired` with the note "no counterpart within 200 mV in the discharge of the same cycle"; a peak present only in the first analysed cycle is reported "first cycle only"; the `summary.json` block `plateaus` lists both for the reference cycle. These words are what the data show. Possible reasons include a process that does not reverse, a counterpart shifted beyond w by polarisation, a counterpart merged with a neighbour, a counterpart inside a constant-voltage stage (no dQ/dE there) or below the prominence threshold; the researcher decides.

### 9.5 Settings and outputs

Settings: `dqde_mv` (Run, default 10 mV), `Settings.peak_pair_window_mV` (default 200 mV), `MIN_PROMINENCE_FRACTION` 0.05, `MAX_PEAKS` 6; all four are written to `settings.json` under `differential`, the window also under `settings`, and the rules under `methods` (`dqde_peaks`, `dqde_peak_charge`, `dqde_pairs`, `dqde_presence`, `average_voltage`).

Tables (every cycle; `dqde_curves.csv` keeps the plotted cycles):

- `dqde_peaks.csv`: cycle, branch, direction, peak, voltage_V, dqdv, prominence, width_V, basis, bin_mV (the 0.7.0 columns, first), then charge, charge_unit, share_of_branch_pct, curve_capacity, window_low_V, window_high_V, partner_voltage_V, separation_mV, midpoint_V, pairing, pairing_note, pair_window_mV, track, cycles_seen, evolution, peaks_found, peaks_reported, capped, peaks_note, no_curve_cycles (0.9.1).
- `dqde_pairs.csv`: cycle, pair, charge_peak, discharge_peak, charge_voltage_V, discharge_voltage_V, separation_mV, midpoint_V, charge_capacity, discharge_capacity, capacity_unit, pair_window_mV, bin_mV.
- `summary.json` → `plateaus`: cycle, pair_window_mV, bin_mV, pairs, pair_potentials_V, unpaired_peaks, first_cycle_only_peaks (each with its direction, cycle and potential: the first analysed cycle of a direction whose first branch has no curve is a later one), peaks_appearing_later, capped_branches, note (and notes when the analysis has any).
- `origin/dqde_peaks.csv`, `origin/dqde_pairs.csv`: the same tables in Origin's three-header layout.

### 9.6 Assumptions, failure conditions and limitations

- Peak potentials depend on current, temperature, electrode polarisation and state of health; ΔE_pair contains ohmic, kinetic and any thermodynamic hysteresis together and is not a kinetic parameter.
- Pairing by proximity is a convention. With w larger than the spacing of neighbouring peaks, a peak can pair with, or be followed into, the wrong neighbour; with w smaller than the hysteresis nothing pairs (the notes then say "no charge peak has a discharge peak within w mV in any analysed cycle").
- A plateau split by a rest, a current change or a step boundary appears as two peaks; constant-voltage stages carry no dQ/dE, so capacity passed there has no peak.
- Plateaus closer than about two bins merge into one peak; peak potentials are grid nodes, so they are known to within half a bin.
- The charge under a peak includes the sloping (background) capacity inside its window; for a small peak on a large background this can be several per cent of its value (5 % for the 0.04 mAh plateau of the test cell).
- The cap N_max drops the least prominent peaks; their capacity then falls into a neighbouring peak's window. A capped branch is marked in the table and in the summary.
- "First cycle only" and "appears from cycle k" are judged over the analysed cycles: the tables cover every cycle of the file so that this is the whole record.
- Failure conditions: a branch with fewer than four points outside constant-voltage stages, or a grid of fewer than three nodes, or a curve break or a pause inside its curve (section 9.3, item 1), has no curve and so no peaks; a file whose charging direction is not stated has no cycles and no peak tables.

### 9.7 Verification (software tests, not experimental validation)

`tests/plateau_cell.py` builds Q(E) as a sum of logistic steps (Q_i at E_i, scale 12 mV) plus a linear background, with plateau centres between grid nodes, samples it at constant current with instrument-like time stamps and a partial last interval, and writes an EC-Lab text export. Checked in `tests/test_plateaus.py`: one peak per plateau within one bin; pair separations of 60 mV within one bin and mid-points at the constructed centres; the 4.10 V first-charge plateau unpaired with the exact note and "first cycle only"; the 2.65 V plateau "appears from cycle 3" in both directions; each Q_k equal to Q_i plus the background in its window within 1 % (main plateaus within 3 % of Q_i); branch means equal to the constructed ∫E dQ / Q within 0.2 mV and to Σ Q_i E_i / Σ Q_i within 3 mV; the reported Q_k and E_p,k reproduce the branch mean within 3 mV; a 50 mV window pairs nothing and says so; a cap of two peaks is stated; the exported tables, summary block, settings and Origin tables. Pure functions are checked on hand-made inputs (greedy pairing order and tie rule, inclusive window, peak areas of two Gaussians, tracking through drift and a gap). Two deliberate mutations (pairing order, charge scaled by 4 %) were confirmed to fail these tests. Branches without a curve (0.9.1): the time of the same cell made to go back halfway through cycle 2's discharge, or cycle 1's charge, so that branch has no curve; the partner peaks then say that branch has no dQ/dE curve, presence is judged over the cycles with a curve ("seen in cycles 2-5", not "appears from cycle 2"), `no_curve_cycles` names the cycle, and the summary lists no first-cycle-only peak for a first charge without a curve.

## 10. dQ/dE evolution map and surface (P14)

**Status:** implemented (`differential.evolution_grid`, `plotting.fig6_dqde_map`, `plotting.fig7_dqde_surface`, `studio.views.EvolutionView`, `dqde_map.csv`) and tested; display only, no new quantity.

**Purpose:** show how the dQ/dE curves change from cycle to cycle: peaks that persist, drift, grow, fade, appear or disappear.

**Grid (equation):** for one direction, nodes E'_j = jΔ (integer multiples of the bin width) from the lowest to the highest potential of any curve; for each cycle n, D_n(E'_j) = linear interpolation of that branch's dQ/dE curve at E'_j when E'_j lies inside the branch's own grid, and NaN otherwise. A branch's own nodes start at its lowest measured potential, so the common grid moves each value by less than one bin; that is the only change. Rows are cycles in increasing order; `DqdeGrid.filled()` inserts NaN rows for missing cycles so every row sits at its cycle number. Peak tables never use this grid.

**Figures:** figure 6 (`fig6_dqde_map`, 1.5 column) draws abs(D) as cells one cycle high and one bin wide, charge (a) and discharge (b) on one shared colour scale and one shared potential scale (the union of the two directions' ranges, so a pair lines up vertically; beyond a direction's measured range the panel is grey, as not measured; main session, same day), colour map `magma_r` (sequential; CIELAB lightness falls monotonically from 98 to 0, so zero is paper-light and readable in greyscale and with colour-vision deficiencies), grey (#D9D9D9) where a branch was not measured or a cycle has no dQ/dE curve in that direction (section 9.3, item 1). When no branch of the cycles has a curve, figures 6 and 7 draw the reason instead of an empty scale (figure 7 without a 3D box), as figure 3 and the summary's panel c do. Figure 7 (`fig7_dqde_surface`, double column) draws the same values as two 3D surfaces with cycle number as the depth axis, height and colour both abs(D), on the same potential range in both panels, the height named on the first panel and by the colour bar, elevation 26°, azimuth −58°: charge and discharge are separate panels because, in one box, the flat zero region of one surface hides the peaks of the other. Every potential node is drawn; above 120 cycles every k-th cycle is drawn and the figure says so. Values in a.u. are divided by the common maximum of both directions; "real" keeps mAh/V per g or per cm2. Surfaces and meshes are rasterised at 600 dpi inside vector PDF/SVG; text stays editable. Option `ExportOptions.evolution_cycles`: "all" (default) or "selected".

**Table:** `dqde_map.csv`: a header row (cycle, direction, basis, then one column per node potential in V) and one row per cycle and direction, signed real units (discharge negative), empty where not measured.

**App:** `EvolutionView` shows the map of every cycle for the chosen direction (colour bar in real units, the focused cycle as a dashed line, a click focuses a cycle) or a waterfall of the selected cycles' own curves offset by rank; the readout under the cursor gives the stored value (the grid node in map mode, the curve point in waterfall mode), never a display-derived number.

**Figure checks for 3D axes:** `check_figure` keeps its twelve checks. Tick labels are counted only for axes that draw them (a 2D axes turned off draws none; a 3D axes draws its own while its 3D axes are on). For a 3D axes, tick labels are read where the 3D axis drew them (calling `Axis._update_ticks()` would move them back to 2D positions and corrupt their extents); "data inside the axes" compares the recorded data limits with the x, y and z limits (a 3D axes does not clip); "line weights" includes 3D axis lines, pane edges, grid and tick strokes; text and legend checks act on the projected drawing in display space (depth occlusion is not considered). "Colour contrast" now also checks every colour map in the figure: lightness monotonic for a sequential scale, monotonic outwards from zero on both sides for a diverging one (warn otherwise). Overlap of obliquely rotated labels is tested on their own rotated rectangles, not their axis-aligned boxes. A check that cannot be evaluated returns status "skip" with "not evaluated: reason" (none does with matplotlib 3.11).

**Limitations:** the colour scale is linear, so small peaks are faint beside large ones (read them in the tables); a 3D view hides what lies behind a ridge and makes values hard to read, so numbers come from the tables, the map readout or `dqde_map.csv`; a cycle drawn as a row of cells does not imply anything about unrecorded cycles (they stay grey).
