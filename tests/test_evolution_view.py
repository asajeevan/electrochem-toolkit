"""The Evolution view (dQ/dE over cycles), offscreen: it shows the grid the figures use, unchanged, and says
under the cursor what is stored there."""
from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")
pg = pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from electrochem import differential, workflow
from electrochem.cycling import Settings
from electrochem.studio import theme
from electrochem.studio.model import Record
from tests import plateau_cell as pc


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    theme.load_fonts()
    theme.apply(a, theme.LIGHT)
    from electrochem.studio.motion import Motion
    Motion.mode = "off"
    return a


@pytest.fixture(scope="module")
def rec(tmp_path_factory):
    path = pc.write(tmp_path_factory.mktemp("evo") / "plateau_cell.mpt")
    loaded = workflow.open_file(path)
    run = workflow.analyse_file(loaded, Settings(charge="ox", reference="Li/Li+"), cycles="1:-1")
    return Record(path=path, loaded=loaded, run=run)


@pytest.fixture
def view(app, rec):
    from electrochem.studio.views import EvolutionView
    v = EvolutionView()
    v.resize(900, 600)
    v.show()
    v.show_record(rec, [1, 3, 5], 3)
    app.processEvents()
    yield v
    v.close()
    v.deleteLater()


def test_the_map_shows_the_grid_of_the_figures_unchanged(view, rec):
    run = rec.run
    expected = differential.evolution_grid(run.dqde_curves(run.all_cycles), "charge").filled()
    g = view.grid
    assert g is not None and g.direction == "charge"
    assert np.array_equal(g.cycles, expected.cycles) and np.array_equal(g.voltage_V, expected.voltage_V)
    assert np.array_equal(g.dqde, expected.dqde, equal_nan=True)
    assert np.array_equal(view.image.image, np.abs(expected.dqde).T, equal_nan=True)   # the pixels are the values
    assert view.image in view.plot.getPlotItem().items
    assert view.cbar is not None and view.cbar.isVisible()
    lo, hi = view.cbar.levels()
    assert lo == 0 and hi == pytest.approx(float(np.nanmax(np.abs(expected.dqde))))
    r = view.image.mapRectToParent(view.image.boundingRect())
    assert r.left() == pytest.approx(expected.voltage_V[0] - 0.005) and r.bottom() == pytest.approx(pc.N_CYCLES + 0.5)


def test_the_readout_names_cycle_potential_and_the_stored_value(view, app):
    g = view.grid
    j = int(np.argmin(np.abs(g.voltage_V - 3.4321)))
    text = view.readout_at(3.4321 + 0.002, 2.2)                  # the nearest node and the nearest cycle
    assert text == (f"Cycle 2, charge: dQ/dE {g.dqde[1, j]:.4g} mAh V⁻¹ at {g.voltage_V[j]:.4f} V "
                    "(grid node, 10 mV bins)")
    assert view.readout_at(g.voltage_V[0] - 1.0, 2) == " "         # outside the map: nothing
    vb = view.plot.getPlotItem().getViewBox()
    view._hover(view.plot, vb.mapViewToScene(QPointF(3.4321 + 0.002, 2.2)))
    assert view.readout.text() == text                           # the mouse path gives the same words


def test_unmeasured_cells_say_so(view, rec):
    from electrochem.studio.views import EvolutionView
    curves = [(c, cv) for c, cv in rec.run.dqde_curves(rec.run.all_cycles) if c != 2]   # cycle 2 missing
    view._cache_run = rec.run
    view._curves = curves
    view._grids = {}
    view.redraw()
    assert view.readout_at(3.4, 2) == "Cycle 2: no charge dQ/dE curve"
    assert np.isnan(view.image.image[:, 1]).all()                 # drawn transparent over the grey background
    view._cache_run = None


def test_the_waterfall_draws_the_selected_cycles_own_curves(view, app, rec):
    view.mode.setCurrentIndex(1)
    app.processEvents()
    assert not view.cbar.isVisible()
    items = [i for i in view.plot.getPlotItem().items if isinstance(i, pg.PlotDataItem)]
    assert len(items) == 3                                       # cycles 1, 3 and 5
    curves = {c: cv for c, cv in rec.run.dqde_curves([1, 3, 5]) if cv.direction == "charge"}
    off = view.WATERFALL_OFFSET * max(float(np.nanmax(np.abs(cv.dqdv))) for cv in curves.values())
    for rank, c in enumerate([1, 3, 5]):
        x, y = items[rank].xData, items[rank].yData                  # drawn in cycle order
        assert np.array_equal(x, curves[c].voltage_V)
        assert np.allclose(y - rank * off, np.abs(curves[c].dqdv), rtol=0, atol=1e-12)
    ticks = view.plot.getPlotItem().getAxis("left")._tickLevels
    assert [t[1] for t in ticks[0]] == ["1", "3", "5"]
    plot, x, y, label = view._points[1]
    k = int(np.nanargmax(y - off))
    assert label(k).startswith(f"Cycle 3, charge: dQ/dE {curves[3].dqdv[k]:.4g} mAh V⁻¹")   # the stored, signed value
    view.direction.setCurrentIndex(1)
    app.processEvents()
    assert all("discharge" in lab(0) for _, _, _, lab in view._points)
    view.mode.setCurrentIndex(0)
    app.processEvents()
    assert view.grid.direction == "discharge" and view.cbar.isVisible()
    assert view.plot.getPlotItem().getAxis("left")._tickLevels is None


def test_nothing_is_computed_while_the_view_is_hidden(app, rec):
    from electrochem.studio.views import EvolutionView
    v = EvolutionView()
    v.show_record(rec, [1], 1)
    assert v._cache_run is None and v._dirty            # every cycle's curve waits until the view is shown
    v.show()
    app.processEvents()
    assert v._cache_run is rec.run and v.grid is not None
    v.close()


# ------------------------------------------------------------------ branches without a curve (0.9.1)

def _cex_record(tmp_path, changes):
    """A synthetic LANHE file (tests/cex_synthetic.py) with the given step changes, as the app holds it."""
    import sys
    from dataclasses import replace
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    import cex_synthetic as cs
    steps = cs.two_cycles()
    for k, fields in changes.items():
        steps[k] = replace(steps[k], **fields)
    p = tmp_path / "run.cex"
    p.write_bytes(cs.write(steps)[0])
    loaded = workflow.open_file(p)
    run = workflow.analyse_file(loaded, Settings(charge="ox", terminal_voltage=True))
    return Record(path=p, loaded=loaded, run=run)


def test_the_evolution_view_says_when_a_direction_has_no_curve_and_drops_its_note(app, tmp_path):
    """Both discharges paused partway: the charge map has its note; the discharge map and the discharge waterfall say
    there is no curve, with the axis's symbol (a cell voltage: dQ/dV), and no note of the charge map stays above."""
    from electrochem.studio.views import EvolutionView
    rec = _cex_record(tmp_path, {4: {"pause": (1500.0, 120)}, 7: {"pause": (3000.0, 120)}})
    v = EvolutionView()
    v.resize(900, 600)
    v.show()
    try:
        v.show_record(rec, [1, 2], None)
        app.processEvents()
        assert v.grid is not None and v.grid.direction == "charge" and not v.note.isHidden()
        assert "too few points or too narrow a range" in v.note.text() and "dQ/dV curve" in v.note.text()
        v.direction.setCurrentIndex(1)
        app.processEvents()
        assert v.empty.text() == "No discharge branch has a dQ/dV curve." and v.note.isHidden()
        v.mode.setCurrentIndex(1)
        app.processEvents()
        assert v.empty.text() == "None of the selected cycles has a discharge dQ/dV curve." and v.note.isHidden()
        v.direction.setCurrentIndex(0)
        app.processEvents()
        assert v.empty.isHidden() and not v.note.isHidden()
    finally:
        v.close()
        v.deleteLater()


def test_the_dqde_view_gives_each_missing_curve_its_reason(app, tmp_path):
    """Cycle 1's charge restarted in its constant-current part (interrupted) and its discharge a step of one
    interval (too few points): the note names both with their reasons; cycle 2 is drawn."""
    from electrochem.studio.views import DifferentialView
    rec = _cex_record(tmp_path, {1: {"restart": (1495.0, 30.0, 600)}, 4: {"duration": 1.0}})
    assert [cv.branch for _, cv in rec.run.dqde_curves([1, 2])] == [3, 4]
    v = DifferentialView()
    v.resize(900, 600)
    v.show()
    try:
        v.show_record(rec, [1, 2], None)
        app.processEvents()
        assert v.empty.isHidden()
        assert ("No dQ/dV curve for cycle 1 charge (interrupted), cycle 1 discharge (too few points or too narrow a "
                "range outside constant-voltage stages).") in v.note.text()
    finally:
        v.close()
        v.deleteLater()
