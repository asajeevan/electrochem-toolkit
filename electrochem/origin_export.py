"""Export for OriginLab Origin (2021 or later).

Origin's project format (.opj/.opju) is proprietary and can only be written
by Origin. This module therefore writes two things into an `origin/` folder:

1. Data files in Origin's three-line header layout (Long Name, Units,
   Comments) so that File > Import > Single ASCII, or drag-and-drop, gives
   correctly labelled columns. Curve data are in wide XY-pair layout, one
   X/Y pair per branch, which is what Origin plots directly.
2. `build_origin_project.py`, a script for Origin's `originpro` Python
   package. Run it on the PC where Origin 2021+ is installed
   (`pip install originpro`, then `python build_origin_project.py`); it
   imports every table, builds the graphs with the same styling as the
   matplotlib figures, and saves `<cell>.opju`. Every graph and worksheet in
   that project is a normal, editable Origin object.

The script cannot be executed here (Origin is Windows-only), so it is
written conservatively against the documented originpro 1.1 API.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from .cycling import capacity_basis, cumulative_charge, cycle_capacity
from . import plotting


def _write_origin_csv(path, columns, long_names, units, comments):
    """columns: list of equal-length sequences (padded with '' when shorter)."""
    n = max((len(c) for c in columns), default=0)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:   # BOM so Origin and Excel read the units correctly
        w = csv.writer(fh)
        w.writerow(long_names); w.writerow(units); w.writerow(comments)
        for k in range(n):
            w.writerow([("" if k >= len(c) or c[k] is None or (isinstance(c[k], float) and np.isnan(c[k])) else c[k]) for c in columns])


def _units_from_name(name: str) -> str:
    table = {"_mAh_g": "mAh/g", "_mAh_cm2": "mAh/cm²", "_mAh": "mAh", "_pct": "%", "_V": "V", "_s": "s", "_h": "h",
             "_mA_g": "mA/g", "_mA_cm2": "mA/cm²", "_mA": "mA", "_mWh": "mWh", "_Wh_kg": "Wh/kg", "_C": "°C"}
    for suffix, unit in table.items():
        if name.endswith(suffix):
            return unit
    return ""


def _long_name(name: str) -> str:
    for suffix in ("_mAh_g", "_mAh_cm2", "_mAh", "_pct", "_V", "_s", "_h", "_mA_g", "_mA_cm2", "_mA", "_mWh", "_Wh_kg", "_C"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", " ").capitalize().replace("Ocv", "OCV").replace("Cv ", "CV ").replace("Cc ", "CC ").replace("Dqdv", "dQ/dE")


def _origin_reference(ref: str) -> str:
    """'Li/Li+' -> 'Li\\+(+)/Li' (Origin superscript escape, oxidised form first)."""
    import re
    m = re.fullmatch(r"([A-Z][a-z]?)(\d?\+)?/([A-Z][a-z]?)(\d?\+)?", ref.strip().replace(" ", ""))
    if m and m.group(1) == m.group(3):
        charge = m.group(2) or m.group(4) or "+"
        return f"{m.group(1)}\\+({charge})/{m.group(1)}"
    return ref


def _table(path, records, units=None):
    if not records:
        return
    keys = list(records[0].keys())
    cols = [[r[k] for r in records] for k in keys]
    units = units or {}
    _write_origin_csv(path, cols, [_long_name(k) for k in keys], [units.get(k, _units_from_name(k)) for k in keys], keys)


def write(out: Path, tab, seg, an, s, selected, dqde_curves, dqde_units="au", bin_mV=10.0, ce_range="auto") -> Path:
    odir = out / "origin"
    odir.mkdir(exist_ok=True)
    from dataclasses import asdict
    basis = capacity_basis(s)
    qunit = {"specific": "mAh/g", "areal": "mAh/cm²", "absolute": "mAh"}[basis]
    # complete cycles only, so no stray points; the two *_plotted columns are the capacities on the basis the
    # axis title names (per gram, per cm2 or absolute), so a label can never sit over the wrong numbers (r01)
    rows_ = [{**asdict(c), "charge_plotted": cycle_capacity(c, "charge", s),
              "discharge_plotted": cycle_capacity(c, "discharge", s)} for c in an.cycles if c.complete]
    _table(odir / "cycles.csv", rows_, {"charge_plotted": qunit, "discharge_plotted": qunit})
    _table(odir / "branches.csv", [asdict(b) for b in an.branches])
    _table(odir / "rests.csv", [asdict(r) for r in an.rests])

    # wide potential-capacity curves: X/Y pair per branch
    qlabel = plotting.capacity_label(s).replace("$^{-1}$", "^-1").replace("$", "")
    qunit_title = {"specific": "mAh g\\+(-1)", "areal": "mAh cm\\+(-2)", "absolute": "mAh"}[basis]
    elabel = "Cell voltage" if s.terminal_voltage else ("Potential vs. " + s.reference if s.reference else "Potential")
    elabel_title = "Cell voltage (V)" if s.terminal_voltage else ("Potential (V) vs. " + _origin_reference(s.reference) if s.reference else "Potential (V)")
    pairs = {p.index: p for p in seg.pairs}
    cols, ln, un, cm = [], [], [], []
    for c in selected:
        p = pairs.get(c)
        if not p:
            continue
        for br in (p.charge, p.discharge):
            if br is None:
                continue
            q = plotting.capacity_basis(cumulative_charge(tab, seg, br, s.use_instrument_dq), s)
            cols += [list(map(float, q)), list(map(float, tab.e[br.rows]))]
            ln += [qlabel.split(" (")[0], elabel]
            un += [qunit, "V"]
            cm += [f"cycle {c} {br.direction}", f"cycle {c} {br.direction}"]
    _write_origin_csv(odir / "curves_potential_capacity_wide.csv", cols, ln, un, cm)

    # wide dQ/dE: X = dQ/dE, Y = potential (vertical orientation), pair per branch
    scale = max((float(np.nanmax(np.abs(cv.dqdv))) for _, cv in dqde_curves), default=1.0) or 1.0
    cols, ln, un, cm = [], [], [], []
    for c, cv in dqde_curves:
        d = cv.dqdv / (scale if dqde_units == "au" else 1.0)
        cols += [list(map(float, d)), list(map(float, cv.voltage_V))]
        ln += ["dQ/dE", elabel]
        un += ["a.u." if dqde_units == "au" else cv.basis, "V"]
        cm += [f"cycle {c} {cv.direction}, {bin_mV:g} mV bins"] * 2
    _write_origin_csv(odir / "dqde_wide.csv", cols, ln, un, cm)

    # overview
    _write_origin_csv(odir / "overview_time.csv",
                      [list(map(float, tab.t / 3600)), list(map(float, tab.e)) if tab.e is not None else [], list(map(float, tab.i * 1e3))],
                      ["Time", elabel, "Current"], ["h", "V", "mA"], ["", "", ""])

    e_all = np.concatenate([tab.e[b.rows] for b in seg.branches]) if seg.branches and tab.e is not None else np.array([0, 1])
    q_max = 0.0
    for c in selected:
        p = pairs.get(c)
        for br in ((p.charge, p.discharge) if p else ()):
            if br is not None:
                q_max = max(q_max, float(plotting.capacity_basis(cumulative_charge(tab, seg, br, s.use_instrument_dq), s)[-1]))
    from . import CREDIT
    spec = {
        "software": CREDIT,
        "cell": tab.source_name, "capacity_unit_title": qunit_title, "potential_label_title": elabel_title,
        "potential_min": float(np.nanmin(e_all)), "potential_max": float(np.nanmax(e_all)), "capacity_max": q_max,
        "n_cycles": int(an.summary.complete_cycles), "capacity_label": qlabel.split(" (")[0], "capacity_unit": qunit,
        "potential_label": elabel, "selected_cycles": selected, "dqde_units": "a.u." if dqde_units == "au" else "real",
        "n_curve_pairs": len(cm) // 2, "specific": basis == "specific", "capacity_basis": basis,
        "ce_ylim": list(plotting.ce_limits([c.coulombic_efficiency_pct if c.coulombic_efficiency_pct is not None
                                            else np.nan for c in an.cycles if c.complete], ce_range)), "colors_blue_ramp": [plotting.plt.get_cmap("Blues")(x)[:3] for x in np.linspace(1.0, 0.45, max(len(selected), 1))],
    }
    (odir / "origin_spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    (odir / "build_origin_project.py").write_text(_SCRIPT)
    (odir / "README.txt").write_text(_README)
    return odir


def write_plateau_tables(odir: Path, report) -> list[Path]:
    """dqde_peaks.csv and dqde_pairs.csv (differential.PlateauReport) in Origin's three-header layout."""
    odir = Path(odir)
    odir.mkdir(parents=True, exist_ok=True)
    unit = next((p.charge_unit for p in report.peaks), "")
    basis = next((p.basis for p in report.peaks), "")
    units = {"voltage_V": "V", "dqdv": basis, "prominence": basis, "width_V": "V", "bin_mV": "mV", "charge": unit,
             "share_of_branch_pct": "%", "curve_capacity": unit, "window_low_V": "V", "window_high_V": "V",
             "partner_voltage_V": "V", "separation_mV": "mV", "midpoint_V": "V", "pair_window_mV": "mV",
             "charge_voltage_V": "V", "discharge_voltage_V": "V", "charge_capacity": unit, "discharge_capacity": unit}
    names = {"dqdv": "dQ/dE at the peak", "charge": "Capacity under the peak", "share_of_branch_pct": "Share of the branch",
             "curve_capacity": "Branch capacity outside CV stages", "partner_voltage_V": "Partner peak potential",
             "separation_mV": "Separation (charge minus discharge)", "midpoint_V": "Apparent mid-point",
             "charge_capacity": "Capacity under the charge peak", "discharge_capacity": "Capacity under the discharge peak",
             "pair_window_mV": "Pairing window", "bin_mV": "Bin width", "width_V": "Peak width",
             "no_curve_cycles": "Cycles without a dQ/dE curve"}
    out = []
    for name, records in (("dqde_peaks.csv", report.peak_rows()), ("dqde_pairs.csv", report.pair_rows())):
        path = odir / name
        if records:
            keys = list(records[0].keys())
            _write_origin_csv(path, [[r[k] for r in records] for k in keys],
                              [names.get(k, _long_name(k)) for k in keys], [units.get(k, "") for k in keys], keys)
        else:
            _write_origin_csv(path, [], [], [], [])
        out.append(path)
    return out


def _python_with_originpro():
    """The interpreter that can import originpro: this one, or the launcher's Python 3.12 on Windows."""
    import subprocess, sys
    candidates = [[sys.executable], ["py", "-3.12"], ["py", "-3"], ["python"]]
    for cmd in candidates:
        try:
            r = subprocess.run(cmd + ["-c", "import originpro"], capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                return cmd
        except Exception:
            continue
    return None


def build(odir: Path, timeout: int = 900) -> str:
    """Run build_origin_project.py with a Python that has originpro. Returns a message for the user."""
    import subprocess
    script = Path(odir) / "build_origin_project.py"
    if not script.exists():
        return "Origin export folder not found; nothing to build."
    py = _python_with_originpro()
    if py is None:
        return ("originpro is not installed, so the Origin project was not built. The tables and the build script are in "
                f"{odir}. Install Origin, then Help > Set up the Origin link (or: py -3.12 -m pip install originpro)")
    try:
        r = subprocess.run(py + [str(script)], cwd=str(odir), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "Origin did not finish within the time limit; check whether an Origin dialog is waiting."
    tail = (r.stdout + r.stderr).strip().splitlines()[-8:]
    if r.returncode == 0:
        return "\n".join(tail) if tail else "Origin project built."
    return "Origin build failed:\n" + "\n".join(tail)


_README = """Origin export
=============

Origin project files can only be written by Origin, so this folder holds:

  cycles.csv, branches.csv, rests.csv        one row per cycle / branch / rest,
                                             three header lines (Long Name, Units, Comments)
  curves_potential_capacity_wide.csv         X/Y column pair per plotted branch
  dqde_wide.csv                              X = dQ/dE, Y = potential, pair per branch
  dqde_peaks.csv, dqde_pairs.csv             dQ/dE peaks of every cycle (capacity under each peak,
                                             pairing, cycles seen) and the charge/discharge pairs
  overview_time.csv                          time, potential, current
  build_origin_project.py                    builds the graphs and saves <cell>.opju

To get the editable Origin project from Cyclara: Export, then click "Build Origin
project" in the message that follows. The first time, Help > Set up the Origin link
installs OriginLab's originpro package into Cyclara's own Python (Origin 2021 or
later must be installed; Windows only). By hand instead:
  1. On the PC with Origin 2021 or later:  pip install originpro
  2. Copy this folder there, open a command prompt in it and run:
         python build_origin_project.py
  3. Origin opens, imports the tables, draws the four graphs and saves
     <cell>.opju next to the script. Every graph is a normal Origin graph:
     double-click any axis, curve or legend to edit it.

Without Python: drag each CSV into Origin. The three header lines are read as
Long Name, Units and Comments. Select the XY pairs and choose Plot > Line.
"""

_SCRIPT = r'''"""Build an editable Origin project from the exported tables.

Run on a PC with Origin 2021 or later:  pip install originpro ; python build_origin_project.py
"""
import csv
import json
import math
import os
import sys

import originpro as op

op.set_show(True)

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = open(os.path.join(HERE, "origin_build.log"), "w", encoding="utf-8")


def log(*parts):
    msg = " ".join(str(x) for x in parts)
    print(msg)
    LOG.write(msg + "\n"); LOG.flush()
spec = json.load(open(os.path.join(HERE, "origin_spec.json")))

if op.oext:
    sys.excepthook = lambda *a: (op.exit(), sys.__excepthook__(*a))


def _num(v):
    if v is None or v == "":
        return None
    if v == "True":
        return 1
    if v == "False":
        return 0
    try:
        return float(v)
    except ValueError:
        return v


def load_table(name, path):
    """Read our three-header-line CSV ourselves and fill a worksheet column by column."""
    rows = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, newline="", encoding=enc) as fh:
                rows = list(csv.reader(fh))
            break
        except UnicodeDecodeError:
            continue
    long_names, units, comments, data = rows[0], rows[1], rows[2], rows[3:]
    wb = op.new_book("w", name)
    wks = wb[0]
    ncol = len(long_names)
    wks.cols = ncol
    for k in range(ncol):
        values = [_num(r[k]) if k < len(r) else None for r in data]
        if all(isinstance(v, (int, float)) or v is None for v in values):
            values = [float("nan") if v is None else v for v in values]
        wks.from_list(k, values, lname=long_names[k], units=units[k], comments=comments[k])
    return wks, comments


def lt(gl, *cmds):
    """Run LabTalk commands one by one so a rejected command cannot cancel the others."""
    for cmd in cmds:
        try:
            gl.lt_exec(cmd)
        except Exception as exc:      # styling must never abort the build
            log("  (style skipped:", cmd, ")", exc)


def nice_step(lo, hi, max_ticks=7):
    """Smallest 1, 2, 2.5, 5 x 10^k step that gives at most max_ticks major intervals."""
    span = abs(hi - lo)
    if span <= 0:
        return 1
    k = math.floor(math.log10(span / max_ticks))
    for mag in (10 ** k, 10 ** (k + 1), 10 ** (k + 2)):
        for m in (1, 2, 2.5, 5):
            if span / (m * mag) <= max_ticks:
                return m * mag
    return span / max_ticks


def style_layer(gl, xtitle, ytitle, xlim=None, ylim=None, black=True):
    gl.axis("x").title = xtitle
    gl.axis("y").title = ytitle
    if xlim:
        try:
            gl.set_xlim(xlim[0], xlim[1], nice_step(xlim[0], xlim[1]))
        except Exception as exc:
            log("  (xlim skipped)", exc)
    if ylim:
        try:
            gl.set_ylim(ylim[0], ylim[1], nice_step(ylim[0], ylim[1]))
        except Exception as exc:
            log("  (ylim skipped)", exc)
    lt(gl, "layer.x.opposite=1;", "layer.y.opposite=1;",              # boxed axes
           "layer.x.ticks=1;", "layer.y.ticks=1;",                     # ticks inward
           "layer.x.showGrids=0;", "layer.y.showGrids=0;",
           "layer.x.minorTicks=1;", "layer.y.minorTicks=1;",
           "layer.x.label.pt=16;", "layer.y.label.pt=16;",             # tick label size
           "xb.fsize=18;", "yl.fsize=18;")                             # axis title size
    if black:
        lt(gl, "layer.x.color=1;", "layer.y.color=1;", "layer.x.label.color=1;", "layer.y.label.color=1;",
               "xb.color=1;", "yl.color=1;")


def legend_text(gl, txt, corner="top-left"):
    lt(gl, "legend;", f'legend.text$="{txt}";', "legend.fsize=16;", "legend.border.type=0;", "legend.background=0;")
    dx, dy = "(layer.x.to-layer.x.from)", "(layer.y.to-layer.y.from)"
    x = f"layer.x.from+0.04*{dx}+0.5*legend.dx" if "left" in corner else f"layer.x.to-0.04*{dx}-0.5*legend.dx"
    y = f"layer.y.to-0.03*{dy}-0.5*legend.dy" if "top" in corner else f"layer.y.from+0.03*{dy}+0.5*legend.dy"
    lt(gl, f"legend.x={x};", f"legend.y={y};")


def legend_per_cycle(gl, cycles, corner="top-left", title=None):
    """One legend entry per cycle in two columns (plots are charge, discharge pairs, so every other plot)."""
    entries = [f"\\l({2 * i + 1}) Cycle {c}" for i, c in enumerate(cycles)]
    if len(entries) > 4:
        half = (len(entries) + 1) // 2
        left, right = entries[:half], entries[half:]
        lines = [l + ("%(TAB)" + r if r else "") for l, r in zip(left, right + [""] * (len(left) - len(right)))]
    else:
        lines = entries
    if title:
        lines = [title] + lines
    legend_text(gl, "%(CRLF)".join(lines), corner)


def plot_props(p, color=None, **props):
    """Plot properties by their documented LabTalk names: symbol.kind, symbol.interior, symbol.size, line.width."""
    if color:
        try:
            p.color = color
        except Exception:
            pass
    for k, v in props.items():
        try:
            p.set_int(k, v)
        except Exception as exc:
            log("  (plot property skipped:", k, ")", exc)


cycles, ckeys = load_table("cycles", os.path.join(HERE, "cycles.csv"))
branches, _ = load_table("branches", os.path.join(HERE, "branches.csv"))
rests, _ = load_table("rests", os.path.join(HERE, "rests.csv"))
curves, _ = load_table("curves", os.path.join(HERE, "curves_potential_capacity_wide.csv"))
dqde, _ = load_table("dqde", os.path.join(HERE, "dqde_wide.csv"))
overview, _ = load_table("overview", os.path.join(HERE, "overview_time.csv"))


def col(name):
    return ckeys.index(name)


colors = ["#%02x%02x%02x" % tuple(int(255 * v) for v in rgb) for rgb in spec["colors_blue_ramp"]]

sel = spec["selected_cycles"]
emin, emax = spec["potential_min"], spec["potential_max"]
epad = 0.05 * (emax - emin)

# Graph 1: potential vs capacity, one XY pair per branch, cycles in blue shades
g1 = op.new_graph(template="line", lname="Potential_capacity")
gl = g1[0]
for k in range(0, curves.cols, 2):
    p = gl.add_plot(curves, coly=k + 1, colx=k, type="l")
    plot_props(p, color=colors[(k // 2) // 2 % len(colors)], **{"line.width": 2})
gl.rescale()
style_layer(gl, spec["capacity_label"] + " (" + spec["capacity_unit_title"] + ")", spec["potential_label_title"],
            xlim=(-0.03 * spec["capacity_max"], 1.05 * spec["capacity_max"]), ylim=(emin - epad, emax + 0.35 * (emax - emin)))
legend_per_cycle(gl, sel, "top-left")

# Graph 2: capacity and coulombic efficiency vs cycle number (double Y)
key_d, key_c = "discharge_plotted", "charge_plotted"      # on the basis the axis title names
g2 = op.new_graph(template="DoubleY", lname="Capacity_efficiency")
l1, l2 = g2[0], g2[1]
pc_ = l1.add_plot(cycles, coly=col(key_c), colx=col("cycle"), type="s"); plot_props(pc_, "#56B4E9", **{"symbol.kind": 5, "symbol.interior": 1, "symbol.size": 5})   # charge: light-blue diamond
pd_ = l1.add_plot(cycles, coly=col(key_d), colx=col("cycle"), type="s"); plot_props(pd_, "#0072B2", **{"symbol.kind": 2, "symbol.interior": 1, "symbol.size": 5})   # discharge: blue circle
pe_ = l2.add_plot(cycles, coly=col("coulombic_efficiency_pct"), colx=col("cycle"), type="s"); plot_props(pe_, "#000000", **{"symbol.kind": 3, "symbol.interior": 1, "symbol.size": 5})
l1.rescale(); l2.rescale()
qmax = max((v for v in cycles.to_list(col(key_c)) + cycles.to_list(col(key_d)) if isinstance(v, (int, float)) and not math.isnan(v)), default=1.0)
style_layer(l1, "Cycle number", spec["capacity_label"] + " (" + spec["capacity_unit_title"] + ")", xlim=(0, spec["n_cycles"] + 1), ylim=(0, qmax * 1.4))
style_layer(l2, "Cycle number", "Coulombic efficiency (%)", xlim=(0, spec["n_cycles"] + 1),
            ylim=tuple(spec["ce_ylim"]))      # contains every value, as in the exported figure
legend_text(l1, "\\l(1) Charge%(CRLF)\\l(2) Discharge%(CRLF)\\l(2.1) Coulombic efficiency", "bottom-right")

# Graph 3: dQ/dE with potential on the vertical axis
g3 = op.new_graph(template="line", lname="dQdE")
gl = g3[0]
for k in range(0, dqde.cols, 2):
    p = gl.add_plot(dqde, coly=k + 1, colx=k, type="l")
    plot_props(p, color=colors[(k // 2) // 2 % len(colors)], **{"line.width": 2})
gl.rescale()
xl = 1.1 if spec["dqde_units"] == "a.u." else None
rows = ((len(sel) + 1) // 2 if len(sel) > 4 else len(sel)) + 1
frac_bottom = rows * 0.068 + 0.03
frac_top = 0.16
total = (emax - emin) / (1 - frac_bottom - frac_top)
style_layer(gl, "d\\i(Q)/d\\i(E) (" + spec["dqde_units"] + ")", spec["potential_label_title"],
            xlim=(-xl, xl) if xl else None, ylim=(emin - frac_bottom * total, emax + frac_top * total))
legend_per_cycle(gl, sel, "bottom-left", title="10 mV bins")
lt(gl, "draw -n zline -l -v 0;", "zline.color=color(190,190,190);")      # grey line at dQ/dE = 0
ya = emax + 0.05 * total                                                  # arrows just above the data
yl_ = emax + 0.10 * total                                                 # labels above the arrows, inside the frame
xa = xl if xl else 1.0
lt(gl, 'label -s -n lblD Discharge;', f"lblD.x={-0.5 * xa};", f"lblD.y={yl_};", "lblD.fsize=16;",
       'label -s -n lblC Charge;', f"lblC.x={0.5 * xa};", f"lblC.y={yl_};", "lblC.fsize=16;",
       f"draw -n arrD -la {{{-0.05 * xa}, {ya}, {-0.95 * xa}, {ya}}};",
       f"draw -n arrC -la {{{0.05 * xa}, {ya}, {0.95 * xa}, {ya}}};")

# Graph 4: average potentials and hysteresis (double Y)
g4 = op.new_graph(template="DoubleY", lname="Average_voltage")
l1, l2 = g4[0], g4[1]
p1 = l1.add_plot(cycles, coly=col("average_charge_voltage_V"), colx=col("cycle"), type="s"); plot_props(p1, "#D55E00", **{"symbol.kind": 3, "symbol.interior": 1, "symbol.size": 5})
p2 = l1.add_plot(cycles, coly=col("average_discharge_voltage_V"), colx=col("cycle"), type="s"); plot_props(p2, "#0072B2", **{"symbol.kind": 4, "symbol.interior": 1, "symbol.size": 5})
p3 = l2.add_plot(cycles, coly=col("average_voltage_hysteresis_V"), colx=col("cycle"), type="s"); plot_props(p3, "#000000", **{"symbol.kind": 1, "symbol.interior": 1, "symbol.size": 4})
l1.rescale(); l2.rescale()
vc = [v for v in cycles.to_list(col("average_charge_voltage_V")) if isinstance(v, (int, float)) and not math.isnan(v)]
vd = [v for v in cycles.to_list(col("average_discharge_voltage_V")) if isinstance(v, (int, float)) and not math.isnan(v)]
span = max(vc) - min(vd)
style_layer(l1, "Cycle number", "Average potential (V)", xlim=(0, spec["n_cycles"] + 1), ylim=(min(vd) - 0.08 * span, max(vc) + 0.40 * span))
style_layer(l2, "Cycle number", "Average voltage hysteresis, \\g(D)\\i(E) (V)", xlim=(0, spec["n_cycles"] + 1), ylim=(0, (max(vc) - min(vd)) * 2.2))
legend_text(l1, "\\l(1) Average charge voltage%(CRLF)\\l(2) Average discharge voltage%(CRLF)\\l(2.1) Hysteresis, \\g(D)\\i(E)", "top-right")

# Graph 5: overview, potential on the left axis and current on the right
g5 = op.new_graph(template="DoubleY", lname="Overview_time")
l1, l2 = g5[0], g5[1]
plot_props(l1.add_plot(overview, coly=1, colx=0, type="l"), "#0072B2", **{"line.width": 1})
plot_props(l2.add_plot(overview, coly=2, colx=0, type="l"), "#D55E00", **{"line.width": 1})
l1.rescale(); l2.rescale()
style_layer(l1, "Time (h)", spec["potential_label_title"])
style_layer(l2, "Time (h)", "Current (mA)")
lt(l1, "label -r legend;")
lt(l2, "label -r legend;")

try:
    op.lt_exec(f'type "Built by {spec.get("software", "electrochem-toolkit")}";')
except Exception:
    pass
out = os.path.join(HERE, os.path.splitext(spec["cell"])[0] + ".opju")
op.save(out)
log("saved", out)
LOG.close()
if op.oext:
    op.exit()
'''
