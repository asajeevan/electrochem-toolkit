"""Publication figures: exact sizes, journal rules, and a checker that catches real faults.

The checker is tested against figures broken on purpose, so a check that
always passes would fail here.
"""
import io
import re
from pathlib import Path

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
import matplotlib.pyplot as plt

from electrochem import differential, plotting, workflow
from electrochem.cycling import Settings

DATA = Path(__file__).resolve().parents[1] / "data" / "public" / "mpt" / "020-formation_CB5.mpt"


@pytest.fixture(scope="module")
def run():
    loaded = workflow.open_file(DATA)
    return workflow.analyse_file(loaded, Settings(charge="ox", terminal_voltage=True, active_mass_mg=10.0))


@pytest.mark.parametrize("journal", list(plotting.JOURNALS))
def test_every_figure_passes_its_journal_checks(run, journal):
    for name, build in workflow.figure_builders(run, workflow.ExportOptions(journal=journal)).items():
        fig = build()
        bad = [c for c in plotting.check_figure(fig, journal) if c.status == "fail"]
        plt.close(fig)
        assert not bad, f"{name} ({journal}): " + "; ".join(f"{c.name}: {c.detail}" for c in bad)


def test_saved_pdf_is_exactly_the_column_width(run, tmp_path):
    """No tight bounding box: an 89 mm figure is 89.0 mm in the file."""
    fig = workflow.figure_builders(run, workflow.ExportOptions())["potential_capacity"]()
    path = plotting.save(fig, tmp_path / "f", ("pdf",))[0]
    box = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", path.read_bytes())
    assert box, "no MediaBox in the PDF"
    assert float(box.group(1)) / 72 * 25.4 == pytest.approx(89.0, abs=0.05)


def test_summary_is_double_column_and_within_the_height_limit(run):
    fig = workflow.figure_builders(run, workflow.ExportOptions())["summary"]()
    w, h = fig.get_size_inches() * 25.4
    plt.close(fig)
    assert w == pytest.approx(183.0, abs=0.05) and h <= 170.0


def test_panel_letters_are_8pt_bold_lowercase_and_inside(run):
    fig = workflow.figure_builders(run, workflow.ExportOptions())["summary"]()
    letters = [t for t in fig.texts if t.get_gid() == "panel-label"]
    assert [t.get_text() for t in letters] == ["a", "b", "c", "d"]
    assert all(t.get_fontsize() == 8.0 and t.get_fontweight() in ("bold", 700) for t in letters)
    checks = {c.name: c for c in plotting.check_figure(fig)}
    plt.close(fig)
    assert checks["text inside the figure"].status == "pass"


def _status(fig, name):
    return {c.name: c.status for c in plotting.check_figure(fig)}[name]


def test_checker_catches_type_above_the_journal_maximum():
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    ax = fig.add_subplot(); ax.plot([0, 1], [0, 1], color="#0072B2")
    ax.set_xlabel("Too big", fontsize=9)
    assert _status(fig, "type size") == "fail"
    plt.close(fig)


def test_checker_catches_a_width_no_journal_uses():
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(100 * plotting.MM, 70 * plotting.MM), layout="constrained")
    fig.add_subplot().plot([0, 1], [0, 1], color="#0072B2")
    assert _status(fig, "width") == "fail"
    plt.close(fig)


def test_checker_catches_a_legend_over_the_data():
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    ax = fig.add_subplot()
    x = np.linspace(0, 1, 400)
    ax.plot(x, np.ones_like(x) * 0.95, color="#0072B2", label="a long legend entry")
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left")
    assert _status(fig, "legends clear of data") == "fail"
    plt.close(fig)


def test_checker_catches_a_straight_segment_under_the_legend():
    """Two measured points far apart: no point is under the legend, but the drawn line is."""
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    ax = fig.add_subplot()
    ax.plot([0, 1], [0.95, 0.95], color="#0072B2", label="a long legend entry")
    ax.set_xlim(-0.2, 1.2); ax.set_ylim(0, 1)
    ax.legend(loc="upper left")
    assert _status(fig, "legends clear of data") == "fail"
    plt.close(fig)


def test_checker_passes_a_legend_in_empty_space():
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    ax = fig.add_subplot()
    ax.plot([0, 1], [0.1, 0.2], color="#0072B2", label="entry")
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left")
    assert _status(fig, "legends clear of data") == "pass"
    plt.close(fig)


def test_checker_catches_overlapping_labels():
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    ax = fig.add_subplot(); ax.plot([0, 1], [0, 1], color="#0072B2")
    ax.text(0.5, 0.5, "one label", transform=ax.transAxes)
    ax.text(0.52, 0.5, "two labels", transform=ax.transAxes)
    assert _status(fig, "no overlapping text") == "fail"
    plt.close(fig)


def test_checker_catches_a_colour_too_light_to_read():
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    fig.add_subplot().plot([0, 1], [0, 1], color="#F0E442")   # Okabe-Ito yellow: 1.2:1 on white
    assert _status(fig, "colour contrast") == "warn"
    plt.close(fig)


@pytest.mark.parametrize("palette", ["blues", "viridis"])
@pytest.mark.parametrize("n", [2, 7, 20])
def test_every_cycle_colour_reaches_3_to_1_on_white(palette, n):
    for c in plotting.cycle_colors(n, palette):
        assert plotting.contrast(c[:3] if isinstance(c, tuple) else c) >= 3.0


def test_dqde_grid_stays_inside_the_measured_potentials(run):
    """A grid point beyond the last measured potential holds a clamped capacity
    and so a fabricated dQ/dE near zero (found in a real 110-cycle figure at 4.0 V)."""
    pairs = {p.index: p for p in run.seg.pairs}
    for p in pairs.values():
        for br in (p.charge, p.discharge):
            if br is None:
                continue
            cv = differential.curve(run.tab, run.seg, run.settings, br, p.index, 10.0)
            if cv is None:
                continue
            e = run.tab.e[br.rows]
            if run.tab.mode is not None:
                e = e[run.tab.mode[br.rows] != 2]
            assert cv.voltage_V.min() >= np.nanmin(e) - 1e-12
            assert cv.voltage_V.max() <= np.nanmax(e) + 1e-12
            assert np.allclose(np.diff(cv.voltage_V), 0.010, atol=1e-9)


def test_potential_label_puts_the_unit_last():
    s = Settings(reference="Li/Li+")
    assert plotting.potential_label(None, s) == "Potential vs. Li$^{+}$/Li (V)"
    assert plotting.potential_label(None, Settings(terminal_voltage=True)) == "Cell voltage (V)"


# ------------------------------------------------------------------ dQ/dE evolution: map and 3D surfaces

@pytest.fixture(scope="module")
def plateau_run(tmp_path_factory):
    from tests import plateau_cell
    path = plateau_cell.write(tmp_path_factory.mktemp("plateau_fig") / "plateau_cell.mpt")
    return workflow.analyse_file(workflow.open_file(path), Settings(charge="ox", reference="Li/Li+"), cycles="1:-1")


@pytest.mark.parametrize("journal", list(plotting.JOURNALS))
def test_evolution_figures_pass_their_journal_checks(plateau_run, journal):
    builders = workflow.figure_builders(plateau_run, workflow.ExportOptions(journal=journal))
    for name in ("dqde_map", "dqde_surface"):
        fig = builders[name]()
        checks = plotting.check_figure(fig, journal)
        plt.close(fig)
        assert len(checks) == 12
        bad = [c for c in checks if c.status == "fail"]
        assert not bad, f"{name} ({journal}): " + "; ".join(f"{c.name}: {c.detail}" for c in bad)
        assert all("not evaluated" in c.detail for c in checks if c.status == "skip")   # a skip says why
        by = {c.name: c for c in checks}
        assert "magma_r, sequential" in by["colour contrast"].detail
        if name == "dqde_surface":
            assert "3D axes" in by["data inside the axes"].detail
            assert "3D axis lines" in by["line weights"].detail


def test_the_map_draws_the_grid_values(plateau_run):
    """The colours are |dQ/dE| of differential.evolution_grid, cell for cell, normalised or in real units."""
    curves = plateau_run.dqde_curves(plateau_run.all_cycles)
    grids = [differential.evolution_grid(curves, d).filled() for d in ("charge", "discharge")]
    top = max(float(np.nanmax(np.abs(g.dqde))) for g in grids)
    for units, scale in (("real", 1.0), ("au", top)):
        fig = plotting.fig6_dqde_map(curves, plateau_run.settings, plateau_run.tab, units=units)
        meshes = [c for ax in fig.axes for c in ax.collections if c.get_gid() == "dqde-map"]
        assert len(meshes) == 2
        for mesh, g in zip(meshes, grids):
            arr = np.ma.filled(np.ma.asarray(mesh.get_array()).astype(float), np.nan).reshape(g.dqde.shape)
            assert np.allclose(arr, np.abs(g.dqde) / scale, equal_nan=True, rtol=0, atol=1e-12)
        plt.close(fig)


def test_a_long_test_draws_every_kth_cycle_and_says_so():
    v = np.round(3.0 + 0.01 * np.arange(60), 6)
    curves = [(c, differential.DqdvCurve(c, 2 * c, d, v, np.exp(-((v - 3.3) / 0.03) ** 2) * (1 if d == "charge" else -1),
                                         "mAh/V", 10.0)) for c in range(1, 251) for d in ("charge", "discharge")]
    fig = plotting.fig7_dqde_surface(curves, Settings(reference="Li/Li+"))
    notes = [t.get_text() for t in fig.texts if t.get_gid() == "surface-note"]
    assert notes == ["Every 3rd cycle drawn (250 cycles)"]
    assert not [c for c in plotting.check_figure(fig) if c.status == "fail"]
    plt.close(fig)


def test_checker_catches_3d_data_beyond_the_axis_limits():
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    ax = fig.add_subplot(projection="3d")
    X, Y = np.meshgrid(np.linspace(0, 1, 10), np.arange(4.0))
    ax.plot_surface(X, Y, np.sin(6 * X), cmap="magma_r")
    assert _status(fig, "data inside the axes") == "pass"
    ax.set_zlim(-0.5, 0.5)                     # a 3D axes does not clip: the surface now pokes out of the box
    assert _status(fig, "data inside the axes") == "fail"
    plt.close(fig)


def test_checker_catches_a_thin_3d_grid():
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    ax = fig.add_subplot(projection="3d")
    ax.plot([0, 1], [0, 1], [0, 1], color="#0072B2")
    ax.xaxis._axinfo["grid"]["linewidth"] = 0.1
    assert _status(fig, "line weights") == "fail"
    plt.close(fig)


@pytest.mark.parametrize("cmap,vmin,status", [("magma_r", 0, "pass"), ("jet", 0, "warn"),
                                              ("coolwarm", -1, "pass"), ("coolwarm", 0, "warn")])
def test_checker_judges_a_colour_map_by_its_lightness(cmap, vmin, status):
    """jet rises and falls in lightness; coolwarm is ordered only when its light centre sits at zero."""
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    ax = fig.add_subplot()
    ax.pcolormesh(np.arange(5.0), np.arange(4.0), np.linspace(vmin, 1, 12).reshape(3, 4), cmap=cmap, vmin=vmin, vmax=1)
    assert _status(fig, "colour contrast") == status
    plt.close(fig)


def test_checker_catches_a_colour_map_beyond_the_axes():
    plotting.apply_style("nature")
    fig = plt.figure(figsize=(89 * plotting.MM, 70 * plotting.MM), layout="constrained")
    ax = fig.add_subplot()
    ax.pcolormesh(np.arange(5.0), np.arange(4.0), np.ones((3, 4)), cmap="magma_r")
    ax.set_xlim(0, 4); ax.set_ylim(0, 3)
    assert _status(fig, "data inside the axes") == "pass"
    ax.set_xlim(0, 3)
    assert _status(fig, "data inside the axes") == "fail"
    plt.close(fig)


def test_a_rotated_label_is_tested_by_its_own_rectangle():
    """A 100 x 10 px label at 20 degrees has an axis-aligned box of 97.4 x 43.6 px; a small text in a corner of
    that box does not touch the label, a text on the label does."""
    import math
    from matplotlib.transforms import Bbox

    class T:
        def __init__(self, rot):
            self.rot = rot

        def get_rotation(self):
            return self.rot
    th = math.radians(20)
    W, H = 100 * math.cos(th) + 10 * math.sin(th), 100 * math.sin(th) + 10 * math.cos(th)
    label = plotting._text_polygon(T(20), Bbox.from_bounds(0, 0, W, H))
    sides = sorted(np.hypot(*(label[(k + 1) % 4] - label[k])) for k in range(4))
    assert sides == pytest.approx([10, 10, 100, 100], abs=1e-9)
    corner = plotting._text_polygon(T(0), Bbox.from_bounds(2, H - 12, 10, 10))       # top-left corner of the box
    centre = plotting._text_polygon(T(0), Bbox.from_bounds(W / 2 - 5, H / 2 - 5, 10, 10))
    assert not plotting._polygons_overlap(label, corner)
    assert plotting._polygons_overlap(label, centre)
    a, b = (plotting._text_polygon(T(0), Bbox.from_bounds(x, 0, 10, 10)) for x in (0, 8.5))
    assert plotting._polygons_overlap(a, b) and not plotting._polygons_overlap(a, b, tol=1.5)   # 1.5 px overlap


def test_checking_a_3d_figure_does_not_move_its_tick_labels(plateau_run):
    fig = workflow.figure_builders(plateau_run, workflow.ExportOptions())["dqde_surface"]()
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    ax = [a for a in fig.axes if plotting.is_3d(a)][0]
    before = [t.label1.get_window_extent(r).bounds for t in plotting._ticks_in_view(ax.xaxis)]
    plotting.check_figure(fig)
    after = [t.label1.get_window_extent(r).bounds for t in plotting._ticks_in_view(ax.xaxis)]
    plt.close(fig)
    assert before == after


def test_evolution_figures_are_written_at_their_column_widths(plateau_run, tmp_path):
    workflow.export(plateau_run, tmp_path, workflow.ExportOptions(plots={"dqde_map", "dqde_surface"}, origin=False))
    for stem, mm in (("fig6_dqde_map", 120.0), ("fig7_dqde_surface", 183.0)):
        for f in ("pdf", "svg", "png"):
            assert (tmp_path / f"{stem}.{f}").exists()
        box = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", (tmp_path / f"{stem}.pdf").read_bytes())
        assert float(box.group(1)) / 72 * 25.4 == pytest.approx(mm, abs=0.05)


def test_both_panels_of_the_evolution_figures_share_one_potential_scale():
    """Charge and discharge are read against each other (pairs line up vertically), so both panels of
    figures 6 and 7 use the union of the two directions' potential ranges and the same ticks; the part of a
    panel beyond its own measured range is drawn as not measured (grey), never as zero."""
    import matplotlib.pyplot as plt
    from electrochem import plotting, workflow
    from electrochem.cycling import Settings
    root = Path(__file__).resolve().parents[1]
    run = workflow.analyse_file(workflow.open_file(root / "data" / "demo" / "cyclara_demo_synthetic.mpt"),
                                Settings(charge="ox", terminal_voltage=True, active_mass_mg=5.0), "1,2,5")
    curves = run.dqde_curves(run.all_cycles)
    lo = min(float(cv.voltage_V.min()) for _, cv in curves)
    hi = max(float(cv.voltage_V.max()) for _, cv in curves)
    for build in (plotting.fig6_dqde_map, plotting.fig7_dqde_surface):
        fig = build(curves, run.settings, run.tab)
        panels = [ax for ax in fig.axes if ax.get_label() != "<colorbar>"][:2]
        (a0, a1), (b0, b1) = panels[0].get_xlim(), panels[1].get_xlim()
        assert (a0, a1) == (b0, b1), build.__name__
        assert a0 <= lo + 1e-9 and a1 >= hi - 1e-9, build.__name__
        assert list(panels[0].get_xticks()) == list(panels[1].get_xticks()), build.__name__
        assert all(c.status != "fail" for c in plotting.check_figure(fig)), build.__name__
        plt.close(fig)
    fig = plotting.fig6_dqde_map(curves, run.settings, run.tab)
    from matplotlib.colors import to_hex
    assert {to_hex(ax.get_facecolor()) for ax in fig.axes[:2]} == {to_hex(plotting.NOT_MEASURED)}
    plt.close(fig)
