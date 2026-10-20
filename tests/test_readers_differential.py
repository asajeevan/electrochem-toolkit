"""Differential test: the generic profile engine against the validated reader.

The toolkit already has a dedicated, experimentally validated EC-Lab text
reader. If the generic engine can reproduce it exactly on real files, the new
layer can be added without putting the validated path at risk. Any divergence
is a defect in one of the two and must be explained, not tolerated.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from electrochem.readers.profile import Binding, Conventions, ImportProfile, Layout
from electrochem.readers.reader import read

REPO = Path(__file__).resolve().parents[1]

BIOLOGIC_MPT = ImportProfile(
    name="biologic-mpt",
    instrument="BioLogic EC-Lab / BT-Lab (text export)",
    layout=Layout(kind="delimited", encoding="cp1252", delimiter="\t", decimal="auto",
                  header_contains=("time/s",)),
    sniff_any=("EC-Lab ASCII FILE", "BT-Lab ASCII FILE"),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="per_row_increment",
        cycle_base=0,
        evidence="compared row by row against eclab_import.text on the public "
                 "CC-BY BioLogic files in data/public",
    ),
    bindings={
        "test_time_second": Binding(source=("time",)),
        "current_ampere": Binding(source=("I", "<I>")),
        "voltage_volt": Binding(source=("Ewe", "Ecell", "<Ewe>")),
        "step_id": Binding(source=("Ns",), source_unit="1"),
        "cycle_count": Binding(source=("cycle number",), source_unit="1"),
        "net_capacity_ah": Binding(source=("dq", "dQ")),
    },
)

FILES = sorted((REPO / "data/public/mpt").glob("*.mpt")) + \
        sorted((REPO / "data/public/pyprobe").glob("*.txt"))


def _reference(path: Path):
    """The repository's own validated text reader."""
    from eclab_import.text import Options, parse
    p = parse(path.read_bytes(), path.name,
              Options(encoding="cp1252", missing_terminal_empty_field=True))
    names = [c.original_name for c in p.source.columns]
    rows = [r.fields for r in p.rows]
    return names, rows


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_generic_engine_reproduces_the_validated_reader(path):
    try:
        names, rows = _reference(path)
    except Exception as exc:                      # not a file the reference accepts
        pytest.skip(f"reference reader rejected it: {type(exc).__name__}")
    if any(n.startswith("freq/Hz") for n in names):
        pytest.skip("impedance spectrum, not a time series")
    if not any(n.startswith("time/s") for n in names):
        pytest.skip("no time column: not a time series")
    if not any(n.split("/")[0] in ("I", "<I>") for n in names):
        pytest.skip("no measured current column")
    k = next(j for j, n in enumerate(names) if n.split("/")[0] == "time")
    if rows and "/" in rows[0][k]:
        pytest.skip("time column is an absolute timestamp, not elapsed seconds")

    tab = read(path, BIOLOGIC_MPT)
    assert tab.n == len(rows), "row count"

    comma = any("," in c for r in rows[:20] for c in r)

    def ref_col(prefix, scale):
        k = next(j for j, n in enumerate(names) if n.split("/")[0] == prefix)
        out = np.full(len(rows), np.nan)
        for j, r in enumerate(rows):
            s = r[k].strip().replace(",", ".") if comma else r[k].strip()
            try:
                out[j] = float(s)
            except ValueError:
                pass
        return out * scale

    assert np.allclose(tab.t, ref_col("time", 1.0), rtol=0, atol=1e-9, equal_nan=True)
    cur = "I" if any(n.split("/")[0] == "I" for n in names) else "<I>"
    assert np.allclose(tab.i, ref_col(cur, 1e-3), rtol=0, atol=1e-15, equal_nan=True)
    volt = "Ewe" if any(n.split("/")[0] == "Ewe" for n in names) else "Ecell"
    assert np.allclose(tab.e, ref_col(volt, 1.0), rtol=0, atol=1e-12, equal_nan=True)
