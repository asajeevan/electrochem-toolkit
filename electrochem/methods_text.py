"""How every number is calculated, in words: the text behind Help > How the numbers are calculated.

Each Topic explains one quantity twice, in plain words (`short`) and in full
(`detail`: equation, symbols, units, sign convention, what the file must
contain, the numerical procedure, the settings that change the result, and
when the number is not produced). `for_file()` adds the settings of the open
file, so the explanation shown is the one that applies to the result on the
screen. `paragraph()` writes a methods paragraph for a manuscript from the
same settings and ends with the citation.

The texts describe what `cycling.py`, `segment.py`, `differential.py` and
`workflow.py` do; `tests/test_methods_text.py` ties the figures quoted here
(bin width, prominence threshold, the formulas' constants) to the code so a
change in one place is caught in the other. Where the text makes a claim the
method specification makes (M01), the card is named.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import __version__, citation
from .cycling import CAPACITY_UNITS, ENDED_AT_ONCE, F, capacity_basis
from .differential import MAX_PEAKS, MIN_PROMINENCE_FRACTION as PROMINENCE_FRACTION, PEAK_PAIR_WINDOW_MV


@dataclass(frozen=True)
class Topic:
    key: str
    title: str
    short: str                      # HTML, plain words
    detail: str                     # HTML, the full method
    outputs: str                    # where the numbers appear (table columns, figures)
    spec: str                       # the method specification card(s)


@dataclass
class Context:
    """What the explanation is about: the settings and the run of the file on the screen, if any."""
    settings: Any = None            # cycling.Settings
    run: Any = None                 # workflow.Run
    dqde_mv: float = 10.0
    dqde_units: str = "au"
    file_name: str = ""
    profile_name: str | None = None  # the import profile of a file from another cycler
    mass_warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------- the topics
TOPICS: list[Topic] = [
    Topic(
        "segmentation", "Branches, cycles and pairing",
        short=(
            "<p>Before anything is calculated, the file is cut into <b>branches</b>: a branch is an unbroken run of rows "
            "under current of one sign, with the rest rows left out. A constant-current stage and the "
            "constant-voltage stage that follows it in the same direction belong to one branch. A <b>cycle</b> is one "
            "charge branch and the discharge branch that follows it (or the reverse, when the protocol starts with a "
            "discharge). A branch with no partner (a first discharge, a run that was interrupted) is kept in the "
            "tables with its capacity, but has no efficiency and no retention.</p>"
            "<p>Which current sign is the charge of the cell is never guessed. You answer it, unless the file was read "
            "through an import that settles it (a LANHE .cex whose step types name the direction, or a profile that "
            "declares its sign convention with evidence): then the import answers it, shows why, and the answer is "
            "one step you can undo. As a guide: for a positive-electrode "
            "material against lithium metal, charge is the positive (oxidation) current; for a negative-electrode "
            "material against lithium, charge is the negative (reduction) current; for a full cell the instrument's "
            "sign for charge applies. The instrument's own cycle number is listed beside the cycle number used here, "
            "because instruments count differently.</p>"),
        detail=(
            "<h4>Rows at rest</h4><p>A row is at rest when the instrument's mode column says so (EC-Lab's "
            "<i>mode</i>, other cyclers' step type), or, when no such column exists, when |<i>I</i>| is at or below "
            "the rest current you set (0 A by default, so only an exact zero counts). Rest rows are excluded from "
            "every integral; a rest ends a branch.</p>"
            "<h4>Supported edges</h4><p>An <i>edge</i> is the interval between two consecutive rows. Charge is "
            "integrated over supported edges only. An edge is <b>unsupported</b> when time does not advance (a reset, "
            "a duplicate time, or time going back where a tester resumed from a saved state), when either current "
            "sample is missing, when an instrument error flag is set, or when the current changes sign across a "
            "programmed step boundary. A step boundary with advancing time and unchanged direction is included and "
            "counted. Nothing is sorted, filled in or extrapolated across an unsupported edge (M01 section 5.1). When "
            "a tester resumes from a saved state, its charge counter goes back with the time: that step back is not "
            "a charge, and the increments recorded before the stop are kept, so the capacity includes what the "
            "counter left out.</p>"
            "<h4>Branches</h4><p>A branch is a maximal run of non-rest rows with one current sign. It is <b>complete</b> "
            "when it ends in a rest or in a change of direction and contains no unsupported edge; a branch that reaches "
            "the end of the file is treated as interrupted. The constant-current and constant-voltage parts of a "
            "branch are integrated separately as well (<i>Q</i><sub>CC</sub>, <i>Q</i><sub>CV</sub>) and the "
            "constant-voltage share is reported; the branch capacity includes both (tail policy, M01 section 6).</p>"
            "<h4>Cycles</h4><p>Consecutive branches are paired in the order you declare (charge first, or discharge "
            "first). Cycles are numbered from 1 in the order paired; a cycle is complete when both branches are. "
            "Efficiency and retention are only calculated for complete cycles. Pairing never uses row parity or the "
            "instrument's cycle counter, which is listed as <i>native_cycle</i> for comparison; EC-Lab's counter can "
            "differ by one from the cycle number here, Arbin's and others' can reset.</p>"
            "<h4>Not produced when</h4><p>No current column: no branches. No charge convention given: branches are "
            "labelled by sign only and no cycle, efficiency or retention exists until you answer.</p>"),
        outputs="branches.csv (direction, steps, modes, complete, terminated_by, native_cycle), cycles.csv (complete, "
                "charge_branch, discharge_branch, note), the Branches and Cycles tables, the cycle strip",
        spec="M01 sections 5.1 and 6; segmentation cases S05 to S19",
    ),
    Topic(
        "charge", "Charge and capacity",
        short=(
            "<p>The capacity of a branch is the charge that passed during it: the area under the current against "
            "time. Two ways of obtaining it are always calculated and both are kept. When the file carries the "
            "instrument's own charge increment for every row (EC-Lab's <i>dq</i>), the increments are summed, "
            "because the instrument integrates at its full acquisition rate while the file holds only a sample of "
            "the points. Otherwise the recorded current is integrated with the trapezoidal rule between consecutive "
            "rows. The trapezoidal value is reported beside the one used, so you can see how far the sampled current "
            "is from the instrument's integral (on constant-current stages they agree to about one part in a "
            "million; on a sparsely sampled constant-voltage tail they can differ by tens of per cent, and the "
            "instrument's increment is the better value).</p>"
            "<p>Capacities are given per gram of active material when you give a mass, per cm² when you give only an "
            "area, otherwise in mAh. The same basis is used for every number and every axis of one file.</p>"),
        detail=(
            "<h4>Equation</h4><p>Signed charge over the supported edges <i>k</i> of a branch, with the current "
            "taken as linear between samples (M01.01, point-linear model):</p>"
            "<p class='eq'><i>Q</i><sub>s</sub> = Σ<sub><i>k</i></sub> <i>h</i><sub><i>k</i></sub> "
            "(<i>I</i><sub><i>k</i></sub> + <i>I</i><sub><i>k</i>+1</sub>) / 2,&nbsp;&nbsp; "
            "<i>h</i><sub><i>k</i></sub> = <i>t</i><sub><i>k</i>+1</sub> − <i>t</i><sub><i>k</i></sub></p>"
            "<p>With instrument increments d<i>q</i><sub><i>k</i>+1</sub> attached to the row that ends edge "
            "<i>k</i>: <i>Q</i><sub>s</sub> = Σ<sub><i>k</i></sub> d<i>q</i><sub><i>k</i>+1</sub> over the same "
            "edges. The branch capacity is the magnitude (M01.02): <i>Q</i> = |<i>Q</i><sub>s</sub>| / 3.6 in mAh "
            "(1 mAh = 3.6 C). A branch has one current sign by construction, so the magnitude of the signed sum is "
            "the directional capacity; a reversal starts another branch and is never hidden in a net value.</p>"
            "<h4>Symbols and units</h4><p><i>t</i> in s, <i>I</i> in A (the file's units are converted on "
            "reading), <i>Q</i> in C internally and mAh in every table and figure. Specific capacity "
            "<i>q</i> = <i>Q</i> / <i>m</i> in mAh g⁻¹ with <i>m</i> the active-material mass; areal capacity "
            "<i>Q</i> / <i>A</i> in mAh cm⁻² with <i>A</i> the geometric electrode area (M01.03).</p>"
            "<h4>Procedure and what it assumes</h4><p>Edges in acquisition order; unsupported edges contribute "
            "nothing and make the branch incomplete; no smoothing, resampling, baseline or offset correction "
            "(M01 section 5.3). The trapezoidal rule is exact for a current that is linear between samples and is "
            "not a claim that the current was. Summation is a plain floating-point sum; for a branch of a million "
            "rows the rounding is below one part in 10¹⁰ of the result.</p>"
            "<h4>Both paths kept</h4><p><i>charge_mAh</i> is the value used and <i>charge_method</i> says which "
            "path produced it; <i>charge_trapezoid_mAh</i> is always the trapezoidal value; "
            "<i>instrument_charge_mAh</i> is the difference of the instrument's cumulative counter between the last "
            "and the first row of the branch when the file has such a counter, with the relative difference to the "
            "value used. The three are never averaged (M01 section 3).</p>"
            "<h4>Not produced when</h4><p>No current column, or no time column. A branch with an unsupported edge "
            "keeps its charge over the supported edges and is marked incomplete.</p>"),
        outputs="branches.csv: charge_mAh, charge_method, charge_trapezoid_mAh, charge_cc_mAh, charge_cv_mAh, "
                "cv_fraction_pct, specific_capacity_mAh_g, areal_capacity_mAh_cm2, instrument_charge_mAh, "
                "instrument_relative_difference, supported_duration_s; cycles.csv: charge_ and "
                "discharge_capacity_mAh and _specific_mAh_g; figures 1 and 2",
        spec="M01.01, M01.02, M01.03; reference cases R01, R03, R06",
    ),
    Topic(
        "energy", "Energy and average potential",
        short=(
            "<p>The energy of a branch is the integral of potential times current over time. The <b>average "
            "potential</b> of the branch is the energy divided by the charge: the mean of the potential weighted by "
            "the charge that passed at each potential. That is the number that matters for the energy a cell "
            "stores. It is not the time average of the potential and not the middle of the voltage window.</p>"
            "<p><b>When a branch has several plateaus</b>, the average potential is the capacity-weighted mean of the "
            "plateau potentials, with the sloping parts between them weighted by the charge they pass. Three "
            "plateaus carrying 40 mAh g⁻¹ at 3.0 V, 80 at 3.4 V and 30 at 3.8 V give (40 × 3.0 + 80 × 3.4 + "
            "30 × 3.8) / 150 = 3.373 V. So a branch has one average potential; it is not the potential of any one "
            "plateau, and it moves when the share of the plateaus changes, for instance when a plateau present in "
            "the first charge only has gone. The potential of each plateau is a different question, answered by "
            "the dQ/dE peaks (see that topic).</p>"
            "<p>Energy needs to know what the potential column is: the voltage of a two-electrode cell, or the "
            "potential of the working electrode against a named reference. For a metal half-cell the measured "
            "potential includes the polarisation of the lithium counter electrode, and the energy refers to the "
            "active material against that reference only, never to a packaged cell.</p>"),
        detail=(
            "<h4>Equation</h4><p>Over the supported edges of a branch, with potential <i>U</i> and current "
            "<i>I</i> each linear between samples, the exact integral of their product (M01.N1):</p>"
            "<p class='eq'><i>W</i> = Σ<sub><i>k</i></sub> <i>h</i><sub><i>k</i></sub> (2 <i>I</i><sub>0</sub>"
            "<i>U</i><sub>0</sub> + <i>I</i><sub>0</sub><i>U</i><sub>1</sub> + <i>I</i><sub>1</sub><i>U</i><sub>0</sub>"
            " + 2 <i>I</i><sub>1</sub><i>U</i><sub>1</sub>) / 6</p>"
            "<p>where the subscripts 0 and 1 are the two ends of edge <i>k</i>. With instrument increments: "
            "<i>W</i> = Σ d<i>q</i> (<i>U</i><sub>0</sub> + <i>U</i><sub>1</sub>) / 2. This differs from the "
            "trapezoid of sampled power by <i>h</i> Δ<i>U</i> Δ<i>I</i> / 6 per edge; the two are not exchanged "
            "(M01 section 5.2). Energy in mWh is |<i>W</i>| / 3.6.</p>"
            "<p class='eq'>Average potential&nbsp; <i>Ē</i> = <i>W</i> / <i>Q</i><sub>s</sub> = ∫ <i>U</i> d<i>Q</i> / "
            "∫ d<i>Q</i>&nbsp;&nbsp; (M01.05)</p>"
            "<p>Both integrals run over exactly the same edges, so <i>Ē</i> is the charge-weighted mean potential of "
            "the branch. For plateaus at <i>E</i><sub><i>j</i></sub> carrying charges <i>q</i><sub><i>j</i></sub>, "
            "<i>Ē</i> = Σ <i>q</i><sub><i>j</i></sub> <i>E</i><sub><i>j</i></sub> / Σ <i>q</i><sub><i>j</i></sub>, "
            "sloping regions included as the charge they carry at each potential.</p>"
            "<h4>Derived numbers</h4><p>Specific energy = energy / active mass, in Wh kg⁻¹ of active material only "
            "(M01.05). Energy efficiency = 100 <i>W</i><sub>discharge</sub> / <i>W</i><sub>charge</sub> of a "
            "complete cycle (M01.08). Voltage hysteresis = <i>Ē</i><sub>charge</sub> − <i>Ē</i><sub>discharge</sub> "
            "of the same cycle.</p>"
            "<h4>Requirements and labels</h4><p>A synchronised potential column and your answer on what it is "
            "(M01.04): <i>cell voltage</i> (two-electrode) or <i>against a reference</i> (half-cell; the reference "
            "is named in every label and note). Without that answer no energy, average potential or hysteresis is "
            "produced. A half-cell's energy is labelled 'vs. the reference' and is not a cell-level energy.</p>"
            "<h4>Not produced when</h4><p>The potential is missing or not finite on a supported edge of the "
            "branch; the configuration is unanswered.</p>"),
        outputs="branches.csv: energy_mWh, specific_energy_Wh_kg, average_voltage_V; cycles.csv: charge_ and "
                "discharge_energy_mWh, energy_efficiency_pct, average_charge_voltage_V, average_discharge_voltage_V, "
                "average_voltage_hysteresis_V; figure 4",
        spec="M01.04, M01.05, M01.08, M01.N1; reference cases R04, R05, R07 (S02: 38/3 J)",
    ),
    Topic(
        "midpoint", "Mid-capacity potential and hysteresis",
        short=(
            "<p>The mid-capacity potential is the potential read at half of the branch's capacity, following the "
            "charge as it accumulates along the branch. The hysteresis of a cycle is the charge value minus the "
            "discharge value, reported twice: for the average potentials and for the mid-capacity potentials.</p>"
            "<p>Both are descriptors of the measured curve at the current that was applied: they contain the ohmic, "
            "kinetic and concentration overpotentials of that measurement and are not thermodynamic quantities. "
            "For a cell with several plateaus the mid-capacity point can fall on a step between two plateaus, "
            "where a small change in capacity moves it by a large voltage; the dQ/dE peak table then gives the "
            "position of each plateau separately.</p>"),
        detail=(
            "<p class='eq'><i>E</i><sub>mid</sub> = <i>E</i>(<i>Q</i> = <i>Q</i><sub>branch</sub> / 2)</p>"
            "<p><i>Q</i> is the cumulative |charge| along the branch from the same increments the capacity uses "
            "(instrument d<i>q</i> or trapezoid), zero at the first row; <i>E</i> is interpolated linearly between "
            "the two rows that bracket half the capacity. Hysteresis: Δ<i>Ē</i> = <i>Ē</i><sub>charge</sub> − "
            "<i>Ē</i><sub>discharge</sub> and Δ<i>E</i><sub>mid</sub> = <i>E</i><sub>mid,charge</sub> − "
            "<i>E</i><sub>mid,discharge</sub> of the same cycle; positive for an ordinary cell. The potential "
            "role (cell voltage, or against a reference) is the one you declared; the mid-capacity potential "
            "itself needs no such answer since it is read, not integrated.</p>"
            "<h4>Not produced when</h4><p>The branch has zero capacity, or the potential is not finite on it.</p>"),
        outputs="branches.csv: mid_capacity_voltage_V, voltage_start_V, voltage_end_V; cycles.csv: "
                "mid_capacity_charge_voltage_V, mid_capacity_discharge_voltage_V, mid_capacity_hysteresis_V, "
                "average_voltage_hysteresis_V",
        spec="cycling.py terminology block; M01 section 6 (baseline plots)",
    ),
    Topic(
        "efficiency", "Coulombic efficiency, retention and fade",
        short=(
            "<p>Coulombic efficiency is the discharge capacity divided by the charge capacity of the same cycle, in "
            "per cent, for complete cycles only. Capacity retention is the discharge capacity of a cycle divided by "
            "the discharge capacity of the reference cycle you chose (cycle 1 unless you say otherwise). Capacity "
            "fade is minus the slope of a straight line fitted to retention against cycle number from the reference "
            "cycle on, in per cent per cycle; it needs at least three cycles.</p>"
            "<p>Nothing is clipped at 100 %: an efficiency above 100 % is reported as measured, because it says "
            "something about the cell or the protocol. The first cycle's efficiency includes the formation losses; "
            "the summary therefore also gives the mean efficiency from cycle 2 and over the last ten cycles.</p>"),
        detail=(
            "<p class='eq'>CE = 100 <i>Q</i><sub>discharge</sub> / <i>Q</i><sub>charge</sub>&nbsp;&nbsp; (M01.06)"
            "<br>Retention<sub><i>n</i></sub> = 100 <i>Q</i><sub>discharge,<i>n</i></sub> / "
            "<i>Q</i><sub>discharge,ref</sub>&nbsp;&nbsp; (M01.07)"
            "<br>Fade = −slope of the least-squares line through (<i>n</i>, Retention<sub><i>n</i></sub>) for "
            "<i>n</i> ≥ ref, in % per cycle</p>"
            "<p>Both capacities of a cycle are on the same basis and the same path (instrument increments or "
            "trapezoid), so a common mass or a common current gain cancels in the ratio; that is why these ratios "
            "are more precise than either capacity (M01 section 7). Coulombic inefficiency is 100 − CE.</p>"
            "<h4>Rules</h4><p>Only complete cycles (both branches complete) have an efficiency and a retention. The "
            "reference is the discharge of the cycle you name; if that cycle is incomplete or unpaired, retention "
            "is not produced for any cycle rather than silently taken from another cycle. The cycle reaching 80 % "
            "is the first complete cycle whose retention is below 80 %. The fade line is an ordinary least-squares "
            "fit (numpy.polyfit, degree 1) over the complete cycles from the reference on with a finite "
            "retention; the cycle range used is written beside it. A change of rate between cycles makes retention "
            "a comparison of protocols, not a measure of degradation: that judgement is yours.</p>"
            "<h4>Not produced when</h4><p>The pair is incomplete, the charge capacity is zero, the reference cycle "
            "is missing or incomplete, or fewer than three cycles are available for the fit. Nor for a pair in "
            "which one branch has at most two rows (one recorded interval, or a single record) and carries under "
            "0.1 % of the other's charge, a step that ended at once (for example a charge to a voltage limit begun "
            "beyond that limit): the efficiency, energy efficiency and hysteresis of such a pair would describe "
            "that step, not the cell, so they are not given and the cycle's note says why; the capacities, "
            "energies and potentials of both branches are kept. When the discharge is the branch that ended at "
            "once, the cycle has no retention either and takes no part in the cycle reaching 80 % or the fade "
            "line; when it is the reference cycle's discharge, no retention is given for any cycle (M01 section "
            "6).</p>"),
        outputs="cycles.csv: coulombic_efficiency_pct, coulombic_inefficiency_pct, capacity_retention_pct; "
                "summary.json: mean_coulombic_efficiency_pct (from cycle 2), mean_coulombic_efficiency_last10_pct, "
                "retention_at_last_cycle_pct, cycle_reaching_80pct_retention, capacity_fade_pct_per_cycle, "
                "capacity_fade_fit_cycles; figure 2",
        spec="M01.06, M01.07; reference cases R08, R09",
    ),
    Topic(
        "dqde", "dQ/dE, the differential capacity curve",
        short=(
            "<p>dQ/dE says how much charge passes per volt. A flat plateau in the potential against capacity curve "
            "becomes a peak in dQ/dE, because much charge passes while the potential hardly moves; a sloping region "
            "becomes a low, flat part. The curve is calculated for each branch separately: the cumulative capacity "
            "is read on a regular potential grid (10 mV steps unless you change it) and differentiated. The grid "
            "step is the only smoothing there is, and it is written with every curve and every peak.</p>"
            "<p>Constant-voltage stages are left out, because the potential does not change there and dQ/dE is "
            "undefined. Charge branches are drawn positive, discharge branches negative.</p>"),
        detail=(
            "<h4>Procedure</h4><p>For one branch: the cumulative capacity <i>Q</i>(<i>t</i>) from the same "
            "increments as the capacity (instrument d<i>q</i> or trapezoid), on the file's capacity basis; rows of "
            "constant-voltage stages and rows without a finite potential removed; the remaining points ordered by "
            "potential (a stable sort); a grid from the lowest to the highest measured potential of the branch in "
            "steps of the bin width (the grid never reaches beyond the measured range, where the capacity would be "
            "clamped and dQ/dE invented); <i>Q</i> interpolated linearly onto the grid; the derivative by central "
            "differences on the grid (one-sided at the two ends).</p>"
            "<p class='eq'>d<i>Q</i>/d<i>E</i> |<sub><i>E</i><sub><i>j</i></sub></sub> ≈ "
            "[<i>Q</i>(<i>E</i><sub><i>j</i>+1</sub>) − <i>Q</i>(<i>E</i><sub><i>j</i>−1</sub>)] / "
            "(2 Δ<i>E</i>)</p>"
            "<h4>Units and sign</h4><p>mAh V⁻¹, mAh g⁻¹ V⁻¹ or mAh cm⁻² V⁻¹, following the capacity basis of the "
            "file. Charge positive, discharge negative. The figure can show the curves normalised to their common "
            "maximum (a.u.) to compare shapes; the CSV always holds the real units.</p>"
            "<h4>What it assumes</h4><p>The potential changes monotonically within the branch. Where it does not "
            "(noise on a flat plateau, a current change inside the branch), the points are still ordered by "
            "potential, and dQ/dE around that potential depends on the bin width; a coarser grid or the dQ/dE "
            "evolution across cycles shows whether a feature is reproducible. The bin width trades resolution "
            "against noise: two plateaus closer than about two bins merge. This is dQ/dE (incremental capacity), "
            "not dE/dQ (differential voltage); the two emphasise different features.</p>"
            "<h4>Not produced when</h4><p>Fewer than four usable rows in the branch, or a potential range shorter "
            "than two bins. Nor for a branch with a <b>curve break</b>, an unsupported edge where the time goes back "
            "or is invalid, a current is missing or an error flag is set, nor for a branch with a <b>pause</b> the "
            "instrument marked inside it (a LANHE .cex). The potential after such a place need not continue the "
            "curve before it (a cell left without current relaxes, and the current resumes from the relaxed "
            "potential), and sorting by potential would fold the two parts onto each other and show false peaks. "
            "Only a break or pause between the branch's first and last row outside constant-voltage stages counts: "
            "one inside a constant-voltage hold at the start or end of the branch cannot fold the curve (a break "
            "there still leaves the branch partial, so its cycle has no efficiency or retention). A zero-duration "
            "edge (a time printed coarsely, or a programmed discontinuity) loses no time and is not a break, and a "
            "branch cut off by the end of the file keeps its curve. The cycle's note says which branch has no dQ/dE "
            "and why; "
            "the figures, the map and the peak tables leave such a branch out, and a peak whose partner branch has no "
            "curve says so (M01 section 9.3).</p>"),
        outputs="dqde_curves.csv (cycle, branch, direction, potential, dQ/dE, basis, bin); figure 3; the dQ/dE view",
        spec="differential.py; M01 appendix on differential capacity",
    ),
    Topic(
        "peaks", "dQ/dE peaks, pairs and several plateaus",
        short=(
            "<p>Each peak of |dQ/dE| is one plateau (or one step) of the branch. Peaks are found with a standard "
            "peak finder and kept when they stand out by at least 5 % of the branch's highest value; up to six per "
            "branch are reported, in order of potential. For every peak you get its potential (where the plateau "
            "is flattest), its height and width, and the <b>charge under the peak</b>: the capacity between the "
            "valleys of |dQ/dE| on either side, which is the capacity of that plateau, with its share of the "
            "branch.</p>"
            "<p><b>Pairing.</b> Within each cycle, every charge peak is matched with the nearest discharge peak "
            f"within a window ({PEAK_PAIR_WINDOW_MV:g} mV unless you change it), closest pairs first, each peak used once. A pair gets "
            "its separation in mV and a mid-point potential, an apparent descriptor at the applied rate. A peak "
            f"with no counterpart is reported as <i>unpaired: no counterpart within {PEAK_PAIR_WINDOW_MV:g} mV in the discharge of the "
            "same cycle</i>, which is what an irreversible process looks like in these data; the wording stays "
            "with what the data show and the conclusion is yours. Across cycles each peak is tagged as seen in "
            "cycles a to b, present in the first cycle only, or appearing from cycle k.</p>"
            "<p><b>Three or four reversible plateaus and two or three irreversible ones</b> therefore come out as: in "
            "the first charge, six or seven peaks (raise the peak limit if the table says the count was capped); "
            "in the first discharge, the three or four reversible ones; three or four pairs; the irreversible "
            "peaks unpaired and, from the second cycle on, tagged first cycle only. The charge under each peak "
            "gives the capacity of each plateau. The branch's average potential stays one number, the "
            "capacity-weighted mean of all its plateaus (see Energy and average potential).</p>"),
        detail=(
            "<h4>Peak finding</h4><p>scipy.signal.find_peaks on |dQ/dE| on the grid, with a prominence of at least "
            f"{PROMINENCE_FRACTION * 100:g} % of the branch maximum and a width of at least one grid point; the "
            f"{MAX_PEAKS} most prominent are kept and numbered in order of potential. Peak potential = the grid "
            "point of the maximum; height = dQ/dE there, signed; prominence as find_peaks defines it (height "
            "above the higher of the two surrounding valleys); width = find_peaks' width at half prominence, in V.</p>"
            "<h4>Charge under a peak</h4><p>The cumulative capacity on the grid between the adjacent local minima of "
            "|dQ/dE| on each side of the peak (or the grid end when there is none), in the file's capacity basis "
            "(<i>charge</i>, <i>window_low_V</i>, <i>window_high_V</i>), and its share of the capacity the curve "
            "spans, which is the branch capacity outside constant-voltage stages (<i>share_of_branch_pct</i>, "
            "<i>curve_capacity</i>). The valley between two peaks is the boundary of both, so the sloping region "
            "is split at its flattest point; a feature below the prominence threshold is counted with its "
            "neighbours, and the background under a small peak is part of its charge. The sum of the peak "
            "charges therefore approaches the curve capacity only when every feature of the branch is a reported "
            "peak.</p>"
            "<h4>Pairing</h4><p>Greedy by smallest separation |<i>E</i><sub>charge</sub> − "
            "<i>E</i><sub>discharge</sub>| within the window; separation = <i>E</i><sub>charge</sub> − "
            "<i>E</i><sub>discharge</sub> in mV (positive for an ordinary cell); mid-point = their mean. Pairing by "
            "proximity is a convention, not a proof that two peaks are the same process. A peak without a partner "
            "is 'unpaired', and <i>pairing_note</i> says whether the opposite branch of the cycle has no peak "
            "within the window, has no dQ/dE curve, or is absent. Across cycles, each peak is linked to the "
            "nearest peak of the same direction within the window in the next analysed cycle, one per cycle; the "
            "chain is a <i>track</i>, and its <i>evolution</i> reads 'seen in cycles a-b', 'first cycle only' or "
            "'appears from cycle k', judged over the cycles in which that direction has a dQ/dE curve. "
            "<i>cycles_seen</i> lists the cycles in which the peak was found, a range running only through "
            "consecutive cycles of the analysis, and <i>no_curve_cycles</i> the cycles whose branch of that "
            "direction has no curve.</p>"
            "<h4>What a peak is not</h4><p>Peak potentials are descriptors of the measured curve at the applied "
            "rate and temperature; they contain the polarisation of the cell and shift with rate. A plateau split "
            "by a rest or a current change inside a branch gives two peaks; two plateaus closer than about two "
            "bins give one. No mechanism, phase or reaction is inferred from a peak, a pair or a missing partner.</p>"
            "<h4>Not produced when</h4><p>No dQ/dE curve, or no peak clears the prominence threshold. When more "
            "than the peak limit clear it, the table says the count was capped.</p>"),
        outputs="dqde_peaks.csv, every cycle: voltage_V, dqdv, prominence, width_V, charge, charge_unit, "
                "share_of_branch_pct, curve_capacity, window_low_V, window_high_V, partner_voltage_V, separation_mV, "
                "midpoint_V, pairing, pairing_note, pair_window_mV, track, cycles_seen, evolution, peaks_found, "
                "peaks_reported, capped, peaks_note, no_curve_cycles; dqde_pairs.csv: one row per pair and cycle (charge_voltage_V, "
                "discharge_voltage_V, separation_mV, midpoint_V, charge_capacity, discharge_capacity); summary.json: "
                "plateaus (the reference cycle's pairs, unpaired peaks, first-cycle-only peaks, peaks appearing later); "
                "origin/dqde_peaks.csv and origin/dqde_pairs.csv",
        spec="differential.py; M01 section 'dQ/dE peaks, pairing and plateau descriptors'",
    ),
    Topic(
        "evolution", "dQ/dE evolution: map and surface",
        short=(
            "<p>The evolution figures put every cycle's dQ/dE curve side by side: a colour map with potential "
            "along one axis and cycle number along the other, charge and discharge in two panels, and a 3D "
            "surface of the same grid. A peak that stays at one potential becomes a vertical ridge; a peak that "
            "shifts, grows or fades shows as a bending, brightening or vanishing ridge; a plateau present in the "
            "first cycle only is a spot on the first row. The numbers are exactly the curves of the dQ/dE topic, "
            "arranged, nothing is smoothed between cycles.</p>"),
        detail=(
            "<p>Rows are cycles, columns a common potential grid at multiples of the bin width (each curve resampled "
            "onto it, a shift of less than one bin); each row holds that cycle's dQ/dE on its own measured range and "
            "nothing outside it. The colour scale is perceptually uniform (lightness falling steadily from white "
            "for zero) and both panels of a figure share it and one potential scale, so a charge peak and its "
            "discharge counterpart line up; grey marks potentials a branch did not reach, and cycles whose branch "
            "has no dQ/dE curve (see the dQ/dE topic). The surface uses cycle "
            "number as depth and draws "
            "every k-th cycle above 120 cycles, saying so. Every cycle is shown unless the export is set to the "
            "selected cycles. The map CSV holds the grid so another program can draw it.</p>"
            "<h4>Reading it</h4><p>Compare ridge positions within a direction; compare charge and discharge panels "
            "for the pairing; the same cautions as for peaks apply (rate, polarisation, bin width).</p>"),
        outputs="fig6_dqde_map and fig7_dqde_surface (figures 7 and 8 of the command line), dqde_map.csv (cycle, "
                "direction, basis, one column per grid potential); the Evolution view (colour map or waterfall)",
        spec="plotting.py; M01 section 'dQ/dE evolution map and surface'",
    ),
    Topic(
        "rate", "C-rate, theoretical capacity, degree of reaction",
        short=(
            "<p>The theoretical capacity of the active material is the charge of <i>n</i> electrons per formula "
            "unit, per gram. The C-rate of a branch is its mean current per gram divided by that theoretical "
            "capacity: 1C is the current that would pass the theoretical capacity in one hour. The degree of "
            "reaction Δ<i>x</i> is the number of electrons (ions) per formula unit exchanged in the branch; "
            "utilisation is the measured specific capacity as a percentage of the theoretical one.</p>"
            "<p>These need the molar mass, the electron count and the active mass from you. The C-rate here is "
            "based on the theoretical capacity and on the mean current of the whole branch, constant-voltage "
            "tail included; a paper that quotes a C-rate should say which reference capacity it means.</p>"),
        detail=(
            f"<p class='eq'><i>q</i><sub>th</sub> = <i>n F</i> / (3.6 <i>M</i>) mAh g⁻¹,&nbsp;&nbsp; <i>F</i> = {F} C mol⁻¹"
            "<br>C-rate = (mean |<i>I</i>| / <i>m</i>) / <i>q</i><sub>th</sub> in h⁻¹;&nbsp; label 'xC' for ≥ 1, "
            "'C/x' below"
            "<br>Δ<i>x</i> = |<i>Q</i><sub>s</sub>| <i>M</i> / (<i>F m</i>)"
            "<br>Utilisation = 100 <i>q</i> / <i>q</i><sub>th</sub></p>"
            "<p><i>M</i> in g mol⁻¹, <i>m</i> the active-material mass in g, <i>n</i> electrons per formula unit "
            "(M01.09, M01.10). The mean current is the mean of |<i>I</i>| over the branch's rows, so a branch with "
            "a long constant-voltage tail has a lower mean C-rate than its constant-current setpoint; the label "
            "is the mean, never the setpoint. No claim that all <i>n</i> electrons are accessible is made.</p>"
            "<h4>Not produced when</h4><p>Molar mass, electron count or active mass missing or not positive.</p>"),
        outputs="branches.csv: c_rate, c_rate_label, mean_current_mA, specific_current_mA_g, current_density_mA_cm2, "
                "delta_x, utilisation_pct; summary.json: theoretical_capacity_mAh_g, first_cycle_utilisation_pct",
        spec="M01.09, M01.10; reference cases R10, R12",
    ),
    Topic(
        "basis", "Mass, area and the capacity basis",
        short=(
            "<p>Every capacity of a file is on one basis: per gram of active material when you give a mass, per "
            "cm² of electrode when you give only an area, otherwise in mAh. Labels, axes and tables all come from "
            "that one decision, so a label can never name a basis its numbers are not on.</p>"
            "<p>The active-material mass is the mass of the active compound alone (coating mass times the active "
            "fraction), not the electrode, the composite or the cell. The area is the geometric electrode area, "
            "not an active interfacial area. Nothing is guessed: the mass in an EC-Lab header is shown to you and "
            "used only when you confirm it, and EC-Lab's default of 0.001 g is flagged as probably never set.</p>"),
        detail=(
            "<p>Basis = <i>specific</i> if the active mass is given and positive; else <i>areal</i> if the area is "
            "given and positive; else <i>absolute</i>. Specific capacity = <i>Q</i> / <i>m</i> (mAh g⁻¹); areal "
            "capacity = <i>Q</i> / <i>A</i> (mAh cm⁻²); specific energy = <i>W</i> / <i>m</i> (Wh kg⁻¹); specific "
            "current = mean |<i>I</i>| / <i>m</i> (mA g⁻¹); current density = mean |<i>I</i>| / <i>A</i> "
            "(mA cm⁻²). dQ/dE follows the same basis (M01.03).</p>"
            "<p>The header mass of an EC-Lab file is compared with the mass you give, in the same unit, and a "
            "difference is reported as a warning; the mass you give is the one used. Both the absolute and the "
            "specific value are kept in the tables, so a mass can be corrected afterwards without re-reading.</p>"
            "<h4>Not produced when</h4><p>Specific values need a positive mass, areal values a positive area; "
            "a mass or area of zero or less is refused, never used.</p>"),
        outputs="branches.csv and cycles.csv: both _mAh and _mAh_g columns; settings.json: active_mass_mg, area_cm2, "
                "capacity_basis, mass warnings",
        spec="M01.03; review finding r01 (one basis decision)",
    ),
    Topic(
        "rests", "Rests and open-circuit potential",
        short=(
            "<p>A rest is a run of rows at open circuit. For each rest the duration, the potential at its start and "
            "end and the change between them (the relaxation) are reported. The open-circuit potential before a "
            "charge is the potential at the end of the rest that precedes it; the relaxation after a branch is "
            "the potential at the end of the following rest minus the last potential under current. These are "
            "read from the file, not fitted or extrapolated.</p>"),
        detail=(
            "<p>Rest rows are the ones the mode column marks (or |<i>I</i>| ≤ the rest current when there is no "
            "mode column). Rest <i>k</i> runs from its first to its last row; duration = "
            "<i>t</i><sub>last</sub> − <i>t</i><sub>first</sub>; relaxation = <i>E</i><sub>last</sub> − "
            "<i>E</i><sub>first</sub>. A rest shorter than the sampling interval has one row and a zero "
            "duration. No equilibrium is assumed: the end-of-rest potential is the value after that rest, "
            "whatever its length.</p>"
            "<h4>Not produced when</h4><p>No mode column and a rest current of zero with no exact zero in the "
            "current: no rest is recognised, and the open-circuit and relaxation columns stay empty.</p>"),
        outputs="rests.csv; branches.csv: ocv_before_V, rest_before_s, ocv_after_V, rest_after_s, relaxation_after_V",
        spec="cycling.py (_rests); M01 section 6",
    ),
    Topic(
        "limits", "What is not calculated, and uncertainty",
        short=(
            "<p>The cycling results involve no fitting, smoothing, resampling or extrapolation, apart from the "
            "straight line of the fade and the grid of dQ/dE, both stated with their settings. No measurement "
            "uncertainty is attached to the numbers: the instrument's current and time accuracy are not known to "
            "the software, and an unknown uncertainty is reported as not evaluated, never as zero.</p>"
            "<p>Repeated cycles of one cell are not independent replicates of the cell; variability between cells "
            "needs several cells. A common mass error cancels in efficiency and retention and is never counted "
            "twice. The instrument's counter and the integral of the current are two views of the same "
            "measurement, not two independent ones. Peak potentials and hysteresis are descriptors at the applied "
            "rate. No mechanism is inferred from any number here.</p>"),
        detail=(
            "<p>What a methods section can claim from these outputs: capacities by integration of the recorded "
            "current (or the instrument's increments) over the recorded intervals, with the integration rule and "
            "the tail policy stated; efficiencies and retention as ratios of those capacities with the reference "
            "cycle named; energies and average potentials with the potential's role named; dQ/dE with the bin "
            "width and the prominence threshold; peak pairing with the window. Sensitivity to the bin width can "
            "be tested by changing it and re-exporting; the difference is numerical, not experimental "
            "(M01 section 7).</p>"
            "<p>Unit conversions are exact (1 mAh = 3.6 C; 1 mWh g⁻¹ = 1 Wh kg⁻¹). Time is the file's elapsed "
            "time; a reset of the clock starts a new block and the edge across it is unsupported.</p>"),
        outputs="settings.json: methods, settings, exclusions, version; the notes columns of every table",
        spec="M01 section 7",
    ),
]

BY_KEY = {t.key: t for t in TOPICS}


# ---------------------------------------------------------------------------- the open file
def _fmt(x, unit="", digits=4) -> str:
    if x is None:
        return "not given"
    return f"{x:.{digits}g}{(' ' + unit) if unit else ''}"


def _charge_words(s) -> str:
    return {"ox": "positive (oxidation) current", "positive": "positive current",
            "red": "negative (reduction) current", "negative": "negative current"}.get(s.charge, "not answered yet")


def for_file(key: str, ctx: Context) -> list[str]:
    """The lines of 'For this file': the settings and counts that decide this topic's numbers for the open file."""
    s, run = ctx.settings, ctx.run
    if s is None:
        return []
    seg = getattr(run, "seg", None)
    an = getattr(run, "an", None)
    conv = seg.convention if seg is not None else {}
    basis = capacity_basis(s)
    out: list[str] = []
    if key == "segmentation":
        out.append(f"Charge is the {_charge_words(s)}; cycles are paired {s.cycle_order.replace('-', ' ')}.")
        src = conv.get("mode_source", "mode column") if conv else "mode column"
        out.append("Rest rows are the ones the file's mode column marks." if src == "mode column"
                   else f"No mode column: rest rows are those with {src}.")
        if seg is not None:
            complete = sum(1 for p in seg.pairs if p.complete)
            unpaired = sum(1 for p in seg.pairs if p.charge is None or p.discharge is None)
            out.append(f"{len(seg.branches)} branches, {len(seg.pairs)} cycles of which {complete} complete"
                       + (f", {unpaired} unpaired branch{'es' if unpaired != 1 else ''}" if unpaired else "") + ".")
            out.append(f"{conv.get('supported_edges', 0)} supported edges, {conv.get('unsupported_edges', 0)} "
                       f"unsupported, {conv.get('programmed_boundaries_included', 0)} programmed step boundaries "
                       "included.")
    elif key == "charge":
        tab = getattr(run, "tab", None)
        has_dq = tab is not None and getattr(tab, "dq", None) is not None
        if has_dq and s.use_instrument_dq:
            out.append("Charge from the instrument's dq increments; the trapezoid of the sampled current is reported "
                       "beside it.")
        elif has_dq:
            out.append("The file has dq increments, but you chose the trapezoid of the sampled current.")
        else:
            out.append("No instrument increments in this file: charge is the trapezoid of the sampled current.")
        if tab is not None and getattr(tab, "q_instrument", None) is not None:
            out.append("The file's cumulative charge counter is compared with the value used, branch by branch.")
        out.append(f"Capacity basis: {basis} ({CAPACITY_UNITS[basis]}); active mass {_fmt(s.active_mass_mg, 'mg')}, "
                   f"area {_fmt(s.area_cm2, 'cm²')}.")
    elif key == "energy":
        if s.terminal_voltage:
            out.append("The potential column is the two-electrode cell voltage: energies are cell energies.")
        elif s.reference:
            out.append(f"The potential is the working electrode against {s.reference}: energies and average potentials "
                       f"are vs. {s.reference} and refer to the active material only.")
        else:
            out.append("Not answered yet whether the potential is the cell voltage or against a reference: no energy, "
                       "average potential or hysteresis until then.")
        if an is not None and an.cycles:
            c = next((c for c in an.cycles if c.complete and c.average_charge_voltage_V is not None), None)
            if c is not None:
                out.append(f"Cycle {c.cycle}: average charge potential {_fmt(c.average_charge_voltage_V, 'V')}, discharge "
                           f"{_fmt(c.average_discharge_voltage_V, 'V')}, hysteresis "
                           + (f"{c.average_voltage_hysteresis_V * 1000:.3g} mV." if c.average_voltage_hysteresis_V
                              is not None else "not given (see the cycle's note).")
                           )
    elif key == "midpoint":
        if an is not None and an.cycles:
            c = next((c for c in an.cycles if c.complete and c.mid_capacity_charge_voltage_V is not None), None)
            if c is not None:
                out.append(f"Cycle {c.cycle}: mid-capacity potential {_fmt(c.mid_capacity_charge_voltage_V, 'V')} on charge, "
                           f"{_fmt(c.mid_capacity_discharge_voltage_V, 'V')} on discharge.")
    elif key == "efficiency":
        out.append(f"Reference cycle for retention: {s.reference_cycle}.")
        if an is not None:
            sm = an.summary
            if sm.capacity_fade_fit_cycles:
                out.append(f"Fade fitted over cycles {sm.capacity_fade_fit_cycles}: "
                           f"{sm.capacity_fade_pct_per_cycle:.3g} % per cycle.")
            elif sm.complete_cycles:
                out.append(f"{sm.complete_cycles} complete cycle{'s' if sm.complete_cycles != 1 else ''}: fewer than "
                           "three from the reference on, so no fade line." if sm.complete_cycles < 3 else
                           f"{sm.complete_cycles} complete cycles.")
            if sm.notes:
                out.append(sm.notes[0].upper() + sm.notes[1:] + ".")
    elif key in ("dqde", "peaks", "evolution"):
        out.append(f"Potential grid: {ctx.dqde_mv:g} mV; units: {CAPACITY_UNITS[basis]} V⁻¹"
                   + (" (figure normalised to the common maximum, a.u.)" if ctx.dqde_units == "au" else "") + ".")
        if key == "peaks":
            window = getattr(s, "peak_pair_window_mV", PEAK_PAIR_WINDOW_MV)
            out.append(f"Peaks kept at a prominence of at least {PROMINENCE_FRACTION * 100:g} % of the branch maximum, "
                       f"up to {MAX_PEAKS} per branch; pairing and tracking window {window:g} mV.")
            rep = run.plateaus() if run is not None and hasattr(run, "plateaus") else None
            if rep is not None and rep.cycles:
                sm = rep.summary(s.reference_cycle)
                unp = sm.get("unpaired_peaks", []); fco = sm.get("first_cycle_only_peaks", [])
                out.append(f"Cycle {sm['cycle']}: {sm['pairs']} pair{'s' if sm['pairs'] != 1 else ''}"
                           + (f", {len(unp)} unpaired peak{'s' if len(unp) != 1 else ''} ("
                              + ", ".join(f"{u['direction']} {u['voltage_V']:.3f} V" for u in unp) + ")" if unp else "")
                           + ("; first cycle only: " + ", ".join(
                               f"{u['direction']} {u['voltage_V']:.3f} V"
                               + (f" (cycle {u['cycle']}, the first with a {u['direction']} dQ/dE curve)"
                                  if u.get("cycle", 1) != 1 else " (cycle 1)" if sm["cycle"] != 1 else "")
                               for u in fco)
                              if fco else "") + ".")
    elif key == "rate":
        out.append(f"Molar mass {_fmt(s.molar_mass_g_mol, 'g mol⁻¹')}, electrons per formula unit "
                   f"{_fmt(s.electrons)}, active mass {_fmt(s.active_mass_mg, 'mg')}.")
        qth = s.theoretical_capacity_mAh_g
        if qth:
            out.append(f"Theoretical capacity {qth:.4g} mAh g⁻¹.")
        else:
            out.append("C-rate, degree of reaction and utilisation are not produced until all three are given.")
    elif key == "basis":
        out.append(f"Basis: {basis} ({CAPACITY_UNITS[basis]}); active mass {_fmt(s.active_mass_mg, 'mg')}, area "
                   f"{_fmt(s.area_cm2, 'cm²')}.")
        out.extend(w + "." for w in ctx.mass_warnings)
    elif key == "rests":
        if an is not None:
            out.append(f"{len(an.rests)} rest{'s' if len(an.rests) != 1 else ''} in the file.")
    elif key == "limits":
        out.append(f"Cyclara {__version__}; the settings and methods of this analysis are written to settings.json "
                   "with every export.")
    if ctx.profile_name == "lanhe-cex":
        out.append("Read natively from the tester's .cex file (reader lanhe-cex); its scales, their check against the "
                   "tester's own capacity and energy counters (or why the check could not be made), the pauses, "
                   "restarts and other events of the tester, and its step table are in settings.json and "
                   "instrument_steps.csv.")
    elif ctx.profile_name:
        out.append(f"Read with the import profile '{ctx.profile_name}'; its conventions (current sign, direction "
                   "source, capacity semantics, cycle base) are in settings.json.")
    return out


# ---------------------------------------------------------------------------- the paragraph
def _interrupted(seg, branches) -> dict:
    """{branch index: (the curve-break reasons of its intervals, how many such intervals)}, anywhere in the branch
    (segment.CURVE_BREAKS). Branch.curve_breaks counts only those inside the dQ/dE curve; every one leaves the
    branch partial."""
    from bisect import bisect_right
    from .segment import CURVE_BREAKS
    reasons = getattr(getattr(seg, "edges", None), "reason", None) or {}
    starts = [b.start for b in branches]
    out = {}
    for k, why in reasons.items():
        if why not in CURVE_BREAKS:
            continue
        i = bisect_right(starts, int(k)) - 1
        if i >= 0 and branches[i].start <= int(k) < branches[i].end:
            kinds, count = out.get(branches[i].index, (set(), 0))
            out[branches[i].index] = (kinds | {why}, count + 1)
    return out


_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


def _number(k: int, start: bool = False) -> str:
    """A count in running prose: words for one to nine, digits above; capitalised at the start of a sentence,
    where digits are not used ("In all, 12")."""
    if k < len(_NUMBER_WORDS):
        word = _NUMBER_WORDS[k]
        return word.capitalize() if start else word
    return f"In all, {k}" if start else str(k)


def _interruption_sentences(seg, branches) -> list[str]:
    """What the interruptions and pauses did, in the methods paragraph: an interval of a curve-break reason
    anywhere in a branch leaves it partial (no efficiency or retention for its cycle); one inside its dQ/dE
    curve (Branch.curve_breaks), or a pause there (Branch.pauses), means no dQ/dE; one in a constant-voltage
    stage at the start or end of the branch, which dQ/dE leaves out, does not affect the dQ/dE. A pause changes
    neither the capacity of a branch nor the efficiency and retention of its cycle."""
    def many(k, one, more):
        return one if k == 1 else more
    out = []
    interrupted = _interrupted(seg, branches)
    broken = [b for b in branches if b.index in interrupted]
    in_curve = [b for b in branches if getattr(b, "curve_breaks", 0)]
    paused = [b for b in branches if getattr(b, "pauses", 0) and not getattr(b, "curve_breaks", 0)]
    outside = [b for b in broken if not getattr(b, "curve_breaks", 0)]
    n = len(broken)
    if broken:
        words = {"time reset or invalid time": "the time went back or was invalid",
                 "missing or invalid current": "the current was missing",
                 "instrument error flag": "the instrument flagged an error"}
        found = [words[r] for r in words if any(r in interrupted[b.index][0] for b in broken)]
        what = found[0] if len(found) == 1 else ", ".join(found[:-1]) + ", or " + found[-1]
        m = sum(interrupted[b.index][1] for b in broken)
        out.append(f"{_number(n, True)} {many(n, 'branch', 'branches')} contained {_number(m)} "
                   f"{many(m, 'interval', 'intervals')} where {what}: "
                   f"{many(n, 'its capacity is', 'their capacities are')} given over the integrated intervals, and "
                   f"{many(n, 'its cycle has', 'their cycles have')} no coulombic efficiency or retention.")
    if outside:
        h, k = len(outside), sum(interrupted[b.index][1] for b in outside)
        where = (f"lay among the constant-voltage rows at the start or end of {many(h, 'its branch', 'their branches')}, "
                 f"which dQ/dE leaves out, so {many(k, 'it does', 'they do')} not affect the dQ/dE.")
        out.append((f"The {many(k, 'interval', 'intervals')} " if h == n else
                    f"In {_number(h)} of them the {many(k, 'interval', 'intervals')} ") + where)
    if in_curve or paused:
        items = []
        if in_curve:
            k = len(in_curve)
            items.append(f"{_number(k)} {many(k, 'branch', 'branches')} with such an interval inside "
                         f"{many(k, 'its curve', 'their curves')}")
        if paused:
            k = len(paused)
            items.append(f"{_number(k)} {many(k, 'branch', 'branches')} paused by the instrument inside "
                         f"{many(k, 'its curve', 'their curves')} (the potential relaxes while the current is off)")
        out.append("No dQ/dE was calculated for " + " and ".join(items) + ".")
    if paused:
        out.append("A pause changes neither the capacity of a branch nor the efficiency and retention of its cycle.")
    return out


def paragraph(ctx: Context) -> str:
    """A methods paragraph for a manuscript, from the settings of the open file, ending with the citation."""
    s, run = ctx.settings, ctx.run
    tab = getattr(run, "tab", None)
    has_dq = tab is not None and getattr(tab, "dq", None) is not None
    use_dq = has_dq and (s is None or s.use_instrument_dq)
    parts = []
    parts.append(f"Cycling data were analysed with Cyclara {__version__} ({citation.FAMILY}, {citation.year()}).")
    parts.append("The data were segmented into branches of one current direction, excluding rest periods; a cycle is "
                 + ("one charge followed by one discharge" if (s is None or s.cycle_order == "charge-first")
                    else "one discharge followed by one charge") + ".")
    if use_dq:
        parts.append("Capacities were obtained as the sum of the instrument's recorded charge increments over each "
                     "branch, constant-voltage stages included; the trapezoidal integral of the recorded current was "
                     "computed alongside as a check.")
    else:
        parts.append("Capacities were obtained by trapezoidal integration of the recorded current over the recorded "
                     "time intervals of each branch, constant-voltage stages included.")
    if s is not None:
        basis = capacity_basis(s)
        if basis == "specific":
            parts.append(f"Specific capacities refer to the active-material mass ({s.active_mass_mg:g} mg).")
        elif basis == "areal":
            parts.append(f"Areal capacities refer to the geometric electrode area ({s.area_cm2:g} cm²).")
        an = getattr(run, "an", None)
        ref = next((c for c in an.cycles if c.cycle == s.reference_cycle), None) if an is not None else None
        no_ret = None                                  # why no cycle has a retention, as the summary says
        if an is not None and (ref is None or not ref.complete):
            no_ret = f"the reference cycle, {s.reference_cycle}, is not a complete cycle of this file"
        elif ref is not None and ref.capacity_retention_pct is None:
            no_ret = (f"the discharge of the reference cycle, {s.reference_cycle}, ended at once"
                      if ENDED_AT_ONCE in (ref.note or "") else
                      f"the reference cycle, {s.reference_cycle}, has no discharge capacity to refer to")
        if no_ret:
            parts.append(f"Coulombic efficiency is the discharge capacity divided by the charge capacity of the same "
                         f"cycle; no capacity retention is given, because {no_ret}.")
        else:
            parts.append(f"Coulombic efficiency is the discharge capacity divided by the charge capacity of the same "
                         f"cycle; capacity retention refers to the discharge capacity of cycle {s.reference_cycle}.")
        how = ("the sum of the recorded charge increments times the mean potential of each recording interval"
               if use_dq else "the time integral of potential times current, both taken as linear between samples")
        if s.terminal_voltage:
            parts.append(f"Energies are {how.replace('potential', 'cell voltage', 1)}; average voltages are the "
                         "energy divided by the charge of the same branch (charge-weighted mean voltages).")
        elif s.reference:
            parts.append(f"Energies and average potentials are given against {s.reference} and refer to the active "
                         f"material; the energy is {how}, and the average potential the energy divided by the charge "
                         "of the same branch (charge-weighted mean potential).")
        qth = s.theoretical_capacity_mAh_g
        if qth:
            parts.append(f"C-rates refer to the theoretical capacity of {qth:.4g} mAh g⁻¹ "
                         f"({s.electrons:g} e⁻ per formula unit, M = {s.molar_mass_g_mol:g} g mol⁻¹) and to the "
                         "mean current of each branch.")
    parts.append(f"Differential capacity dQ/dE was calculated per branch by linear interpolation of the cumulative "
                 f"capacity on a {ctx.dqde_mv:g} mV potential grid and central differences, constant-voltage stages "
                 f"excluded; peaks were located with a prominence threshold of {PROMINENCE_FRACTION * 100:g} % of the "
                 "branch maximum"
                 + f" and charge and discharge peaks of a cycle were paired within "
                 f"{getattr(s, 'peak_pair_window_mV', PEAK_PAIR_WINDOW_MV):g} mV"
                 + ". Peak potentials are descriptors of the measured curves at the applied rate.")
    seg = getattr(run, "seg", None)
    branches = getattr(seg, "branches", None) or []
    parts.extend(_interruption_sentences(seg, branches))
    parts.append("No smoothing, resampling or baseline correction was applied; the complete settings of the analysis "
                 "are recorded in the settings.json file written with the results.")
    return " ".join(parts) + "\n\nReference: " + citation.plain()
