#!/usr/bin/env python3
"""Check a GitHub release of Cyclara, draft or published, against the release files on this computer.

Before publishing it shows that the draft holds exactly the tested files; after publishing, that GitHub made the
release immutable, put the tag on the expected commit and signed a release attestation naming every file. It only
reads: GitHub's REST API through the GitHub CLI (`gh`, signed in with read access to the repository).

    python scripts/check_github_release.py --tag v0.8.0 --dir FOLDER [--commit SHA] [--notes FILE] [--record JSON]

FOLDER holds SHA256SUMS.txt and every file it lists; those files and SHA256SUMS.txt itself are the release.
The attestation's signature is not checked here: `gh release verify TAG` and `gh release verify-asset TAG FILE`
do that, and need network access to GitHub's attestation storage and to the Sigstore trust root.
Exit status: 0 nothing wrong, 1 something wrong, 2 no release with that tag.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_REPO = "asajeevan/electrochem-toolkit"
SUMS = "SHA256SUMS.txt"


def gh_api(path, accept=None, out=None):
    """GET one GitHub REST path with the GitHub CLI; JSON back, or the raw bytes written to `out`."""
    cmd = ["gh", "api"] + (["-H", f"Accept: {accept}"] if accept else []) + [path]
    if out is not None:
        with open(out, "wb") as f:
            r = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
        if r.returncode:
            raise RuntimeError(f"gh api {path}: {r.stderr.decode(errors='replace').strip()}")
        return None
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"gh api {path}: {(r.stderr or r.stdout).strip()}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def release_files(folder):
    """{name: (size, sha256)} for SHA256SUMS.txt and every file it lists; a listed file that differs is refused."""
    folder = Path(folder)
    sums = folder / SUMS
    files = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        name = name.strip().lstrip("*")                       # sha256sum marks binary mode with '*'
        actual = sha256_file(folder / name)
        if actual != digest.lower():
            raise ValueError(f"{name}: SHA-256 {actual} on disk, {digest} in {SUMS}")
        files[name] = ((folder / name).stat().st_size, actual)
    files[SUMS] = (sums.stat().st_size, sha256_file(sums))
    return files


def normalise(text):
    return "\n".join(line.rstrip() for line in (text or "").replace("\r\n", "\n").strip().split("\n"))


def release_notes(path):
    """The text a notes file gives the release page: without its first '# ' heading, which the title replaces."""
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    if text.startswith("# "):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text


class Report:
    def __init__(self):
        self.lines, self.problems, self.notes = [], [], []

    def ok(self, text):
        self.lines.append(("ok", text))

    def fail(self, text):
        self.lines.append(("FAIL", text))
        self.problems.append(text)

    def note(self, text):
        self.lines.append(("note", text))
        self.notes.append(text)

    def expect(self, condition, good, bad, fatal=True):
        if condition:
            self.ok(good)
        elif fatal:
            self.fail(bad)
        else:
            self.note(bad)


def _commit_of(api, repo, target):
    """The commit a branch name or a commit SHA stands for."""
    return api(f"repos/{repo}/commits/{target}")["sha"]


def _statement(attestation):
    envelope = (attestation.get("bundle") or {}).get("dsseEnvelope") or {}
    return json.loads(base64.b64decode(envelope.get("payload", "") or "e30="))


def check(api, repo, tag, files, *, title=None, commit=None, notes=None, prerelease=False, download=None):
    """Compare the release `tag` of `repo` with `files` ({name: (size, sha256)}). Returns (Report, record, state)."""
    report, record = Report(), {}
    releases = api(f"repos/{repo}/releases?per_page=100") or []
    found = [r for r in releases if r.get("tag_name") == tag]
    if not found:
        report.note(f"no release, draft or published, has the tag {tag} ({len(releases)} release(s) listed)")
        return report, record, "absent"
    if len(found) > 1:
        report.fail(f"{len(found)} releases use the tag {tag}: " + ", ".join(
            f"id {r['id']} ({'draft' if r['draft'] else 'published'})" for r in found))
    rel = max(found, key=lambda r: (not r["draft"], r["id"]))
    state = "draft" if rel["draft"] else "published"
    record["release"] = {k: rel.get(k) for k in ("id", "html_url", "tag_name", "target_commitish", "name", "draft",
                                                "prerelease", "immutable", "created_at", "published_at")}
    record["release"]["author"] = (rel.get("author") or {}).get("login")

    try:
        enabled = bool(api(f"repos/{repo}/immutable-releases").get("enabled"))
    except RuntimeError as err:
        enabled = None
        report.note(f"could not read the repository's immutability setting ({err})")
    if enabled is not None:
        report.expect(enabled, "release immutability is enabled for the repository",
                      "release immutability is NOT enabled (Settings > Releases > Enable release immutability)",
                      fatal=rel["draft"])

    want_title = title or f"Cyclara {tag.lstrip('v')}"
    report.expect(rel.get("name") == want_title, f"title is {want_title!r}",
                  f"title is {rel.get('name')!r}, expected {want_title!r} (editable)", fatal=False)
    report.expect(bool(rel.get("prerelease")) == prerelease,
                  "marked as a pre-release" if prerelease else "not marked as a pre-release",
                  "not marked as a pre-release" if prerelease else "marked as a pre-release")
    if notes is not None:
        report.expect(normalise(rel.get("body")) == normalise(notes), "the description equals the notes file",
                      "the description differs from the notes file (editable)", fatal=False)

    assets = {a["name"]: a for a in rel.get("assets", [])}
    missing = [n for n in files if n not in assets]
    extra = [n for n in assets if n not in files]
    report.expect(not missing, f"all {len(files)} release files are attached", "missing: " + ", ".join(missing))
    report.expect(not extra, "no other files are attached", "other files attached: " + ", ".join(extra))
    record["assets"] = []
    for name, (size, digest) in files.items():
        a = assets.get(name)
        if a is None:
            continue
        record["assets"].append({k: a.get(k) for k in ("name", "size", "digest", "state", "browser_download_url",
                                                       "created_at", "updated_at")})
        if a.get("state") != "uploaded":
            report.fail(f"{name}: upload state {a.get('state')!r}, not finished")
            continue
        report.expect(a.get("size") == size, f"{name}: {size:,} bytes", f"{name}: {a.get('size')} bytes, expected {size:,}")
        remote, how = (a.get("digest") or "").removeprefix("sha256:"), "GitHub's digest"
        if not remote and download is not None:
            remote, how = download(a["id"]), "downloaded and hashed"
        report.expect(remote == digest, f"{name}: SHA-256 {digest[:16]}... matches ({how})",
                      f"{name}: SHA-256 {remote[:16] or 'unknown'}... is not the tested file's {digest[:16]}... ({how})")

    if rel["draft"]:
        target = rel.get("target_commitish") or ""
        if commit:
            at = _commit_of(api, repo, target)
            report.expect(at.startswith(commit.lower()),
                          f"the tag will be created on {target} = {at[:7]}",
                          f"the tag would be created on {target} = {at[:7]}, expected {commit[:7]}")
        else:
            report.note(f"the tag will be created on {target!r} (no --commit given to compare with)")
        return report, record, state

    report.expect(bool(rel.get("immutable")), "the published release is immutable",
                  "the published release is NOT immutable: its files and tag can still be changed")
    obj = api(f"repos/{repo}/git/ref/tags/{tag}")["object"]
    tag_sha = obj["sha"] if obj["type"] == "commit" else api(f"repos/{repo}/git/tags/{obj['sha']}")["object"]["sha"]
    record["tag_commit"] = tag_sha
    if commit:
        report.expect(tag_sha.startswith(commit.lower()), f"tag {tag} is on {tag_sha[:7]}",
                      f"tag {tag} is on {tag_sha[:7]}, expected {commit[:7]}")
    else:
        report.note(f"tag {tag} is on {tag_sha[:7]} (no --commit given to compare with)")

    attestations = (api(f"repos/{repo}/attestations/sha1:{tag_sha}?per_page=100&predicate_type=release")
                    or {}).get("attestations", [])
    statements = [(a, _statement(a)) for a in attestations]
    statements = [(a, s) for a, s in statements if (s.get("predicate") or {}).get("tag") == tag]
    report.expect(bool(statements), "GitHub's release attestation exists",
                  "no release attestation found for this tag (GitHub signs one for an immutable release)")
    if statements:
        att, st = statements[-1]
        pred = st.get("predicate") or {}
        subjects = [(s.get("name"), s.get("digest") or {}) for s in st.get("subject", [])]
        named = {name: digest for name, digest in subjects if name}
        report.expect(str(st.get("predicateType", "")).startswith("https://in-toto.io/attestation/release/"),
                      f"attestation type {st.get('predicateType')}", f"unexpected attestation type {st.get('predicateType')}")
        report.expect(pred.get("repository") == repo and pred.get("tag") == tag,
                      f"the attestation names {repo} and {tag}",
                      f"the attestation names {pred.get('repository')} and {pred.get('tag')}")
        report.expect(any(digest.get("sha1") == tag_sha for _, digest in subjects),
                      f"the attestation names the commit {tag_sha[:7]}", "the attestation does not name the tag's commit")
        unlisted = sorted(n for n in named if n not in files)
        if unlisted:
            report.note("the attestation also names: " + ", ".join(unlisted))
        for name, (_size, digest) in files.items():
            report.expect(named.get(name, {}).get("sha256") == digest, f"the attestation names {name} with its SHA-256",
                          f"the attestation does not name {name} with the tested SHA-256")
        bundle = att.get("bundle") or {}
        vm = bundle.get("verificationMaterial") or {}
        record["attestation"] = {
            "statement": st,
            "bundle_media_type": bundle.get("mediaType"),
            "signed_with": sorted(k for k in vm if k != "tlogEntries"),
            "transparency_log_entries": len(vm.get("tlogEntries") or []),
            "rfc3161_timestamps": len((vm.get("timestampVerificationData") or {}).get("rfc3161Timestamps") or []),
            "bundle": bundle,
            "signature_checked_here": False,
        }
    return report, record, state


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tag", required=True, help="the release tag, e.g. v0.8.0")
    ap.add_argument("--dir", required=True, type=Path, help="folder with SHA256SUMS.txt and the files it lists")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--title", help="expected release title (default: Cyclara X.Y.Z from the tag)")
    ap.add_argument("--commit", help="expected commit of the tag (full or abbreviated SHA)")
    ap.add_argument("--notes", type=Path, help="notes file the release description should equal (its first "
                                                "'# ' heading excepted, the release title stands for it)")
    ap.add_argument("--prerelease", action="store_true", help="the release is meant to be a pre-release")
    ap.add_argument("--record", type=Path, help="write what was checked, as JSON evidence, to this file")
    args = ap.parse_args(argv)

    files = release_files(args.dir)

    def download(asset_id):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "asset"
            gh_api(f"repos/{args.repo}/releases/assets/{asset_id}", accept="application/octet-stream", out=target)
            return sha256_file(target)

    report, record, state = check(gh_api, args.repo, args.tag, files, title=args.title, commit=args.commit,
                                  notes=release_notes(args.notes) if args.notes else None,
                                  prerelease=args.prerelease, download=download)
    rel = record.get("release", {})
    if rel:
        print(f"Release {args.tag} of {args.repo}: {state}, id {rel['id']}, published {rel.get('published_at')}")
    for status, text in report.lines:
        print(f"  {status:4s} {text}")
    if args.record and record:
        record["checked"] = {"tag": args.tag, "repo": args.repo, "expected_commit": args.commit,
                             "files": {n: {"size": s, "sha256": d} for n, (s, d) in files.items()},
                             "problems": report.problems, "notes": report.notes}
        args.record.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"  record written to {args.record}")
    print()
    if state == "absent":
        print("NO RELEASE with this tag yet.")
        return 2
    if report.problems:
        print("PROBLEMS: " + " | ".join(report.problems))
        return 1
    verdict = "READY TO PUBLISH: every file on the draft is the tested file." if state == "draft" else \
        "PUBLISHED AND VERIFIED (the attestation's signature: gh release verify)."
    print(verdict + (" Notes: " + " | ".join(report.notes) if report.notes else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
