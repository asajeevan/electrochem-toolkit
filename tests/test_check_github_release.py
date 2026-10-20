"""The release checker (scripts/check_github_release.py) against simulated GitHub answers: it must pass a release
that is right, before and after publishing, and catch each way a release can go wrong while it can still be fixed
(a draft) and after it cannot (a published release). The tool is for the author's releases, not shipped with the
app, so the test skips where the script is absent."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_github_release.py"
pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="the release tool is not shipped with the app")

REPO, TAG, COMMIT = "owner/repo", "v1.2.3", "a" * 40


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("check_github_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def folder(tmp_path):
    content = {"Cyclara-1.2.3-Setup.exe": b"windows", "Cyclara-1.2.3-macOS.zip": b"mac", "handout.pdf": b"pdf"}
    for name, data in content.items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / "SHA256SUMS.txt").write_text(
        "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in content.items()))
    return tmp_path


def github(files, *, draft, immutable, enabled=True, tag_commit=COMMIT, main=COMMIT, drop=(), extra=(), wrong=(),
           state="uploaded", body="the notes", attest=True, unattested=(), attested_commit=None):
    """A stand-in for `gh api`: the answers GitHub gives for one release in the given condition."""
    assets = [{"id": i, "name": name, "state": state, "size": size,
               "digest": "sha256:" + ("0" * 64 if name in wrong else digest)}
              for i, (name, (size, digest)) in enumerate(files.items()) if name not in drop]
    assets += [{"id": 100 + i, "name": name, "state": "uploaded", "size": 1, "digest": "sha256:" + "1" * 64}
               for i, name in enumerate(extra)]
    release = {"id": 7, "tag_name": TAG, "name": "Cyclara 1.2.3", "draft": draft, "prerelease": False,
               "immutable": immutable, "target_commitish": "main", "body": body, "assets": assets,
               "html_url": "https://github.invalid/release", "author": {"login": "author"}}
    statement = {"predicateType": "https://in-toto.io/attestation/release/v0.2",
                 "predicate": {"repository": REPO, "tag": TAG},
                 "subject": [{"digest": {"sha1": attested_commit or tag_commit}}] +
                            [{"name": n, "digest": {"sha256": d}} for n, (_s, d) in files.items() if n not in unattested]}
    bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
              "dsseEnvelope": {"payload": base64.b64encode(json.dumps(statement).encode()).decode()},
              "verificationMaterial": {"certificate": {}, "timestampVerificationData": {"rfc3161Timestamps": [{}]}}}

    def api(path):
        if path.startswith(f"repos/{REPO}/releases?"):
            return [release]
        if path == f"repos/{REPO}/immutable-releases":
            return {"enabled": enabled}
        if path.startswith(f"repos/{REPO}/commits/"):
            return {"sha": main}
        if path == f"repos/{REPO}/git/ref/tags/{TAG}":
            return {"object": {"type": "commit", "sha": tag_commit}}
        if path.startswith(f"repos/{REPO}/attestations/sha1:{tag_commit}"):
            return {"attestations": [{"bundle": bundle}] if attest else []}
        raise AssertionError(f"unexpected request {path}")
    return api


def run(tool, folder, **condition):
    files = tool.release_files(folder)
    report, record, state = tool.check(github(files, **condition), REPO, TAG, files, commit=COMMIT[:7],
                                       notes="the notes")
    return report, record, state


def test_a_right_draft_and_a_right_release_pass(tool, folder):
    report, _, state = run(tool, folder, draft=True, immutable=False)
    assert (state, report.problems, report.notes) == ("draft", [], [])
    report, record, state = run(tool, folder, draft=False, immutable=True)
    assert (state, report.problems, report.notes) == ("published", [], [])
    assert record["tag_commit"] == COMMIT and record["attestation"]["signature_checked_here"] is False
    assert {a["name"] for a in record["assets"]} == set(tool.release_files(folder))


@pytest.mark.parametrize("condition, expected", [
    (dict(draft=True, immutable=False, enabled=False), "NOT enabled"),
    (dict(draft=True, immutable=False, drop=("handout.pdf",)), "missing: handout.pdf"),
    (dict(draft=True, immutable=False, extra=("Release_description.md",)), "other files attached: Release_description.md"),
    (dict(draft=True, immutable=False, wrong=("Cyclara-1.2.3-Setup.exe",)), "Cyclara-1.2.3-Setup.exe: SHA-256 0000"),
    (dict(draft=True, immutable=False, state="starter"), "not finished"),
    (dict(draft=True, immutable=False, main="b" * 40), "expected aaaaaaa"),
    (dict(draft=False, immutable=False), "NOT immutable"),
    (dict(draft=False, immutable=True, tag_commit="c" * 40), "expected aaaaaaa"),
    (dict(draft=False, immutable=True, attest=False), "no release attestation"),
    (dict(draft=False, immutable=True, unattested=("Cyclara-1.2.3-macOS.zip",)), "does not name Cyclara-1.2.3-macOS.zip"),
    (dict(draft=False, immutable=True, attested_commit="d" * 40), "does not name the tag's commit"),
])
def test_each_fault_is_reported(tool, folder, condition, expected):
    report, _, _ = run(tool, folder, **condition)
    assert any(expected in p for p in report.problems), report.lines


def test_editable_differences_are_notes_not_problems(tool, folder):
    report, _, _ = run(tool, folder, draft=False, immutable=True, body="other notes")
    assert report.problems == [] and any("differs from the notes" in n for n in report.notes)


def test_the_notes_heading_is_left_out_of_the_comparison(tool, tmp_path):
    notes = tmp_path / "v1.2.3.md"
    notes.write_text("# Cyclara 1.2.3\n\nthe notes\r\n")
    assert tool.normalise(tool.release_notes(notes)) == "the notes"
    notes.write_text("## New\n\nthe notes\n")                       # only a first-level heading is the title
    assert tool.normalise(tool.release_notes(notes)).startswith("## New")


def test_a_missing_release_and_a_changed_local_file(tool, folder):
    files = tool.release_files(folder)
    report, record, state = tool.check(lambda path: [], REPO, TAG, files)
    assert state == "absent" and record == {}
    (folder / "handout.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="handout.pdf"):
        tool.release_files(folder)
