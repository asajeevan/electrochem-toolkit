"""Publication figures for cycling data.

Sizes and type follow each journal's own artwork instructions (JOURNALS,
with the page each number was read from). Two rules make the output exact:

1. A figure is drawn at its final size and saved at that size. No tight
   bounding box: a "89 mm" figure is 89.0 mm wide in the PDF, so it can be
   placed at 100 % without rescaling the 7 pt type.
2. The layout is computed once (constrained layout), then frozen before panel
   letters are placed and before saving, so the preview in the app and the
   file on disk are the same drawing.

check_figure() verifies each figure against its journal after drawing: size,
type sizes, overlapping or clipped text, legends covering data, line weights,
contrast of plotted colours and the font actually used. Its result is stored
in settings.json beside the figures.

Axes are boxed with inward ticks on all four sides, the convention of the
electrochemistry literature. Colours are colour-blind safe: Okabe and Ito for
categories, a single blue ramp for cycle progression whose lightest step
still reaches 3:1 against white (WCAG 2.1 non-text contrast). Nothing is
downsampled: full-resolution observations are drawn.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.lines import Line2D
from matplotlib.text import Text
from matplotlib.collections import QuadMesh
from matplotlib import transforms as mtransforms
from matplotlib.ticker import AutoMinorLocator, MaxNLocator
import numpy as np

from .cycling import capacity_basis as basis_of, cumulative_charge, cycle_capacity

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

MM = 1 / 25.4


@dataclass(frozen=True)
class Journal:
    name: str
    widths_mm: dict            # role -> width
    max_height_mm: float
    text_pt: float             # axis labels and tick labels
    small_pt: float            # legend, annotations
    min_pt: float
    max_pt: float
    panel_pt: float
    source: str
    script_min_pt: float = 5.0  # smallest sub- or superscript
    panel_lowercase: bool = True


# Numbers read from the publishers' pages on 2026-10-19.
JOURNALS = {
    "nature": Journal(
        "Nature", {"single": 89.0, "one_half": 120.0, "one_half_wide": 136.0, "double": 183.0},
        max_height_mm=170.0, text_pt=7.0, small_pt=6.5, min_pt=5.0, max_pt=7.0, panel_pt=8.0,
        source="nature.com/documents/nature-final-artwork.pdf; research-figure-guide.nature.com "
               "(89/120/136/183 mm, text 5-7 pt, panel labels 8 pt bold lowercase, 170 mm with legend)",
        script_min_pt=5.0, panel_lowercase=True),
    "elsevier": Journal(
        "Elsevier", {"single": 90.0, "one_half": 140.0, "double": 190.0},
        max_height_mm=240.0, text_pt=7.0, small_pt=7.0, min_pt=6.0, max_pt=8.0, panel_pt=8.0,
        source="elsevier.com artwork sizing (90/140/190 mm; 7 pt text, 6 pt sub- and superscripts); "
               "maximum height and panel label style not stated there",
        script_min_pt=6.0, panel_lowercase=False),
}

OKABE_ITO = ["#0072B2", "#D55E00", "#009E73", "#E69F00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]
BLUE, VERMILION, GREEN, BLACK = OKABE_ITO[0], OKABE_ITO[1], OKABE_ITO[2], "#000000"
GREY = "0.72"

# Cycle ramp: deep violet through blue to teal, darkest first. Chosen from
# candidates by the smallest CIELAB distance between neighbouring cycles
# (Delta E 13.3 for seven cycles, against 7.4 for a plain blue ramp) under the
# constraint that every step keeps at least 3:1 contrast on white (3.4:1).
RAMP = LinearSegmentedColormap.from_list("cycle_ramp", ["#2A0A4E", "#3B3B9E", "#2F78C4", "#169C8C"])
RAMP_VIRIDIS = LinearSegmentedColormap.from_list(
    "viridis_dark", [plt.get_cmap("viridis")(x) for x in np.linspace(0.0, 0.55, 16)])

FONTS = ["Arial", "Helvetica", "Liberation Sans", "Arimo", "DejaVu Sans"]
METRIC_ARIAL = ("arial", "helvetica", "liberation sans", "liberationsans", "arimo", "nimbus sans")

_J = JOURNALS["nature"]


def style(j: Journal) -> dict:
    return {
        "font.family": "sans-serif", "font.sans-serif": FONTS,
        "font.size": j.text_pt, "axes.labelsize": j.text_pt, "axes.titlesize": j.text_pt,
        "xtick.labelsize": j.text_pt, "ytick.labelsize": j.text_pt, "legend.fontsize": j.small_pt,
        "legend.title_fontsize": j.small_pt,
        "axes.linewidth": 0.6, "lines.linewidth": 1.0, "lines.markersize": 3.2,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.minor.width": 0.45, "ytick.minor.width": 0.45,
        "xtick.major.size": 3.0, "ytick.major.size": 3.0, "xtick.minor.size": 1.7, "ytick.minor.size": 1.7,
        "xtick.major.pad": 2.5, "ytick.major.pad": 2.5, "axes.labelpad": 3.0,
        "xtick.direction": "in", "ytick.direction": "in", "xtick.top": True, "ytick.right": True,
        "xtick.minor.visible": True, "ytick.minor.visible": True,
        "axes.spines.top": True, "axes.spines.right": True,
        "axes.grid": False, "legend.frameon": False, "legend.handlelength": 1.5, "legend.handletextpad": 0.5,
        "legend.borderaxespad": 0.5, "legend.labelspacing": 0.3, "legend.columnspacing": 1.1,
        "savefig.dpi": 600, "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.dpi": 150, "axes.unicode_minus": True, "mathtext.default": "regular",
        "figure.constrained_layout.h_pad": 2.5 / 72, "figure.constrained_layout.w_pad": 2.5 / 72,
        "figure.constrained_layout.hspace": 0.04, "figure.constrained_layout.wspace": 0.04,
        "axes.formatter.useoffset": False, "axes.formatter.limits": (-4, 5),
    }


def apply_style(journal: str = "nature"):
    global _J
    _J = JOURNALS[journal]
    plt.rcParams.update(style(_J))
    _script_scale(_J)


def script_factor(j: Journal) -> float:
    """Size of sub- and superscripts relative to their text. Matplotlib draws them at 0.7, which puts
    the superscript of a 7 pt "mAh g⁻¹" at 4.9 pt: under Nature's 5 pt minimum and Elsevier's 6 pt
    for sub- and superscripts (independent review, finding r12). The factor is raised just enough
    for the journal's minimum, never lowered below matplotlib's 0.7."""
    return max(0.7, (j.script_min_pt + 0.02) / j.text_pt)


def _script_scale(j: Journal):
    import matplotlib._mathtext as mathtext_impl
    f = script_factor(j)
    if getattr(mathtext_impl, "SHRINK_FACTOR", None) == f:
        return
    mathtext_impl.SHRINK_FACTOR = f
    try:                                   # parsed expressions are cached without the factor in the key
        from matplotlib.mathtext import MathTextParser
        MathTextParser._parse_cached.cache_clear()
    except AttributeError:
        pass


def col_width(role: str, journal: str = "nature") -> float:
    j = JOURNALS[journal]
    return j.widths_mm.get(role, j.widths_mm["single"]) * MM


# backwards-compatible constants (Nature)
SINGLE = 89 * MM
ONE_HALF = 120 * MM
DOUBLE = 183 * MM


# ---------------------------------------------------------------- helpers

def reference_label(ref: str) -> str:
    """'Li/Li+' or 'Li+/Li' -> 'Li$^+$/Li' (oxidised form first). Other strings pass through."""
    m = re.fullmatch(r"([A-Z][a-z]?)(\d?\+)?/([A-Z][a-z]?)(\d?\+)?", ref.strip().replace(" ", ""))
    if m and m.group(1) == m.group(3):
        charge = m.group(2) or m.group(4) or "+"
        return f"{m.group(1)}$^{{{charge}}}$/{m.group(1)}"
    return ref


def potential_label(tab, s) -> str:
    """Quantity, reference, then unit: the order of IUPAC usage and of most journals."""
    if s.terminal_voltage:
        return "Cell voltage (V)"
    if getattr(s, "reference", None):
        return f"Potential vs. {reference_label(s.reference)} (V)"
    col = tab.labels.get("potential", "E") if tab is not None else "E"
    return f"Potential, {col.split('/')[0]} (V)"


def potential_symbol(s) -> str:
    return "V" if s.terminal_voltage else "E"


def capacity_label(s, per="") -> str:
    b = basis_of(s)
    if b == "specific":
        return "Specific capacity (mAh g$^{−1}$)"
    if b == "areal":
        return "Areal capacity (mAh cm$^{−2}$)"
    return "Capacity (mAh)"


def capacity_basis(q_C, s):
    """Charge in C to capacity on the basis of cycling.capacity_basis(s)."""
    q = q_C / 3.6
    b = basis_of(s)
    if b == "specific":
        return q / (s.active_mass_mg * 1e-3)
    if b == "areal":
        return q / s.area_cm2
    return q


def _nan(v):
    return np.nan if v is None else v


def ce_limits(ce, ce_range="auto"):
    """Coulombic-efficiency axis limits that contain every plotted value.

    "auto" zooms on the spread of the values with 100 % inside the axis; it never
    cuts a point off. The previous rule capped the axis a little above 100 % and
    so dropped any cycle above it without a word (independent review, finding r02;
    M01.06: no clipping above 100 %). "full" is 0 to 105 %, or higher if a value is."""
    ce = np.asarray(ce, float)
    ok = ce[np.isfinite(ce)]
    if ce_range == "full" or ok.size == 0:
        top = max(105.0, float(np.ceil(ok.max() + 1))) if ok.size else 105.0
        return 0.0, top
    lo = float(np.floor(min(np.percentile(ok, 1) - 1, ok.min() - 0.5)))
    hi = max(100 + (100 - lo) * 0.08, float(ok.max()) + max(0.08 * (ok.max() - lo), 0.3))
    return lo, hi


def cycle_colors(n, palette="blues"):
    """First cycle darkest, last cycle lightest; every step at least 3:1 on white."""
    if palette == "okabe" and n <= 7:
        return [c for c in OKABE_ITO if c not in ("#F0E442", "#56B4E9")][:n] if n <= 6 else OKABE_ITO[:n]
    cmap = RAMP if palette != "viridis" else RAMP_VIRIDIS
    if n <= 1:
        return [cmap(0.0)]
    return [cmap(x) for x in np.linspace(0.0, 1.0, n)]


def box(ax, xlabel=None, ylabel=None):
    if xlabel is not None:
        ax.set_xlabel(xlabel)
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    ax.xaxis.set_minor_locator(AutoMinorLocator(2))
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    ax.tick_params(which="both", top=True, right=True, direction="in")


def legend_band(ax, n_entries, ncol=1, where="top", row_height=None, pad=0.035, title=False):
    """Extend the y range so a legend of n_entries fits in an empty band above or below the data.

    The band height is computed from the legend's type size and the axes'
    physical height, so it holds for any figure size.
    """
    rows = int(np.ceil(n_entries / ncol)) + (1 if title else 0)
    if row_height is None:
        h_pt = ax.get_position().height * ax.figure.get_size_inches()[1] * 72
        row_height = (plt.rcParams["legend.fontsize"] * 1.32) / max(h_pt, 1.0)
    lo, hi = ax.get_ylim()
    frac = min(rows * row_height + pad, 0.6)
    span = (hi - lo) / (1 - frac)
    if where == "top":
        ax.set_ylim(lo, lo + span)
    else:
        ax.set_ylim(hi - span, hi)


def _corner_note(ax, text):
    """A short note in a lower corner of the axes clear of the data: the lower left, else the lower right, else
    the lower left of a band added below the data for it (a fixed corner drew the bin width over a curve that
    reached it, found with a synthetic file, 20 October 2026)."""
    fig = ax.figure
    for x, ha in ((0.03, "left"), (0.97, "right")):
        t = ax.text(x, 0.03, text, transform=ax.transAxes, ha=ha, va="bottom", fontsize=_J.small_pt)
        try:
            fig.draw_without_rendering()
        except Exception:
            fig.canvas.draw()
        if _data_in_box(ax, t.get_window_extent(fig.canvas.get_renderer())) == 0:
            return t
        t.remove()
    legend_band(ax, 0, 1, "bottom", title=True)
    return ax.text(0.03, 0.03, text, transform=ax.transAxes, ha="left", va="bottom", fontsize=_J.small_pt)


def place_legend(ax, handles, labels, locs, axes=None, **kw):
    """Put the legend at the first of `locs` where it covers no data (lines, points, bands, guides).

    The layout is computed without rendering for each candidate. If every place
    covers something, the least covered one is used, and check_figure reports it.
    """
    fig = ax.figure
    axes = axes or [a for a in fig.axes if a.bbox.bounds == ax.bbox.bounds]
    tried = []
    for loc in locs:
        leg = ax.legend(handles, labels, loc=loc, **kw)
        try:
            fig.draw_without_rendering()
        except Exception:
            fig.canvas.draw()
        r = fig.canvas.get_renderer()
        n = sum(_data_in_box(a, leg.get_window_extent(r)) for a in axes)
        if n == 0:
            return leg
        tried.append((n, len(tried), loc))
    n, _, loc = min(tried)
    return ax.legend(handles, labels, loc=loc, **kw)


def _new(ax, w, ratio):
    if ax is not None:
        return ax.figure, ax
    fig = plt.figure(figsize=(w, w * ratio), layout="constrained")
    return fig, fig.add_subplot()


def _selected_pairs(seg, cycles):
    pairs = {p.index: p for p in seg.pairs}
    return [(c, pairs[c]) for c in cycles if c in pairs]


def _ncol(n, ax=None, longest="Cycle 100", max_cols=4):
    """Columns that fit the axes' physical width, so legend bands stay as short as possible."""
    if ax is None or n <= 3:
        return 1 if n <= 4 else (2 if n <= 8 else 3)
    fs = plt.rcParams["legend.fontsize"]
    rc = plt.rcParams
    entry = (rc["legend.handlelength"] + rc["legend.handletextpad"] + rc["legend.columnspacing"]) * fs \
        + 0.56 * fs * len(longest)                                        # points
    avail = ax.get_position().width * ax.figure.get_size_inches()[0] * 72 - 2 * rc["legend.borderaxespad"] * fs
    fit = max(1, int(avail // entry))
    cols = min(max_cols, fit, n)
    rows = int(np.ceil(n / cols))
    return int(np.ceil(n / rows))                                         # balance the columns


def finalize(fig, letters: dict | None = None):
    """Run the layout once, freeze it, then place panel letters at the left of each panel's labels.

    Letters are 8 pt bold lowercase and share one baseline per row of panels.
    """
    if letters:
        # reserve one line of panel-label type above each lettered panel, so the
        # layout engine keeps the letters inside the canvas
        for ax, letter in letters.items():
            ax.set_title(letter, fontsize=_J.panel_pt, fontweight="bold", loc="left", pad=2.0, alpha=0.0)
    fig.canvas.draw()
    fig.set_layout_engine("none")
    if letters:
        r = fig.canvas.get_renderer()
        inv = fig.transFigure.inverted()
        for ax, letter in letters.items():
            tb = ax.get_tightbbox(r)
            x0 = inv.transform((tb.x0, tb.y0))[0]
            ref = ax._left_title.get_window_extent(r)          # the reserved line above the panel
            y0 = inv.transform((ref.x0, ref.y0))[1]
            ax._left_title.set_text("")
            fig.text(max(x0, 0.002), y0, letter, fontsize=_J.panel_pt, fontweight="bold",
                     va="bottom", ha="left", gid="panel-label")
        fig.canvas.draw()
    return fig


def save(fig, stem, formats=("pdf", "svg", "png")) -> list[Path]:
    """Save at the figure's exact size (no tight bounding box)."""
    from . import CREDIT, __author__
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    if fig.get_layout_engine() is not None:
        finalize(fig)
    out = []
    for f in formats:
        p = stem.with_suffix("." + f)
        meta = {"Creator": CREDIT}
        if f == "pdf":
            meta["Author"] = __author__
        fig.savefig(p, format=f, metadata=meta)
        out.append(p)
    plt.close(fig)
    return out


# ---------------------------------------------------------------- panels

def voltage_capacity(tab, seg, s, cycles, ax=None, width=None, palette="blues", ocv_marker=False, journal="nature"):
    """Potential against capacity for the selected cycles (1-based)."""
    apply_style(journal)
    fig, ax = _new(ax, width or col_width("single", journal), 0.86)
    sel = _selected_pairs(seg, cycles)
    colors = cycle_colors(len(sel), palette)
    xmax = 0.0
    for color, (c, p) in zip(colors, sel):
        first = True
        for br in (p.charge, p.discharge):
            if br is None:
                continue
            q = capacity_basis(cumulative_charge(tab, seg, br, s.use_instrument_dq), s)
            xmax = max(xmax, float(q[-1]))
            ax.plot(q, tab.e[br.rows], color=color, lw=1.0, solid_capstyle="round", solid_joinstyle="round",
                    zorder=3, label=f"Cycle {c}" if first else None)
            first = False
    if ocv_marker and sel:
        first = sel[0][1].charge or sel[0][1].discharge
        if first is not None and first.start > 0 and tab.mode is not None and tab.mode[first.start - 1] == 3:
            ax.plot(0, tab.e[first.start - 1], "o", markersize=4.0, markerfacecolor="white", markeredgecolor=GREEN,
                    markeredgewidth=0.9, zorder=4, label="OCV")
    box(ax, capacity_label(s), potential_label(tab, s))
    ax.set_xlim(-0.03 * xmax if xmax > 0 else -1, xmax * 1.05 if xmax > 0 else 1)
    ax.margins(y=0.04)
    ax.autoscale_view()
    n = len(sel) + (1 if ocv_marker else 0)
    if n:
        ncol = _ncol(n, ax, f"Cycle {max(c for c, _ in sel)}" if sel else "Cycle 1")
        legend_band(ax, n, ncol, "top")
        ax.legend(loc="upper left", ncol=ncol)
    return fig


def capacity_efficiency(cycles, s, ax=None, width=None, ce_range="auto", show_charge=True, journal="nature"):
    """Discharge (filled) and charge (open) capacity with coulombic efficiency on the right axis."""
    apply_style(journal)
    fig, ax = _new(ax, width or col_width("single", journal), 0.80)
    rows = [c for c in cycles if c.complete]
    n = np.array([c.cycle for c in rows])
    qd = np.array([_nan(cycle_capacity(c, "discharge", s)) for c in rows], float)
    qc = np.array([_nan(cycle_capacity(c, "charge", s)) for c in rows], float)
    ce = np.array([(np.nan if c.coulombic_efficiency_pct is None else c.coulombic_efficiency_pct) for c in rows], float)
    ms = 3.2 if len(n) <= 60 else (2.5 if len(n) <= 200 else 1.8)
    if show_charge:
        ax.plot(n, qc, "o", color=BLUE, markerfacecolor="white", markeredgewidth=0.7, markersize=ms,
                label="Charge", zorder=3, linestyle="none")
    ax.plot(n, qd, "o", color=BLUE, markeredgewidth=0, markersize=ms, label="Discharge", zorder=4, linestyle="none")
    both = np.concatenate([qd, qc])
    top = float(np.nanmax(both)) if np.isfinite(both).any() else 1.0
    ax.set_ylim(0, top * 1.42)
    box(ax, "Cycle number", capacity_label(s))
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, steps=[1, 2, 5, 10], nbins=6))
    ax.set_xlim(0, (n.max() + max(1, 0.02 * n.max())) if n.size else 2)
    ax2 = ax.twinx()
    ax2.plot(n, ce, "^", color=BLACK, markeredgewidth=0, markersize=ms * 1.05,
             label="Coulombic efficiency" if np.isfinite(ce).any() else "_nolegend_",     # none given: no entry
             zorder=3, linestyle="none")
    ax2.set_ylim(*ce_limits(ce, ce_range))
    ax2.set_ylabel("Coulombic efficiency (%)")
    ax2.yaxis.set_minor_locator(AutoMinorLocator(2))
    ax2.tick_params(which="both", direction="in")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    place_legend(ax, h1 + h2, l1 + l2, ("lower right", "lower left", "center right", "center left", "upper center"),
                 axes=[ax, ax2], handletextpad=0.3, borderaxespad=0.6)
    return fig


def dqde(tab, seg, s, cycles, ax=None, width=None, bin_mV=10.0, palette="blues", orientation="vertical", units="au",
         journal="nature", legend=True):
    """Differential capacity. Vertical: potential on the y axis, dQ/dE on x, discharge left, charge right.

    units="au" normalises all plotted curves by their common maximum |dQ/dE| (axis label a.u.);
    units="real" keeps mAh/V per gram or per cm2. The CSV export always keeps real units.
    """
    from .differential import curve
    apply_style(journal)
    fig, ax = _new(ax, width or col_width("single", journal), 0.86)
    sel = _selected_pairs(seg, cycles)
    colors = cycle_colors(len(sel), palette)
    sym = potential_symbol(s)
    curves = []
    for color, (c, p) in zip(colors, sel):
        for br in (p.charge, p.discharge):
            if br is None:
                continue
            cv = curve(tab, seg, s, br, c, bin_mV)
            if cv is not None:
                curves.append((color, c, br, cv))
    scale = max((float(np.nanmax(np.abs(cv.dqdv))) for _, _, _, cv in curves), default=1.0) or 1.0
    norm = scale if units == "au" else 1.0
    seen = set()
    for color, c, br, cv in curves:
        lab = f"Cycle {c}" if c not in seen else None
        seen.add(c)
        if orientation == "vertical":
            ax.plot(cv.dqdv / norm, cv.voltage_V, color=color, lw=0.9, zorder=3, label=lab)
        else:
            ax.plot(cv.voltage_V, cv.dqdv / norm, color=color, lw=0.9, zorder=3, label=lab)
    if units == "au":
        unit = "a.u."
    else:
        unit = {"specific": "mAh g$^{−1}$ V$^{−1}$", "areal": "mAh cm$^{−2}$ V$^{−1}$",
                "absolute": "mAh V$^{−1}$"}[basis_of(s)]
    lab = f"d$\\mathit{{Q}}$/d$\\mathit{{{sym}}}$ ({unit})"
    n = len(sel)
    ncol = _ncol(n, ax, f"Cycle {max(c for c, _ in sel)}" if sel else "Cycle 1")
    if orientation == "vertical":
        box(ax, lab, potential_label(tab, s))
        lim = (scale / norm) * 1.12
        ax.set_xlim(-lim, lim)
        ax.margins(y=0.03)
        ax.autoscale_view(scalex=False)
        lo, hi = ax.get_ylim()
        data_lo = lo
        band = 0.15
        ax.set_ylim(lo, hi + (hi - lo) * band / (1 - band))
        y_arrow = 1 - band * 0.42
        for x0, x1, text, xt in ((0.45, 0.06, "Discharge", 0.255), (0.55, 0.94, "Charge", 0.745)):
            ax.annotate("", xy=(x1, y_arrow), xytext=(x0, y_arrow), xycoords="axes fraction",
                        arrowprops=dict(arrowstyle="-|>,head_length=0.35,head_width=0.18", lw=0.6, color=BLACK,
                                        shrinkA=0, shrinkB=0))
            ax.text(xt, y_arrow + 0.012, text, transform=ax.transAxes, ha="center", va="bottom",
                    fontsize=_J.small_pt)
        if n and legend:
            legend_band(ax, n, ncol, "bottom", title=True)
        top = ax.get_ylim()[1]
        zero, = ax.plot([0, 0], [data_lo, top], color=GREY, linewidth=0.5, zorder=1)   # from the data up, not
        zero.set_gid("zero")                                                          # through the legend band
        ax.set_ylim(ax.get_ylim())
        if n and legend:
            h, l_ = ax.get_legend_handles_labels()
            place_legend(ax, h, l_, ("lower left", "lower right"), ncol=ncol, title=f"{bin_mV:g} mV bins",
                         alignment="left")
        elif n:
            _corner_note(ax, f"{bin_mV:g} mV bins")
    else:
        box(ax, potential_label(tab, s), lab)
        ax.axhline(0, color=GREY, linewidth=0.5, zorder=1)
        if n:
            legend_band(ax, n, ncol, "top", title=True)
            ax.legend(loc="upper left", ncol=ncol, title=f"{bin_mV:g} mV bins", alignment="left")
    return fig


def average_voltage(cycles, s, ax=None, width=None, journal="nature"):
    """Average charge and discharge voltage (energy / charge: charge-weighted mean) and their difference against cycle number."""
    apply_style(journal)
    fig, ax = _new(ax, width or col_width("single", journal), 0.80)
    rows = [c for c in cycles if c.complete and c.average_charge_voltage_V is not None
            and c.average_discharge_voltage_V is not None]
    n = np.array([c.cycle for c in rows])
    vc = np.array([c.average_charge_voltage_V for c in rows], float)
    vd = np.array([c.average_discharge_voltage_V for c in rows], float)
    ms = 3.2 if len(n) <= 60 else (2.5 if len(n) <= 200 else 1.8)
    ax.plot(n, vc, "^", color=VERMILION, markeredgewidth=0, markersize=ms, label="Charge", zorder=3, linestyle="none")
    ax.plot(n, vd, "v", color=BLUE, markeredgewidth=0, markersize=ms, label="Discharge", zorder=3, linestyle="none")
    sym = "V" if s.terminal_voltage else "E"
    what = "cell voltage" if s.terminal_voltage else "potential"
    ref = f" vs. {reference_label(s.reference)}" if (not s.terminal_voltage and getattr(s, "reference", None)) else ""
    box(ax, "Cycle number", f"Average {what}{ref} (V)")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, steps=[1, 2, 5, 10], nbins=6))
    ax.set_xlim(0, (n.max() + max(1, 0.02 * n.max())) if n.size else 2)
    if n.size:
        lo_v = float(min(np.nanmin(vc), np.nanmin(vd))); hi_v = float(max(np.nanmax(vc), np.nanmax(vd)))
        span = max(hi_v - lo_v, 0.01)
        ax.set_ylim(lo_v - 0.10 * span, hi_v + 0.10 * span)
    ax2 = ax.twinx()
    # the cycle's own hysteresis, not vc - vd: it is withheld for a pair with a step that ended at once
    hyst = np.array([np.nan if c.average_voltage_hysteresis_V is None else c.average_voltage_hysteresis_V
                     for c in rows], float)
    ax2.plot(n, hyst, "s", color=BLACK, markeredgewidth=0, markersize=ms * 0.85,
             label=(f"Hysteresis, $\\Delta\\mathit{{{sym}}}$" if np.isfinite(hyst).any() else "_nolegend_"),
             zorder=3, linestyle="none")
    ax2.set_ylabel(f"Hysteresis, $\\Delta\\mathit{{{sym}}}$ (V)")
    if np.isfinite(hyst).any():
        h_lo = min(0.0, float(np.nanmin(hyst)))
        h_rng = max(float(np.nanmax(hyst)) - h_lo, 0.05 / 2.6)
        ax2.set_ylim(h_lo - 0.04 * h_rng, h_lo + h_rng * 2.6)        # hysteresis in the lower part
    ax2.yaxis.set_minor_locator(AutoMinorLocator(2))
    ax2.tick_params(which="both", direction="in")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    if n.size:
        # the band between the two voltage series and the hysteresis below is empty by construction
        legend_band(ax, 4, 1, "top")
    place_legend(ax, h1 + h2, l1 + l2, ("upper right", "upper left", "center right", "lower right"),
                 axes=[ax, ax2], title="Average", alignment="right")
    return fig


def overview_time(tab, s, width=None, journal="nature"):
    """Potential and current against time for the whole file."""
    apply_style(journal)
    w = width or col_width("double", journal)
    fig, (a1, a2) = plt.subplots(2, 1, sharex=True, figsize=(w, w * 0.42), layout="constrained")
    th = tab.t / 3600.0
    a1.plot(th, tab.e, color=BLUE, linewidth=0.6)
    a2.plot(th, tab.i * 1e3, color=VERMILION, linewidth=0.6)
    a2.axhline(0, color=GREY, linewidth=0.45, zorder=0)
    box(a1, None, potential_label(tab, s))
    box(a2, "Time (h)", "Current (mA)")
    a1.tick_params(labelbottom=False)
    a1.set_xlim(th[0], th[-1]) if len(th) else None
    fig.align_ylabels([a1, a2])
    fig.get_layout_engine().set(hspace=0.0, h_pad=1.5 / 72)
    return fig


def summary_figure(tab, seg, analysis, s, cycles, bin_mV=10.0, palette="blues", ce_range="auto", dqde_units="au",
                   journal="nature"):
    """Double-column, four-panel figure: a potential-capacity, b capacity and efficiency, c dQ/dE, d average voltages."""
    apply_style(journal)
    w = col_width("double", journal)
    fig, axes = plt.subplots(2, 2, figsize=(w, w * 0.80), layout="constrained")
    fig.get_layout_engine().set(wspace=0.08, hspace=0.06)
    (a, b), (c, d) = axes
    voltage_capacity(tab, seg, s, cycles, ax=a, palette=palette, journal=journal)
    capacity_efficiency(analysis.cycles, s, ax=b, ce_range=ce_range, journal=journal)
    # colours are those of panel a, so c carries no second cycle legend
    dqde(tab, seg, s, cycles, ax=c, bin_mV=bin_mV, palette=palette, units=dqde_units, journal=journal, legend=False)
    average_voltage(analysis.cycles, s, ax=d, journal=journal)
    return finalize(fig, {a: "a", b: "b", c: "c", d: "d"})


# ---------------------------------------------------------------- dQ/dE evolution

# Sequential, perceptually uniform (CIELAB lightness falls monotonically from 98 to 0): zero dQ/dE is the
# paper-light end, so the plateaus read as ink; legible in greyscale and for colour-vision deficiencies.
MAP_CMAP = "magma_r"
NOT_MEASURED = "#D9D9D9"          # cells outside a branch's measured potential range, or a cycle without it
SURFACE_MAX_ROWS = 120            # cycles drawn in the 3D surface; above this, every k-th cycle (stated on the figure)


def _dqde_unit(s, units):
    if units == "au":
        return "a.u."
    return {"specific": "mAh g$^{−1}$ V$^{−1}$", "areal": "mAh cm$^{−2}$ V$^{−1}$", "absolute": "mAh V$^{−1}$"}[basis_of(s)]


def _evolution_grids(curves, common_rows=False):
    """The charge and discharge grids, each filled to contiguous cycles; with common_rows, both to the cycles of
    either, so panels that share a cycle axis show the same rows (a direction without a curve in the first or
    last cycle no longer leaves the other panel's rows outside the shared range)."""
    from .differential import evolution_grid
    raw = [g for g in (evolution_grid(curves, d) for d in ("charge", "discharge")) if g is not None]
    if not raw:
        return []
    if not common_rows:
        return [g.filled() for g in raw]
    lo = min(int(g.cycles.min()) for g in raw)
    hi = max(int(g.cycles.max()) for g in raw)
    return [g.filled(lo, hi) for g in raw]


def _grid_scale(grids, units):
    m = max((float(np.nanmax(np.abs(g.dqde))) for g in grids if np.isfinite(g.dqde).any()), default=1.0) or 1.0
    return m if units == "au" else 1.0, m


def _shared_potential_range(grids):
    """One potential range for every panel of an evolution figure (the union of the directions' grids, with
    half a node of margin at each end), so a charge peak and its discharge counterpart line up by eye and
    the two panels read on one scale."""
    if not grids:
        return None
    lo = min(float(g.voltage_V[0]) - g.bin_mV / 2000.0 for g in grids)
    hi = max(float(g.voltage_V[-1]) + g.bin_mV / 2000.0 for g in grids)
    return lo, hi


def fig6_dqde_map(curves, s, tab=None, units="au", journal="nature", width=None):
    """Colour map of |dQ/dE| over potential (horizontal) and cycle number (vertical): charge (a) and discharge (b).

    curves: (cycle, DqdvCurve) items, as Run.dqde_curves returns them. The values are those of
    differential.evolution_grid: each curve resampled onto one grid of nodes at multiples of the bin width.
    Each row is drawn at its cycle number, one cycle high; cycles without a curve stay grey. Both panels
    share one colour scale, so their intensities compare. Magnitudes are drawn: the discharge sign
    (negative) is kept in dqde_map.csv.
    """
    from matplotlib.colors import Normalize
    apply_style(journal)
    grids = _evolution_grids(curves, common_rows=True)          # the panels share one cycle axis
    w = width or col_width("one_half", journal)
    n = max(len(grids), 1)
    fig, axes = plt.subplots(1, n, figsize=(w, w * 0.50), layout="constrained", sharex=True, sharey=True,
                             squeeze=False)
    axes = list(axes[0])
    xr = _shared_potential_range(grids)
    norm_by, top = _grid_scale(grids, units)
    norm = Normalize(0.0, top / norm_by)
    cmap = plt.get_cmap(MAP_CMAP).with_extremes(bad=NOT_MEASURED)
    sym = potential_symbol(s)
    xlab = potential_label(tab, s)
    mesh = None
    for ax, g in zip(axes, grids):
        step = g.bin_mV / 1000.0
        xe = np.concatenate((g.voltage_V - step / 2, [g.voltage_V[-1] + step / 2]))
        ye = np.concatenate((g.cycles - 0.5, [g.cycles[-1] + 0.5]))
        z = np.ma.masked_invalid(np.abs(g.dqde) / norm_by)
        mesh = ax.pcolormesh(xe, ye, z, cmap=cmap, norm=norm, shading="flat", rasterized=True, linewidth=0)
        mesh.set_gid("dqde-map")
        ax.set_facecolor(NOT_MEASURED)       # beyond this direction's measured range: not measured, as NaN cells
        ax.set_xlim(*xr)
        ax.set_ylim(ye[0], ye[-1])
        box(ax, xlab, "Cycle number" if ax is axes[0] else None)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6, min_n_ticks=1 if len(g.cycles) == 1 else 2))
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.set_title(g.direction.capitalize(), fontsize=_J.text_pt, pad=3.0)
        if ax is not axes[0]:
            ax.tick_params(labelleft=False)
    if mesh is not None:
        cb = fig.colorbar(mesh, ax=axes, location="right", fraction=0.05, pad=0.02, aspect=22)
        cb.set_label(f"|d$\\mathit{{Q}}$/d$\\mathit{{{sym}}}$| ({_dqde_unit(s, units)})")
        cb.ax.tick_params(direction="in", which="both")
        cb.outline.set_linewidth(0.6)
    if not grids:
        _no_curve(axes[0])
    letters = {ax: chr(ord("a") + k) for k, ax in enumerate(axes)} if len(axes) > 1 else None
    return finalize(fig, letters)


def _ordinal(k: int) -> str:
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


NO_CURVE = "No dQ/dE curve: no branch has four points outside constant-voltage stages"


def _no_curve(ax):
    ax.set_axis_off()
    ax.text(0.5, 0.5, NO_CURVE, transform=ax.transAxes, ha="center", va="center", fontsize=_J.small_pt, wrap=True)


def fig7_dqde_surface(curves, s, tab=None, units="au", journal="nature", width=None, elev=26.0, azim=-58.0):
    """3D surfaces of |dQ/dE| over potential and cycle number (the depth axis): charge (a) and discharge (b).

    The same grid and the same colour scale as fig6_dqde_map (differential.evolution_grid), height and
    colour both |dQ/dE|. Charge and discharge are separate panels: drawn in one box, the flat zero region of
    one surface hides the peaks of the other. Every potential node is drawn; above SURFACE_MAX_ROWS cycles,
    every k-th cycle is drawn and the figure says so. The view (elevation 26 degrees, azimuth -58 degrees)
    looks along the cycle axis from the low-potential side, so a peak that persists reads as a ridge running
    into the page and a peak that appears or disappears as a ridge that starts or ends.
    """
    from matplotlib.colors import Normalize
    apply_style(journal)
    grids = _evolution_grids(curves)
    w = width or col_width("double", journal)
    n = max(len(grids), 1)
    fig = plt.figure(figsize=(w, w * 0.28), layout="constrained")
    fig.get_layout_engine().set(w_pad=0.5 / 72, h_pad=0.5 / 72, wspace=0.0)
    axes = [fig.add_subplot(1, n, k + 1, projection="3d") for k in range(n)]
    norm_by, top = _grid_scale(grids, units)
    lim = top / norm_by
    norm = Normalize(0.0, lim)
    cmap = plt.get_cmap(MAP_CMAP)
    sym = potential_symbol(s)
    zlab = f"|d$\\mathit{{Q}}$/d$\\mathit{{{sym}}}$| ({_dqde_unit(s, units)})"
    note = None
    xr = _shared_potential_range(grids)
    for ax, g in zip(axes, grids):
        rows = np.arange(len(g.cycles))
        if len(rows) > SURFACE_MAX_ROWS:
            k = int(np.ceil(len(rows) / SURFACE_MAX_ROWS))
            rows = rows[::k]
            note = f"Every {_ordinal(k)} cycle drawn ({len(g.cycles)} cycles)"
        Z = np.abs(g.dqde[rows]) / norm_by
        if len(rows) >= 2:
            X, Y = np.meshgrid(g.voltage_V, g.cycles[rows].astype(float))
            surf = ax.plot_surface(X, Y, Z, cmap=cmap, norm=norm, rcount=len(rows), ccount=len(g.voltage_V),
                                   linewidth=0, antialiased=False, rasterized=True)
            surf.set_gid(f"dqde-surface-{g.direction}")
        else:                          # one cycle of this direction: a surface needs two, so its curve is drawn
            ax.plot(g.voltage_V, np.full(len(g.voltage_V), float(g.cycles[0])), Z[0], color=BLACK, lw=0.8)
        ax.set_xlim(*xr)                     # both panels on one potential scale, as in figure 6
        ax.set_ylim(float(g.cycles[0]) - 0.5, float(g.cycles[-1]) + 0.5)
        ax.set_zlim(0.0, lim * 1.02)
        ax.view_init(elev=elev, azim=azim)
        ax.set_box_aspect((1.5, 1.0, 0.6), zoom=0.98)
        ax.set_xlabel(potential_label(tab, s), labelpad=6.0)
        ax.set_ylabel("Cycle number", labelpad=5.0)
        if ax is axes[0]:                    # the second panel's height is named by the colour bar beside it
            ax.set_zlabel(zlab, labelpad=1.0)
        ax.set_title(g.direction.capitalize(), fontsize=_J.text_pt)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
        # one cycle: MaxNLocator drops integer=True when fewer than two integers fit and labels 1.50, 1.75...
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=4, min_n_ticks=1 if len(g.cycles) == 1 else 2))
        ax.zaxis.set_major_locator(MaxNLocator(nbins=3))
        ax.tick_params(axis="both", which="major", pad=-1.0)
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            axis.set_minor_locator(matplotlib.ticker.NullLocator())
            axis.set_pane_color((1, 1, 1, 0))
            axis.pane.set_edgecolor("0.55")
            axis.pane.set_linewidth(0.5)
            axis._axinfo["grid"].update(linewidth=0.4, color="0.86")
            axis._axinfo["tick"].update(linewidth={True: 0.6, False: 0.45}, inward_factor=0.0, outward_factor=0.2)
            axis._axinfo["axisline"]["linewidth"] = 0.6
    if not grids:
        _no_curve(axes[0])
    from matplotlib.cm import ScalarMappable
    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=axes, location="right", fraction=0.03, pad=0.07,
                      aspect=18, shrink=0.62)
    cb.set_label(zlab)
    cb.ax.tick_params(direction="in", which="both")
    cb.outline.set_linewidth(0.6)
    if note:
        fig.text(0.005, 0.005, note, fontsize=_J.small_pt, ha="left", va="bottom", gid="surface-note")
    letters = {ax: chr(ord("a") + k) for k, ax in enumerate(axes)} if len(axes) > 1 else {}
    return _frame_3d(fig, axes, cb.ax, letters)


def _frame_3d(fig, axes, cbar_ax, letters):
    """Freeze the layout of a figure of 3D panels, then put each title just above its drawn box and centre the
    drawing vertically.

    A 3D box is projected at the centre of its axes area and its axis titles hang below it, outside what the
    layout engine reserves, so the box sits low with an empty band above. After the layout is frozen the
    titles are moved down to the top of the box (the highest pane), the panels and the colour bar are moved
    together so the drawing is centred on the canvas, and the panel letters are placed level with the titles,
    at the left of each panel's labels."""
    fig.canvas.draw()
    fig.set_layout_engine("none")
    r = fig.canvas.get_renderer()
    for ax in axes:
        top = max(a.pane.get_window_extent(r).y1 for a in (ax.xaxis, ax.yaxis, ax.zaxis))
        ax.set_title(ax.get_title(), fontsize=_J.text_pt, y=(top - ax.bbox.y0) / ax.bbox.height, pad=3.0)
    fig.canvas.draw()
    union = mtransforms.Bbox.union([ax.get_tightbbox(r) for ax in axes])
    H = fig.bbox.height
    dy = ((H - union.y1) - (union.y0 - fig.bbox.y0)) / 2.0 / H
    for a in list(axes) + [cbar_ax]:
        pos = a.get_position()
        a.set_position([pos.x0, pos.y0 + dy, pos.width, pos.height])
    fig.canvas.draw()
    inv = fig.transFigure.inverted()
    for ax, letter in letters.items():
        tb = ax.get_tightbbox(r)
        x0 = inv.transform((tb.x0, tb.y0))[0]
        y0 = inv.transform((0, ax.title.get_window_extent(r).y0))[1]
        fig.text(max(x0, 0.002), y0, letter, fontsize=_J.panel_pt, fontweight="bold", va="bottom", ha="left",
                 gid="panel-label")
    fig.canvas.draw()
    return fig


def panel_label(ax, letter, dx=None, dy=None):
    """Kept for callers of 0.5.0; new figures use finalize(fig, letters)."""
    ax.text(-0.2 if dx is None else dx, 1.02 if dy is None else dy, letter, transform=ax.transAxes,
            fontsize=_J.panel_pt, fontweight="bold", va="bottom", ha="left", gid="panel-label")


# ---------------------------------------------------------------- checks

@dataclass
class Check:
    name: str
    status: str          # "pass", "warn", "fail", or "skip" (not evaluated; the detail says why)
    detail: str


def _luminance(rgb):
    def ch(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(c1, c2="#FFFFFF") -> float:
    l1, l2 = _luminance(to_rgb(c1)), _luminance(to_rgb(c2))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def font_used() -> str:
    path = font_manager.findfont(font_manager.FontProperties(family=plt.rcParams["font.sans-serif"]))
    try:
        return font_manager.get_font(path).family_name
    except Exception:
        return Path(path).stem


def _segments_through(d, box) -> int:
    """Line segments that cross a rectangle (Liang-Barsky), so a straight stretch drawn under a
    legend between two measured points is caught too."""
    x0, y0 = d[:-1, 0], d[:-1, 1]
    dx, dy = d[1:, 0] - x0, d[1:, 1] - y0
    t0 = np.zeros_like(x0); t1 = np.ones_like(x0)
    ok = np.ones_like(x0, dtype=bool)
    for p, q in ((-dx, x0 - box.x0), (dx, box.x1 - x0), (-dy, y0 - box.y0), (dy, box.y1 - y0)):
        par = p == 0
        ok &= ~(par & (q < 0))
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(par, 0.0, q / np.where(par, 1.0, p))
        t0 = np.where(~par & (p < 0), np.maximum(t0, r), t0)
        t1 = np.where(~par & (p > 0), np.minimum(t1, r), t1)
    ok &= t0 <= t1
    return int(np.sum(ok))


def is_3d(ax) -> bool:
    return getattr(ax, "name", "") == "3d"


def _axes_axes(ax):
    return (ax.xaxis, ax.yaxis, ax.zaxis) if is_3d(ax) else (ax.xaxis, ax.yaxis)


def _ticks_in_view(axis):
    """The ticks a drawn 3D axis shows, read without moving them: Axis._update_ticks() would put the labels
    back at 2D positions that a 3D axis never draws them at, so their extents would be wrong."""
    lo, hi = sorted(axis.get_view_interval())
    eps = 1e-10 * max(abs(hi - lo), 1e-300)
    out = []
    for locs, ticks in ((axis.get_majorticklocs(), axis.get_major_ticks()),
                        (axis.get_minorticklocs(), axis.get_minor_ticks())):
        for loc, t in zip(locs, ticks):
            if lo - eps <= loc <= hi + eps:
                out.append(t)
    return out


def _drawn_texts(fig):
    """Every text the renderer actually draws: tick labels only for ticks inside the view."""
    tick_ids, out = set(), []
    for ax in fig.axes:
        for axis in _axes_axes(ax):
            for t in axis.get_major_ticks() + axis.get_minor_ticks():
                tick_ids.update((id(t.label1), id(t.label2)))
            if not (ax.get_visible() and axis.get_visible()):
                continue
            try:
                drawn = _ticks_in_view(axis) if is_3d(ax) else axis._update_ticks()
            except Exception:
                drawn = []
            for t in drawn:
                for lab in (t.label1, t.label2):
                    if lab.get_visible() and lab.get_text().strip():
                        out.append(lab)
    for t in fig.findobj(Text):
        if id(t) not in tick_ids and t.get_visible() and t.get_text().strip() and (t.get_alpha() is None or t.get_alpha() > 0):
            out.append(t)
    return out


def _smallest_glyph(t) -> float | None:
    """The smallest glyph of a text drawn with mathtext, in pt, as the renderer lays it out."""
    s = t.get_text()
    if s.count("$") < 2 or t.get_usetex():
        return None
    try:
        from matplotlib.mathtext import MathTextParser
        vp = MathTextParser("path").parse(s, dpi=72, prop=t.get_fontproperties())
        return min((float(g[1]) for g in vp.glyphs), default=None)
    except Exception:
        return None


def _artist_skip(a) -> bool:
    return (not a.get_visible()) or a.get_gid() == "guide"


def _data_in_box(ax, bb) -> int:
    """How many data elements of one axes fall inside a display-space box: points and segments of lines,
    scatter points, and the outlines or areas of bands, bars and error bars."""
    from matplotlib.collections import PathCollection
    n = 0
    for ln in ax.get_lines():
        if _artist_skip(ln):
            continue
        xy = np.column_stack(ln.get_data()).astype(float)
        xy = xy[np.all(np.isfinite(xy), axis=1)]
        if not len(xy):
            continue
        d = ln.get_transform().transform(xy)
        if ln.get_marker() not in ("None", "none", "", None, " "):
            n += int(np.sum((d[:, 0] >= bb.x0) & (d[:, 0] <= bb.x1) & (d[:, 1] >= bb.y0) & (d[:, 1] <= bb.y1)))
        if ln.get_linestyle() not in ("None", "none", "", " ") and len(d) > 1:
            n += _segments_through(d, bb)
            n += int(np.sum((d[:, 0] >= bb.x0) & (d[:, 0] <= bb.x1) & (d[:, 1] >= bb.y0) & (d[:, 1] <= bb.y1)))
    for coll in ax.collections:
        if _artist_skip(coll):
            continue
        offs = np.asarray(coll.get_offsets(), float)
        if isinstance(coll, PathCollection) and offs.size:
            d = coll.get_offset_transform().transform(offs.reshape(-1, 2))
            d = d[np.all(np.isfinite(d), axis=1)]
            n += int(np.sum((d[:, 0] >= bb.x0) & (d[:, 0] <= bb.x1) & (d[:, 1] >= bb.y0) & (d[:, 1] <= bb.y1)))
            continue
        fc = coll.get_facecolor()
        filled = len(fc) > 0 and float(np.max(np.asarray(fc)[:, 3])) > 0
        tr = coll.get_transform()
        for path in coll.get_paths():
            if path.transformed(tr).intersects_bbox(bb, filled=filled):
                n += 1
    for patch in ax.patches:
        if _artist_skip(patch):
            continue
        if patch.get_path().transformed(patch.get_transform()).intersects_bbox(bb, filled=patch.get_fill()):
            n += 1
    return n


def _data_outside(ax, tol=0.75) -> int:
    """Plotted points of lines and scatter series that lie beyond the axes (and so are not drawn)."""
    from matplotlib.collections import PathCollection
    box = ax.bbox
    n = 0

    def count(d):
        d = d[np.all(np.isfinite(d), axis=1)]
        return int(np.sum((d[:, 0] < box.x0 - tol) | (d[:, 0] > box.x1 + tol) |
                          (d[:, 1] < box.y0 - tol) | (d[:, 1] > box.y1 + tol)))
    for ln in ax.get_lines():
        if _artist_skip(ln) or not ln.get_clip_on():
            continue
        xy = np.column_stack(ln.get_data()).astype(float)
        if len(xy):
            n += count(ln.get_transform().transform(xy))
    for coll in ax.collections:
        if _artist_skip(coll):
            continue
        if isinstance(coll, QuadMesh) and coll.get_clip_on():          # colour maps: every cell corner
            xy = np.asarray(coll.get_coordinates(), float).reshape(-1, 2)
            n += count(coll.get_transform().transform(xy))
            continue
        if not isinstance(coll, PathCollection):
            continue
        offs = np.asarray(coll.get_offsets(), float)
        if offs.size:
            n += count(coll.get_offset_transform().transform(offs.reshape(-1, 2)))
    return n


def _data_outside_3d(ax) -> str | None:
    """A 3D axes does not clip: data beyond its limits are drawn outside the box. Compares the data limits
    the plotting calls recorded with the x, y and z limits. None when the data limits cannot be read."""
    try:
        lims = {"x": (ax.xy_dataLim.intervalx, ax.get_xlim()), "y": (ax.xy_dataLim.intervaly, ax.get_ylim()),
                "z": (ax.zz_dataLim.intervalx, ax.get_zlim())}
    except AttributeError:
        return None
    bad = []
    for name, (data, view) in lims.items():
        d0, d1 = sorted(map(float, data)); v0, v1 = sorted(map(float, view))
        if not (np.isfinite(d0) and np.isfinite(d1)):
            continue
        tol = 1e-9 * max(abs(v1 - v0), 1e-300)
        if d0 < v0 - tol or d1 > v1 + tol:
            bad.append(f"{name} data {d0:.4g} to {d1:.4g} beyond the {name} limits {v0:.4g} to {v1:.4g}")
    return "; ".join(bad)


def lightness(rgb) -> np.ndarray:
    """CIELAB L* (D65) of sRGB colours, an (n, 3) or (n, 4) array in 0 to 1."""
    rgb = np.asarray(rgb, float)[:, :3]
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    y = lin @ np.array([0.2126, 0.7152, 0.0722])
    f = np.where(y > (6 / 29) ** 3, np.cbrt(y), y / (3 * (6 / 29) ** 2) + 4 / 29)
    return 116 * f - 16


def colour_order(cmap, norm, tol=0.5) -> tuple[bool, str]:
    """Whether a colour map's lightness orders its values: monotonic across a sequential scale, monotonic
    outwards from the centre on both sides of a diverging scale (one whose limits straddle zero)."""
    L = lightness(cmap(np.linspace(0.0, 1.0, 256)))
    name = getattr(cmap, "name", "colour map")
    vmin, vmax = getattr(norm, "vmin", None), getattr(norm, "vmax", None)
    if vmin is not None and vmax is not None and vmin < 0 < vmax:
        c = int(round(float(norm(0.0)) * 255))
        left, right = L[:c + 1][::-1], L[c:]
        dl, dr = np.diff(left), np.diff(right)
        ok = len(left) > 1 and len(right) > 1 and ((dl.max() <= tol and dr.max() <= tol) or
                                                   (dl.min() >= -tol and dr.min() >= -tol))
        return ok, (f"{name}, diverging: L* {L[0]:.0f} to {L[c]:.0f} at zero to {L[-1]:.0f}, "
                    + ("monotonic on each side" if ok else "not monotonic on each side"))
    d = np.diff(L)
    ok = d.max() <= tol or d.min() >= -tol
    return ok, f"{name}, sequential: L* {L[0]:.0f} to {L[-1]:.0f}, " + ("monotonic" if ok else "not monotonic")


def colour_maps(fig):
    """(descriptions, any unordered) for the colour-mapped artists of a figure (meshes, images, surfaces)."""
    seen, out, bad = set(), [], False
    for ax in fig.axes:
        for art in list(ax.collections) + list(ax.images):
            if not art.get_visible() or getattr(art, "get_array", None) is None or art.get_array() is None:
                continue
            cm, nm = art.get_cmap(), art.norm
            key = (getattr(cm, "name", id(cm)), getattr(nm, "vmin", None), getattr(nm, "vmax", None))
            if key in seen:
                continue
            seen.add(key)
            ok, text = colour_order(cm, nm)
            bad |= not ok
            out.append(text)
    return out, bad


def _text_polygon(t, bb) -> np.ndarray:
    """The four corners of a text's own rotated rectangle, in display pixels.

    get_window_extent gives the axis-aligned box around the rotated text; for a label drawn at an oblique
    angle (the axis titles of a 3D plot) that box is much larger than the glyphs and reports overlaps that
    are not there. The rotated rectangle (a by b at angle theta) is recovered from the box (W by H):
    W = a|cos| + b|sin|, H = a|sin| + b|cos|. At 0 and 90 degrees it is the box itself; near 45 degrees the
    system is singular and the box is kept (conservative)."""
    th = np.deg2rad(float(t.get_rotation() or 0.0) % 180.0)
    c, s = abs(np.cos(th)), abs(np.sin(th))
    W, H = bb.width, bb.height
    det = c * c - s * s
    cx, cy = (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2
    if abs(det) < 0.2:
        a, b, th = W, H, 0.0
    else:
        a, b = (c * W - s * H) / det, (c * H - s * W) / det
        if a <= 0 or b <= 0:
            a, b, th = W, H, 0.0
    u = np.array([np.cos(th), np.sin(th)]); v = np.array([-np.sin(th), np.cos(th)])
    return np.array([[cx, cy] + sx * a / 2 * u + sy * b / 2 * v for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))])


def _polygons_overlap(p, q, tol=1.0) -> bool:
    """Separating-axis test for two convex quadrilaterals: they overlap when their projections overlap by more
    than tol pixels on every edge normal. For two axis-aligned boxes this is the width-and-height test."""
    for poly in (p, q):
        for k in range(4):
            e = poly[(k + 1) % 4] - poly[k]
            n = np.array([-e[1], e[0]])
            ln = np.hypot(*n)
            if ln == 0:
                continue
            n = n / ln
            a, b = p @ n, q @ n
            if min(a.max(), b.max()) - max(a.min(), b.min()) <= tol:
                return False
    return True


def check_figure(fig, journal: str = "nature") -> list[Check]:
    """Verify a finished figure against the journal's rules. Never changes the figure."""
    j = JOURNALS[journal]
    out: list[Check] = []
    if fig.get_layout_engine() is not None:
        finalize(fig)
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    W, H = fig.get_size_inches() / MM
    fb = fig.bbox

    # size
    match = [k for k, v in j.widths_mm.items() if abs(v - W) < 0.05]
    out.append(Check("width", "pass" if match else "fail",
                     f"{W:.1f} mm" + (f" ({match[0].replace('_', ' ')} column)" if match
                                      else f"; {j.name} widths are " + ", ".join(f"{v:g}" for v in j.widths_mm.values()) + " mm")))
    out.append(Check("height", "pass" if H <= j.max_height_mm + 0.05 else "fail",
                     f"{H:.1f} mm (maximum {j.max_height_mm:g} mm)"))

    # text
    texts = _drawn_texts(fig)
    sizes, bad_size, scripts = [], [], []
    for t in texts:
        sz = float(t.get_fontsize())
        sizes.append(sz)
        if t.get_gid() == "panel-label":
            txt = t.get_text().strip().strip("()")
            if abs(sz - j.panel_pt) > 0.01 or t.get_fontweight() not in ("bold", 700):
                bad_size.append(f"panel label {t.get_text()!r} at {sz:g} pt")
            if j.panel_lowercase and not (len(txt) == 1 and txt.islower()):
                bad_size.append(f"panel label {t.get_text()!r} is not one lowercase letter")
            continue
        if not (j.min_pt - 0.01 <= sz <= j.max_pt + 0.01):
            bad_size.append(f"{t.get_text()[:24]!r} at {sz:g} pt")
        g = _smallest_glyph(t)
        if g is not None and g < sz - 0.01:            # a sub- or superscript
            scripts.append(g)
            if g < j.script_min_pt - 0.01:
                bad_size.append(f"sub- or superscript in {t.get_text()[:24]!r} at {g:.2f} pt "
                                f"(minimum {j.script_min_pt:g})")
    plain = [s_ for s_, t in zip(sizes, texts) if t.get_gid() != "panel-label"]
    detail = (f"{min(plain):g} to {max(plain):g} pt (allowed {j.min_pt:g} to {j.max_pt:g})"
              + (f"; sub- and superscripts at least {min(scripts):.2f} pt (minimum {j.script_min_pt:g})" if scripts else "")
              + f"; panel labels {j.panel_pt:g} pt bold" + (" lowercase" if j.panel_lowercase else "")) if plain else "no text"
    out.append(Check("type size", "fail" if bad_size else "pass", "; ".join(bad_size[:4]) if bad_size else detail))

    boxes = []
    for t in texts:
        try:
            bb = t.get_window_extent(r)
        except Exception:
            continue
        if bb.width > 0 and bb.height > 0:
            boxes.append((t, bb))
    clipped = [t.get_text()[:24] for t, bb in boxes
               if bb.x0 < fb.x0 - 0.5 or bb.y0 < fb.y0 - 0.5 or bb.x1 > fb.x1 + 0.5 or bb.y1 > fb.y1 + 0.5]
    out.append(Check("text inside the figure", "fail" if clipped else "pass",
                     ("cut at the edge: " + ", ".join(repr(c) for c in clipped[:4])) if clipped else "all text within the canvas"))

    overlaps = []
    polys = [_text_polygon(t, bb) for t, bb in boxes]
    for k in range(len(boxes)):
        for m in range(k + 1, len(boxes)):
            (t1, b1), (t2, b2) = boxes[k], boxes[m]
            w = min(b1.x1, b2.x1) - max(b1.x0, b2.x0)
            h = min(b1.y1, b2.y1) - max(b1.y0, b2.y0)
            if w > 1.0 and h > 1.0 and _polygons_overlap(polys[k], polys[m], 1.0):
                overlaps.append(f"{t1.get_text()[:18]!r} / {t2.get_text()[:18]!r}")
    out.append(Check("no overlapping text", "fail" if overlaps else "pass",
                     "; ".join(overlaps[:4]) if overlaps else "no two labels touch"))

    def siblings(ax):
        return [a for a in fig.axes if a.bbox.bounds == ax.bbox.bounds]

    # legends over data: axis legends against their panel, figure legends against every panel; every
    # kind of artist (lines, markers, scatter, filled bands, bars, error bars), not only lines (r12)
    covered = []
    legends = [(ax.get_legend(), siblings(ax)) for ax in fig.axes if ax.get_legend() is not None]
    legends += [(lg, list(fig.axes)) for lg in fig.legends]
    for leg, axes in legends:
        if not leg.get_visible():
            continue
        lb = leg.get_window_extent(r)
        n_in = sum(_data_in_box(a, lb) for a in axes)
        if n_in:
            covered.append(f"{n_in} data elements under the legend")
    out.append(Check("legends clear of data", "fail" if covered else "pass",
                     "; ".join(covered) if covered else ("every legend sits in empty space" if legends
                                                         else "no legend in this figure")))

    # text inside a panel (annotations) clear of the data
    over = []
    for ax in fig.axes:
        for t in ax.texts:
            if not t.get_visible() or not t.get_text().strip() or t.get_gid() == "panel-label":
                continue
            bb = t.get_window_extent(r)
            if sum(_data_in_box(a, bb) for a in siblings(ax)):
                over.append(repr(t.get_text()[:24]))
    for t in fig.texts:
        if t.get_visible() and t.get_text().strip() and t.get_gid() != "panel-label":
            bb = t.get_window_extent(r)
            if sum(_data_in_box(a, bb) for a in fig.axes):
                over.append(repr(t.get_text()[:24]))
    out.append(Check("text clear of data", "fail" if over else "pass",
                     ("drawn over data: " + ", ".join(over[:4])) if over else "no annotation sits on a curve or a point"))

    # every plotted point inside its axes: a point outside the limits is silently missing (r02, r12)
    outside, unread, n3d = [], [], 0
    for ax in fig.axes:
        if is_3d(ax):
            n3d += 1
            why = _data_outside_3d(ax)
            if why is None:
                unread.append("the data limits of a 3D axes could not be read")
            elif why:
                outside.append("3D: " + why)
            continue
        n_out = _data_outside(ax)
        if n_out:
            outside.append(f"{n_out} point{'s' if n_out != 1 else ''} beyond the axis limits")
    note3d = f"; {n3d} 3D axes: data limits within the x, y and z limits (a 3D axes does not clip)" if n3d else ""
    if outside:
        out.append(Check("data inside the axes", "fail", "; ".join(outside[:3])))
    elif unread:
        out.append(Check("data inside the axes", "skip", "not evaluated: " + unread[0]))
    else:
        out.append(Check("data inside the axes", "pass", "every plotted point lies within its axes" + note3d))

    # line weights and colours
    thin, low = [], []
    for ax in fig.axes:
        for ln in ax.get_lines():
            if not ln.get_visible():
                continue
            if ln.get_linestyle() not in ("None", "none", "", " ") and ln.get_linewidth() < 0.25:
                thin.append(f"{ln.get_linewidth():g} pt")
            col = ln.get_color() if ln.get_marker() in ("None", "none", "", None) else (ln.get_markerfacecolor()
                  if ln.get_markerfacecolor() not in ("none", "white", "#ffffff", (1, 1, 1, 1)) else ln.get_markeredgecolor())
            try:
                rgb = to_rgb(col)
            except ValueError:
                continue
            if max(rgb) - min(rgb) < 0.02 and rgb[0] > 0.6:     # light grey guide lines are reference marks
                continue
            c = contrast(rgb)
            if c < 3.0:
                low.append(f"{matplotlib.colors.to_hex(rgb)} at {c:.1f}:1")
        for sp in ax.spines.values():
            if sp.get_visible() and sp.get_linewidth() < 0.25:
                thin.append(f"axis {sp.get_linewidth():g} pt")
        if is_3d(ax):                  # a 3D axes draws its own axis lines, panes, grid and tick strokes
            for axis in _axes_axes(ax):
                if not (ax.get_visible() and axis.get_visible()):
                    continue
                if axis.line.get_visible() and axis.line.get_linewidth() < 0.25:
                    thin.append(f"3D axis line {axis.line.get_linewidth():g} pt")
                if axis.pane.get_visible() and axis.pane.get_edgecolor()[3] > 0 and axis.pane.get_linewidth() < 0.25:
                    thin.append(f"3D pane edge {axis.pane.get_linewidth():g} pt")
                gw = np.atleast_1d(axis.gridlines.get_linewidth())
                if ax._draw_grid and gw.size and float(gw.min()) < 0.25:
                    thin.append(f"3D grid {float(gw.min()):g} pt")
                for tick in _ticks_in_view(axis):
                    tl = tick.tick1line
                    if tl.get_visible() and tl.get_linewidth() < 0.25:
                        thin.append(f"3D tick {tl.get_linewidth():g} pt")
            continue
        for axis in (ax.xaxis, ax.yaxis):
            if not (ax.get_visible() and axis.get_visible()):
                continue
            for tick in axis.get_major_ticks()[:1] + axis.get_minor_ticks()[:1]:
                for tl in (tick.tick1line, tick.tick2line):
                    if tl.get_visible() and tl.get_markersize() > 0 and tl.get_markeredgewidth() < 0.25:
                        thin.append(f"tick {tl.get_markeredgewidth():g} pt")
    out.append(Check("line weights", "fail" if thin else "pass",
                     ("below 0.25 pt: " + ", ".join(sorted(set(thin))[:4])) if thin else
                     "every stroke and tick at least 0.25 pt" + ("; 3D axis lines, panes, grid and ticks included"
                                                                 if any(is_3d(a) for a in fig.axes) else "")))
    maps, unordered = colour_maps(fig)
    detail = ("under 3:1 on white: " + ", ".join(sorted(set(low))[:4])) if low else \
        "every data colour at least 3:1 on white (WCAG 2.1 non-text)"
    if maps:
        detail += "; colour scales: " + "; ".join(maps[:3])
    out.append(Check("colour contrast", "warn" if (low or unordered) else "pass", detail))

    name = font_used()
    ok = any(k in name.lower().replace("-", " ") for k in METRIC_ARIAL)
    out.append(Check("typeface", "pass" if ok else "warn",
                     f"{name}" + ("" if ok else "; install Arial or Liberation Sans for journal-conformant type")))
    out.append(Check("editable text", "pass" if plt.rcParams["pdf.fonttype"] == 42 and plt.rcParams["svg.fonttype"] == "none"
                     else "fail", "TrueType (Type 42) fonts embedded in PDF; SVG keeps text as text"))
    return out
