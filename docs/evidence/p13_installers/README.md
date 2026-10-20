# Evidence for the installers

The files here belong to the released build of 0.8.0 (20 October 2026), the one attached to the GitHub release; `0.7.0/` keeps the morning's build of
the same day. `build_windows.log` and `build_macos.log` are the build's own log (pip command lines shortened);
`*.sha256` are the checksums of the files delivered; the four PNGs are the installer's pages photographed under
Wine and Xvfb.

Two builds of 0.8.0 were made. Build A (16:02) was tested in full: the Wine harness on its staged Windows tree
(imports, every view of the demonstration file, then the whole self-test suite with the bundled Windows
interpreter: 920 passed, 3 skipped, 12 min 52 s), and the install check below. Build B (16:31) is the one
delivered; it was made after `STATUS.md` and `docs/U02_Cyclara.md` were updated with A's results. Its staged
Windows tree was compared with A's file by file: 10 799 files, the same except those two documents and
`Cyclara.exe`, whose bytes differ only in the PE time stamp and the header checksum that mingw writes at link
time. B was then run under Wine (imports, every view) and install-checked. `wine_run_summary.txt` has both runs.

Install check (32-bit Wine, `/S`), for A and again for B: the morning's 0.7.0 installed first (10 759 files),
then 0.8.0 over it (39 s and 38 s); the installed tree equals the built stage file for file and byte for byte
(B: 10 799 files hashed), no file of 0.7.0 left behind, only `Uninstall.exe` added; Start menu and Desktop
shortcuts, the uninstall key (DisplayVersion 0.8.0) and the "Open with" registration present; `Uninstall.exe /S`
removed the folder, both shortcuts and the keys.

Released build (19:21, from a clean checkout of commit c7014cc, the source of the program; the tag `v0.8.0` is on
the next commit, 1463d92, which adds only these checksums and this evidence): the same 10 799 files as
build B except `README.md` and `docs/Cyclara_handout.pdf` (the corrected macOS first-launch advice) and the
launcher's PE time stamp and header checksum, compared file by file; the whole suite on that checkout passed (925
passed, 2 skipped, 8 min 28 s); under Wine, imports and every view; the install check again: 0.7.0 first, then
this build over it in 37 s, the installed tree byte-identical to the stage (10 799 files) plus `Uninstall.exe`, no
file of 0.7.0 left, shortcuts and keys present, a clean uninstall. Its checksums are the `*.sha256` files here.

GitHub release (published 20 October 2026, 18:30:07 UTC, by the author from his own account; the build
environment may not create releases): https://github.com/asajeevan/electrochem-toolkit/releases/tag/v0.8.0, release
id 418709205, immutable, tag `v0.8.0` on 1463d92, five files: the three installers, the handout and
`SHA256SUMS.txt`. Before it was published the draft was checked three times with a first version of
`scripts/check_github_release.py` (the same checks of a draft; the attestation checks apply only after publishing):
the first check found the two macOS archives not yet attached and the notes file attached by mistake, the second
the notes file still attached, the third nothing wrong; then the release was published. After publishing the script found the
release immutable, the tag on 1463d92, GitHub's SHA-256 digest of each file equal to the tested file's, and GitHub's
release attestation (in-toto `release/v0.2`, a Sigstore bundle with a certificate and an RFC 3161 time stamp) naming
the commit and all five files with those digests: `github_release_v0.8.0_check.txt`, and the record with the
attestation bundle in `github_release_v0.8.0.json`. Not checked here: the attestation's signature. `gh release verify`
needs GitHub's attestation store and the Sigstore trust root, which this environment's network policy refuses;
`gh release verify v0.8.0 -R asajeevan/electrochem-toolkit` does it on any connected computer.
