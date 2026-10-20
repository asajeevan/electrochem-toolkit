# ADR-006: How Cyclara is shared

Date: 20 October 2026. Status: **proposed**; the decision and the accounts are the author's. Facts below were
checked on this date at the sources listed; prices and eligibility change, so check again before paying.

## Context

Cyclara 0.8.0 is three installers of 105 to 154 MB (Windows, Apple Silicon Mac, Intel Mac), the handout and the
source, under GPL-3.0-or-later. None is code-signed. The app already points to
`https://github.com/asajeevan/electrochem-toolkit` in About, Help > Cite Cyclara, Help > Report a problem and
`CITATION.cff`. The first readers are colleagues; later anyone. What "safe" has to mean here:

1. A recipient gets exactly the file that was built and tested, and can check it.
2. A link cannot later serve a different file under the same name.
3. A version can be cited and found again years later.
4. Nothing private leaves with it (the release build already refuses files that mention the author's own cells).
5. The author's accounts cannot be used to replace the files.

## Options checked

| Option | What it gives | Against it |
|---|---|---|
| Google Drive link | easy | Drive does not scan files over 100 MB ("There's a 100MB scanning limit"), so every recipient of these installers sees a warning; a recipient cannot check where the file came from; the file behind a link can be replaced silently; no versions visible to recipients |
| E-mail attachment | none | Gmail blocks `.exe` files, also inside a `.zip`; the installers are also far above attachment sizes |
| **GitHub Releases** (public repository) | each file under 2 GiB, no limit on total size or bandwidth; a stable page per version; with **immutable releases** (generally available since 28 October 2025) assets cannot be added, modified or deleted and the tag cannot be moved once published, and GitHub signs a release attestation; anyone can check a download with `gh release verify-asset v0.8.0 <file>` or by its SHA-256 | the files stay unsigned (see below) |
| **Zenodo** (connected to the repository) | once a repository is enabled, "new releases from the repository will be automatically ingested and archived" with a DOI; metadata from `CITATION.cff` (ignored if a `.zenodo.json` exists); run by CERN, records also archived in Software Heritage | none for this purpose; whether the binaries themselves are archived was not confirmed, the release's source is |
| Private GitHub repository | releases visible only to people given read access | recipients need a GitHub account; no DOI until public |

### Code signing (removes "unknown publisher"; does not remove the first warnings at once)

Microsoft: a newly signed file "could still show a SmartScreen warning until its hash or publisher certificate
accumulates sufficient evidence of positive reputation"; "EV certificates no longer bypass SmartScreen";
unsigned files "must build reputation anew with every update", whereas signed ones share the certificate's
reputation.

| Option | Cost | Fit |
|---|---|---|
| Azure Artifact Signing (formerly Trusted Signing) | 9.99 USD a month | public-trust certificates for organisations in the USA, Canada, EU and UK, and for **individuals only in the USA and Canada**: not open to an individual in France |
| Certum Open Source Code Signing on SimplySign | 49 EUR | for open-source developers; cloud key with a phone app, no card reader; the certificate carries the developer's own name after "Open Source Developer"; the shop page showed "out of stock" on 20 October 2026 |
| SignPath Foundation | free | OSI licence without commercial dual-licensing, actively maintained, already released; binaries must be built from the public source by CI (origin verification) and each signing approved; **the certificate is issued to SignPath Foundation**, so that name, not the author's, is shown as publisher |
| Apple Developer Program (macOS) | 99 USD a year | Developer ID signing and notarisation; without it, since macOS Sequoia a user must go to System Settings > Privacy & Security > Open Anyway once (Control-click > Open no longer does it) |

## Decision (recommended)

1. **Publish each version as an immutable GitHub Release** of the public repository, with the three installers,
   the handout and `SHA256SUMS.txt` as assets, and the release notes (`docs/releases/v0.8.0.md`) as its text.
   Share the link to the release page, never the files themselves.
2. **Connect Zenodo to the repository before publishing the release**, so the release receives a DOI; then add the
   DOI to `CITATION.cff` and to Help > Cite Cyclara (`electrochem/citation.py`).
3. **Protect the accounts**: two-factor authentication on GitHub; revoke any access token that was ever pasted
   into a chat; publish from your own login, or let an assistant work through a GitHub connection scoped to this
   one repository rather than a pasted token.
4. **Signing later, when the user base justifies it**: Windows first, with Certum's open-source certificate (your
   name as publisher) or SignPath Foundation (free, once the installers are built by GitHub Actions); macOS only if
   Mac users are many. Until then the handout's one-time "Run anyway" and "Open Anyway" steps stay.
5. **For a closed group before a public release**: a private repository with invited readers.

## Consequences

Recipients get a stable address, files that cannot be swapped after publication, and a way to check them; papers
can cite a DOI that resolves to the exact version; the one-time Windows and macOS warnings remain until signing.

## Sources (inspected 20 October 2026)

- Google Drive security and the 100 MB scanning limit: https://support.google.com/drive/answer/141702
- File types blocked in Gmail: https://support.google.com/mail/answer/6590
- About releases (2 GiB per file, no total or bandwidth limit): https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- Immutable releases generally available: https://github.blog/changelog/2025-10-28-immutable-releases-are-now-generally-available/
- Immutable releases: https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases
- `gh release verify-asset`: https://cli.github.com/manual/gh_release_verify-asset
- Zenodo, enable a repository: https://help.zenodo.org/docs/github/enable-repository/
- Zenodo, CITATION.cff: https://help.zenodo.org/docs/github/describe-software/citation-file/
- Zenodo, archive a release from GitHub: https://help.zenodo.org/docs/github/archive-software/github-upload
- SmartScreen reputation: https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation
- Azure Artifact Signing eligibility: https://devclass.com/2026/01/14/code-signing-windows-apps-may-be-easier-and-more-secure-with-new-azure-artifact-service/ and https://learn.microsoft.com/en-us/answers/questions/5915697/can-an-irish-sole-trader-(non-incorporated)-qualif (an AI-generated answer on Microsoft Q&A, June 2026; check the Artifact Signing FAQ before relying on it)
- Certum Open Source Code Signing on SimplySign: https://shop.certum.eu/open-source-code-signing-on-simplysign.html
- SignPath Foundation terms: https://signpath.org/terms
- Apple Developer Program and Gatekeeper behaviour (secondary source): https://flaviocopes.com/apple-developer-free-vs-paid/
