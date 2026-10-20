"""Large exports (P08f): bounded memory, no long stall, and the same answer as a small file.

A synthetic Arbin MITS Pro CSV of 2 000 000 rows and 14 columns (about 300 MB) is written in
blocks, then read by the arbin-csv profile in a separate Python process, so that the peak
resident memory measured is the reader's and not the writer's: the child's own high-water mark
(VmHWM in /proc/self/status; ru_maxrss, which on Linux carries the parent's resident size across
fork and exec, only where /proc is absent).
The test prints the time and the peak memory, and asserts below 90 s and 1.5 GB. The arrays are
checked against the experiment the file was written from, and the capacities against the
constructed truth, so a fast wrong answer cannot pass either.

The whole-grid reader this replaces held every field of every row as a Python string. Measured on
this machine (docs/handoffs/P08f_Large_Files_Handoff.md, VmHWM of a process doing nothing else):
on this 2 000 000-row file it peaked at 3940 MB and took 25.7 s; the streaming reader peaks at
about 320 MB and takes about 12 s warm.

Set ELECTROCHEM_LARGE_ROWS to change the row count (the test is skipped at 0).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
ROWS = int(os.environ.get("ELECTROCHEM_LARGE_ROWS", "2000000"))
STEP_ROWS = 2500                   # rows per programmed step, 1 s apart
CURRENT_A = 0.0125
HEADER = ["Data_Point", "Date_Time", "Test_Time(s)", "Step_Time(s)", "Step_Index", "Cycle_Index", "Current(A)",
          "Voltage(V)", "Charge_Capacity(Ah)", "Discharge_Capacity(Ah)", "Charge_Energy(Wh)",
          "Discharge_Energy(Wh)", "dV/dt(V/s)", "Internal_Resistance(Ohm)"]


def experiment(n: int):
    """Rest, constant-current charge, rest, constant-current discharge, repeated; one row per second.
    Counters accumulate by the trapezoidal rule within a cycle and restart at each cycle, as the
    profile declares (cycle_cumulative)."""
    k = np.arange(n)
    step_seq = k // STEP_ROWS                         # programmed step number from 0
    step = 1 + step_seq % 4
    cycle = 1 + step_seq // 4
    cur = np.select([step == 2, step == 4], [CURRENT_A, -CURRENT_A], 0.0)
    t = k.astype(float)
    in_step = k % STEP_ROWS
    v = 3.6 + np.select([step == 2, step == 4], [1e-4 * in_step / 2.5, -1e-4 * in_step / 2.5], 0.0)
    inc = np.where(in_step > 0, cur, 0.0) * 1.0 / 3600.0  # the first row of a step accrues nothing
    qc = np.zeros(n)
    qd = np.zeros(n)
    for c in np.unique(cycle):
        m = cycle == c
        qc[m] = np.cumsum(np.where(inc > 0, inc, 0.0)[m])
        qd[m] = np.cumsum(np.where(inc < 0, -inc, 0.0)[m])
    return dict(k=k, t=t, step=step, cycle=cycle, cur=cur, v=v, qc=qc, qd=qd, in_step=in_step)


def write_arbin(path: Path, n: int, block: int = 100_000) -> None:
    import datetime as dt
    e = experiment(n)
    t0 = dt.datetime(2026, 1, 1)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(",".join(HEADER) + "\r\n")
        for a in range(0, n, block):
            b = min(n, a + block)
            s = slice(a, b)
            stamp = [(t0 + dt.timedelta(seconds=float(x))).strftime("%Y-%m-%d %H:%M:%S") + ".000" for x in e["t"][s]]
            cols = [list(map(str, e["k"][s] + 1)), stamp, list(map("{:.4f}".format, e["t"][s])),
                    list(map("{:.4f}".format, e["in_step"][s].astype(float))), list(map(str, e["step"][s])),
                    list(map(str, e["cycle"][s])), list(map("{:.6f}".format, e["cur"][s])),
                    list(map("{:.6f}".format, e["v"][s])), list(map("{:.9f}".format, e["qc"][s])),
                    list(map("{:.9f}".format, e["qd"][s])), list(map("{:.9f}".format, e["qc"][s] * 3.7)),
                    list(map("{:.9f}".format, e["qd"][s] * 3.7)), ["0.000E+00"] * (b - a), ["0.0425"] * (b - a)]
            fh.write("\r\n".join(map(",".join, zip(*cols))) + "\r\n")


READ_AND_MEASURE = textwrap.dedent("""
    import json, sys, time
    sys.path.insert(0, sys.argv[1])
    from electrochem.readers.builtin import ARBIN_CSV
    from electrochem.readers.reader import read
    import numpy as np

    def high_water_kib():
        # VmHWM is this process's own peak (Linux); PeakWorkingSetSize on Windows (psapi); ru_maxrss
        # elsewhere (on Linux it would carry the parent's resident size across fork and exec)
        try:
            with open("/proc/self/status") as fh:
                for line in fh:
                    if line.startswith("VmHWM:"):
                        return int(line.split()[1])
        except OSError:
            pass
        if sys.platform == "win32":
            import ctypes, ctypes.wintypes as wt
            class C(ctypes.Structure):
                _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]
            c = C(); c.cb = ctypes.sizeof(C)
            ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
            return c.PeakWorkingSetSize // 1024
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    base = high_water_kib()
    calls = []
    t0 = time.perf_counter()
    tab = read(sys.argv[2], ARBIN_CSV, progress=lambda r, b, tot: calls.append((r, b, tot)))
    elapsed = time.perf_counter() - t0
    peak = high_water_kib()
    np.savez(sys.argv[3], t=tab.t, i=tab.i, e=tab.e, step=tab.step_id, cycle=tab.cycle, dq=tab.dq)
    print(json.dumps({"seconds": elapsed, "peak_kib": peak, "baseline_kib": base, "n": tab.n,
                      "codes": [f["code"] for f in tab.findings], "progress_calls": len(calls),
                      "last_progress": calls[-1] if calls else None,
                      "semantics": tab.report["capacity_semantics_consistent"]}))
""")


@pytest.mark.skipif(ROWS <= 0, reason="ELECTROCHEM_LARGE_ROWS=0")
def test_a_two_million_row_arbin_export_reads_in_bounded_memory_and_time(tmp_path):
    path = tmp_path / "big_arbin.csv"
    write_arbin(path, ROWS)
    size = path.stat().st_size
    out = tmp_path / "arrays.npz"
    proc = subprocess.run([sys.executable, "-c", READ_AND_MEASURE, str(ROOT), str(path), str(out)],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stderr[-3000:]
    m = json.loads(proc.stdout.strip().splitlines()[-1])
    peak_mb = m["peak_kib"] / 1024
    print(f"\n[P08f] {ROWS:,} rows x {len(HEADER)} columns, {size / 2**20:.0f} MiB: read in {m['seconds']:.1f} s, "
          f"peak resident memory {peak_mb:.0f} MB (interpreter and imports before reading: "
          f"{m['baseline_kib'] / 1024:.0f} MB), {m['progress_calls']} progress calls")
    assert m["n"] == ROWS
    assert m["last_progress"] == [ROWS, size, size]
    assert m["seconds"] < 90.0
    assert peak_mb < 1536.0
    e = experiment(ROWS)
    got = np.load(out)
    assert np.array_equal(got["t"], e["t"])
    assert np.array_equal(got["step"], e["step"].astype(float)) and np.array_equal(got["cycle"], e["cycle"].astype(float))
    assert np.allclose(got["i"], e["cur"], rtol=0, atol=5e-7) and np.allclose(got["e"], e["v"], rtol=0, atol=5e-7)
    # the instrument counter, read back as increments, gives the constructed charge and discharge
    inside = e["in_step"] > 0
    true_c = float(e["cur"][inside & (e["cur"] > 0)].sum()) / 3600.0
    true_d = float(-e["cur"][inside & (e["cur"] < 0)].sum()) / 3600.0
    dq = got["dq"]
    assert float(dq[dq > 0].sum()) == pytest.approx(true_c, rel=1e-6)
    assert float(-dq[dq < 0].sum()) == pytest.approx(true_d, rel=1e-6)
    assert "invalid_tokens" not in m["codes"] and "counter_agrees_with_integral" in m["codes"]
    assert m["semantics"] == ["cycle_cumulative"]


def _sizes(wb):
    return {ws.title: (ws.min_column, ws.min_row, ws.max_column, ws.max_row) for ws in wb.worksheets}


def test_sizing_a_sheet_finds_the_same_dimension(tmp_path):
    """open_workbook sizes each sheet from start events (stopping at <sheetData>) instead of
    openpyxl's end events (which parse a dimension-less sheet to its end): the sizes must be the
    ones openpyxl finds, with and without a declared dimension, and openpyxl is left as it was."""
    from openpyxl import Workbook, load_workbook
    from openpyxl.worksheet._read_only import ReadOnlyWorksheet
    from electrochem.readers.workbook import open_workbook
    original = ReadOnlyWorksheet._get_size
    files = sorted((ROOT / "data" / "public").glob("*/*.xlsx"))
    wo = Workbook(write_only=True)                       # write-only output declares no dimension
    ws = wo.create_sheet("records")
    for k in range(300):
        ws.append([k, k * 0.5, "x"])
    wo.save(tmp_path / "no_dimension.xlsx")
    normal = Workbook()
    normal.active.append(["a", "b"])
    normal.active["D7"] = 3
    normal.create_sheet("empty")
    normal.save(tmp_path / "with_dimension.xlsx")
    files += [tmp_path / "no_dimension.xlsx", tmp_path / "with_dimension.xlsx"]
    for f in files:
        a = load_workbook(f, read_only=True, data_only=True)
        b = open_workbook(f)
        try:
            assert _sizes(a) == _sizes(b), f.name
            for x, y in zip(a.worksheets, b.worksheets):
                assert list(x.iter_rows(values_only=True)) == list(y.iter_rows(values_only=True)), f.name
        finally:
            a.close()
            b.close()
    assert _sizes(load_workbook(tmp_path / "no_dimension.xlsx", read_only=True))["records"][2] is None
    assert ReadOnlyWorksheet._get_size is original
