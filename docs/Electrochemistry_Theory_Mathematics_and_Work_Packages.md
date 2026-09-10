# Electrochemistry software: scientific foundation and execution specification

Version 0.1 — 10 September 2026

This document supplements the earlier software build plan. It records a first scientific specification, a source register with access status, mathematical definitions, applicability restrictions, numerical reference cases, and bounded implementation work packages. It is not a claim that the software or all advanced methods have been implemented or experimentally validated. Advanced methods marked provisional require the specified further source and benchmark checks before release.

## 1. Scientific contract

Every calculation must have an equation ID, defined symbols and units, reference frame and sign convention, required data and metadata, applicability conditions, numerical procedure, diagnostics, uncertainty treatment, and at least one independent reference case. A plot is a view of identified data; a calculated descriptor is a numerical reduction; a physical parameter is an estimate conditional on a model. Keep these categories distinct in both the API and the interface.

Outputs carry one of: available; provisional; needs metadata; inapplicable; failed numerical validation. Missing inputs cannot silently become zero. Model failure cannot silently become a plausible-looking number.

Methods are supported per cell configuration. A two-electrode full cell, a metal half-cell, a three-electrode experiment, a blocking-electrode conductivity cell, and a symmetric cell are different measurement models. Preserve the actual measured potential channels. Do not turn an arbitrary Ewe channel into full-cell voltage by renaming it.

## 2. Source register and evidence status

Sources were sought from papers, author/institutional records, instrument manufacturers, standards bodies, and numerical-library documentation. No downloaded collection of copyrighted papers is included. Links and original synthesis are provided instead. “Inspected” refers to accessible relevant text/equations, not a claim to have independently reproduced every result in that source.

| ID | Source and direct link | Use | Access/review status |
|---|---|---|---|
| S01 | [Pine Research: Cyclic Voltammetry](https://pineresearch.com/support-article/cyclic-voltammetry-cv/) | CV waveform and Randles–Ševčík equation | Relevant sections and equation alt text inspected |
| S02 | [Dubarry and Anseán, Best practices for incremental capacity analysis, 2022](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2022.1023555/full) | Derivative analysis, experimental suitability | Accessible article guidance inspected |
| S03 | [Correction to S02, 2023](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2023.1203569/full) | Corrected Figure 13 | Correction inspected; duplicated figure replaced, conclusions unchanged |
| S04 | [Gamry: Basics of Electrochemical Impedance Spectroscopy](https://www.gamry.com/application-notes/EIS/basics-of-electrochemical-impedance-spectroscopy/) | Complex response, small-signal conditions, circuit/geometry foundations | Relevant sections inspected |
| S05 | [impedance.py circuit elements](https://impedancepy.readthedocs.io/en/latest/circuit-elements.html) | Exact implemented R/C/L/CPE/Warburg conventions | Equations inspected; implementation reference, not proof of physical applicability |
| S06 | [impedance.py validation](https://impedancepy.readthedocs.io/en/latest/validation.html) | Lin-KK method and residuals | Relevant documentation inspected |
| S07 | [Schönleber et al., 2014, DOI 10.1016/j.electacta.2014.01.034](https://doi.org/10.1016/j.electacta.2014.01.034) | Original robust Lin-KK method | Identified through S06; publisher full text not obtained |
| S08 | [BioLogic Application Note 70](https://www.biologic.net/documents/determination-diffusion-coefficient-inserted-species-host-electrode-eis-pitt-gitt-techniques-an70/) | GITT/PITT and bounded diffusion, with assumptions | Equations and limitations inspected; sign/transcription ambiguities require independent derivation |
| S09 | [Kang and Chueh, GITT Reinvented Part I, 2021, institutional record](https://snu.elsevierpure.com/en/publications/galvanostatic-intermittent-titration-technique-reinvented-part-i-) | Geometry, overpotential, area and transient errors | Abstract inspected; full-text derivation not obtained. DOI 10.1149/1945-7111/ac3940 |
| S10 | [Shao and Zhang, Bruce–Vincent transference numbers from molecular dynamics simulations](https://arxiv.org/html/2302.07017v2) | Concentrated-electrolyte interpretation and reference frame | Author manuscript equations and discussion inspected; cite the version explicitly |
| S11 | [NIST TN 1297 Appendix A](https://www.nist.gov/pml/nist-technical-note-1297/nist-tn-1297-appendix-law-propagation-uncertainty) | First-order uncertainty propagation and covariance | Equations inspected |
| S12 | [SciPy trapezoid](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.trapezoid.html) | Integration over supplied sample coordinates | Documentation inspected |
| S13 | [SciPy Savitzky–Golay filter](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_filter.html) | Smoothing and derivative settings | Inspected in preceding planning work |
| S14 | [SciPy least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html) | Bounded least squares and residual conventions | Documentation retrieved; numerical dependency to pin and test |
| S15 | [yadg](https://github.com/dgbowl/yadg) | EC-Lab extraction, metadata and provenance | Inspected in preceding planning work; user-file compatibility still untested |
| S16 | [eclabfiles](https://github.com/vetschn/eclabfiles) | Historical format descriptions and migration notice | Inspected in preceding planning work; archived, not default dependency |
| S17 | [Elgrishi et al., A Practical Beginner’s Guide to Cyclic Voltammetry](https://doi.org/10.1021/acs.jchemed.7b00361) | Additional CV scientific reference | Identified; publisher full text blocked in this session |
| S18 | [Correction to S17, 2025](https://doi.org/10.1021/acs.jchemed.5c01102) | Must reconcile before treating S17 as a verified method source | Correction identified in publisher search; full correction not inspected |
| S19 | [BioLogic Application Note 18](https://www.biologic.net/documents/eis-zfit-electrochemistry-battery-corrosion-application-note-18/) | Repeated EIS and automated successive fitting | Manufacturer workflow inspected; not copying its model derivatives unchecked |

Source discipline: a manufacturer equation is useful but not immune to typographical errors. For example, the decaying-current PITT slope must be negative under the signed-log convention derived below. A formula that would yield a negative diffusion coefficient under that convention cannot be implemented unchanged. Keep a record of the actual convention rather than silently taking an absolute value everywhere.

## 3. Common notation and foundational physics

Use SI units internally: seconds, amperes, volts, coulombs, joules, metres, square metres, kilograms, kelvin, hertz and ohms. Specific capacity can be exposed in mAh/g, conductivity in S/cm, and diffusion in cm²/s through explicit conversion. Keep charge Q distinct from specific capacity q and the CPE coefficient Y0. Use j for the imaginary unit, i for current density, I for current, U for cell voltage, E for electrode potential, W for energy, and L_ind for inductance.

F ≈ 96485.33212 C/mol and R ≈ 8.314462618 J/(mol K) are numerical constants for the reference examples, rounded from the SI-defined constants. Store one versioned constants table. Conversions include 1 mAh = 3.6 C; 1 Wh = 3600 J; 1 cm²/s = 10^-4 m²/s; 1 S/cm = 100 S/m; 1 mg = 10^-6 kg. Celsius must be converted to kelvin before temperature-model fitting.

### Foundational relations: explanatory layer

For Ox + ne− ⇌ Red, the equilibrium Nernst relation is E_eq = E° + RT/(nF) ln(a_Ox/a_Red), with the general reaction quotient used for other stoichiometries. Activities, not arbitrary concentrations, define this equilibrium relation. ΔG = −nF E_cell applies to the specified equilibrium cell reaction. A resting voltage is not automatically a verified equilibrium voltage.

For a simple charge-transfer reaction, a chosen Butler–Volmer convention is i = i0[exp(α_a nFη/RT) − exp(−α_c nFη/RT)], where η = E − E_eq and α_a + α_c = 1 in this simplified form. Linearizing around equilibrium gives r_ct = RT/(nF i0) in resistance-area units, or R_ct = RT/(nF I0) for total exchange current. These are model relations, not universal interpretations of fitted arcs. S04 provides the relevant physical context.

Fickian diffusion without convection or migration in the modeled phase: J = −D∇c and ∂c/∂t = ∇·(D∇c). For constant D in one-dimensional planar geometry, ∂c/∂t = D∂²c/∂x². Surface flux magnitude links to faradaic current by |I_F| = nF A|J_surface|. A complete forward model also needs geometry, initial conditions and boundary conditions. Electrolyte transport in a concentrated solution cannot generally be reduced to uncoupled Fickian diffusion of ions. These equations provide mathematical scaffolding for later model-specific checks.

## 4. M01 — Charge, capacity, energy and cycling

### Definitions and short derivation

I = dQ/dt gives Q_C = ∫ I(t)dt. Within a verified unidirectional half-cycle, report capacity magnitude Q_mAh = |Q_C|/3.6. For direction-changing data, split at the transition before integration; applying an absolute value to the net integral loses throughput.

On valid contiguous samples, a piecewise-linear approximation gives Q_C ≈ Σ[(I_k + I_(k+1))/2]Δt_k. This is a numerical model of the sampled current, not an excuse to bridge unrecorded gaps. At programmed discontinuities use known step boundaries and documented endpoint/sample semantics. S12 supplies the numerical integration interface.

Normalize only with explicit bases: q = Q_mAh/m_active,g; Q_areal = Q_mAh/A_cm². Capacity retention = 100 Q_dis,n/Q_dis,ref. Coulombic efficiency = 100 Q_dis/Q_chg for the defined paired portions. Record partial cycles and formation separately. Do not clip efficiencies above 100%; flag and investigate them.

For a terminal-voltage/current convention in which positive UI means absorbed power, W_in = ∫max(UI,0)dt/3600 and W_out = −∫min(UI,0)dt/3600, in Wh. Compute each over the chosen complete process or matched cycle. Energy efficiency = 100 W_out/W_in. Mean charge or discharge voltage magnitude = corresponding Wh/Ah, when that direction convention is appropriate. This power-based definition handles sign explicitly; absolute electrode potential is not a substitute for terminal voltage.

Theoretical specific capacity follows from nF coulombs per mole divided by molar mass: q_th = nF/(3.6M), M in g/mol. Utilization = 100 q_measured/q_th with a consistent material and electron-count basis. For C-rate r in h^-1, applied current I_mA = r Q_reference,mAh. State whether the reference is nominal, measured, or theoretical.

Required inputs: time, current, boundaries, cell convention; voltage for energy; mass/area for normalization. Checks: chronological continuity within a segment, no duplicate contribution, complete denominators, imported-counter agreement, visible CV-tail policy. Output raw signed charge as well as named capacity magnitudes when the convention is unresolved.

## 5. M02 — Numerical derivatives and incremental capacity

Definitions: IC = dQ/dU and DV = dU/dQ; units follow the capacity basis. Their reciprocal relationship holds only locally where the relevant derivative exists and is nonzero. Numerically computed smoothed derivatives are not globally interchangeable through reciprocal inversion.

Central difference on a uniform potential grid: IC(U_k) ≈ [Q_(k+1) − Q_(k−1)]/(2ΔU). For nonuniform data, use an appropriate local polynomial fit rather than pretending the spacing is uniform. A local fit Q(U) ≈ Σ a_r(U−U0)^r yields IC(U0)=a1. A symmetric noise model with independent equal variance s_Q² gives Var(IC) ≈ s_Q²/(2ΔU²) for that simple central difference. This shows mathematically why a finer grid alone can magnify noise.

Proposed algorithm: separate current direction and monotonic branches; retain raw data; identify constant-voltage/turning regions; choose a documented grid; apply one declared preprocessing operation; differentiate; inspect processing sensitivity. Never combine unrelated branches by sorting all points by voltage. Store derivative polarity; if discharge is displayed with reversed sign, label that transformation.

S02 recommends careful control of experimental rate, resolution and noise; it does not justify assigning universal degradation mechanisms to every derivative feature. S03 corrects a duplicated figure. S13 documents filter order, window, spacing and boundary behavior. Our implementation must expose those settings and test peak displacement and area changes.

## 6. M03 — CV: descriptive results and conditional kinetic models

Scan rate ν = dE/dt. Identify segments using recorded program metadata and potential direction, including staircase acquisition where relevant. Peak current must refer to a defined local baseline and search region. Store anodic/cathodic candidates before selecting pairs. ΔE_p = E_pa − E_pc is meaningful only for the chosen pair. (E_pa+E_pc)/2 is a midpoint descriptor; formal-potential interpretation needs additional conditions.

Faradaic charge over a branch is Q_F = ∫(I−I_background)dt. Equivalently Q_F = ∫(I−I_background)/ν(E)dE where the local signed scan rate is valid. A whole-loop geometric area is not automatically stored charge.

For a reversible dissolved redox couple under planar semi-infinite diffusion, the candidate equation is |I_p| = 0.4463 nFAc sqrt(nF Dν/(RT)). Use coherent SI units (A in m², c in mol/m³, D in m²/s, ν in V/s). S01 provides this relation. It is not an automatic diffusion estimator for porous insertion electrodes.

Additional candidate descriptors: log|I_p| = log a + b log ν, and I(E,ν)=k1(E)ν+k2(E)ν^(1/2). They require matched conditions, adequate distinct rates, baseline control, consistent branch/feature tracking, fit diagnostics, and a declared domain. These scalings alone do not uniquely establish a storage mechanism. The k1/k2 decomposition remains a deferred research module until its specific literature and failure cases are reviewed. No clipping of negative coefficients to fabricate a percentage.

Nicholson/Laviron fits are also deferred: they need their own theory cards, applicable kinetic regimes and independent benchmarks. S17 and its correction S18 remain on the reading queue; neither is represented here as fully checked.

## 7. M04 — Impedance representations, fitting and quality

Use the phasor convention Z(ω)=E_tilde/I_tilde=Z′+jZ″ with ω=2πf. |Z|=sqrt(Z′²+Z″²) and phase=atan2(Z″,Z′). The default electrochemical Nyquist display is (Z′,−Z″); the source may already export −Z″, so map once. Preserve inductive points. S04 supplies the small-signal and stability context.

Candidate element registry, using S05 conventions:

- Z_R=R; Z_C=1/(jωC); Z_L=jωL_ind.
- Z_CPE=1/[Y0(jω)^α], with Y0 in S·s^α; Y0 has units of capacitance only at α=1.
- Z_series=ΣZ_k; Z_parallel=(Σ1/Z_k)^−1.
- Z_RparallelC=R/(1+jωRC), with τ=RC and f_peak=1/(2πτ) for the isolated arc.
- Semi-infinite Warburg: Z_W=A_W(1−j)/sqrt(ω), A_W in Ω·s^−1/2. Another convention using 1/sqrt(jω) differs by sqrt(2); adapter tests must prevent mixing coefficients.
- Planar blocking finite diffusion: Z=R_d coth(sqrt(jωτ_d))/sqrt(jωτ_d); transmissive boundary replaces coth with tanh. The boundary condition is part of the model identity.

Area-specific impedance Z_A=ZA in Ω·cm² when A is in cm²; do not divide by area. Do not assign bulk or interfacial meaning from element names alone.

Proposed fitting objective: minimize χ²(θ)=Σ_k{w_Re,k[Z′_obs−Z′_model(θ)]²+w_Im,k[Z″_obs−Z″_model(θ)]²}. Known component variances give inverse-variance weights; absent such information, a declared empirical weighting defines an objective, not a calibrated statistical chi-square. Fit both components, use bounds and multiple starts, inspect residuals, and report convergence separately from identifiability. S14 supports the bounded numerical solver.

Use Jacobian rank/conditioning and profile or resampling diagnostics when parameters are weakly identified. A small residual alone cannot establish a unique circuit. Do not use a universal R² acceptance gate. A local covariance approximation requires its noise and linearization assumptions; residuals correlated across frequency need appropriate treatment.

S06 describes the Lin-KK representation Z≈R0+ΣR_k/(1+jωτ_k) with fixed time constants and residual inspection. Treat this as a compatibility screen. Passing does not independently establish causality, stationarity and linearity experimentally; failures also need investigation of frequency coverage and noise. Direct reconciliation with S07 is a release gate for a research-grade validation module.

## 8. M05 — Conductivity, temperature dependence and symmetric cells

For uniform through-plane current in a defined sample, R_b=ℓ/(σA), giving σ=ℓ/(R_b A). With ℓ in cm and A in cm², σ is S/cm. S04 supplies the geometry relation. R_b must correspond to the bulk transport response under the selected model. Electrode polarization, contact resistance, electronic leakage and overlapping contributions can invalidate a simple assignment.

Two explicitly different candidate temperature equations are:

1. Arrhenius: σ(T)=σ0 exp[−E_a/(RT)]. Fitting ln σ versus 1/T gives slope −E_a/R. Fitting ln σ versus 1000/T gives slope −E_a/(1000R). Fitting log10 σ versus 1000/T gives E_a=−1000R ln(10)×slope, in J/mol.
2. VTF family: σ(T)=A0 T^(−p) exp[−B/(T−T0)], where p is fixed by the selected model, e.g. 0 or 1/2, B has units kelvin and T>T0. The prefactor units depend on p. Do not silently interchange these forms or report B as an Arrhenius activation energy.

These temperature forms are specified as candidate mathematical models; a dedicated polymer-transport primary-source review is still required before physical-parameter interpretation is released. Fit heating/cooling branches and distinct temperature regimes separately where appropriate. Three free VTF parameters over a narrow temperature interval can be poorly constrained.

For a symmetric cell, the measured response belongs to the complete cell. Splitting an impedance or polarization into two equal interface contributions requires an explicit symmetry assumption and treatment of the common bulk contribution. A finite-time ΔU/ΔI is pulse resistance at the stated time, not automatically instantaneous ohmic resistance.

## 9. M06 — Polarization-based transference estimate

Candidate operational expression:

t_plus,BV = I_ss(ΔV−I0R0) / [I0(ΔV−I_ss R_ss)].

I0 and I_ss are consistently defined initial and steady-state currents; R0 and R_ss are the relevant interfacial resistance corrections before and after polarization, not arbitrary total-cell resistance. Store all selections and effective driving voltages. Require a suitable reversible-metal symmetric cell, small polarization, steady-state evidence, consistent temperature and impedance interpretation. Singular or inconsistent denominators yield a failed result, not clipping to [0,1].

S10 distinguishes the Bruce–Vincent quantity from a general concentrated-electrolyte transference number and makes the reference frame important. Thus the software should name the measured operational quantity explicitly. The complete resistance-correction protocol and original experimental-method source must still be reconciled before releasing this candidate formula. A numerical calculator can be tested before claiming a validated measurement workflow.

## 10. M07 — CA, Cottrell behavior and PITT

For planar semi-infinite diffusion after an ideal diffusion-limited concentration step, |I(t)|=nFAΔc sqrt[D/(πt)]. If I versus t^−1/2 has slope k under these assumptions, D=π[k/(nFAΔc)]². Initial charging, resistance, convection, finite geometry and kinetic limitations require exclusions or another model. At t=0 this ideal expression is singular; no fit may include it. S08 gives the insertion-step version and its restrictions.

For a planar slab 0<x<ℓ, assume a fixed concentration perturbation at x=0 after a potential step, zero flux at x=ℓ, constant D and a uniform initial state. Separation of variables gives eigenvalues λ_m=(m+1/2)π/ℓ. At sufficiently long time the first diffusion mode dominates: |I|≈K exp[−π²Dt/(4ℓ²)]. This derivation establishes the numerical factor and boundary conditions.

Consequently, if s_ln=d ln|I|/dt<0, D=−4ℓ²s_ln/π². If s_10=d log10|I|/dt<0, D=−4ℓ²ln(10)s_10/π². This explicitly signed form prevents a negative diffusion coefficient from a decaying signal. Do not apply a slab factor to spheres or two accessible faces without rederiving the model. Independent PDE convergence checks are required before implementation is called validated.

## 11. M08 — GITT and chemical diffusion

Start with pulse segmentation and plots: current steps, pre/post relaxation, E versus sqrt(t), and fitted windows. Those descriptive outputs can be released before diffusion extraction.

In the simplified short-time planar constant-D model, define ℓ_eff=mV_m/(MA), using active-material mass m, molar mass M, molar volume V_m and the model's active interfacial area A. Under a small composition perturbation, the diffusion surface concentration change scales as 2J sqrt(t/(πD)), while the relaxed average change scales as Jτ/ℓ_eff. Linearizing equilibrium potential over that small composition interval gives:

D=(4ℓ_eff²/(πτ))(ΔE_s/ΔE_τ)².

Here ΔE_s is the relaxed equilibrium-potential change caused by the pulse; ΔE_τ is the diffusion-associated pulse change, with non-diffusive instantaneous and kinetic contributions treated appropriately. If the selected early-time response is E=a+k sqrt(t), an equivalent slope form under the same approximations is D=(4ℓ_eff²/π)[ΔE_s/(τk)]². Use the actual pulse duration τ; do not substitute the fitted-window length.

Requirements: short-time behavior τD/ℓ²≪1 for the assumed characteristic geometry; small perturbation; locally suitable thermodynamic slope; meaningful relaxation; no dominant phase-boundary/kinetic response; justified active area/length; and robust fit-window sensitivity. Check the short-time condition again after estimating D. A composite-electrode thickness is not automatically the solid diffusion length.

S08 provides a conventional formula; S09's abstract identifies significant error sources in real implementation. Further full-text study is required. For two-electrode measurements, do not label a coefficient as belonging uniquely to one electrode without a defensible separation model. A fitted apparent coefficient must be labeled as such.

## 12. M09 — DRT and other inverse problems: deferred

Candidate RC-distribution representation:

Z(ω)=R∞+jωL_ind+∫γ(lnτ)/(1+jωτ)dlnτ.

Discretization produces a poorly conditioned inverse problem. A candidate regularized objective is ||W(Kγ−z)||²+λ||L_reg γ||², possibly with γ≥0 under a compatible RC-only interpretation. State the integration measure and coefficient units; grid weights matter. Inductive or more general responses need appropriate additional terms or another representation.

This is a mathematical outline, not an approved DRT algorithm. Before implementation: review a specific primary method, choose the regularizer and λ selection, test resolution/noise/frequency-window sensitivity, quantify nonuniqueness, and verify reconstruction. A DRT peak is not automatically a unique electrochemical process.

## 13. M10 — Uncertainty, replicate statistics and reporting

For y=f(x), the first-order propagation rule is u_y²=JΣ_xJᵀ, including covariance. For q=Q/m with independent errors, (u_q/q)²=(u_Q/Q)²+(u_m/m)². For σ=ℓ/(R_bA), the corresponding independent relative-variance terms add for ℓ, R_b and A. Correlation must be included when present. This is first-order approximation, as specified by S11; substantial nonlinear uncertainty needs a suitable simulation or other method.

Separate measurement uncertainty, fitting uncertainty, and between-cell variability. Mass uncertainty is shared across cycles of one electrode. An error bar from repeated cycles is not an independent-cell replicate uncertainty. Display independent cell count, exclusions, mean, and the selected SD/SEM/confidence interval definition. Do not invent uncertainty from significant digits alone when calibration and other systematic errors dominate.

Every export needs the equation IDs, metadata revision, actual numerical settings, exclusions, source row references, versions, units and denominator. A changed mass should invalidate normalization results; a changed smoothing recipe should invalidate derivatives; a color edit should invalidate neither.

## 14. Numerical reference cases

The values below were calculated directly from the stated equations during specification preparation. They are independent arithmetic targets for future implementation tests, not evidence of completed importer or analysis validation. Avoid creating a test that merely calls the same implementation twice.

| ID | Inputs and definition | Expected result |
|---|---|---|
| T01 | Constant 1 mA for 3600 s | 3.6 C = 1 mAh |
| T02 | T01 with 10 mg active material | 100 mAh/g |
| T03 | 3 V terminal voltage, 1 mAh transferred in one direction | 0.003 Wh = 3 mWh |
| T04 | Q_chg=1 mAh, Q_dis=0.98 mAh | CE=98% |
| T05 | n=1, M=232.28 g/mol | q_th≈115.38437 mAh/g using the constants above |
| T06 | Q(U)=2U+3 on a uniform valid branch | dQ/dU=2; dU/dQ=0.5 in corresponding units |
| T07 | Z=5 Ω + 100 Ω parallel 10 μF | τ=0.001 s; arc peak≈159.15494 Hz; Z at peak=55−j50 Ω |
| T08 | ℓ=0.02 cm, A=1 cm², R_b=1000 Ω | σ=2×10^-5 S/cm |
| T09 | CV: n=1, A=10^-4 m², c=1 mol/m³, D=10^-9 m²/s, ν=0.1 V/s, T=298.15 K | Randles–Ševčík peak-current magnitude≈268.648 μA |
| T10 | Cottrell with n=1, A=10^-4 m², Δc=1 mol/m³, D=10^-9 m²/s, t=1 s | Current magnitude≈172.142 μA |
| T11 | GITT: ℓ_eff=0.001 cm, τ=100 s, ΔE_s=0.01 V, ΔE_τ=0.1 V | D≈1.27324×10^-10 cm²/s; τD/ℓ_eff²≈0.0127 |
| T12 | PITT slab: ℓ=0.001 cm, s_ln=−0.01 s^-1 | D≈4.05285×10^-9 cm²/s |
| T13 | BV candidate: ΔV=0.01 V, I0=10 μA, I_ss=2 μA, R0=R_ss=100 Ω | t_plus,BV=0.183673... |
| T14 | q with independent 1% charge uncertainty and 2% mass uncertainty | Relative standard uncertainty≈2.236% |

T11 checks the simplified formula only; it does not establish that an experimental pulse satisfies that model. For T09, quadrupling scan rate should double peak current within the ideal model. For T10, quadrupling time should halve current. These scaling checks help catch unit and exponent errors.

Mandatory negative cases: missing/zero mass; empty branch; zero charge denominator; truncated half-cycle; first step discharge; multiple potentials; ms mistaken for s; mA mistaken for A; negative imaginary column transformed twice; a time reset; a long gap; duplicate source file; current reversal; capacitive spike; no CV peak; identical scan rates; no steady state; overlapping EIS arcs; a flat GITT thermodynamic response; wrong diffusion geometry; and conflicting replicate identifiers. Preserve diagnostics instead of returning fabricated results.

## 15. How I will split the implementation work

Each package is sized around one reviewable deliverable. Large packages below should be implemented as small internal steps, but each finishes with a saved handoff containing equations, code scope, test evidence, unresolved issues and the next permitted dependency. These are execution tasks for me; the table does not assume or launch parallel agents.

| Package | Dependencies | Work I will do | Completion gate |
|---|---|---|---|
| P00 Scientific register | None | Maintain this source/equation register, reconcile corrections, rank missing method sources | Every enabled method has checked equations and declared limits; unresolved advanced methods remain disabled |
| P01 Units and measurement conventions | P00 core | Define quantity types, constants, mass/area bases, potential roles, sign and time rules | Unit conversions and dimensional errors tested, conventions documented |
| P02 Reference fixtures | P01 | Build analytic and synthetic datasets, frozen expected outputs, invalid-input cases | Independent expected values and perturbation cases available before analysis code |
| P03 EC-Lab import adapter | P01 | Test candidate parsers; map raw columns, metadata, flags and provenance | Matched MPR/MPT comparisons pass for declared versions/techniques |
| P04 Segmentation engine | P02,P03 | Reconstruct techniques, rest/CC/CV, cycles, pulses and spectra without losing native IDs | Hand-annotated cases agree; unresolved boundaries are visible |
| P05 Cycling engine | P04 | Implement charge, capacity, energy, CE, retention and rate summaries | T01–T05, variable-current cases and real-data comparisons pass |
| P06 Calculation workspace | P01,P02 | Theoretical capacity, loading, C-rate, area and normalization calculators | Unit, denominator and missing-input tests pass |
| P07 CV descriptors | P04 | Branches, baselines, candidate peaks, selected pairs and charge | Synthetic peak/charge cases and annotated CV examples pass |
| P08 Differential engine | P05 | Branch-safe IC/DV, interpolation, smoothing and sensitivity report | T06 plus known peaks/noise cases pass; no cross-branch artifacts |
| P09 EIS representation | P03,P04 | Frequency groups, signs, Nyquist/Bode, area normalization | T07 and R/C/L phase/sign cases pass |
| P10 EIS fitting and validation | P00 EIS,P02,P09 | Circuit registry, fitting, residuals, Lin-KK, identifiability | Recover identifiable synthetic parameters; flag ambiguous/invalid cases; reconcile source method |
| P11 Conductivity and temperature | P06,P10 | Bulk-resistance selection, conductivity, explicitly named temperature models | T08, slope/base conversion tests and model-sensitivity checks pass |
| P12 CA and pulse descriptors | P04 | Transient selection, relaxation metrics, pulse ΔU/ΔI at declared times | Pulse boundaries and timing definitions pass reference traces |
| P13 Diffusion models | P00 diffusion,P12 | Independent slab forward solver, GITT/PITT estimators, window/geometry gates | T10–T12 plus independent PDE and deliberately invalid-model cases pass |
| P14 Transference workflow | P00 transport,P10,P12 | Link polarization and before/after EIS; implement operational BV estimate | T13 and resistance/steady-state sensitivity pass; protocol interpretation checked |
| P15 Uncertainty and comparisons | P01,P05,P07,P10 | Carry covariance/provenance, independent-cell grouping and error bars | T14 plus known shared-error and grouping tests pass |
| P16 Automated recipes | P05–P12 as available | Applicability checks, metadata prompts, cache invalidation and batch jobs | Valid outputs run automatically; unavailable outputs explain exact reason |
| P17 Interface and export | P05,P07,P09,P16 | Build usable screens and reproducible figures/tables/projects | Import–analyze–edit–export–reopen workflow reproduces results |
| P18 Release hardening | P03–P17 for enabled scope | Installer, offline operation, compatibility documentation and large-file/recovery checks | Declared release corpus and end-to-end gates pass |
| P19 Research extensions | Separate method approval | DRT, Nicholson/Laviron, scan-rate decomposition, other vendors | Each extension gets its own source card and independent validation |

### Execution batches

Batch A: P00–P02, the scientific contract and reference cases. This document starts P00 and defines P02 targets; it does not complete either package's release gates.

Batch B: P03–P06, reliable EC-Lab import and cycling. This yields the first complete scientific workflow.

Batch C: P07–P10, CV, derivatives, EIS plots and defensible fitting.

Batch D: P11–P15, polymer electrolyte, pulse methods, gated diffusion/transport and statistical treatment. Parts can be deferred without blocking the battery core.

Batch E: P16–P18, automatic recipes, integrated user interface, export and packaging. A minimal interface can accompany Batch B; full automation follows validated dependencies.

Batch F: P19 only after the relevant literature and applicability questions are resolved.

### Handoff format for every package

Record: package ID and state; exact inputs and assumptions; equation/source IDs; permitted code areas; produced artifacts; commands/tests and their observed results; known limitations; dependency changes; and the next task. Freeze a shared analysis result shape early: values, units, normalization basis, input references, method ID/version, settings, diagnostics, uncertainty and artifacts. The same numerical engine must serve interactive and batch runs.

Do not split work by screens before defining scientific contracts. Import, segmentation, calculations, fitting and presentation have different responsibilities. A package may extend the common schema only through an explicit schema change with downstream checks.

## 16. Current status and immediate next work

Completed in this turn: collected and classified sources; drafted core mathematical definitions and conditional advanced models; derived the signed PITT slope relation and simplified GITT relation; calculated selected arithmetic benchmarks; and defined the bounded execution packages and dependencies.

Outstanding scientific verification: full correction to the CV guide; original Lin-KK reconciliation; full GITT critical-method review; primary polymer temperature-model references; full resistance-corrected transference protocol; advanced kinetic/DRT primary-method selection. These gaps are explicit gates, not reasons to invent defaults or delay independent core work.

Next executable work: implement P01 and the core of P02, then test P03 on representative user files. Native EC-Lab compatibility and real-data segmentation require actual files. A minimal starter set is one GCPL run, one CV run and one PEIS run with matching MPR/MPT exports where possible, settings and cell metadata. Until those are available, mathematical and synthetic validation can proceed without claiming instrument-file compatibility.
