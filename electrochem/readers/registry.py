"""Identify a file's instrument, and learn a new one once.

This is what "universal for all cyclers" actually means here, and it is worth
being precise about the claim.

What is true: every cycler on the market can export delimited text or Excel,
and the generic reader handles any such export once it knows four conventions
that no file states about itself. So the tool can read any cycler's data.

What is not true, and is not claimed: that the tool recognises every cycler out
of the box. Writing a profile for an instrument whose files have never been
seen would mean inventing column names, and a profile invented that way fails
silently, the worst way to fail. So the registry is built the other way round:
the proposer reads an unknown file, a person answers what the file cannot say,
and the answers are saved against a fingerprint of the header. The second file
from that instrument, and every file after it, needs no questions.

A profile in this registry therefore always carries evidence of who confirmed
it against which file, which is exactly what a reviewer needs to see.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .profile import ImportProfile
from .propose import detect_layout, normalise


def sniff_text(path: Path, headers: list[str]) -> str:
    """What a built-in profile's sniff strings are searched in: the first kilobytes of a text
    file, then every column name on a line of its own. A workbook's bytes are compressed, so
    for it only the column names count. Because each name sits between newlines, a sniff
    string written as '\\nTest_Time\\n' matches that whole column name and never a longer one
    such as 'Test_Time(s)' (builtin.column builds such strings)."""
    with open(path, "rb") as fh:
        raw = fh.read(8192).decode("latin-1", errors="replace")
    return raw + "\n" + "\n".join(h.strip().lstrip("\ufeff") for h in headers) + "\n"


def claims(profile: ImportProfile, path: Path, kind: str, headers: list[str], text: str | None = None) -> bool:
    """Does this built-in profile claim the file? Three conditions, all from the file itself:
    the same kind (text or workbook), one of its sniff strings present, and a column for each of
    time, current and voltage under the names it binds. The last condition stops a dialect from
    claiming a sibling dialect's file merely because the two share a column name."""
    if profile.layout.kind != kind or not profile.sniff_any:
        return False
    text = sniff_text(path, headers) if text is None else text
    if not any(s in text for s in profile.sniff_any):
        return False
    from .reader import REQUIRED_ROLES, _match
    names = [h.strip().lstrip("\ufeff") for h in headers]
    return all(_match(profile.bindings[r], names) is not None for r in REQUIRED_ROLES)


def claims_saved(profile: ImportProfile, kind: str, headers: list[str]) -> bool:
    """Does a saved (confirmed) profile claim this file? The same kind, and a column for each of
    time, current and voltage under the names it binds, units aside."""
    if profile.layout.kind != kind:
        return False
    from .reader import REQUIRED_ROLES, _match
    names = [h.strip().lstrip("\ufeff") for h in headers]
    return all(_match(profile.bindings[r], names) is not None for r in REQUIRED_ROLES)


def shared_columns(profile: ImportProfile, headers: list[str]) -> list[str]:
    """The bound columns of a profile that this header also has (units aside)."""
    from .reader import _match
    names = [h.strip().lstrip("\ufeff") for h in headers]
    out = []
    for role, b in profile.bindings.items():
        hit = _match(b, names)
        if hit is not None:
            out.append(names[hit[0][0]])
    return out


def fingerprint(headers: list[str]) -> str:
    """Identity of a file layout: its set of normalised column names.

    Order-independent and unit-independent, because instruments reorder columns
    between firmware versions and let the user choose units at export time,
    while the set of quantities recorded stays the same.
    """
    names = sorted({normalise(h) for h in headers if h.strip()})
    return hashlib.sha256("\n".join(names).encode()).hexdigest()[:32]


@dataclass
class Entry:
    profile: ImportProfile
    fingerprints: list[str]
    source_files: list[str]

    def to_json(self) -> str:
        return json.dumps({"profile": self.profile.model_dump(mode="json"),
                           "fingerprints": self.fingerprints,
                           "source_files": self.source_files}, indent=2)

    @staticmethod
    def from_json(text: str) -> "Entry":
        d = json.loads(text)
        return Entry(ImportProfile.model_validate(d["profile"]),
                     list(d["fingerprints"]), list(d.get("source_files", [])))


class Registry:
    """Confirmed profiles on disk, one JSON file each."""

    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass                                     # read-only home: built-in profiles still work; save() will say

    def entries(self) -> list[Entry]:
        out = []
        if not self.dir.is_dir():
            return out
        for p in sorted(self.dir.glob("*.json")):
            try:
                out.append(Entry.from_json(p.read_text(encoding="utf-8")))
            except Exception as exc:                      # a corrupt entry is not fatal
                raise ValueError(f"profile {p.name} is not readable: {exc}") from exc
        return out

    def nearest(self, headers: list[str], kind: str) -> tuple[ImportProfile, list[str]] | None:
        """The saved profile of the same kind sharing the most bound columns with this header, if it
        shares at least one of the time, current and voltage columns: the same instrument exported
        with a different selection of columns. Returns (profile, shared column names) or None."""
        from .reader import REQUIRED_ROLES, _match
        names = [h.strip().lstrip("\ufeff") for h in headers]
        best = None
        for e in self.entries():
            if e.profile.layout.kind != kind:
                continue
            shared = shared_columns(e.profile, names)
            required = sum(1 for r in REQUIRED_ROLES if _match(e.profile.bindings[r], names) is not None)
            if required == 0 or not shared:
                continue
            key = (required, len(shared))
            if best is None or key > best[0]:
                best = (key, e.profile, shared)
        return None if best is None else (best[1], best[2])

    def save(self, profile: ImportProfile, headers: list[str], source_file: str) -> Path:
        fp = fingerprint(headers)
        path = self.dir / f"{profile.name}.json"
        if path.exists():
            e = Entry.from_json(path.read_text(encoding="utf-8"))
            if fp not in e.fingerprints:
                e.fingerprints.append(fp)
            if source_file not in e.source_files:
                e.source_files.append(source_file)
            e.profile = profile
        else:
            e = Entry(profile, [fp], [source_file])
        path.write_text(e.to_json(), encoding="utf-8")
        return path

    def identify(self, path: str | Path, builtin: list[ImportProfile] = ()) -> ImportProfile:
        """Return the one profile that fits, or raise saying why none does.

        Two profiles claiming the same file is an ambiguity to report, never to
        resolve by order: the two may disagree about the sign convention, and
        picking one silently would decide that for the user.
        """
        path = Path(path)
        layout, headers, _ = detect_layout(path)
        fp = fingerprint(headers)

        entries = self.entries()
        hits = [e.profile for e in entries if fp in e.fingerprints]
        if not hits:
            # The same instrument exported with other columns, another order or other units: a
            # saved profile claims the file when its time, current and voltage columns resolve
            # (reader._match takes the header's own unit). Nothing is asked twice for an
            # instrument that was confirmed once (P08e).
            hits = [e.profile for e in entries if claims_saved(e.profile, layout.kind, headers)]
        if not hits:
            text = sniff_text(path, headers)
            hits = [p for p in builtin if claims(p, path, layout.kind, headers, text)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise LookupError(
                f"{len(hits)} profiles claim {path.name}: {[p.name for p in hits]}. They may "
                "disagree about the sign convention or the capacity semantics, so the choice "
                "is yours to make, not the registry's.")
        raise LookupError(
            f"no profile recognises {path.name} (fingerprint {fp}). Run the proposer, answer "
            "what the file cannot state about itself, and save the result; every later file "
            "from this instrument will then be recognised automatically.")


def confirm(proposal, *, name: str, instrument: str, conventions,
            registry: Registry) -> ImportProfile:
    """Turn an answered proposal into a saved, reusable profile.

    Refuses while anything blocking is unanswered, because a profile saved with
    an open question would apply that question's wrong answer to every future
    file from the same instrument.
    """
    if proposal.blocking:
        raise ValueError(
            "this proposal still has unanswered blocking questions, and saving it would apply "
            "a guess to every future file from this instrument:\n  - "
            + "\n  - ".join(proposal.blocking))
    profile = proposal.to_profile(name, instrument, conventions)
    registry.save(profile, proposal.headers, proposal.path.name)
    return profile
