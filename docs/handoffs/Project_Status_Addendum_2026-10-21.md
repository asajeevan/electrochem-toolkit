# Project status addendum, 21 October 2026: the 0.9.0 release and its review

Follows `Project_Status_Addendum_2026-10-20c.md` (the native LANHE `.cex` reader and the rule for a step that ended at once).

## What was asked

"Update it. Do everything by yourself": put the `.cex` reader into an installer, publish it, and update the web page.

## An independent review before the build

The first 0.9.0 build (from commit ca01400) passed the whole suite on Linux (995 passed, 2 skipped) and, as the Windows program under Wine, its own suite (974 passed, 18 skipped: the release tool's 15 tests and the installer's test module, which are not shipped, and the 2 that skip on Linux too). Before it was published, a separate agent that had not written the code compared every statement about the two new features (README, `HOW_TO_USE.txt`, the handout, `STATUS.md`, P08g, P08d, M01, the methods text, the release notes, the web page draft) with the code. That build was not released. The findings and what was done:

| Finding | Kind | Done |
|---|---|---|
| Help > How the numbers are calculated failed (TypeError) on its Energy topic when the first complete cycle has a withheld hysteresis: exactly the kind of file the new rule is for | defect | fixed; a withheld value is written "not given"; `tests/test_degenerate_pairs.py` renders every topic and the methods paragraph for such a file |
| A discharge that ended at once kept its retention, which then set the cycle reaching 80 % (a synthetic case gave cycle 2) and entered the fade fit | method gap | M01 section 6: no retention for such a cycle, so it stays out of the 80 % cycle, the fade line, the mean discharge potential and the first-cycle utilisation; no retention at all when it is the reference cycle's discharge; three tests |
| The `.cex` voltage check (needs a positive voltage) and clock check (needs two step starts 60 s apart) were skipped without a word | transparency | notes `cex_voltage_not_checked` and `cex_clock_not_checked`, like `cex_scale_not_checked`; a test |
| The step table's `start_clock_utc` claimed UTC though the file records no time zone | wrong label | renamed `start_clock`, written without a time zone |
| A one-row branch was described as "spans one recorded interval (0 s)" | wording | "is a single record" |
| "Checked on every file", "anything not seen refused", "every refusal ends with the remedy", "until 0.8.0 refused with an instruction", the rule without its conditions, `instrument_steps.csv` missing from output lists, `metadata.json` said to hold a step table for every file, stale versions | wording | corrected in the README, `HOW_TO_USE.txt`, the handout (still 15 pages), `STATUS.md`, P08g, P08d, M01, the methods text, the release notes and the web page draft |
| Qualitative descriptions of the user's private file in code comments, tests and documents | privacy | generalised; the documents now quote only how closely the four checks agreed |
| No test tied the methods text's 0.1 % and two rows to the constants | test gap | `tests/test_methods_text.py` |

Each fix was checked by undoing it in a copy of the repository: ten such changes (four in the pairing rule and the summary, one in the utilisation, two in the `.cex` notes, three in the methods text and `settings.json`), each made a new test fail. The private regression check on the real file still passes with the same values, and no "not checked" note appears for it (every check can be made on it).

## The release

| Item | Status | Evidence |
|---|---|---|
| Installers from a clean checkout of 36be5dd | built; 1002 tests pass on Linux; the Windows program under Wine opens every view and passes its own 981 tests; installed over 0.8.0 under Wine, the tree equals the tested one byte for byte, and it uninstalls cleanly; macOS bundles checked statically | `docs/evidence/p13_installers/0.9.0/` |
| GitHub release v0.9.0 | published 20 October 2026, 23:30 UTC, by the author from his phone; immutable; tag on f20082f; digests and attestation verified | `docs/evidence/p13_installers/0.9.0/github_release_v0.9.0*` |
| Web page | 0.9.0 downloads, sizes, checksums, citation; the cycler table and claims name the `.cex` reader with its conditions; new screenshots (version 0.9.0 in the status bar) | https://asajeevan.github.io/cyclara/ (site commit 9dd70ab) |

The draft check caught one fault the author's phone introduced (the checksum file renamed `SHA256SUMS-2.txt`); it was corrected before publishing. Not done: the attestation's signature (`gh release verify v0.9.0 -R asajeevan/electrochem-toolkit` on a connected computer), a physical Windows PC or Mac, and LANHE's own Excel export of the real `.cex` for comparison.
