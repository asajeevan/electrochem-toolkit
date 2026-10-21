"""From the generic reader's RawTable to the engine's Table, and the choice of path for a file.

The validated EC-Lab readers (eclab_import.text, eclab_import.native) stay the only
path for EC-Lab and BT-Lab files: is_eclab() decides from the file's own signature,
never from its extension alone. Every other file goes through a profile, and the
table that comes out here carries the same arrays the EC-Lab path produces, so the
segmentation, the cycling engine, the figures and the exports see no difference.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..table import Table
from .profile import ImportProfile
from .reader import RawTable

ECLAB_SIGNATURES = (b"EC-Lab ASCII FILE", b"BT-Lab ASCII FILE", b"BIO-LOGIC MODULAR FILE")

# The engine's mode codes (EC-Lab's): 1 constant current, 2 constant voltage, 3 rest.
_MODE = {"cc_charge": 1, "cc_discharge": 1, "cv_charge": 2, "cv_discharge": 2, "rest": 3, "ocv": 3}


def is_eclab(path: str | Path) -> bool:
    """True for a file the validated EC-Lab readers handle: an .mpr, or a text export that
    begins with EC-Lab's or BT-Lab's signature line (after an optional byte-order mark)."""
    path = Path(path)
    if path.suffix.lower() == ".mpr":
        return True
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    head = head[3:] if head.startswith(b"\xef\xbb\xbf") else head
    return any(head.lstrip().startswith(s) for s in ECLAB_SIGNATURES)


def native_table(raw: RawTable) -> Table:
    """The engine's Table from a native binary reader's RawTable (readers.lanhe_cex).

    Such a reader states a step type on every row, from the file's own step-start units, so the mode array is
    complete (1 constant current, 2 constant voltage, 3 rest) and a row of unknown type cannot get here (the
    reader refuses it). Its counter increments arrive in Ah and leave in coulombs, like the generic path's."""
    kinds = np.asarray(raw.step_kind, dtype=object)
    mode = np.full(raw.n, np.nan)
    for kind, code in _MODE.items():
        mode[kinds == kind] = code
    if np.isnan(mode).any():
        raise ValueError("a row of the native reader has no known step type")
    rep = raw.report
    return Table(
        source_name=raw.source_name, source_sha256=raw.source_sha256, format=raw.profile,
        columns=tuple(raw.columns), t=raw.t, i=raw.i, e=raw.e, ns=raw.step_id, mode=mode, oxred=None, error=None,
        half_cycle=None, cycle=raw.cycle, q_instrument=None, dq=raw.dq * 3600.0 if raw.dq is not None else None,
        temperature=raw.temperature, invalid_rows={}, labels=dict(rep.get("labels", {})), header=(),
        potentials={rep.get("potential_name", "voltage"): raw.e}, paused=raw.paused_rows,
    )


def to_table(raw: RawTable, profile: ImportProfile) -> Table:
    """The engine's Table from a RawTable: SI arrays, charge-positive current, the instrument's
    charge increments in coulombs, and labels naming the source columns.

    What the generic path does not provide is left None and the engine falls back as it does
    for an EC-Lab file lacking the same column: no ox/red flag (direction comes from the sign
    of the current), no error flag, no half-cycle counter. The mode array is derived from the
    step types when the profile's vocabulary names constant-voltage stages; a step type the
    profile calls "other" is then constant current where current flows and rest where it does
    not. A vocabulary that names direction only yields no mode array (see below).
    """
    n = raw.n
    mode = None
    # A vocabulary that never names a constant-voltage stage cannot label one: Maccor's State
    # ('C', 'D', 'R') and Basytec's Command ('Charge') give the direction only, and a CC-CV
    # charge is one 'C' run. Labelling such rows constant current would make the engine report a
    # constant-voltage share of 0 % for a charge that ends in a voltage hold, so no mode array is
    # built and the engine takes rest from zero current, as for an EC-Lab file without a mode
    # column; the CC/CV split is then not reported rather than reported wrong.
    names_cv = any(k.startswith("cv_") for k in profile.conventions.step_type_map.values())
    if raw.step_kind is not None and names_cv:
        kinds = np.asarray(raw.step_kind, dtype=object)
        mode = np.full(n, np.nan)
        for kind, code in _MODE.items():
            mode[kinds == kind] = code
        other = np.isnan(mode)
        if other.any():
            flowing = np.abs(np.nan_to_num(raw.i[other])) > 0
            mode[other] = np.where(flowing, 1, 3)
    dq = raw.dq * 3600.0 if raw.dq is not None else None          # Ah -> C
    rep = raw.report.get("columns_resolved", {})

    def col(role):
        d = rep.get(role)
        return d.get("column") if d else None

    labels = {k: v for k, v in (("time", col("test_time_second")), ("current", col("current_ampere")),
                                 ("potential", col("voltage_volt")), ("step", col("step_id")),
                                 ("cycle", col("cycle_count")), ("mode", col("step_type")),
                                 ("temperature", col("surface_temperature_celsius")
                                  or col("ambient_temperature_celsius"))) if v}
    if dq is not None:
        src = [c for c in (col("net_capacity_ah"), col("charging_capacity_ah"),
                           col("discharging_capacity_ah")) if c]
        labels["dq"] = f"derived from {' and '.join(src)} ({raw.report.get('capacity_semantics')})"
    tab = Table(
        source_name=raw.source_name, source_sha256=raw.source_sha256, format=profile.name,
        columns=tuple(raw.columns), t=raw.t, i=raw.i, e=raw.e,
        ns=raw.step_id, mode=mode, oxred=None, error=None, half_cycle=None, cycle=raw.cycle,
        q_instrument=None, dq=dq, temperature=raw.temperature,
        invalid_rows=dict(raw.report.get("invalid_tokens", {})), labels=labels, header=(),
        potentials={col("voltage_volt") or "voltage": raw.e},
    )
    return tab
