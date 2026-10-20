# Releasing Cyclara

How a version reaches other people, as done for 0.8.0 on 20 October 2026. Why this way, and what was compared:
`docs/adr/ADR-006_Distribution.md`. Share the link to the release page
(`https://github.com/asajeevan/electrochem-toolkit/releases/latest`), never the files themselves.

## Once per repository

- **Immutable releases.** Settings > General > Releases > *Enable release immutability* (on since 20 October
  2026). It applies to releases published afterwards: their files cannot be added, replaced or deleted, the tag
  cannot be moved or deleted, and GitHub signs a release attestation that names the tag's commit and the SHA-256
  of every file. The title and the description stay editable. A tag that belonged to an immutable release can
  never be used again, even after the release is deleted, so a mistake found after publishing means a new version.
- **Zenodo, for a DOI** (not used for now, the author's choice). If a DOI is wanted: sign in at zenodo.org with
  GitHub and switch this repository on *before* publishing the release that should get one. Zenodo archives the
  releases published after that, not earlier ones, and takes the metadata from `CITATION.cff` (a `.zenodo.json`
  file would replace it).

## Each release

1. **Version.** Set `__version__` and `__released__` in `electrochem/__init__.py`, regenerate `CITATION.cff` with
   `python -m electrochem.citation --write` (a test requires the committed file to equal the generated one), and
   write `docs/releases/vX.Y.Z.md`: a first-level heading, then one line per paragraph, because the release page
   breaks lines where the text does.
2. **Build what is published.** Commit and push to `main`. From a clean checkout of that commit run the whole
   suite and build the installers (`installer/README.md`), then the Wine harness and the install check on the
   Windows build.
3. **The release folder.** The three installers, the handout, and `SHA256SUMS.txt` (`sha256sum` of those four
   files). Nothing else is attached.
4. **Record it.** Put the checksums in the notes and the build evidence in `docs/evidence/p13_installers/`;
   commit and push. From now until the release is published, push nothing else to `main`: the tag is created
   on `main` at the moment of publishing.
5. **Draft.** Releases > *Draft a new release*, or
   `https://github.com/asajeevan/electrochem-toolkit/releases/new?tag=vX.Y.Z&target=main&title=Cyclara%20X.Y.Z`:
   tag `vX.Y.Z` (*Create new tag*, target `main`), title `Cyclara X.Y.Z`, the notes without their heading, the
   files of the release folder. Wait for every upload to finish, then *Save draft*, not *Publish*.
6. **Check the draft.**

   ```
   python scripts/check_github_release.py --tag vX.Y.Z --dir FOLDER --commit <main's SHA> --notes docs/releases/vX.Y.Z.md
   ```

   It must end with READY TO PUBLISH. It needs the GitHub CLI (`gh`) signed in with read access, and it only
   reads. For 0.8.0 it caught the two macOS archives not yet attached and the notes file attached by mistake.
7. **Publish**, then run the same command with `--record docs/evidence/p13_installers/github_release_vX.Y.Z.json`.
   It must end with PUBLISHED AND VERIFIED: immutable, the tag on the expected commit, GitHub's digest of every
   file equal to the tested one, and the attestation naming each of them.
8. **The attestation's signature**, on any computer with ordinary network access:
   `gh release verify vX.Y.Z -R asajeevan/electrochem-toolkit`, and for a downloaded file
   `gh release verify-asset vX.Y.Z FILE -R asajeevan/electrochem-toolkit`. (The build machine's network policy
   blocks the attestation store and the Sigstore trust root, so this step was not run there for 0.8.0.)
9. **With Zenodo on:** when the DOI appears, add it to `electrochem/citation.py`, regenerate `CITATION.cff`, and
   commit.
