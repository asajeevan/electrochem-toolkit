"""Capture what the generic reader returns today, as the reference a rewrite is held to (P08f).

Run once before changing electrochem/readers, and again only when a change of behaviour is
intended and documented:

    python scripts/capture_reader_reference.py

It writes tests/fixtures/reader_reference/reference.json and arrays.npz (the arrays of the real
files; every array, real or synthetic, is also stored as a NaN-canonical SHA-256). For every shipped public
instrument file (data/public/{arbin,maccor,neware,basytec,novonix,pec,landt}) it records

- the profile the registry identifies from the built-in profiles alone, or why none;
- the RawTable read with that profile: every array (t, i, e, step_id, cycle, q_charge,
  q_discharge, dq, temperature), step_kind, the column names, the import report and the full
  findings (code, severity, message, detail); or the exception, with its code and message;
- for a file whose import stops at ambiguous_sign, the table read once the current is declared
  unsigned (the answer tests/test_readers_real_files.py gives);
- the proposer's output as if no profile existed (layout, headers, the rows detect_layout
  returned, chosen columns, measurements, questions, blocking items, preview);

and the same for the BioLogic text exports read through the generic engine
(tests/test_readers_differential.py) and for every case of the synthetic corpus in
tests/reader_corpus.py. The SHA-256 of every source file is stored with its entry, so that the
test compares like with like. tests/test_readers_reference.py performs the comparison.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "tests" / "fixtures" / "reader_reference"
VENDORS = ("arbin", "maccor", "neware", "basytec", "novonix", "pec", "landt")
ARRAYS = ("t", "i", "e", "step_id", "cycle", "q_charge", "q_discharge", "dq", "temperature")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def workbook_digest(path: Path) -> str:
    """SHA-256 of a workbook's content (sheet titles, then every row's values as text): the bytes openpyxl
    writes differ between Python versions (3.12 writes `<x />`, 3.13 `<x/>`; namespace declarations move),
    while the cells are the same, and the generated corpus must verify on every platform the suite runs on."""
    from openpyxl import load_workbook
    h = hashlib.sha256()
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            h.update(("\x1f" + ws.title + "\x1e").encode("utf-8"))
            for row in ws.iter_rows(values_only=True):
                h.update(("\x1f".join("" if v is None else repr(v) for v in row) + "\x1e").encode("utf-8"))
    finally:
        wb.close()
    return h.hexdigest()


def array_digest(a: np.ndarray) -> str:
    """SHA-256 of dtype, shape and bytes, every NaN written as the same NaN (NaN-equal identity)."""
    a = np.ascontiguousarray(a)
    if a.dtype.kind == "f":
        a = a.copy()
        a[np.isnan(a)] = np.nan
    h = hashlib.sha256(f"{a.dtype.str}|{a.shape}|".encode())
    h.update(a.tobytes())
    return h.hexdigest()


def _plain(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    raise TypeError(f"not serialisable: {type(o)}")


def canonical(obj) -> str:
    """One JSON text per value, NaN included, keys sorted: equal texts mean equal values."""
    return json.dumps(obj, sort_keys=True, default=_plain, ensure_ascii=False)


def text_digest(values) -> dict:
    """A list of strings by length, digest and value counts (enough to locate a difference)."""
    values = list(values)
    counts: dict = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return {"len": len(values), "sha256": hashlib.sha256(canonical(values).encode()).hexdigest(),
            "counts": canonical(counts)}


def dump_error(exc: BaseException) -> dict:
    return {"kind": "error", "type": type(exc).__name__, "code": getattr(exc, "code", None), "message": str(exc)}


def dump_table(raw, arrays: dict | None, key: str) -> dict:
    out = {"kind": "table", "source_name": raw.source_name, "source_sha256": raw.source_sha256,
           "profile": raw.profile, "n": raw.n, "columns": list(raw.columns),
           "step_kind": None if raw.step_kind is None else text_digest(raw.step_kind),
           "report": canonical(raw.report), "findings": canonical(raw.findings), "arrays": {}}
    for name in ARRAYS:
        a = getattr(raw, name)
        if a is None:
            out["arrays"][name] = None
            continue
        a = np.asarray(a)
        out["arrays"][name] = {"dtype": a.dtype.str, "shape": list(a.shape), "sha256": array_digest(a)}
        if arrays is not None:
            arrays[f"{key}::{name}"] = a
    return out


def dump_proposal(prop, rows) -> dict:
    return {
        "kind": "proposal",
        "layout": canonical(prop.layout.model_dump(mode="json")),
        "headers": list(prop.headers),
        "bindings": canonical({r: b.model_dump(mode="json") for r, b in prop.bindings.items()}),
        "chosen": canonical({r: [c.column, c.index, c.score, c.reason, c.unit] for r, c in prop.chosen.items()}),
        "rejected": canonical({r: [c.column for c in cs] for r, cs in prop.rejected.items()}),
        "unit_unknown": canonical(prop.unit_unknown),
        "unmapped_columns": list(prop.unmapped_columns),
        "measured": canonical(prop.measured),
        "questions": list(prop.questions),
        "blocking": list(prop.blocking),
        "preview": {"len": len(prop.preview), "sha256": hashlib.sha256(canonical(prop.preview).encode()).hexdigest()},
        "layout_rows": len(rows),
        "layout_rows_sha256": hashlib.sha256(canonical(rows).encode()).hexdigest(),
    }


def capture_read(path: Path, profile, arrays: dict | None, key: str) -> dict:
    from electrochem.readers.reader import read
    try:
        return dump_table(read(path, profile), arrays, key)
    except Exception as exc:                                   # every outcome is part of the reference
        return dump_error(exc)


def capture_propose(path: Path) -> dict:
    from electrochem.readers.propose import detect_layout, propose
    try:
        _, _, rows = detect_layout(path)
        return dump_proposal(propose(path), rows)
    except Exception as exc:
        return dump_error(exc)


def public_files() -> list[Path]:
    out = []
    for v in VENDORS:
        for f in sorted((ROOT / "data" / "public" / v).iterdir()):
            if f.is_file() and f.name not in ("manifest.json", "ATTRIBUTION.md") and not f.name.startswith("LICENSE"):
                out.append(f)
    return out


def biologic_files() -> list[Path]:
    return sorted((ROOT / "data/public/mpt").glob("*.mpt")) + sorted((ROOT / "data/public/pyprobe").glob("*.txt"))


def capture_public(arrays: dict) -> dict:
    from electrochem.readers import BUILTIN, Registry
    entries = {}
    with tempfile.TemporaryDirectory() as d:
        reg = Registry(Path(d) / "profiles")
        for path in public_files():
            rel = path.relative_to(ROOT).as_posix()
            e = {"sha256": sha256_file(path)}
            try:
                prof = reg.identify(path, list(BUILTIN.values()))
                e["identified"] = prof.name
            except Exception as exc:
                prof = None
                e["identified"] = dump_error(exc)
            if prof is not None:
                e["read"] = capture_read(path, prof, arrays, f"{rel}::read")
                if e["read"]["kind"] == "error" and e["read"]["code"] == "ambiguous_sign":
                    answered = prof.model_copy(update={"conventions": prof.conventions.model_copy(
                        update={"current_sign": "unsigned"})})
                    e["read_unsigned"] = capture_read(path, answered, arrays, f"{rel}::read_unsigned")
            e["propose"] = capture_propose(path)
            entries[rel] = e
        from tests.test_readers_differential import BIOLOGIC_MPT
        for path in biologic_files():
            rel = path.relative_to(ROOT).as_posix()
            entries[rel] = {"sha256": sha256_file(path), "profile": "biologic-mpt (tests/test_readers_differential.py)",
                            "read": capture_read(path, BIOLOGIC_MPT, arrays, f"{rel}::read")}
    return entries


def capture_corpus(arrays: dict) -> dict:
    from tests.reader_corpus import write_all
    entries = {}
    with tempfile.TemporaryDirectory() as d:
        for name, path, prof in write_all(Path(d) / "corpus"):
            e = {"sha256": sha256_file(path),
                 "profile_sha256": hashlib.sha256(canonical(prof.model_dump(mode="json")).encode()).hexdigest(),
                 "read": capture_read(path, prof, None, f"corpus/{name}::read")}
            if path.suffix.lower() == ".xlsx":
                e["content_sha256"] = workbook_digest(path)
            if not name.startswith("fuzz_") and not name.startswith("big_"):
                e["propose"] = capture_propose(path)
            entries[name] = e
    return entries


def main() -> None:
    os.environ["ELECTROCHEM_PROFILES"] = tempfile.mkdtemp()     # no profile saved on this machine
    arrays: dict = {}
    ref = {"captured_with": {"python": platform.python_version(), "numpy": np.__version__,
                             "note": "the generic reader before the P08f streaming rewrite"},
           "public": capture_public(arrays), "corpus": capture_corpus(arrays)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "reference.json").write_text(json.dumps(ref, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    np.savez_compressed(OUT / "arrays.npz", **arrays)
    n_tab = sum(1 for sec in ("public", "corpus") for e in ref[sec].values()
                for k in ("read", "read_unsigned") if isinstance(e.get(k), dict) and e[k]["kind"] == "table")
    print(f"{len(ref['public'])} public files, {len(ref['corpus'])} corpus cases, {n_tab} tables, "
          f"{len(arrays)} arrays -> {OUT}")


if __name__ == "__main__":
    main()
