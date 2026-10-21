"""Segmentation of a cycling Table into supported edges, branches and cycle pairs.

Rules (M01 section 5, P02 cases S07 to S19):

* An *edge* is the interval between two consecutive rows. Charge is only
  integrated over supported edges. An edge is unsupported when time does not
  advance (reset or duplicate), when either current sample is missing, when an
  instrument error flag is set, or when the current changes sign across a
  programmed step boundary (S10). A programmed step boundary with advancing
  time and unchanged direction is included and reported.
* A *branch* is a maximal run of non-rest rows with one current direction.
  Constant-current and constant-voltage steps of the same direction belong to
  the same branch (S05). A branch that reaches the end of the data, or that
  contains an unsupported edge, is *partial* (S07, S08, S15). Of its unsupported
  edges, those where time goes back or is invalid, a current is missing, or an
  error flag is set are *curve breaks*: the potential after one need not continue
  the curve before it, so the branch has no dQ/dE (M01 section 9.3). A
  zero-duration edge is not one (a time printed coarsely, or a programmed
  discontinuity, loses no time). A pause the instrument marks inside a branch
  (Table.paused) is integrated as usual, the record time not counting it, but
  the potential relaxes during it, so such a branch has no dQ/dE either. A
  break or pause counts only where the dQ/dE curve lies on both sides of it:
  the curve leaves out constant-voltage rows, so one inside a constant-voltage
  hold, or between the constant-current part and the hold, cannot fold it.
* A *pair* is one charge branch and the discharge branch that follows it (or
  the reverse order, if the protocol starts with discharge). Unpaired branches
  are reported, never silently dropped (S16).

Direction naming needs an explicit convention. Without one, branches are
labelled by current sign only and charge/discharge quantities stay unavailable
(S13).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .table import Table, MODE_LABELS

REST = 3
CC = 1
CV = 2

# why an edge is unsupported (Edge.reason)
TIME_INVALID = "time reset or invalid time"
ZERO_DURATION = "zero-duration programmed discontinuity"
CURRENT_INVALID = "missing or invalid current"
ERROR_FLAG = "instrument error flag"
REVERSAL = "current sign change across programmed boundary"
CURVE_BREAKS = (TIME_INVALID, CURRENT_INVALID, ERROR_FLAG)


@dataclass
class Edge:
    supported: np.ndarray            # bool, length n-1
    reason: dict[int, str]           # index -> reason for unsupported edges
    boundary_included: list[int]     # programmed boundaries that were included


@dataclass
class Branch:
    index: int
    start: int                       # first row (inclusive)
    end: int                         # last row (inclusive)
    sign: int                        # +1 positive current, -1 negative
    direction: str                   # "charge", "discharge" or "positive"/"negative"
    steps: tuple[int, ...]
    modes: tuple[str, ...]
    terminated_by: str
    complete: bool
    unsupported_edges: int
    native_cycle: int | None
    native_half_cycle: int | None
    notes: list[str] = field(default_factory=list)
    curve_breaks: int = 0            # unsupported edges of a CURVE_BREAKS reason: no dQ/dE for the branch
    pauses: int = 0                  # marked pauses inside the branch (Table.paused): no dQ/dE for it either
    breaks_why: tuple[str, ...] = ()  # the reasons of its curve breaks, each once

    @property
    def rows(self):
        return slice(self.start, self.end + 1)


@dataclass
class Pair:
    index: int                       # 1-based cycle index assigned here
    charge: Branch | None
    discharge: Branch | None
    complete: bool
    native_cycle: int | None
    note: str = ""


@dataclass
class Segmentation:
    edges: Edge
    branches: list[Branch]
    pairs: list[Pair]
    convention: dict


def _mode_array(tab: Table, rest_current_a: float) -> np.ndarray:
    if tab.mode is not None and np.all(np.isfinite(tab.mode)):
        return tab.mode.astype(int)
    if tab.i is None:
        raise ValueError("Neither a mode column nor a current column is available")
    mode = np.where(np.abs(np.nan_to_num(tab.i)) <= rest_current_a, REST, 0)
    return mode.astype(int)


def _runs(tab: Table, mode: np.ndarray) -> tuple[np.ndarray, str, str | None]:
    """Row indices where a run starts, a run being the rows whose direction is decided together.

    With a step (Ns) column, a run is one programmed step. Without one, a run
    ends wherever the measured current changes sign. Treating a file without a
    step column as one run gave a single direction to every row, so a charge
    and the discharge after it became one branch whose charge was their
    difference (independent review, finding r13). Rows whose sign cannot be
    read (a missing current, or exactly zero inside an active stretch) belong
    to the run before them; leading ones to the first readable run.
    """
    n = tab.n
    if tab.ns is not None:
        cuts = np.flatnonzero(np.diff(tab.ns) != 0) + 1
        return cuts, ("net measured current per step run" if tab.i is not None else "ox/red flag per step run"), None
    if tab.i is not None:
        rs = np.where(np.isfinite(tab.i), np.sign(tab.i), 0).astype(int)
        evidence = "sign of the measured current, row by row (the file has no step column)"
    elif tab.oxred is not None:
        rs = np.where(np.isfinite(tab.oxred), np.where(tab.oxred > 0.5, 1, -1), 0).astype(int)
        evidence = "ox/red flag, row by row (the file has no step column)"
    else:
        return np.array([], dtype=int), "none", None
    active = mode != REST
    rs[~active] = 0
    known = rs != 0
    if known.any():
        idx = np.where(known, np.arange(n), 0)
        np.maximum.accumulate(idx, out=idx)
        filled = rs[idx]
        first = int(np.argmax(known))
        filled[:first] = rs[first]
    else:
        filled = rs
    key = np.where(active, filled, 2)          # rest rows form runs of their own
    cuts = np.flatnonzero(np.diff(key) != 0) + 1
    return cuts, evidence, "No step (Ns) column: a branch ends wherever the measured current changes sign"


def _sign_array(tab: Table, mode: np.ndarray) -> tuple[np.ndarray, str, list[str]]:
    """Per-row current direction (+1/-1, 0 in rest).

    Direction is decided per programmed step run from the sign of the net
    measured current in that run, because the first row of a step still
    carries the previous step's ox/red flag. The ox/red flag is used as a
    cross-check and as the fallback when no current column exists.
    """
    n = tab.n
    sign = np.zeros(n, dtype=int)
    notes: list[str] = []
    runs, evidence, run_note = _runs(tab, mode)
    if run_note:
        notes.append(run_note)
    starts = np.concatenate(([0], runs))
    ends = np.concatenate((runs, [n]))
    for a, b in zip(starts, ends):
        if np.all(mode[a:b] == REST):
            continue
        active = mode[a:b] != REST
        if tab.i is not None and np.any(np.isfinite(tab.i[a:b][active])):
            cur = tab.i[a:b][active]
            s = 1 if np.nansum(cur) >= 0 else -1
            if tab.oxred is not None:
                flag = np.where(tab.oxred[a:b][active] > 0.5, 1, -1)
                disagree = float(np.mean(flag != s))
                if disagree > 0.05:
                    where = f"step {int(tab.ns[a])}" if tab.ns is not None else f"rows {a + 1} to {b}"
                    notes.append(f"{where}: ox/red flag disagrees with current sign in {disagree:.0%} of rows")
        elif tab.oxred is not None:
            s = 1 if np.nanmean(tab.oxred[a:b][active]) >= 0.5 else -1
        else:
            raise ValueError("No current column and no ox/red flag; direction cannot be established")
        sign[a:b][active] = s
    return sign, evidence, notes


def edges(tab: Table, sign: np.ndarray, mode: np.ndarray) -> Edge:
    """Which edges carry charge, with the reason for each that does not.

    Vectorised (a two-million-row file took eight seconds in a row-by-row loop,
    P08f); the rules and their order of precedence are the ones in the module
    docstring, and a test compares this with the row-by-row form on random tables.
    """
    n = tab.n
    dt = np.diff(tab.t)
    i = tab.i if tab.i is not None else np.zeros(n)
    err = tab.error if tab.error is not None else np.zeros(n)
    ns = tab.ns if tab.ns is not None else np.zeros(n)
    bad_time = ~np.isfinite(dt) | (dt < 0)
    zero = ~bad_time & (dt == 0)
    fin = np.isfinite(i)
    bad_i = ~bad_time & ~zero & ~(fin[:-1] & fin[1:])
    flagged = ~bad_time & ~zero & ~bad_i & ((err[:-1] != 0) | (err[1:] != 0))
    boundary = ~bad_time & ~zero & ~bad_i & ~flagged & (ns[:-1] != ns[1:])
    active = (mode[:-1] != REST) & (mode[1:] != REST)
    reversal = boundary & active & (sign[:-1] != sign[1:])
    supported = ~(bad_time | zero | bad_i | flagged | reversal)
    reason: dict[int, str] = {}
    for mask, text in ((bad_time, TIME_INVALID), (zero, ZERO_DURATION), (bad_i, CURRENT_INVALID),
                       (flagged, ERROR_FLAG), (reversal, REVERSAL)):
        for k in np.flatnonzero(mask):
            reason[int(k)] = text
    reason = dict(sorted(reason.items()))
    included = [int(k) for k in np.flatnonzero(boundary & ~reversal)]
    return Edge(supported, reason, included)


def branches(tab: Table, sign: np.ndarray, mode: np.ndarray, edge: Edge, charge: str | None) -> list[Branch]:
    """Maximal runs of non-rest rows with one current sign (a row with sign 0 outside a rest ends a run and
    belongs to none). Run detection is vectorised; the per-branch bookkeeping is unchanged."""
    n = tab.n
    key = np.where(mode == REST, 0, sign)
    cuts = np.flatnonzero(np.diff(key) != 0) + 1
    starts = np.concatenate(([0], cuts))
    ends = np.concatenate((cuts, [n])) - 1               # inclusive
    unsupported_before = np.concatenate(([0], np.cumsum(~edge.supported)))   # count over edges [0, k)
    breaks = np.zeros(max(n - 1, 0), bool)
    breaks[[k for k, why in edge.reason.items() if why in CURVE_BREAKS]] = True
    breaks_before = np.concatenate(([0], np.cumsum(breaks)))
    paused = np.zeros(n, bool)
    rows = getattr(tab, "paused", None)
    if rows is not None and len(rows):
        paused[np.asarray(rows, dtype=np.int64)] = True
    paused_before = np.concatenate(([0], np.cumsum(paused)))         # count over rows [0, k)
    out: list[Branch] = []
    for start, end in zip(starts.tolist(), ends.tolist()):
        s = int(key[start])
        if s == 0:
            continue
        if end + 1 >= n:
            terminated = "end of data"
        elif mode[end + 1] == REST:
            terminated = "rest"
        else:
            terminated = "direction change"
        unsupported = int(unsupported_before[end] - unsupported_before[start])
        steps = tuple(sorted(set(int(x) for x in (np.unique(tab.ns[start:end + 1]) if tab.ns is not None else [0]))))
        modes = tuple(MODE_LABELS.get(int(m), "unknown") for m in dict.fromkeys(mode[start:end + 1].tolist()))
        direction = _direction(s, charge)
        # the curve's rows: outside constant-voltage stages. A break before row j (edge j-1) or a pause before row j
        # folds the curve only with curve rows on both sides: first_nc < j <= last_nc
        nc = np.flatnonzero(mode[start:end + 1] != CV) + start
        first_nc, last_nc = (int(nc[0]), int(nc[-1])) if nc.size else (end, end)
        b = Branch(
            index=len(out) + 1, start=start, end=end, sign=s, direction=direction,
            steps=steps, modes=modes, terminated_by=terminated,
            complete=(terminated != "end of data") and unsupported == 0,
            unsupported_edges=unsupported,
            native_cycle=int(tab.cycle[end]) if tab.cycle is not None and np.isfinite(tab.cycle[end]) else None,
            native_half_cycle=int(tab.half_cycle[end]) if tab.half_cycle is not None and np.isfinite(tab.half_cycle[end]) else None,
            curve_breaks=int(breaks_before[last_nc] - breaks_before[first_nc]),          # edges first_nc .. last_nc-1
            pauses=int(paused_before[last_nc + 1] - paused_before[first_nc + 1]),        # rows first_nc+1 .. last_nc
        )
        if b.curve_breaks:
            b.breaks_why = tuple(sorted({edge.reason[int(k)] for k in np.flatnonzero(breaks[first_nc:last_nc]) + first_nc}))
        if terminated == "end of data":
            b.notes.append("last branch reaches the end of the file; treated as interrupted")
        if unsupported:
            b.notes.append(f"{unsupported} unsupported edge(s) inside the branch")
        out.append(b)
    return out


def _direction(sign: int, charge: str | None) -> str:
    if charge is None:
        return "positive" if sign > 0 else "negative"
    charge_sign = {"ox": 1, "positive": 1, "red": -1, "negative": -1}[charge]
    return "charge" if sign == charge_sign else "discharge"


def pairs(brs: list[Branch], order: str, charge: str | None) -> list[Pair]:
    """Pair consecutive branches into cycles. order: 'charge-first' or 'discharge-first'."""
    if charge is None:
        return []
    first, second = ("charge", "discharge") if order == "charge-first" else ("discharge", "charge")
    out: list[Pair] = []
    k = 0
    while k < len(brs):
        b = brs[k]
        if b.direction == first and k + 1 < len(brs) and brs[k + 1].direction == second:
            c, d = (b, brs[k + 1]) if first == "charge" else (brs[k + 1], b)
            out.append(Pair(len(out) + 1, c, d, c.complete and d.complete, d.native_cycle))
            k += 2
        else:
            c, d = (b, None) if b.direction == "charge" else (None, b)
            out.append(Pair(len(out) + 1, c, d, False, b.native_cycle,
                            note=f"unpaired {b.direction} branch"))
            k += 1
    return out


def segment(tab: Table, *, charge: str | None = None, order: str = "charge-first",
            rest_current_a: float = 0.0) -> Segmentation:
    """Segment a Table.

    charge: which current sign is the charge of the cell: "ox"/"positive" or
    "red"/"negative". None keeps branches labelled by sign only.
    """
    mode = _mode_array(tab, rest_current_a)
    sign, evidence, notes = _sign_array(tab, mode)
    edge = edges(tab, sign, mode)
    brs = branches(tab, sign, mode, edge, charge)
    prs = pairs(brs, order, charge)
    convention = {
        "charge_current": charge, "direction_evidence": evidence, "cycle_order": order,
        "mode_source": "mode column" if tab.mode is not None else f"|I| <= {rest_current_a} A is rest",
        "rest_rows_excluded": int(np.sum(mode == REST)),
        "supported_edges": int(edge.supported.sum()), "unsupported_edges": int((~edge.supported).sum()),
        "programmed_boundaries_included": len(edge.boundary_included),
        "notes": notes,
    }
    return Segmentation(edge, brs, prs, convention)
