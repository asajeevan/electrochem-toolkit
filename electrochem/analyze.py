"""python -m electrochem.analyze FILE [options]

One command from an EC-Lab cycling file to reviewed tables and publication
figures. Example (the synthetic demonstration file, a positive electrode against
Li metal; data/demo/README.txt):

    python -m electrochem.analyze data/demo/cyclara_demo_synthetic.mpt --charge ox \\
        --reference "Li+/Li" --mass-mg 5 --molar-mass 214.4 --electrons 1 --cycles 1,2,5,10,50

Outputs in --out:
    summary.json                headline metrics for the cell
    cycles.csv                  one row per paired cycle
    branches.csv                one row per charge or discharge branch
    rests.csv                   every rest: duration, potential at start and end, relaxation
    curves_potential_capacity.csv   full-resolution curves of the plotted cycles
    dqde_curves.csv             differential capacity on the stated voltage grid
    dqde_peaks.csv              peak potentials, heights, prominences and widths per branch
    metadata.json               what the EC-Lab header declares (mass, molar mass, steps, dates)
    settings.json               source hash, conventions, methods and every processing choice
    fig1_potential_capacity, fig2_capacity_efficiency, fig3_dqde,
    fig4_average_voltage, fig5_overview_time, fig_summary   (.pdf, .svg, .png)

Conventions are never guessed: --charge names the current sign that charges
the cell; --terminal-voltage (two-electrode cell voltage) or --reference
(metal half-cell) declares what the potential column means. Without
--charge, branches are labelled by current sign only and efficiencies stay
unavailable. The mass used for normalisation is the one you pass; the header
value is written to metadata.json beside it so a mismatch is visible.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .workflow import (FIGURES, ExportOptions, Settings, analyse_file, curve_rows as _curve_rows,
                       export, header_lines as _header_lines, open_file, write_csv)
from .table import load
from . import plotting, origin_export, CREDIT, __version__

VERSION = __version__


def _tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def choose_figures(spec: str | None, interactive: bool) -> set[str]:
    """Parse --plots, or ask on the terminal when nothing was given."""
    names = {k: n for k, n, _ in FIGURES}
    by_name = {n: n for _, n, _ in FIGURES}
    if spec is None and interactive and _tty():
        print("Which figures do you want?")
        for k, n, d in FIGURES:
            print(f"  [{k}] {n:<20} {d}")
        spec = _ask("Enter numbers separated by commas, 'all', or 'none' [all]: ") or "all"
    if spec is None or spec.lower() == "all":
        return {n for _, n, _ in FIGURES}
    if spec.lower() == "none":
        return set()
    chosen = set()
    for tok in spec.replace(";", ",").split(","):
        tok = tok.strip()
        if tok in names:
            chosen.add(names[tok])
        elif tok in by_name:
            chosen.add(tok)
        elif tok:
            print(f"  ignoring unknown figure '{tok}'")
    return chosen


def ask_missing(a):
    """On a terminal, ask for the conventions that were not given on the command line."""
    if not _tty():
        return
    if a.charge is None:
        v = _ask("Which current sign charges the cell? ox (positive) / red (negative) [leave empty to skip]: ").lower()
        if v in ("ox", "red", "positive", "negative"):
            a.charge = v
    if not a.terminal_voltage and not a.reference:
        v = _ask('Potential column meaning: "cell" for a two-electrode cell voltage, or a reference such as Li/Li+ [skip]: ')
        if v.lower() == "cell":
            a.terminal_voltage = True
        elif v:
            a.reference = v
    if a.mass_mg is None:
        v = _ask("Active-material mass in mg [skip]: ")
        if v:
            try:
                a.mass_mg = float(v)
            except ValueError:
                print("  not a number, skipped")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path, nargs="?", help="An EC-Lab .mpr or .mpt file, or another cycler's export")
    ap.add_argument("--cite", action="store_true", help="Print how to cite the software (add --bibtex for BibTeX) and exit")
    ap.add_argument("--bibtex", action="store_true", help="With --cite: the BibTeX entry")
    ap.add_argument("--native", action="store_true", help="Force the native MPR reader")
    ap.add_argument("--encoding", default="cp1252", help="Text export encoding (default cp1252, EC-Lab on Windows)")
    ap.add_argument("--decimal", default=None, choices=[".", ","], help="Decimal separator of a text export (default: detected)")
    ap.add_argument("--profile", default=None, help="For another cycler's export: a built-in profile name (arbin-csv, "
                    "arbin-xlsx, neware-xlsx, neware-csv, maccor-export-sec, landt-xlsx, ...; the full list and what each "
                    "was checked against is in docs/P08d_Instrument_Compatibility_Matrix.md) or a profile .json saved by "
                    "Cyclara. Default: recognised from the file")
    ap.add_argument("--propose", action="store_true", help="Print the proposed column mapping for a file no profile "
                    "recognises, with what it cannot say, and exit")
    ap.add_argument("--charge", choices=["ox", "red", "positive", "negative"],
                    help="Current sign that charges the cell (ox = positive current at the working electrode)")
    ap.add_argument("--cycle-order", default="charge-first", choices=["charge-first", "discharge-first"])
    ap.add_argument("--terminal-voltage", action="store_true", help="The potential column is the two-electrode cell voltage")
    ap.add_argument("--reference", help='Counter/reference electrode of a half-cell, e.g. "Li/Li+"; enables energy vs. that reference')
    ap.add_argument("--mass-mg", type=float, help="Active-material mass in mg for specific capacity")
    ap.add_argument("--area-cm2", type=float, help="Electrode area in cm2 for areal capacity")
    ap.add_argument("--molar-mass", type=float, help="Molar mass of the active material in g/mol (degree of reaction, C-rate)")
    ap.add_argument("--electrons", type=float, help="Electrons per formula unit for the theoretical capacity and C-rate")
    ap.add_argument("--reference-cycle", type=int, default=1, help="Cycle whose discharge capacity defines 100 %% retention")
    ap.add_argument("--rest-current-a", type=float, default=0.0, help="|I| at or below this counts as rest when no mode column exists")
    ap.add_argument("--no-instrument-dq", action="store_true", help="Integrate sampled current only, ignore the dq column")
    ap.add_argument("--cycles", default="1,2,5,10,20,50,100", help="Cycles to draw and to export as curves")
    ap.add_argument("--plots", default=None, help="Figures to produce: numbers or names from the list (see --list-plots), 'all' or 'none'. "
                                                  "When omitted on a terminal, you are asked.")
    ap.add_argument("--list-plots", action="store_true", help="List the available figures and exit")
    ap.add_argument("--no-prompt", action="store_true", help="Never ask questions; use defaults (all figures)")
    ap.add_argument("--dqde-units", default="au", choices=["au", "real"], help="dQ/dE axis: normalised (a.u.) or mAh/V per g or cm2")
    ap.add_argument("--dqde-mv", type=float, default=10.0, help="Voltage bin for dQ/dE in mV")
    ap.add_argument("--peak-pair-window-mv", type=float, default=None,
                    help="Window within which a charge peak and a discharge peak of one cycle are paired, and a peak is "
                         "followed across cycles (default 200 mV)")
    ap.add_argument("--palette", default="blues", choices=["blues", "viridis", "okabe"])
    ap.add_argument("--ce-range", default="auto", choices=["auto", "full"], help="Coulombic-efficiency axis: zoomed or 0 to 100")
    ap.add_argument("--formats", default="pdf,svg,png")
    ap.add_argument("--journal", default="nature", choices=list(plotting.JOURNALS), help="Figure sizes and type rules")
    ap.add_argument("--no-origin", action="store_true", help="Skip the origin/ export folder")
    ap.add_argument("--build-origin", action="store_true", help="Also build the .opju with Origin (needs Origin and originpro)")
    ap.add_argument("--out", type=Path, default=None, help="Output folder (default: <file stem>_analysis)")
    a = ap.parse_args(argv)
    if a.cite:
        from . import citation
        print(citation.bibtex() if a.bibtex else citation.plain())
        return 0
    if a.list_plots:
        for k, n, d in FIGURES:
            print(f"[{k}] {n:<20} {d}")
        return 0
    if a.file is None:
        ap.error("a file to analyse is needed (or --cite, --list-plots)")
    if not a.no_prompt:
        ask_missing(a)
    plots = choose_figures(a.plots, interactive=not a.no_prompt)

    out = a.out or a.file.with_name(a.file.stem + "_analysis")
    out.mkdir(parents=True, exist_ok=True)
    formats = tuple(f.strip() for f in a.formats.split(",") if f.strip())

    if a.propose:
        from .readers import propose_mapping
        print(propose_mapping(a.file).summary())
        return 0
    loaded = open_file(a.file, native=a.native, encoding=a.encoding, decimal=a.decimal, profile=a.profile)
    if loaded.proposal is not None:
        print(f"No import profile recognises {a.file.name}. Open it in Cyclara to map its columns once (the mapping "
              "is then saved and recognised), or give --profile. The proposal:\n")
        print(loaded.proposal.summary())
        return 2
    tab = loaded.tab
    if loaded.meta.get("profile"):
        rep_ = loaded.meta["import_report"]
        print(f"  read with the {loaded.meta['profile']} profile ({loaded.meta['instrument']}); current "
              f"{rep_['current_sign_declared'].replace('_', ' ')} in the file, analysed charge-positive"
              + (f"; counter vs. integral worst {rep_['counter_vs_integral']['worst_relative_difference'] * 100:.3f} %"
                 if rep_.get("counter_vs_integral") and "worst_relative_difference" in rep_["counter_vs_integral"] else ""))
        for f in loaded.meta["import_findings"]:
            if f["severity"] == "warn":
                print("  import warning:", f["message"])
    s = Settings(charge=a.charge, cycle_order=a.cycle_order, terminal_voltage=a.terminal_voltage, reference=a.reference,
                 active_mass_mg=a.mass_mg, area_cm2=a.area_cm2, molar_mass_g_mol=a.molar_mass, electrons=a.electrons,
                 reference_cycle=a.reference_cycle, rest_current_a=a.rest_current_a, use_instrument_dq=not a.no_instrument_dq)
    run = analyse_file(loaded, s, a.cycles, a.dqde_mv, peak_pair_window_mV=a.peak_pair_window_mv)
    seg, an, warnings = run.seg, run.an, run.warnings
    export(run, out, ExportOptions(plots=plots, formats=formats, palette=a.palette, ce_range=a.ce_range,
                                   dqde_units=a.dqde_units, origin=not a.no_origin, journal=a.journal))

    sm = an.summary
    print(f"{tab.source_name}: {tab.n} rows, {len(seg.branches)} branches, {sm.complete_cycles} complete cycles, {sm.total_test_time_h:.1f} h")
    if sm.complete_cycles:
        f = lambda v, fmt="{:.4g}": (fmt.format(v) if v is not None else "n/a")
        print(f"  first cycle: discharge {f(sm.first_cycle_discharge_mAh)} mAh"
              + (f" ({f(sm.first_cycle_specific_discharge_mAh_g)} mAh/g)" if sm.first_cycle_specific_discharge_mAh_g else "")
              + f", CE {f(sm.first_cycle_coulombic_efficiency_pct, '{:.2f}')} %")
        print(f"  cycle {sm.last_cycle}: retention {f(sm.retention_at_last_cycle_pct, '{:.1f}')} %, mean CE (cycles 2+) {f(sm.mean_coulombic_efficiency_pct, '{:.2f}')} %,"
              f" fade {f(sm.capacity_fade_pct_per_cycle, '{:.3f}')} %/cycle")
        if sm.mean_average_discharge_voltage_V is not None:
            print(f"  mean average discharge potential {sm.mean_average_discharge_voltage_V:.3f} V, mean hysteresis "
                  f"{f(sm.mean_voltage_hysteresis_V, '{:.3f}')} V")
        if sm.theoretical_capacity_mAh_g:
            print(f"  theoretical capacity {sm.theoretical_capacity_mAh_g:.1f} mAh/g, first-cycle utilisation {f(sm.first_cycle_utilisation_pct, '{:.1f}')} %")
    for w in warnings + list(seg.convention.get("notes", [])) + [n for n in (sm.notes or "").split("; ") if n]:
        print("  note:", w)
    if s.charge is None:
        print("  --charge not given: branches labelled by current sign only; efficiency and retention unavailable")
    print(f"  written to {out}/")
    if a.build_origin and not a.no_origin:
        print("  " + origin_export.build(out / "origin").replace("\n", "\n  "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
