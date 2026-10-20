"""One-window front end: pick a file, state the conventions, click Run.

Runs the same analysis as `python -m electrochem.analyze`, then, if Origin
and its `originpro` package are installed, builds the Origin project too, and
finally opens the results folder. Start it with Analyse.bat (Windows) or
`python -m electrochem.gui`.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import analyze, origin_export, metadata, __version__, __author__, __url__

SETTINGS = Path.home() / ".electrochem-toolkit-gui.json"

# palette: light workspace, dark banner, one accent (the same blue as the figures)
BG, CARD, BANNER = "#f3f5f8", "#ffffff", "#16243a"
TEXT, MUTED, BORDER = "#1c2430", "#6b7684", "#d5dbe3"
ACCENT, ACCENT_DARK, OK, BAD = "#0072B2", "#005a8e", "#1a7f37", "#b3261e"
ROOT = Path(__file__).resolve().parents[1]

# Plain-language explanations for the errors a user is likely to meet
FRIENDLY = [
    ("native_dependency_missing", "The .mpr reader is not installed. Either export the measurement as .mpt from EC-Lab, "
                                   "or install Git and run Setup.bat again."),
    ("native_backend_unverified", "The installed .mpr reader is not the verified version. Run Setup.bat again."),
    ("size_limit", "The file is larger than 256 MB and holds a value the fast reader could not read, so the "
                   "token-by-token reader would be needed, which stops at 256 MB. Export fewer cycles or split the experiment."),
    ("No time/s column", "The file has no time/s column. Export it again from EC-Lab with the default columns."),
    ("No current column", "The file has no current column. Export it again from EC-Lab with I/mA included."),
    ("UnsupportedTechnique", None),          # message already user-facing
    ("Permission denied", "Windows refused to write the results. Close any file from a previous run that is still open "
                          "(Excel, Origin, a PDF viewer) and run again."),
    ("could not convert string to float", "A number in the file could not be read. If the export uses a decimal comma, "
                                          "the tool normally detects it; send the file to the author if this persists."),
]


def friendly(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for key, msg in FRIENDLY:
        if key in text:
            return msg or str(exc)
    return text


def _load_defaults():
    try:
        return json.loads(SETTINGS.read_text())
    except Exception:
        return {}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"electrochem-toolkit {__version__}")
        self.minsize(760, 640)
        self.configure(background=BG)
        style = ttk.Style(self)
        style.theme_use("clam")                       # the one theme that accepts a full custom palette on every platform
        style.configure(".", background=BG, foreground=TEXT, font=("Segoe UI", 10), bordercolor=BORDER,
                        lightcolor=CARD, darkcolor=CARD, focuscolor=ACCENT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT)
        style.configure("Title.TLabel", background=BANNER, foreground="white", font=("Segoe UI", 16, "bold"))
        style.configure("Banner.TLabel", background=BANNER, foreground="#cfd8e3", font=("Segoe UI", 10))
        style.configure("Banner.TFrame", background=BANNER)
        style.configure("Sub.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Foot.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Ok.TLabel", background=BG, foreground=OK, font=("Segoe UI", 10, "bold"))
        style.configure("Bad.TLabel", background=BG, foreground=BAD, font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe", background=CARD, bordercolor=BORDER, relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=CARD, foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", fieldbackground="white", bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, padding=4)
        style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])
        style.configure("TCheckbutton", background=CARD, foreground=TEXT)
        style.configure("TRadiobutton", background=CARD, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", CARD)])
        style.map("TRadiobutton", background=[("active", CARD)])
        style.configure("TButton", background=CARD, foreground=TEXT, bordercolor=BORDER, padding=(12, 6), relief="flat")
        style.map("TButton", background=[("active", "#e8edf3"), ("disabled", "#f0f2f5")], foreground=[("disabled", MUTED)])
        style.configure("Run.TButton", background=ACCENT, foreground="white", font=("Segoe UI", 10, "bold"), padding=(18, 8), bordercolor=ACCENT)
        style.map("Run.TButton", background=[("active", ACCENT_DARK), ("disabled", "#9db9d4")], foreground=[("disabled", "white")])
        style.configure("Banner.TButton", background=BANNER, foreground="#cfd8e3", bordercolor="#3a4a5e", padding=(10, 4), relief="flat")
        style.map("Banner.TButton", background=[("active", "#2d3d52")], foreground=[("active", "white")])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e6ebf1", bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)

        d = _load_defaults()
        self.header = {}
        self.last_out: Path | None = None
        # ---- banner
        top = ttk.Frame(self, style="Banner.TFrame", padding=(16, 12))
        top.pack(fill="x")
        ttk.Label(top, text="electrochem-toolkit", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text=f"   EC-Lab cycling analysis   ·   by {__author__}", style="Banner.TLabel").pack(side="left", pady=(7, 0))
        ttk.Button(top, text="Help", style="Banner.TButton", command=self.help).pack(side="right")
        ttk.Button(top, text="About", style="Banner.TButton", command=self.about).pack(side="right", padx=6)

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        # ---- file
        box = ttk.LabelFrame(outer, text="  1. Data file  ", padding=10); box.pack(fill="x", pady=(2, 6))
        self.file = tk.StringVar(value=d.get("file", ""))
        ttk.Entry(box, textvariable=self.file).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(box, text="Browse...", command=self.browse).grid(row=0, column=1)
        self.header_note = ttk.Label(box, text="Choose an EC-Lab .mpr or .mpt file", style="Sub.TLabel", wraplength=780, justify="left")
        self.header_note.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        box.columnconfigure(0, weight=1)

        # ---- conventions
        box = ttk.LabelFrame(outer, text="  2. Cell and conventions (never guessed from the file)  ", padding=10); box.pack(fill="x", pady=6)
        self.cell = tk.StringVar(value=d.get("cell", "half"))
        ttk.Label(box, text="Cell", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(box, text="Half-cell vs. metal", variable=self.cell, value="half").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(box, text="Full cell (cell voltage)", variable=self.cell, value="full").grid(row=0, column=2, sticky="w")
        ttk.Label(box, text="Reference", style="Card.TLabel").grid(row=0, column=3, sticky="e", padx=(12, 4))
        self.reference = tk.StringVar(value=d.get("reference", "Li/Li+"))
        ttk.Entry(box, textvariable=self.reference, width=9).grid(row=0, column=4, sticky="w", padx=(0, 6))
        box.columnconfigure(2, weight=1)
        self.charge = tk.StringVar(value=d.get("charge", "ox"))
        ttk.Label(box, text="Charge is", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Radiobutton(box, text="positive current (ox)", variable=self.charge, value="ox").grid(row=1, column=1, sticky="w", pady=(4, 0))
        ttk.Radiobutton(box, text="negative current (red)", variable=self.charge, value="red").grid(row=1, column=2, sticky="w", pady=(4, 0))
        self.mass = self._entry(box, 2, 0, "Active mass (mg)", d.get("mass", ""))
        self.molar = self._entry(box, 2, 2, "Molar mass (g/mol)", d.get("molar", ""))
        self.electrons = self._entry(box, 3, 0, "Electrons per formula unit", d.get("electrons", ""))
        self.area = self._entry(box, 3, 2, "Electrode area (cm²)", d.get("area", ""))
        self.cycles = self._entry(box, 4, 0, "Cycles to plot", d.get("cycles", "1,2,5,10,20,50,100"), width=22)
        self.refcycle = self._entry(box, 4, 2, "Reference cycle (100 % retention)", d.get("refcycle", "1"))

        # ---- outputs
        box = ttk.LabelFrame(outer, text="  3. Outputs  ", padding=10); box.pack(fill="x", pady=6)
        self.figures = tk.BooleanVar(value=d.get("figures", True))
        self.origin = tk.BooleanVar(value=d.get("origin", True))
        self.open_folder = tk.BooleanVar(value=d.get("open_folder", True))
        ttk.Checkbutton(box, text="Figures (PDF, SVG, PNG)", variable=self.figures).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(box, text="Origin project (.opju)", variable=self.origin).grid(row=0, column=1, sticky="w", padx=12)
        ttk.Checkbutton(box, text="Open results folder when done", variable=self.open_folder).grid(row=0, column=2, sticky="w")
        ttk.Label(box, text="Results folder (empty = next to the file)", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.outdir = tk.StringVar(value=d.get("outdir", ""))
        ttk.Entry(box, textvariable=self.outdir).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(6, 0), padx=(0, 6))
        ttk.Button(box, text="Browse...", command=self.browse_out).grid(row=1, column=3, pady=(6, 0))
        box.columnconfigure(2, weight=1)

        # ---- run row
        row = ttk.Frame(outer); row.pack(fill="x", pady=(8, 4))
        self.run_btn = ttk.Button(row, text="Run analysis", style="Run.TButton", command=self.run)
        self.run_btn.pack(side="left")
        self.progress = ttk.Progressbar(row, mode="indeterminate", length=160)
        self.progress.pack(side="left", padx=10)
        self.status = ttk.Label(row, text="")
        self.status.pack(side="left")
        self.open_btn = ttk.Button(row, text="Open results", command=self.open_results, state="disabled")
        self.open_btn.pack(side="right")
        self.origin_btn = ttk.Button(row, text="Open Origin project", command=self.open_origin, state="disabled")
        self.origin_btn.pack(side="right", padx=4)

        # ---- summary + log
        self.summary = ttk.Label(outer, text="", justify="left", style="Foot.TLabel", wraplength=800)
        self.summary.pack(fill="x")
        self.log = tk.Text(outer, height=12, state="disabled", font=("Consolas", 9), relief="flat", background="#ffffff",
                           foreground=TEXT, highlightthickness=1, highlightbackground=BORDER, padx=8, pady=6)
        self.log.pack(fill="both", expand=True, pady=(4, 0))
        ttk.Label(outer, text=f"electrochem-toolkit {__version__}  ·  {__author__}  ·  GPL-3.0-or-later  ·  {__url__}",
                  style="Foot.TLabel").pack(anchor="w", pady=(6, 0))

        self.queue = queue.Queue()
        if self.file.get() and Path(self.file.get()).exists():
            self.prefill_from_header(self.file.get())
        self.after(100, self._poll)

    # ---- widgets
    def _entry(self, frm, row, col, label, value, width=10):
        ttk.Label(frm, text=label, style="Card.TLabel").grid(row=row, column=col, sticky="w", pady=(4, 0), padx=(0, 4))
        var = tk.StringVar(value=str(value))
        ttk.Entry(frm, textvariable=var, width=width).grid(row=row, column=col + 1, sticky="w", pady=(4, 0), padx=(0, 12))
        return var

    def _poll(self):
        """Worker thread talks to the window only through this queue (tkinter is not thread-safe)."""
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self.write(payload)
                elif kind == "status":
                    self.status.configure(text=payload[0], style=payload[1])
                elif kind == "summary":
                    self.summary.configure(text=payload)
                elif kind == "done":
                    self.progress.stop()
                    self.run_btn.configure(state="normal")
                    if self.last_out and self.last_out.exists():
                        self.open_btn.configure(state="normal")
                        if (self.last_out / "origin").glob("*.opju"):
                            self.origin_btn.configure(state="normal" if list((self.last_out / "origin").glob("*.opju")) else "disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def write(self, text):
        self.log.configure(state="normal"); self.log.insert("end", text); self.log.see("end"); self.log.configure(state="disabled")

    # ---- actions
    def browse(self):
        f = filedialog.askopenfilename(filetypes=[("EC-Lab files", "*.mpr *.mpt"), ("All files", "*.*")])
        if f:
            self.file.set(f)
            self.prefill_from_header(f)

    def browse_out(self):
        f = filedialog.askdirectory()
        if f:
            self.outdir.set(f)

    def help(self):
        p = ROOT / "HOW_TO_USE.txt"
        try:
            os.startfile(p)
        except Exception:
            webbrowser.open(p.as_uri())

    def about(self):
        messagebox.showinfo("About", f"electrochem-toolkit {__version__}\n\nCreated by {__author__}\n"
                                     f"Traceable analysis of BioLogic EC-Lab battery cycling data.\n\n"
                                     f"Licence: GPL-3.0-or-later\n{__url__}")

    def open_results(self):
        if self.last_out:
            try:
                os.startfile(self.last_out)
            except AttributeError:
                subprocess.Popen(["xdg-open", str(self.last_out)])

    def open_origin(self):
        if self.last_out:
            for p in (self.last_out / "origin").glob("*.opju"):
                try:
                    os.startfile(p)
                except AttributeError:
                    pass
                return

    def prefill_from_header(self, f):
        """Fill mass, molar mass and electrons from what EC-Lab recorded, so the numbers cannot be mistyped."""
        self.header = {}
        try:
            lines = metadata.read_header_lines(f)
            self.header = metadata.from_header(lines) if lines else {}
        except Exception:
            self.header = {}
        parts = []
        for key, var, label in (("active_mass_declared", self.mass, "mass"), ("molar_mass_declared", self.molar, "M"),
                                ("electrons_per_ion", self.electrons, "electrons")):
            v = self.header.get(key)
            if isinstance(v, dict) and v.get("value") is not None:
                var.set(f"{v['value']:g}")
                parts.append(f"{label} {v['value']:g} {v.get('unit', '')}".strip())
        tech = self.header.get("technique") or ""
        if parts:
            self.header_note.configure(text=(f"{tech}: " if tech else "") + "header declares " + ", ".join(parts) + " (edit if wrong)")
        else:
            self.header_note.configure(text="No EC-Lab header found next to this file; enter the mass yourself")

    def confirm_mass(self):
        v = self.header.get("active_mass_declared")
        try:
            typed = float(self.mass.get().replace(",", "."))
        except ValueError:
            return True
        if isinstance(v, dict) and v.get("value") and abs(typed - v["value"]) / v["value"] > 0.01:
            return messagebox.askyesno("Check the mass",
                                       f"You entered {typed:g} mg but the EC-Lab header says {v['value']:g} mg.\n\nRun with {typed:g} mg anyway?")
        return True

    def save_defaults(self):
        try:
            SETTINGS.write_text(json.dumps({
                "file": self.file.get(), "cell": self.cell.get(), "reference": self.reference.get(), "charge": self.charge.get(),
                "mass": self.mass.get(), "molar": self.molar.get(), "electrons": self.electrons.get(), "area": self.area.get(),
                "cycles": self.cycles.get(), "refcycle": self.refcycle.get(), "outdir": self.outdir.get(), "figures": self.figures.get(),
                "origin": self.origin.get(), "open_folder": self.open_folder.get()}, indent=2))
        except Exception:
            pass

    def out_dir(self) -> Path:
        f = Path(self.file.get().strip())
        base = Path(self.outdir.get().strip()) if self.outdir.get().strip() else f.parent
        return base / (f.stem + "_analysis")

    def argv(self):
        f = self.file.get().strip()
        if not f or not Path(f).exists():
            raise ValueError("Choose an existing .mpr or .mpt file first (button Browse...).")
        argv = [f, "--no-prompt", "--charge", self.charge.get()]
        if self.cell.get() == "full":
            argv.append("--terminal-voltage")
        elif self.reference.get().strip():
            argv += ["--reference", self.reference.get().strip()]
        for flag, var, name in (("--mass-mg", self.mass, "Active mass"), ("--molar-mass", self.molar, "Molar mass"),
                                ("--electrons", self.electrons, "Electrons"), ("--area-cm2", self.area, "Electrode area")):
            v = var.get().strip().replace(",", ".")
            if v:
                try:
                    float(v)
                except ValueError:
                    raise ValueError(f"{name} must be a number (you typed '{v}').")
                argv += [flag, v]
        argv += ["--cycles", self.cycles.get().strip() or "1", "--reference-cycle", self.refcycle.get().strip() or "1"]
        argv += ["--plots", "all" if self.figures.get() else "none"]
        if not self.origin.get():
            argv.append("--no-origin")
        argv += ["--out", str(self.out_dir())]
        return argv

    def run(self):
        try:
            argv = self.argv()
        except Exception as exc:
            messagebox.showerror("Check the inputs", str(exc))
            return
        if not self.confirm_mass():
            return
        self.save_defaults()
        self.run_btn.configure(state="disabled"); self.open_btn.configure(state="disabled"); self.origin_btn.configure(state="disabled")
        self.status.configure(text="running...", style="Foot.TLabel"); self.summary.configure(text="")
        self.log.configure(state="normal"); self.log.delete("1.0", "end"); self.log.configure(state="disabled")
        self.progress.start(12)
        self.last_out = self.out_dir()
        threading.Thread(target=self._work, args=(argv, self.last_out, self.origin.get(), self.open_folder.get()), daemon=True).start()

    def _work(self, argv, out, build_origin, open_folder):
        q = self.queue

        class Tee:
            def write(s, text): q.put(("log", text))
            def flush(s): pass

        try:
            old = sys.stdout; sys.stdout = Tee()
            try:
                analyze.main(argv)
            finally:
                sys.stdout = old
            try:
                sm = json.loads((out / "summary.json").read_text())
                if sm.get("complete_cycles"):
                    q.put(("summary", self._headline(sm)))
                else:
                    q.put(("summary", "No complete charge/discharge pair was found: check the charge sign and that this is a cycling file."))
            except Exception:
                pass
            if build_origin:
                q.put(("log", "\nBuilding the Origin project...\n"))
                q.put(("log", origin_export.build(out / "origin") + "\n"))
            if open_folder:
                try:
                    os.startfile(out)          # Windows
                except AttributeError:
                    subprocess.Popen(["xdg-open", str(out)])
            q.put(("status", (f"done: {out}", "Ok.TLabel")))
        except Exception as exc:
            q.put(("log", "\n" + friendly(exc) + "\n\nTechnical details:\n" + traceback.format_exc()))
            q.put(("status", ("failed, see the message below", "Bad.TLabel")))
        finally:
            q.put(("done", None))

    @staticmethod
    def _headline(sm) -> str:
        f = lambda v, fmt="{:.4g}": (fmt.format(v) if v is not None else "n/a")
        first = f(sm.get("first_cycle_specific_discharge_mAh_g")) + " mAh/g" if sm.get("first_cycle_specific_discharge_mAh_g") else f(sm.get("first_cycle_discharge_mAh")) + " mAh"
        return (f"{sm['complete_cycles']} complete cycles   ·   first discharge {first}, CE {f(sm.get('first_cycle_coulombic_efficiency_pct'), '{:.1f}')} %   ·   "
                f"retention at cycle {sm.get('last_cycle')}: {f(sm.get('retention_at_last_cycle_pct'), '{:.1f}')} %   ·   "
                f"mean CE {f(sm.get('mean_coulombic_efficiency_pct'), '{:.2f}')} %   ·   fade {f(sm.get('capacity_fade_pct_per_cycle'), '{:.3f}')} %/cycle")


def main():
    try:
        App().mainloop()
    except Exception:
        try:
            messagebox.showerror("electrochem-toolkit", traceback.format_exc())
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    main()
