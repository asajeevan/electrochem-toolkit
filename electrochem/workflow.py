"""One workflow for the command line and the desktop app.

open_file -> analyse_file -> export. Both front ends call these functions and
nothing else, so a number shown in the app and a number written by the
command line come from the same code path with the same inputs.

Rules carried over from the P12 interface work (U01, section 3):
- display arrays never enter a calculation: the app draws from the analysed
  Table and Run, never from decimated copies;
- a result is shown only for the inputs it was computed from: every Run keeps
  the Settings it was made with, and the app compares them before showing it;
- nothing is guessed: the header's declared mass is offered, never applied.
"""
from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from . import CREDIT, __version__, citation, differential, methods_text, origin_export, plotting
from .cycling import Settings, analyse, cumulative_charge, rows
from .metadata import _raw_header, from_header, sibling_export, theoretical_from_header
from .segment import segment
from .table import load, with_potential

VERSION = __version__

FIGURES = [
    ("1", "potential_capacity", "Potential vs. capacity for the selected cycles"),
    ("2", "capacity_efficiency", "Capacity and coulombic efficiency vs. cycle number"),
    ("3", "dqde", "Differential capacity dQ/dE (potential on the vertical axis)"),
    ("4", "average_voltage", "Average charge/discharge potential and hysteresis vs. cycle number"),
    ("5", "overview_time", "Potential and current vs. time for the whole file"),
    ("6", "summary", "Four-panel double-column figure (1 to 4)"),
    ("7", "dqde_map", "dQ/dE colour map over potential and cycle number, charge and discharge panels"),
    ("8", "dqde_surface", "dQ/dE surfaces in 3D (potential, cycle number, dQ/dE), charge and discharge panels"),
]
FIGURE_NAMES = [n for _, n, _ in FIGURES]
DEFAULT_CYCLES = "1,2,5,10,20,50,100"


# ------------------------------------------------------------------ opening
@dataclass
class Loaded:
    path: Path
    tab: object
    meta: dict
    header_source: str | None
    proposal: object = None
    """A readers.Proposal when no profile recognises the file: tab is then None and the import review
    step has to map the columns and state the conventions before anything is computed."""

    @property
    def declared_mass_mg(self) -> float | None:
        d = self.meta.get("active_mass_declared")
        if isinstance(d, dict) and d.get("unit") == "mg":
            return float(d["value"])
        if isinstance(d, dict) and d.get("unit") == "g":
            return float(d["value"]) * 1e3
        return None


def header_lines(path: Path, tab):
    """Header from the text export, or from the .mpt exported from this .mpr (metadata.sibling_export).

    Only the header block of the sibling is read: parsing its data as well took
    seconds on a large export (independent review, finding r31)."""
    if tab.header:
        return tab.header
    cand, _ = sibling_export(path)
    if cand is None:
        return ()
    hdr = _raw_header(cand, columns=False)
    return (hdr, cand.name) if hdr else ()


def profiles_dir() -> Path:
    """Where confirmed import profiles live: one JSON file per instrument, shared by the app and the
    command line. ELECTROCHEM_PROFILES overrides it (the tests use that)."""
    return Path(os.environ.get("ELECTROCHEM_PROFILES") or Path.home() / ".electrochem-toolkit" / "profiles")


# Instrument binaries this version does not read, by extension: refused with an instruction to export text.
# (A LANHE .cex is read natively: readers.lanhe_cex, chosen by the file's signature in open_file.)
BINARY_FORMATS = {".res": "Arbin", ".nda": "Neware", ".ndax": "Neware"}


def open_with_profile(path, profile=None, progress=None) -> Loaded:
    """Open a file from another instrument through an import profile.

    profile: None to let the registry identify the file (a saved profile by header fingerprint, else a
    built-in one by its signature strings); a profile name from readers.BUILTIN; a path to a saved
    profile; or an ImportProfile. When nothing recognises the file, the returned Loaded carries a
    Proposal instead of a table and the caller asks the researcher what the file cannot say.
    progress(rows_read, bytes_read, bytes_total), when given, is called as the reader streams the file.
    """
    from .readers import BUILTIN, Entry, ImportFailure, ImportProfile, Registry, propose_mapping, read, to_table
    path = Path(path)
    size = path.stat().st_size
    if size == 0:
        raise ImportFailure("empty_file", "the file is empty")
    suffix = path.suffix.lower()
    if suffix in BINARY_FORMATS:
        raise ImportFailure("binary_export", f"{path.name} is a binary instrument file ({path.suffix}, "
                            f"{BINARY_FORMATS[suffix]}); this version reads text and Excel exports. Export the run "
                            "as .csv, .txt or .xlsx from the cycler's software.")
    if suffix not in (".xlsx", ".xlsm", ".xls"):
        # A text export never contains NUL; an instrument's own binary file almost always does. Refuse it here,
        # before the layout detection tries to read it as delimited text, unless a UTF-16 or UTF-32 byte-order
        # mark says the NULs belong to the encoding.
        with open(path, "rb") as fh:
            head = fh.read(65536)
        if b"\x00" in head and not head.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")):
            raise ImportFailure("binary_content", f"{path.name} is not a text export: it contains NUL bytes, so it "
                                "is an instrument's own binary file, or a UTF-16 text export without its byte-order "
                                "mark. Export the run as .csv, .txt or .xlsx from the cycler's software.")
    if profile is None:
        reg = Registry(profiles_dir())
        try:
            profile = reg.identify(path, list(BUILTIN.values()))
        except LookupError:
            try:
                return Loaded(path, None, {"header_source": None}, None,
                              proposal=propose_mapping(path, registry=reg))
            except ValueError as exc:
                raise ImportFailure("no_table", f"{path.name}: {exc}") from exc
        except ImportFailure:
            raise
        except ValueError as exc:                   # no table found while identifying: say so in the same words
            raise ImportFailure("no_table", f"{path.name}: {exc}") from exc
    elif isinstance(profile, str) and profile in BUILTIN:
        profile = BUILTIN[profile]
    elif isinstance(profile, (str, Path)):
        profile = Entry.from_json(Path(profile).read_text(encoding="utf-8")).profile
    assert isinstance(profile, ImportProfile)
    raw = read(path, profile, progress=progress)
    tab = to_table(raw, profile)
    meta = {"instrument": profile.instrument, "profile": profile.name, "profile_version": profile.version,
            "profile_evidence": profile.conventions.evidence, "import_report": raw.report,
            "import_findings": raw.findings, "import_profile": profile.model_dump(mode="json"), "header_source": None}
    return Loaded(path, tab, meta, None)


def open_file(path, *, native=False, encoding="cp1252", decimal=None, profile=None, progress=None) -> Loaded:
    """Open any measurement file. EC-Lab and BT-Lab files (by their own signature, or an .mpr) take the
    validated readers, and a LANHE .cex (by its signature, or its extension) the native .cex reader;
    everything else goes through an import profile (open_with_profile), which reports its progress
    through `progress(rows_read, bytes_read, bytes_total)` when a callback is given."""
    from .readers import is_eclab, lanhe_cex, native_table
    path = Path(path)
    if path.suffix.lower() == ".cex" or lanhe_cex.is_cex(path):
        raw, meta = lanhe_cex.read(path, progress=progress)
        return Loaded(path, native_table(raw), meta, None)
    if profile is not None or not is_eclab(path):
        return open_with_profile(path, profile, progress=progress)
    if not native and path.suffix.lower() == ".mpr":
        native = True
    tab = load(path, native=native, encoding=encoding, decimal=decimal)
    hdr = header_lines(path, tab)
    source = path.name
    if isinstance(hdr, tuple) and len(hdr) == 2 and isinstance(hdr[1], str):
        hdr, source = hdr
    meta = from_header(hdr) if hdr else {}
    meta["header_source"] = source if hdr else None
    return Loaded(path, tab, meta, meta["header_source"])


# --------------------------------------------------------------- analysing
def parse_cycles(spec: str, available: list[int], missing: list | None = None) -> list[int]:
    """'1,2,5:10,-1' -> cycle numbers present in the file, in the order given.

    a:b is inclusive, negative numbers count from the last cycle (-1 = last),
    a:b:s takes every s-th cycle. Ranges are clipped to the file's cycles before
    they are expanded, keeping the step's phase, so '1:2000000000' costs no more
    than '1:-1' (independent review, finding r23). Single numbers that are not in
    the file are dropped here and appended to `missing` for the caller to report.
    """
    if not available:
        return []
    first, last = min(available), max(available)
    out: list[int] = []

    def num(tok: str) -> int:
        v = int(tok)
        return last + 1 + v if v < 0 else v

    for tok in re.split(r"[,\s;]+", spec.strip()):
        if not tok:
            continue
        try:
            if ":" in tok:
                parts = tok.split(":")
                a = num(parts[0]) if parts[0] else first
                b = num(parts[1]) if len(parts) > 1 and parts[1] else last
                st = max(int(parts[2]) if len(parts) > 2 and parts[2] else 1, 1)
                if a <= b:
                    if a < first:
                        a += -(-(first - a) // st) * st          # first value >= first on the same phase
                    b = min(b, last)
                    out.extend(range(a, b + 1, st))
                else:
                    if a > last:
                        a -= -(-(a - last) // st) * st
                    b = max(b, first)
                    out.extend(range(a, b - 1, -st))
            else:
                v = num(tok)
                out.append(v)
                if missing is not None and v not in available:
                    missing.append(tok)
        except ValueError:
            if missing is not None:
                missing.append(tok)
            continue
    seen, keep = set(), []
    avail = set(available)
    for c in out:
        if c in avail and c not in seen:
            seen.add(c)
            keep.append(c)
    return keep


@dataclass
class Run:
    loaded: Loaded
    settings: Settings
    seg: object
    an: object
    selected: list[int]
    dqde_mv: float
    warnings: list[str] = field(default_factory=list)
    table: object = None              # the table as analysed: the potential column the answers call for

    @property
    def tab(self):
        return self.table if self.table is not None else self.loaded.tab

    @property
    def peak_pair_window_mV(self) -> float:
        """Window for pairing charge and discharge dQ/dE peaks of a cycle and following peaks across cycles;
        carried in the Settings the run was made with (Settings.peak_pair_window_mV)."""
        return float(getattr(self.settings, "peak_pair_window_mV", differential.PEAK_PAIR_WINDOW_MV))

    @property
    def all_cycles(self) -> list[int]:
        return [p.index for p in self.seg.pairs]

    def plateaus(self, cycles=None) -> differential.PlateauReport:
        """dQ/dE peaks, the charge under each, pairs and presence across cycles, for every cycle by default
        (presence across cycles is only as good as the cycles it is judged over). The every-cycle report is
        computed once per run: the inspector asks for it on every rebuild."""
        if cycles is None:
            cached = self.__dict__.get("_plateau_report")
            if cached is None:
                curves, withheld = self.dqde_and_withheld(self.all_cycles)
                cached = differential.plateau_analysis(curves, window_mV=self.peak_pair_window_mV, withheld=withheld)
                self.__dict__["_plateau_report"] = cached
            return cached
        curves, withheld = self.dqde_and_withheld(cycles)
        return differential.plateau_analysis(curves, window_mV=self.peak_pair_window_mV, withheld=withheld)

    def evolution_grids(self, cycles=None) -> list:
        """The charge and discharge evolution grids (differential.evolution_grid), every cycle by default."""
        curves = self.dqde_curves(self.all_cycles if cycles is None else cycles)
        return [g for g in (differential.evolution_grid(curves, d) for d in ("charge", "discharge")) if g is not None]

    def dqde_curves(self, cycles=None):
        """(cycle, curve) for each branch of the cycles, real units, constant-voltage stages excluded."""
        return self.dqde_and_withheld(cycles)[0]

    def dqde_and_withheld(self, cycles=None):
        """The curves of dqde_curves, and the (cycle, direction) of the branches of those cycles that exist but
        have none (differential.curve: interrupted or paused partway, too few points outside constant-voltage
        stages, or less than two bins of potential)."""
        cycles = self.selected if cycles is None else cycles
        pairs = {p.index: p for p in self.seg.pairs}
        out, withheld = [], set()
        for c in cycles:
            p = pairs.get(c)
            if p is None:
                continue
            for br in (p.charge, p.discharge):
                if br is None:
                    continue
                cv = differential.curve(self.tab, self.seg, self.settings, br, c, self.dqde_mv)
                if cv is not None:
                    out.append((c, cv))
                else:
                    withheld.add((c, br.direction))
        return out, withheld


def mass_warnings(loaded: Loaded, s: Settings) -> list[str]:
    """The header's declared mass against the mass used, both in mg (a header in grams was compared
    unconverted before: independent review, finding r29). Worded for the app and the command line alike."""
    warnings = []
    declared = loaded.declared_mass_mg
    if declared is None:
        return warnings
    if s.active_mass_mg and abs(declared - s.active_mass_mg) > 1e-9 * max(abs(declared), 1.0):
        warnings.append(f"The active-material mass used, {s.active_mass_mg:g} mg, differs from the header value "
                        f"{declared:g} mg; the mass you gave was used")
    if s.active_mass_mg is None:
        warnings.append(f"No active-material mass was given; the header declares {declared:g} mg, which was not used")
    if declared <= EC_LAB_DEFAULT_MASS_MG:
        warnings.append(f"The header mass, {declared:g} mg, is EC-Lab's default and was probably never set")
    return warnings


EC_LAB_DEFAULT_MASS_MG = 0.001          # what EC-Lab writes when the mass field was never filled in


def analyse_file(loaded: Loaded, s: Settings, cycles: str = DEFAULT_CYCLES, dqde_mv: float = 10.0,
                 peak_pair_window_mV: float | None = None) -> Run:
    """peak_pair_window_mV, when given, replaces s.peak_pair_window_mV in the run's copy of the settings."""
    if peak_pair_window_mV is not None:
        s = replace(s, peak_pair_window_mV=float(peak_pair_window_mV))
    w = getattr(s, "peak_pair_window_mV", differential.PEAK_PAIR_WINDOW_MV)
    if not (isinstance(w, (int, float)) and w == w and 0 < w < float("inf")):
        raise ValueError("the peak-pairing window must be a positive number of mV")
    tab = with_potential(loaded.tab, s.potential_role)
    seg = segment(tab, charge=s.charge, order=s.cycle_order, rest_current_a=s.rest_current_a)
    an = analyse(tab, seg, s)
    wanted = [int(x) for x in cycles.split(",") if x.strip()] if re.fullmatch(r"[\d,\s]*", cycles) \
        else parse_cycles(cycles, [p.index for p in seg.pairs])
    available = [p.index for p in seg.pairs]
    selected = [c for c in wanted if c in available] or available[:5]
    return Run(loaded, replace(s), seg, an, selected, dqde_mv, mass_warnings(loaded, s), tab)


# ---------------------------------------------------------------- exporting
def write_csv(path, records):
    if not records:
        Path(path).write_text("")
        return
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(records[0].keys()))
        w.writeheader()
        w.writerows(records)


def curve_rows(tab, seg, s, selected):
    out = []
    pairs = {p.index: p for p in seg.pairs}
    for c in selected:
        p = pairs.get(c)
        if p is None:
            continue
        for br in (p.charge, p.discharge):
            if br is None:
                continue
            q = cumulative_charge(tab, seg, br, s.use_instrument_dq)
            qb = plotting.capacity_basis(q, s)
            e = tab.e[br.rows]; t = tab.t[br.rows]; i = tab.i[br.rows]
            for k in range(len(q)):
                out.append({"cycle": c, "branch": br.index, "direction": br.direction, "time_s": float(t[k]),
                            "capacity_mAh": float(q[k] / 3.6), "capacity_basis": float(qb[k]),
                            "potential_V": float(e[k]), "current_mA": float(i[k] * 1e3)})
    return out


@dataclass
class ExportOptions:
    plots: set = field(default_factory=lambda: set(FIGURE_NAMES))
    formats: tuple = ("pdf", "svg", "png")
    palette: str = "blues"
    ce_range: str = "auto"
    dqde_units: str = "au"
    origin: bool = True
    journal: str = "nature"
    evolution_cycles: str = "all"     # dQ/dE map and surface: "all" cycles or the "selected" ones


def methods(s: Settings, dqde_mv: float, dqde_units: str, peak_pair_window_mV: float = differential.PEAK_PAIR_WINDOW_MV,
            evolution_cycles: str = "all") -> dict:
    w = f"{peak_pair_window_mV:g}"
    return {
        "charge": "sum of instrument dq increments over supported edges when available, else trapezoid of sampled current (M01 point-linear)",
        "energy": "dq times mean edge potential, or exact integral of point-linear I(t)E(t); requires the cell voltage or a potential against a stated reference",
        "coulombic_efficiency": "100 x Q_discharge / Q_charge for complete pairs; not given (nor the energy efficiency and "
                                "the hysteresis) for a pair in which one branch has at most two rows and carries under "
                                "0.1 % of the other's charge, a step that ended at once",
        "capacity_retention": f"100 x Q_discharge(n) / Q_discharge(cycle {s.reference_cycle}); not given for a cycle whose "
                              "discharge ended at once, nor for any cycle when the reference cycle's discharge did",
        "average_voltage": "energy / charge of the same branch: the charge-weighted mean potential, which for several plateaus is the "
                           "capacity-weighted mean of the plateau potentials",
        "mid_capacity_voltage": "potential interpolated at half of the branch capacity",
        "voltage_hysteresis": "average charge voltage minus average discharge voltage of the same cycle",
        "dqde": f"finite difference of capacity interpolated on a {dqde_mv:g} mV potential grid; constant-voltage stages excluded; charge positive, discharge negative; "
                "none for a branch with a curve break (an interval where the time goes back or is invalid, a current is missing or "
                "an error flag is set; a zero-duration interval is not one) or with a pause the instrument marked inside it, "
                "counted between the branch's first and last row outside constant-voltage stages; "
                + ("figure normalised by the common maximum (a.u.), CSV in real units" if dqde_units == "au" else "real units"),
        "dqde_peaks": "scipy find_peaks on |dQ/dE| with prominence >= 5 % of the branch maximum, the 6 most prominent per branch (a capped branch is marked); "
                      "descriptors of the measured curve at the applied rate, not equilibrium potentials; dqde_peaks.csv and dqde_pairs.csv cover every cycle, dqde_curves.csv the plotted ones",
        "dqde_peak_charge": "capacity under a peak = |Q(E_hi) - Q(E_lo)| of the capacity interpolated on the dQ/dE grid, on the branch's capacity basis; "
                            "E_lo and E_hi are the grid points of lowest |dQ/dE| between the peak and its neighbouring reported peak, or the curve end; "
                            "share = that capacity over the branch capacity outside constant-voltage stages (the capacity the dQ/dE curve spans)",
        "dqde_pairs": f"each charge peak paired with the nearest discharge peak of the same cycle within {w} mV, greedy by smallest separation, no peak used twice; "
                        "separation = charge minus discharge peak potential; mid-point = their mean, an apparent descriptor of the measured curves, not a formal potential; "
                        f"'unpaired' means no counterpart within {w} mV in the opposite branch of the same cycle, or that branch is absent or has no dQ/dE "
                        "curve (pairing_note says which), a statement about the curves, not a mechanism",
        "dqde_presence": f"peaks of one direction linked cycle to cycle to the nearest peak of the previous occurrence within {w} mV, greedy by smallest shift; "
                         "'seen in cycles a-b', 'first cycle only' (in the first analysed cycle and in no later one) and 'appears from cycle k' describe the linked peaks over the analysed cycles "
                         "of that direction, the cycles in which it has a dQ/dE curve; cycles_seen lists the cycles the peak was found in as ranges over the cycles of "
                         "the analysis, and no_curve_cycles the cycles whose branch of that direction has no curve",
        "dqde_map": ("each branch's dQ/dE linearly resampled onto one grid of nodes at multiples of the bin width (a shift of less than one bin), one row per cycle; "
                     f"{'every cycle' if evolution_cycles == 'all' else 'the selected cycles'}; figure 6 shows |dQ/dE| on a sequential map (magma_r), grey where a branch was not measured or a cycle has no dQ/dE curve; "
                     "figure 7 shows the same grid as 3D surfaces; dqde_map.csv keeps the signed values in real units; peak tables do not use this grid"),
        "c_rate": "mean |I| / (theoretical capacity x active mass); needs --molar-mass and --electrons",
        "delta_x": "Q M / (F m): electrons per formula unit exchanged in the branch",
        "capacity_fade": "negative slope of a linear fit of retention against cycle number from the reference cycle on",
        "specific_energy": "energy per gram of active material (Wh/kg of active material only; for a half-cell, vs. the reference electrode)",
    }


def figure_builders(run: Run, o: ExportOptions) -> dict:
    """name -> zero-argument callable returning a Matplotlib figure, for the figures this run allows.

    The app's figure preview and the export both use this table, so the
    preview is always the figure that will be written.
    """
    tab, seg, s, an, sel = run.tab, run.seg, run.settings, run.an, run.selected
    j = o.journal
    b = {}
    if tab.e is not None and seg.pairs:
        b["potential_capacity"] = lambda: plotting.voltage_capacity(tab, seg, s, sel, palette=o.palette, journal=j)
        b["dqde"] = lambda: plotting.dqde(tab, seg, s, sel, bin_mV=run.dqde_mv, palette=o.palette, units=o.dqde_units, journal=j)
        # the evolution figures: availability from the pairs alone (no curve is computed until a figure is drawn)
        evo = run.all_cycles if getattr(o, "evolution_cycles", "all") == "all" else sel
        pairs = [p for p in seg.pairs if p.index in set(evo)]
        n_dir = max(sum(1 for p in pairs if p.charge is not None), sum(1 for p in pairs if p.discharge is not None))
        if n_dir >= 1:
            b["dqde_map"] = lambda: plotting.fig6_dqde_map(run.dqde_curves(evo), s, tab, units=o.dqde_units, journal=j)
        if n_dir >= 2:
            b["dqde_surface"] = lambda: plotting.fig7_dqde_surface(run.dqde_curves(evo), s, tab, units=o.dqde_units, journal=j)
    if tab.e is not None:
        b["overview_time"] = lambda: plotting.overview_time(tab, s, journal=j)
    if any(c.complete for c in an.cycles):
        b["capacity_efficiency"] = lambda: plotting.capacity_efficiency(an.cycles, s, ce_range=o.ce_range, journal=j)
        if s.energy_allowed and tab.e is not None:
            b["average_voltage"] = lambda: plotting.average_voltage(an.cycles, s, journal=j)
            b["summary"] = lambda: plotting.summary_figure(tab, seg, an, s, sel, run.dqde_mv, o.palette, o.ce_range, o.dqde_units, journal=j)
    return b


FILE_STEMS = {"potential_capacity": "fig1_potential_capacity", "capacity_efficiency": "fig2_capacity_efficiency",
              "dqde": "fig3_dqde", "average_voltage": "fig4_average_voltage", "overview_time": "fig5_overview_time",
              "summary": "fig_summary", "dqde_map": "fig6_dqde_map", "dqde_surface": "fig7_dqde_surface"}
ORDER = ["potential_capacity", "dqde", "overview_time", "capacity_efficiency", "average_voltage", "summary",
         "dqde_map", "dqde_surface"]


def export(run: Run, out: Path, o: ExportOptions, progress=None) -> dict:
    """Write tables, figures, the Origin folder and settings.json. Returns the settings record."""
    tab, seg, s, an, selected = run.tab, run.seg, run.settings, run.an, run.selected
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    say = progress or (lambda msg: None)
    meta = run.loaded.meta

    say("Writing tables")
    write_csv(out / "branches.csv", rows(an.branches))
    write_csv(out / "cycles.csv", rows(an.cycles))
    write_csv(out / "rests.csv", rows(an.rests))
    plateaus = run.plateaus() if tab.e is not None else None
    summary = asdict(an.summary)
    if plateaus is not None:
        summary["plateaus"] = plateaus.summary(s.reference_cycle)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    th = theoretical_from_header(meta) if meta else {}
    # the tester's own step table, rebuilt by a native reader (readers.lanhe_cex): a CSV of its own, not
    # repeated in metadata.json
    steps_table = meta.get("instrument_steps") if meta else None
    declared = {k: v for k, v in meta.items() if k != "instrument_steps"} if meta else meta
    (out / "metadata.json").write_text(json.dumps({"declared_in_header": declared, "theoretical_from_header": th}, indent=2, default=str) + "\n")
    if steps_table:
        write_csv(out / "instrument_steps.csv", steps_table)

    figures = {}
    checks = {}
    builders = figure_builders(run, o)
    if tab.e is not None:
        write_csv(out / "curves_potential_capacity.csv", curve_rows(tab, seg, s, selected))
        crv = []
        dq_objs = run.dqde_curves()
        for c, cv in dq_objs:
            crv.extend({"cycle": c, "branch": cv.branch, "direction": cv.direction, "potential_V": float(v),
                        "dqde": float(d), "basis": cv.basis, "bin_mV": cv.bin_mV} for v, d in zip(cv.voltage_V, cv.dqdv))
        write_csv(out / "dqde_curves.csv", crv)
        write_csv(out / "dqde_peaks.csv", plateaus.peak_rows())        # every cycle: presence needs them all
        write_csv(out / "dqde_pairs.csv", plateaus.pair_rows())
        evo = run.all_cycles if o.evolution_cycles == "all" else selected
        with open(out / "dqde_map.csv", "w", newline="") as fh:
            csv.writer(fh).writerows(differential.grid_rows(run.evolution_grids(evo)))
        if o.origin:
            say("Writing the Origin folder")
            origin_export.write(out, tab, seg, an, s, selected, dq_objs, o.dqde_units, run.dqde_mv, o.ce_range)
            origin_export.write_plateau_tables(out / "origin", plateaus)
    for name in ORDER:
        if name in o.plots and name in builders:
            say(f"Drawing {name.replace('_', ' ')}")
            fig = builders[name]()
            checks[name] = [asdict(c) for c in plotting.check_figure(fig, o.journal)]
            figures[FILE_STEMS[name]] = plotting.save(fig, out / FILE_STEMS[name], o.formats)

    record = {
        "software": CREDIT,
        "analyze_version": VERSION,
        "source": {"name": tab.source_name, "sha256": tab.source_sha256, "format": tab.format, "rows": tab.n,
                   "columns_used": tab.labels, "invalid_tokens": tab.invalid_rows, "header_source": meta.get("header_source")},
        "settings": asdict(s),
        # a file from another instrument: the profile it was read with and what the reader concluded, so the
        # import is reproducible from this record alone
        "import": ({"profile": meta.get("import_profile"), "report": meta.get("import_report"),
                    "findings": meta.get("import_findings"),
                    "steps_table": "instrument_steps.csv" if steps_table else None} if meta.get("profile") else None),
        "derived_settings": {"theoretical_capacity_mAh_g": s.theoretical_capacity_mAh_g, "energy_allowed": s.energy_allowed},
        "segmentation": seg.convention,
        "unsupported_edges": {str(k): v for k, v in seg.edges.reason.items()},
        "branches": len(seg.branches), "cycles": len(seg.pairs), "complete_cycles": an.summary.complete_cycles,
        "plotted_cycles": selected, "requested_figures": sorted(o.plots), "warnings": run.warnings,
        "figures": {k: [p.name for p in v] for k, v in figures.items()},
        "figure_style": {"journal": o.journal, "palette": o.palette, "ce_range": o.ce_range, "dqde_units": o.dqde_units,
                         "evolution_cycles": o.evolution_cycles},
        "differential": {"bin_mV": run.dqde_mv, "peak_pair_window_mV": run.peak_pair_window_mV,
                         "min_prominence_fraction": differential.MIN_PROMINENCE_FRACTION, "max_peaks": differential.MAX_PEAKS,
                         "peak_notes": plateaus.notes if plateaus is not None else []},
        "figure_checks": checks,
        "methods": methods(s, run.dqde_mv, o.dqde_units, run.peak_pair_window_mV, o.evolution_cycles),
        "methods_paragraph": methods_text.paragraph(methods_text.Context(
            settings=s, run=run, dqde_mv=run.dqde_mv, dqde_units=o.dqde_units, file_name=run.loaded.path.name,
            profile_name=meta.get("profile") if meta else None, mass_warnings=tuple(run.warnings))),
        "citation": {"reference": citation.plain(), "bibtex": citation.bibtex()},
    }
    (out / "settings.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
