"""The vectorised segmentation (P08f) gives exactly what the row-by-row rules give, and scales to large files.

The reference implementation below is the row-by-row form of the rules in the module docstring of
`electrochem/segment.py`, kept here as the specification: the vectorised code must agree with it on
random tables that hit every rule (time resets, duplicate times, missing current, error flags, sign
changes across step boundaries, rests, zero current inside an active stretch, the last branch reaching
the end of the file), including which unsupported edges break the dQ/dE curve.
"""
import time
from dataclasses import asdict

import numpy as np
import pytest

from electrochem import segment as seg_module
from electrochem.segment import REST, Branch, Edge, segment
from electrochem.table import Table


def edges_reference(tab, sign, mode):
    n = tab.n
    supported = np.ones(n - 1, dtype=bool)
    reason = {}
    included = []
    dt = np.diff(tab.t)
    i = tab.i if tab.i is not None else np.zeros(n)
    err = tab.error if tab.error is not None else np.zeros(n)
    ns = tab.ns if tab.ns is not None else np.zeros(n)
    for k in range(n - 1):
        if not np.isfinite(dt[k]) or dt[k] < 0:
            supported[k] = False; reason[k] = "time reset or invalid time"
        elif dt[k] == 0:
            supported[k] = False; reason[k] = "zero-duration programmed discontinuity"
        elif not (np.isfinite(i[k]) and np.isfinite(i[k + 1])):
            supported[k] = False; reason[k] = "missing or invalid current"
        elif err[k] or err[k + 1]:
            supported[k] = False; reason[k] = "instrument error flag"
        elif ns[k] != ns[k + 1]:
            active = mode[k] != REST and mode[k + 1] != REST
            if active and sign[k] != sign[k + 1]:
                supported[k] = False; reason[k] = "current sign change across programmed boundary"
            else:
                included.append(k)
    return Edge(supported, reason, included)


def branches_reference(tab, sign, mode, edge, charge):
    n = tab.n
    out = []
    k = 0
    while k < n:
        if mode[k] == REST or sign[k] == 0:
            k += 1
            continue
        start = k
        s = sign[k]
        while k + 1 < n and mode[k + 1] != REST and sign[k + 1] == s:
            k += 1
        end = k
        terminated = "end of data" if end + 1 >= n else ("rest" if mode[end + 1] == REST else "direction change")
        unsupported = sum(1 for e in range(start, end) if not edge.supported[e])
        kinds = ("time reset or invalid time", "missing or invalid current", "instrument error flag")
        curve_rows = [r for r in range(start, end + 1) if mode[r] != seg_module.CV]   # dQ/dE leaves out CV rows
        lo, hi = (curve_rows[0], curve_rows[-1]) if curve_rows else (end, end)
        breaks = sum(1 for e in range(lo, hi) if edge.reason.get(e) in kinds)        # curve rows on both sides
        why = tuple(sorted({edge.reason[e] for e in range(lo, hi) if edge.reason.get(e) in kinds}))
        steps = tuple(sorted(set(int(x) for x in (tab.ns[start:end + 1] if tab.ns is not None else [0]))))
        modes = tuple(seg_module.MODE_LABELS.get(int(m), "unknown") for m in dict.fromkeys(mode[start:end + 1]))
        b = Branch(index=len(out) + 1, start=start, end=end, sign=int(s), direction=seg_module._direction(s, charge),
                   steps=steps, modes=modes, terminated_by=terminated,
                   complete=(terminated != "end of data") and unsupported == 0, unsupported_edges=unsupported,
                   native_cycle=int(tab.cycle[end]) if tab.cycle is not None and np.isfinite(tab.cycle[end]) else None,
                   native_half_cycle=None, curve_breaks=breaks, breaks_why=why)
        if terminated == "end of data":
            b.notes.append("last branch reaches the end of the file; treated as interrupted")
        if unsupported:
            b.notes.append(f"{unsupported} unsupported edge(s) inside the branch")
        out.append(b)
        k += 1
    return out


def random_table(rng, n):
    t = np.cumsum(rng.choice([0.0, 1.0, 1.0, 1.0, 2.0, -3.0, np.nan], size=n, p=[.05, .5, .2, .1, .1, .03, .02]))
    i = rng.choice([1e-3, -1e-3, 0.0, np.nan], size=n, p=[.45, .4, .1, .05])
    ns = np.cumsum(rng.random(n) < 0.05)
    mode = rng.choice([1, 2, 3], size=n, p=[.6, .2, .2])
    err = rng.choice([0, 1], size=n, p=[.97, .03])
    cyc = np.cumsum(rng.random(n) < 0.02).astype(float)
    return Table("r", "0" * 64, "x", ("t",), t, i, 3.0 + rng.random(n), ns, mode, None, err, None, cyc, None, None)


def test_vectorised_edges_and_branches_equal_the_row_by_row_rules():
    rng = np.random.default_rng(2026)
    compared = 0
    for _ in range(250):
        tab = random_table(rng, int(rng.integers(2, 300)))
        mode = seg_module._mode_array(tab, 0.0)
        try:
            sign, _, _ = seg_module._sign_array(tab, mode)
        except ValueError:
            continue                                     # a step with no readable current: refused either way
        for charge in (None, "ox", "red"):
            ref_e = edges_reference(tab, sign, mode)
            got_e = seg_module.edges(tab, sign, mode)
            assert np.array_equal(ref_e.supported, got_e.supported)
            assert ref_e.reason == got_e.reason and ref_e.boundary_included == got_e.boundary_included
            ref_b = branches_reference(tab, sign, mode, ref_e, charge)
            got_b = seg_module.branches(tab, sign, mode, got_e, charge)
            assert [asdict(b) for b in ref_b] == [asdict(b) for b in got_b]
            compared += 1
    assert compared > 500


def big_table(n_cycles=495, rows=2000, rest=20):
    parts = []
    for c in range(n_cycles):
        for step, (n, cur, md) in enumerate(((rows, 1e-3, 1), (rest, 0.0, 3), (rows, -1e-3, 1), (rest, 0.0, 3))):
            parts.append((n, cur, md, 4 * c + step, c))
    total = sum(p[0] for p in parts)
    t = np.arange(total, dtype=float)
    i = np.concatenate([np.full(n, cur) for n, cur, *_ in parts])
    mode = np.concatenate([np.full(n, md, dtype=np.int8) for n, cur, md, *_ in parts])
    ns = np.concatenate([np.full(n, s, dtype=np.int32) for n, cur, md, s, _ in parts])
    cycle = np.concatenate([np.full(n, c, dtype=np.int32) for n, cur, md, s, c in parts])
    e = 3.0 + 0.5 * np.sin(np.linspace(0, 20, total))
    return Table("big", "0" * 64, "synthetic", ("t",), t, i, e, ns, mode, None, None, None, cycle, None, None)


def test_two_million_rows_segment_in_seconds_not_minutes():
    """A two-million-row table (a long Arbin export) segmented in under two seconds; the row-by-row form
    took eight. The branch count and the charge of the first cycle are the ones built in."""
    from electrochem.cycling import Settings, analyse
    tab = big_table()
    assert tab.n > 1_900_000
    t0 = time.time()
    seg = segment(tab, charge="ox")
    elapsed = time.time() - t0
    assert len(seg.branches) == 990 and len(seg.pairs) == 495 and all(p.complete for p in seg.pairs)
    assert elapsed < 2.0, elapsed
    an = analyse(tab, seg, Settings(charge="ox", terminal_voltage=True))
    assert an.cycles[0].charge_capacity_mAh == pytest.approx(1e-3 * 1999 / 3.6, rel=1e-12)
