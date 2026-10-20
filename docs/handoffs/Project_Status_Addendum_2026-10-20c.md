# Project status addendum, 20 October 2026 (c): LANHE `.cex` read natively

Follows `Project_Status_Addendum_2026-10-20b.md`. Everything here is in `main` and not yet in an installer.

## What was asked

A user sent a LANHE `.cex` (private) and asked for every output to be checked. Cyclara crashed on it (a raw `csv` error); that was fixed by refusing it in words (commit c94343d). Then: "We must have a way to read it properly on the software."

## Delivered

| Item | Status | Evidence |
|---|---|---|
| Native `.cex` reader, `electrochem/readers/lanhe_cex.py` (`lanhe-cex` 1.0.0) | implemented, software-tested, verified on one real file by four statements inside it; LANHE's own export of that file not yet compared | `docs/P08g_LANHE_cex_Reader.md`; `tests/test_readers_cex.py` (28 tests on synthetic files; 26 deliberate faults in the reader all caught); a private regression check beside the real file |
| Checks on every `.cex` opened | implemented, tested | record time against the tester's clock; decoded current against the capacity counter and voltage against the energy counter (0.2 %); direction against step type; counter behaviour; framing. Unverified layouts, step types, events and units are refused with what was found |
| `instrument_steps.csv` (the tester's step table rebuilt) and the reader's record in `settings.json` | implemented, tested | `tests/test_readers_cex.py` |
| M01 section 6 amendment: a step that ended at once | implemented, tested at both edges of each condition; 14 deliberate faults in the rule, the figure fixes and the app wording all caught | `tests/test_degenerate_pairs.py`; M01 section 6 |
| The app asks the cycle order when a file opens with such a step; the direction of a `.cex` is answered from its step types, with the evidence shown | implemented, driven offscreen on a synthetic file and the real one | `tests/test_degenerate_pairs.py` (model), `tests/test_studio.py` (the window, a synthetic `.cex`); screenshots not kept in the repository |
| Figure fixes: shared cycle axis of the dQ/dE map, whole cycle numbers for a single cycle, the bin-width note clear of the data, the cycle's own hysteresis drawn and empty legend entries dropped | implemented, tested | `tests/test_degenerate_pairs.py`, `tests/test_figures.py` |
| App wording: cut-short cycles told apart from unpaired ones (diagnostics, cycle strip, capacity view); the methods window names the profile a file was read with (it never did: `getattr` on a string); the CLI no longer fails when a mean hysteresis is withheld | implemented, tested | `tests/test_studio.py`; the window driven offscreen |

## Decisions

- Read the `.cex` natively rather than ask for exports: a real file could be decoded completely and its reading checked against the tester's own physical-unit counters, which no text import offers.
- Accept a range code beyond the verified two only when the file's own counters confirm the scale it gives; refuse otherwise.
- Pass no native cycle number to the engine; list the tester's cycle markers per step.
- Keep M01's last-branch rule (a branch reaching the end of the data is interrupted) even when the tester wrote its end-of-test event: whether that event means "ended as programmed" is not established.

## Open

- Compare the real `.cex` with LANHE's Excel export of the same run (Record, Step and Cycle sheets); more `.cex` files from other channels and protocols (other range codes, constant-voltage discharge, pauses).
- A constant-voltage hold analysis (current against time on a log axis, the current at the end of the hold, charge passed in the hold, normalised by area or mass) would serve hold and stability tests; not started.
- A way for the researcher to state that a run ended as programmed, so the last branch can count as complete; not started (M01 change).
- Installers carrying these changes: released as 0.9.0, after an independent review whose findings are in `Project_Status_Addendum_2026-10-21.md`.
