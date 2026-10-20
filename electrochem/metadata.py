"""Experiment metadata from an EC-Lab text header.

The header is the only place an export records the sample description, the
mass and molar mass the operator typed into EC-Lab, and the programmed step
table. Values are reported as *declared by the operator in EC-Lab*, not as
verified facts; the analysis uses the mass only when the user passes it
explicitly, and the header value is written beside it so a mismatch is
visible.
"""
from __future__ import annotations

import re
from datetime import datetime

_KEYS = {
    "Acquisition started on": "acquisition_started",
    "Run on channel": "channel",
    "Device": "device",
    "Electrode material": "electrode_material",
    "Initial state": "initial_state",
    "Electrolyte": "electrolyte",
    "Mass of active material": "active_mass_declared",
    "Molecular weight of active material (at x = 0)": "molar_mass_declared",
    "Atomic weight of intercalated ion": "ion_atomic_weight",
    "Acquisition started at": "x0",
    "Number of e- transfered per intercalated ion": "electrons_per_ion",
    "for DX = 1, DQ": "charge_per_unit_x",
    "Battery capacity": "battery_capacity",
    "Electrode surface area": "electrode_area_declared",
    "Characteristic mass": "characteristic_mass",
    "Cycle Definition": "cycle_definition",
    "Loaded Setting File": "settings_file",
    "Electrode connection": "electrode_connection",
    "Potential control": "potential_control",
    "Ewe ctrl range": "potential_control_range",
}

_TEXT_ONLY = {"acquisition_started", "channel", "potential_control_range", "settings_file", "cycle_definition",
              "electrode_material", "initial_state", "electrolyte", "electrode_connection", "potential_control"}

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _value(text: str):
    """'4.817 mg' -> (4.817, 'mg'); 'xo = 2.000' -> (2.0, ''); plain text stays text."""
    m = _NUM.search(text)
    if m and text.strip().startswith(("xo", "=")) or (m and m.start() == 0):
        unit = text[m.end():].strip()
        return {"value": float(m.group()), "unit": unit}
    if "=" in text:
        m = _NUM.search(text.split("=", 1)[1])
        if m:
            return {"value": float(m.group()), "unit": text.split("=", 1)[1][m.end():].strip()}
    return text.strip()


def from_header(lines) -> dict:
    lines = list(lines)
    meta: dict = {"comments": [], "software": None, "technique": None, "steps": None}
    if len(lines) > 3 and lines[3].strip():
        meta["technique"] = lines[3].strip()
    for line in lines:
        if "(software)" in line:
            meta["software"] = line.replace("(software)", "").strip()
        if line.startswith("Comments"):
            c = line.split(":", 1)[1].strip()
            if c:
                meta["comments"].append(c)
            continue
        for key, name in _KEYS.items():
            if line.startswith(key):
                rest = line[len(key):].strip()
                if rest.startswith(":"):
                    rest = rest[1:].strip()
                meta[name] = rest if name in _TEXT_ONLY else _value(rest)
                break
    if isinstance(meta.get("acquisition_started"), str):
        for fmt in ("%m/%d/%Y %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S.%f"):
            try:
                meta["acquisition_started_iso"] = datetime.strptime(meta["acquisition_started"], fmt).isoformat()
                break
            except ValueError:
                pass
    meta["steps"] = _steps(lines)
    return meta


def _steps(lines) -> list[dict] | None:
    """Programmed step table: rows 'Ns', 'Is', 'unit Is', 'EM (V)', 'tR (h:m:s)', ... with one column per step."""
    start = next((k for k, l in enumerate(lines) if l.startswith("Ns ")), None)
    if start is None:
        return None
    table = {}
    width = None
    for line in lines[start:]:
        if not line.strip():
            break
        label = line[:20].strip()
        body = line[20:]
        if width is None:
            width = 20
        cells = [body[i:i + width].strip() for i in range(0, len(body), width)]
        table[label] = cells
    n = len(table.get("Ns", []))
    steps = []
    for k in range(n):
        step = {label: (cells[k] if k < len(cells) else "") for label, cells in table.items()}
        try:
            step["Ns"] = int(step["Ns"])
        except (KeyError, ValueError):
            pass
        for key in ("Is", "EM (V)", "Im", "dq", "dE1 (mV)"):
            if key in step:
                try:
                    step[key] = float(step[key])
                except ValueError:
                    pass
        steps.append(step)
    return steps


def theoretical_from_header(meta: dict) -> dict:
    """Theoretical capacity from the declared molar mass and electron count, in mAh/g."""
    from .cycling import theoretical_capacity_mAh_g
    out = {}
    M = meta.get("molar_mass_declared", {})
    n = meta.get("electrons_per_ion", {})
    if isinstance(M, dict) and isinstance(n, dict) and M.get("value", 0) > 0 and n.get("value", 0) > 0:
        out["electrons_declared"] = n["value"]
        out["molar_mass_g_mol"] = M["value"]
        out["theoretical_capacity_mAh_g"] = theoretical_capacity_mAh_g(n["value"], M["value"])
        out["note"] = "n F / (3.6 M) with the electron count and molar mass typed into EC-Lab; check both against the intended redox process"
    return out


def _raw_header(path, encoding="cp1252", limit=400, columns=True):
    """The header block of an .mpt, read line by line without parsing the data.

    columns=False leaves out the last header line, the column names, to match the
    header kept by the text parser."""
    lines, declared = [], None
    with open(path, encoding=encoding, errors="replace") as fh:
        for k, line in enumerate(fh):
            lines.append(line.rstrip("\r\n"))
            if k == 1 and line.startswith("Nb header lines"):
                try:
                    declared = limit = int(line.split(":")[1])
                except ValueError:
                    pass
            if k + 1 >= limit:
                break
    if not columns and declared and len(lines) == declared:
        lines = lines[:-1]
    return tuple(lines)


def exported_from(lines) -> str | None:
    """The binary file an .mpt export says it was saved from ("Saved on :" then "File : name.mpr"), or None."""
    for k, line in enumerate(lines):
        if line.strip().lower().startswith("saved on"):
            for nxt in lines[k + 1:k + 4]:
                t = nxt.strip()
                if t.lower().startswith("file"):
                    name = t.split(":", 1)[1].strip() if ":" in t else ""
                    return name or None
    return None


def sibling_export(mpr_path, encoding="cp1252"):
    """(path, header lines) of the text export of this .mpr in the same folder, or (None, ()).

    The export with exactly the same name stem is EC-Lab's default and is taken as
    it is. Any other .mpt whose name merely starts with the same characters is taken
    only when its header says it was saved from this .mpr: cell1.mpr is not the
    source of cell10.mpt (independent review, finding r19).
    """
    from pathlib import Path
    path = Path(mpr_path)
    stem = path.stem.lower()
    try:
        cands = sorted(c for c in path.parent.iterdir()
                       if c.suffix.lower() == ".mpt" and c.stem.lower().startswith(stem))
    except OSError:
        return None, ()
    cands.sort(key=lambda c: c.stem.lower() != stem)          # the exact name first
    for cand in cands:
        try:
            hdr = _raw_header(cand, encoding)
        except OSError:
            continue
        src = exported_from(hdr)
        if (src and src.lower() == path.name.lower()) or (src is None and cand.stem.lower() == stem):
            return cand, hdr
    return None, ()


def read_header_lines(path, encoding="cp1252", limit=400):
    """Header lines of an .mpt without parsing the data. For an .mpr, those of its text export (sibling_export)."""
    from pathlib import Path
    path = Path(path)
    if path.suffix.lower() != ".mpt":
        return sibling_export(path, encoding)[1]
    return _raw_header(path, encoding, limit)
