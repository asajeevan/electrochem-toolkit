"""The numpy fast paths of table.load (P08f) give exactly the Table the strict P03 importers give.

The strict path (fast=False) keeps every token of every row as a record and is the reference; the fast
path must reproduce it bit for bit on every public file, and must step aside (return None, so the strict
path runs) for anything it does not handle: a non-numeric token other than EC-Lab's XXX, bare
carriage-return line endings, a decimal comma it was not told about.
"""
import time
from pathlib import Path

import numpy as np
import pytest

from electrochem import table
from electrochem.table import _fast_text, _sniff_decimal, load

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = sorted((ROOT / "data" / "public" / "mpt").glob("*.mpt")) + sorted((ROOT / "data" / "public" / "mpr").glob("*.mpr"))
DEMO = ROOT / "data" / "demo" / "cyclara_demo_synthetic.mpt"
ARRAYS = ("t", "i", "e", "ns", "mode", "oxred", "error", "half_cycle", "cycle", "q_instrument", "dq", "temperature")


def identical(a, b) -> bool:
    for k in ARRAYS:
        x, y = getattr(a, k), getattr(b, k)
        if (x is None) != (y is None) or (x is not None and not np.array_equal(x, y, equal_nan=True)):
            return False
    if set(a.potentials) != set(b.potentials) or any(not np.array_equal(a.potentials[k], b.potentials[k], equal_nan=True)
                                                      for k in a.potentials):
        return False
    return (a.columns == b.columns and a.labels == b.labels and a.invalid_rows == b.invalid_rows and a.header == b.header
            and a.source_sha256 == b.source_sha256 and a.format == b.format and a.source_name == b.source_name)


@pytest.mark.parametrize("path", PUBLIC + [DEMO], ids=lambda p: p.name)
def test_fast_path_equals_the_strict_importer_on_every_public_file(path):
    if path.suffix == ".mpr":
        pytest.importorskip("galvani")
    fast = load(path, check=False, fast=True)
    strict = load(path, check=False, fast=False)
    assert identical(fast, strict)
    if path.suffix == ".mpt":
        data = path.read_bytes()
        assert _fast_text(data, path.name, "cp1252", _sniff_decimal(data, "cp1252")) is not None, "took the strict path"


def test_xxx_tokens_are_nan_and_counted_like_the_strict_path():
    """bio_logic5.mpt has EC-Lab's XXX in its first time field: the fast path reads the file and reports
    the one invalid token in the same column."""
    p = ROOT / "data" / "public" / "mpt" / "bio_logic5.mpt"
    fast = load(p, check=False)
    assert fast.invalid_rows == {"time/s": 1} and np.isnan(fast.t[0]) and np.isfinite(fast.t[1:]).all()
    assert identical(fast, load(p, check=False, fast=False))


def _with_data_block(src: bytes, fn) -> bytes:
    """The file with its data block transformed (the header untouched)."""
    header, names, block = table._text_header(src, "cp1252")
    cut = len(src) - len(block)
    return src[:cut] + fn(block)


def test_a_decimal_comma_export_reads_identically(tmp_path):
    src = (ROOT / "data" / "public" / "mpt" / "020-formation_CB5.mpt").read_bytes()
    p = tmp_path / "comma.mpt"
    p.write_bytes(_with_data_block(src, lambda b: b.replace(b".", b",")))
    assert _sniff_decimal(p.read_bytes(), "cp1252") == ","
    fast, strict = load(p, check=False), load(p, check=False, fast=False)
    assert identical(fast, strict)
    assert np.array_equal(fast.t, load(ROOT / "data" / "public" / "mpt" / "020-formation_CB5.mpt", check=False).t)


def test_tokens_numpy_would_accept_but_the_strict_path_rejects_go_to_the_strict_path(tmp_path):
    """'inf' and 'nan' are numbers to numpy and invalid tokens to the strict importer: the fast path must not
    be the one to decide, so it steps aside and the result is the strict one (nan, counted)."""
    src = (ROOT / "data" / "public" / "mpt" / "020-formation_CB5.mpt").read_bytes()
    header, names, block = table._text_header(src, "cp1252")
    first = block.split(b"\n", 1)[0]
    fields = first.split(b"\t")
    k = names.index("I/mA")
    fields[k] = b"inf"
    p = tmp_path / "inf.mpt"
    p.write_bytes(_with_data_block(src, lambda b: b"\t".join(fields) + b"\n" + b.split(b"\n", 1)[1]))
    assert _fast_text(p.read_bytes(), p.name, "cp1252", ".") is None
    tab = load(p, check=False)
    assert np.isnan(tab.i[0]) and tab.invalid_rows == {"I/mA": 1}
    assert identical(tab, load(p, check=False, fast=False))


def test_bare_carriage_returns_go_to_the_strict_path(tmp_path):
    src = (ROOT / "data" / "public" / "mpt" / "020-formation_CB5.mpt").read_bytes()
    p = tmp_path / "cr.mpt"
    p.write_bytes(_with_data_block(src, lambda b: b.replace(b"\r\n", b"\r").replace(b"\n", b"\r")))
    assert _fast_text(p.read_bytes(), p.name, "cp1252", ".") is None
    assert identical(load(p, check=False), load(p, check=False, fast=False))


def test_a_large_export_loads_in_seconds(tmp_path):
    """The demonstration file repeated 10 times (200 000 rows, 27 MB), with the clock continued: read in
    well under the strict importer's time, with the same values per block."""
    src = DEMO.read_bytes()
    header, names, block = table._text_header(src, "cp1252")
    ti = names.index("time/s")
    lines = [l for l in block.split(b"\n") if l.strip()]
    last_t = float(lines[-1].split(b"\t")[ti])
    out = []
    for r in range(10):
        off = r * (last_t + 1.0)
        for l in lines:
            f = l.split(b"\t")
            f[ti] = f"{float(f[ti]) + off:.6f}".encode()
            out.append(b"\t".join(f))
    p = tmp_path / "big.mpt"
    p.write_bytes(src[:len(src) - len(block)] + b"\n".join(out) + b"\n")
    t0 = time.time()
    tab = load(p, check=False)
    elapsed = time.time() - t0
    assert tab.n == 10 * len(lines) and elapsed < 10.0, elapsed
    one = load(DEMO, check=False)
    assert np.array_equal(tab.i[:one.n], one.i) and np.array_equal(tab.e[-one.n:], one.e)
    assert tab.t[one.n] == pytest.approx(one.t[0] + last_t + 1.0)
