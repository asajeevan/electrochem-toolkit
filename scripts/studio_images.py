"""Screenshots of Cyclara and the example figures, from shareable data only.

    python scripts/studio_images.py OUT_DIR

Writes the README images (light_*.png, dark_*.png), the handout assets
(strip.png, reading.png, light_mapping.png, light_methods.png, light_cite.png, light_plateaus.png) and
fig_summary.png and fig_plateau_surface.png into OUT_DIR.
Runs Qt offscreen.

Data: the synthetic demonstration file data/demo/cyclara_demo_synthetic.mpt
(scripts/make_demo_data.py; its header and name say it is synthetic) for the
pictures that need many cycles, and the public data/public/mpt/020-formation_CB5.mpt
(CC BY 4.0) for one view of measured data. Never a private file, so every image
may live in the repository.
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRect, QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from electrochem import plotting, workflow
from electrochem.cycling import Settings
from electrochem.studio import app as A
from electrochem.studio import theme
from electrochem.studio.motion import Motion

DEMO = ROOT / "data" / "demo" / "cyclara_demo_synthetic.mpt"
CB5 = ROOT / "data" / "public" / "mpt" / "020-formation_CB5.mpt"
DEMO_ANSWERS = ({"charge": "ox"}, {"configuration": "half", "reference": "Li+/Li"}, {"mass_mg": 5.0},
                {"molar_mass_g_mol": 214.4, "electrons": 1.0})
CB5_ANSWERS = ({"charge": "ox"}, {"configuration": "full"}, {"no_mass": True, "mass_mg": None})
CYCLES = "1, 2, 5, 10, 20, 30, 40, 50"
STORE = "cyclara-images"


def pump(qa, timeout=180, quiet=0.4):
    """Until no background job has run for `quiet` seconds over at least three passes, re-checked after a
    last pass: a job's result can arrive during a long pass and start the next job."""
    end = time.time() + timeout
    idle, passes = None, 0
    while time.time() < end:
        qa.processEvents()
        if QThreadPool.globalInstance().activeThreadCount() == 0:
            idle = idle or time.time()
            passes += 1
            if time.time() - idle >= quiet and passes >= 3:
                qa.processEvents()
                if QThreadPool.globalInstance().activeThreadCount() == 0:
                    return
                idle, passes = None, 0
        else:
            idle, passes = None, 0
        time.sleep(0.01)


def window(qa, dark):
    theme.apply(qa, theme.DARK if dark else theme.LIGHT)
    QSettings(STORE, "studio").clear()
    w = A.MainWindow(store=STORE)
    w.resize(1600, 1000)
    w.show()
    pump(qa)
    return w


def shoot(qa, out: Path, dark: bool):
    pre = "dark" if dark else "light"
    w = window(qa, dark)
    w.grab().save(str(out / f"{pre}_home.png"))
    w.open_paths([DEMO]); pump(qa)
    w.grab().save(str(out / f"{pre}_unanswered.png"))
    for a in DEMO_ANSWERS:
        w._answer(a); pump(qa)
    w.set_cycles_spec(CYCLES); w.set_focus_cycle(10); pump(qa)
    index = {n: k for k, (n, _) in enumerate(A.VIEWS)}          # by name: views are added over time
    for view, name in (("Overview", "overview"), ("Profiles", "profiles"), ("Capacity", "capacity"),
                       ("dQ/dE", "dqde"), ("Evolution", "evolution"), ("Voltage", "voltage")):
        w.show_view(index[view]); pump(qa)
        w.grab().save(str(out / f"{pre}_{name}.png"))
    w.show_view(len(A.VIEWS)); pump(qa, 90); time.sleep(0.6); pump(qa)      # the Figures page
    w.grab().save(str(out / f"{pre}_figures.png"))
    if not dark:
        w.show_view(index["Overview"]); pump(qa)
        strip = w.strip_row
        top_left = strip.mapTo(w, strip.rect().topLeft())
        w.grab(QRect(top_left, strip.size())).save(str(out / "strip.png"))
        # measured data: the public formation file, full cell, no mass
        w.open_paths([CB5]); pump(qa)
        for a in CB5_ANSWERS:
            w._answer(a); pump(qa)
        w.show_view(index["Profiles"]); pump(qa)
        w.grab().save(str(out / "light_measured_cb5.png"))
    w.close()
    QSettings(STORE, "studio").clear()


def reading(qa, out: Path):
    """The reading screen once every real milestone is on it (held there for the picture)."""
    Motion.mode = "full"
    w = window(qa, dark=True)
    w._ingest_done = lambda rec: None            # hold the reading screen instead of moving on
    w.open_paths([DEMO])
    pump(qa)
    t0 = time.time()
    tel = w.ingest.telemetry
    while time.time() - t0 < 10 and any(ln[1] < len(ln[0]) for ln in tel.lines):
        qa.processEvents(); time.sleep(0.02)
    time.sleep(0.3); qa.processEvents()
    w.grab().save(str(out / "reading.png"))
    Motion.mode = "off"
    w.close()


def mapping(qa, out: Path, dark: bool):
    """The import review page for a file no profile recognises: a synthetic export from an invented
    instrument (the header names are made up here, so no vendor is pictured)."""
    import os
    import tempfile
    pre = "dark" if dark else "light"
    folder = Path(tempfile.mkdtemp(prefix="cyclara_images_"))
    os.environ["ELECTROCHEM_PROFILES"] = str(folder / "profiles")   # nothing saved outside this run
    p = folder / "cell_07.csv"
    rows = ["Elapsed Time(s),Amps(A),Volts(V),Cycle Index,Step Index,Step Name"]
    for k in range(240):
        charge = (k // 60) % 2 == 0
        rows.append(f"{k * 60},{0.0012 if charge else -0.0012},{3.45 + 0.004 * (k % 60) if charge else 3.70 - 0.004 * (k % 60):.4f},"
                    f"{k // 120 + 1},{k // 60 + 1},{'CC_Chg' if charge else 'CC_DChg'}")
    p.write_text("\n".join(rows) + "\n")
    w = window(qa, dark)
    w.open_paths([p]); pump(qa)
    w.grab().save(str(out / f"{pre}_mapping.png"))
    w.close()
    QSettings(STORE, "studio").clear()


def methods(qa, out: Path):
    """Help > How the numbers are calculated on the demonstration file (the energy topic, whose 'For this
    file' lines show a number of the file), and Help > Cite Cyclara."""
    w = window(qa, False)
    w.open_paths([DEMO]); pump(qa)
    for a in ({"charge": "ox"}, {"configuration": "half", "reference": "Li+/Li"}, {"mass_mg": 5.0}):
        w._answer(a); pump(qa)
    w.methods_help("energy"); pump(qa)
    d = w._methods
    d.resize(1040, 680); pump(qa)
    d.grab().save(str(out / "light_methods.png"))
    d.close()
    w.cite(); pump(qa)
    w._cite.grab().save(str(out / "light_cite.png"))
    w._cite.close()
    w.close()
    QSettings(STORE, "studio").clear()


def plateaus(qa, out: Path):
    """The synthetic multi-plateau cell of tests/plateau_cell.py (three plateaus that return, one in the first
    charge only, one appearing from cycle 3): the Evolution view with the inspector's plateau block, and
    figure 7 of the same cell. Synthetic by construction; the handout says so."""
    import tempfile
    sys.path.insert(0, str(ROOT / "tests"))
    import plateau_cell
    folder = Path(tempfile.mkdtemp(prefix="cyclara_plateaus_"))
    cycles, plateau_cell.N_CYCLES = plateau_cell.N_CYCLES, 30     # thirty cycles read better in 3D than the tests' five
    try:
        p = plateau_cell.write(folder / "synthetic_plateaus.mpt")
    finally:
        plateau_cell.N_CYCLES = cycles
    w = window(qa, False)
    w.open_paths([p]); pump(qa)
    for a in ({"charge": "ox"}, {"configuration": "full"}, {"mass_mg": 5.0}):
        w._answer(a); pump(qa)
    w.set_cycles_spec("1, 2, 3, 5, 10, 20, 30"); w.set_focus_cycle(1); pump(qa)
    w.show_view([n for n, _ in A.VIEWS].index("Evolution")); pump(qa)
    from PySide6.QtWidgets import QLabel
    head = next((l for l in w.inspector.findChildren(QLabel) if l.text().startswith("Plateaus, cycle")), None)
    if head is not None:
        w.inspector.ensureWidgetVisible(head.parentWidget(), 0, 0)
        pump(qa)
    w.grab().save(str(out / "light_plateaus.png"))
    run = w.rec.run
    fig = plotting.fig7_dqde_surface(run.dqde_curves(run.all_cycles), run.settings, run.tab)
    bad = [c for c in plotting.check_figure(fig) if c.status == "fail"]
    assert not bad, bad
    fig.savefig(out / "fig_plateau_surface.png", dpi=300)
    w.close()
    QSettings(STORE, "studio").clear()


def main(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    qa = QApplication.instance() or QApplication([])
    theme.load_fonts()
    qa.setFont(theme.font(9.5))
    Motion.mode = "off"
    shoot(qa, out, dark=False)
    shoot(qa, out, dark=True)
    mapping(qa, out, dark=False)
    methods(qa, out)
    plateaus(qa, out)
    reading(qa, out)
    run = workflow.analyse_file(workflow.open_file(DEMO), Settings(charge="ox", reference="Li+/Li", active_mass_mg=5.0,
                                                                   molar_mass_g_mol=214.4, electrons=1),
                                "1,2,5,10,20,30,40,50")
    fig = workflow.figure_builders(run, workflow.ExportOptions())["summary"]()
    bad = [c for c in plotting.check_figure(fig) if c.status == "fail"]
    assert not bad, bad
    fig.savefig(out / "fig_summary.png", dpi=300)
    print("written to", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "images" / "app")
