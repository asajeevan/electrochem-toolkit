"""Small offline project snapshots. No extraction, deletion, or in-place overwrite.

Proof-scale format capped at 50 MiB uncompressed. Streaming storage, migrations,
multi-writer recovery and large experimental corpora are later packages.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

from .models import Project, canonical_bytes

MAX_BYTES = 50 * 1024 * 1024


def _blobs(project, blobs):
    if set(blobs) != {s.sha256 for s in project.sources}:
        raise ValueError("Source payloads do not match the manifest")
    for source in project.sources:
        data = blobs[source.sha256]
        if not isinstance(data, bytes) or len(data) != source.byte_size:
            raise ValueError("Source size/type mismatch")
        if hashlib.sha256(data).hexdigest() != source.sha256:
            raise ValueError("Source hash mismatch")


def save(project: Project, blobs: dict[str, bytes], destination: str | Path) -> None:
    # Revalidate even if a caller used Pydantic's deliberately unchecked constructors.
    project = Project.model_validate_json(project.model_dump_json())
    _blobs(project, blobs)
    manifest = canonical_bytes(project)
    if len(manifest) + sum(map(len, blobs.values())) > MAX_BYTES:
        raise ValueError("Snapshot exceeds the P01 uncompressed size limit")
    target = Path(destination)
    if target.exists():
        raise FileExistsError("Snapshots are immutable; choose a new destination")
    # A hard link publishes a complete file without replacing an existing target.
    # Same-directory temporary file ensures same filesystem. No destructive fallback.
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".p01-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as z:
                entries = {"project.json": manifest, **{"sources/"+k: v for k,v in blobs.items()}}
                for name in sorted(entries):
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, entries[name])
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _no_duplicate_keys(pairs):
    d = {}
    for key, value in pairs:
        if key in d:
            raise ValueError("Duplicate JSON key")
        d[key] = value
    return d


def load(path: str | Path) -> tuple[Project, dict[str, bytes]]:
    """Read and verify a snapshot; no writes or extraction occur."""
    with zipfile.ZipFile(path, "r") as z:
        info = z.infolist()
        names = [i.filename for i in info]
        if len(names) != len(set(names)) or "project.json" not in names:
            raise ValueError("Duplicate members or missing manifest")
        if sum(i.file_size for i in info) > MAX_BYTES:
            raise ValueError("Snapshot exceeds the P01 uncompressed size limit")
        raw = z.read("project.json")
        json.loads(raw, object_pairs_hook=_no_duplicate_keys)
        project = Project.model_validate_json(raw)
        expected = {"project.json"} | {"sources/"+s.sha256 for s in project.sources}
        if set(names) != expected:
            raise ValueError("Unexpected/missing members; only manifest and hashed sources allowed")
        blobs = {s.sha256: z.read("sources/"+s.sha256) for s in project.sources}
        _blobs(project, blobs)
    return project, blobs
