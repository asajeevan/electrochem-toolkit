# Project status addendum, 21 October 2026 (b): a second LANHE file, pauses and restarts

Follows `Project_Status_Addendum_2026-10-21.md` (the 0.9.0 release and its review).

## What was asked

"Try this input file from lanhe": a second real `.cex` file (private; it, its measurements and its protocol stay out of the repository). 0.9.0 refused it, as designed: its layout code (`05 00 04 00`) and its status events had not been seen. The aim was to read it properly and show its analysis; the change goes into the next version, 0.9.1, and 0.9.0 stays as published.

## What the file showed, and what was built

Decoded by hand first, from the records on both sides of every event and the tester's clock (P08g section 8.1): the second layout has the units, records and scales of the first; a pause is not counted by the record time; at a stop with a restored state the tester goes back a few seconds in record time and in its counters, so those seconds are recorded twice and its own counter drops their charge; the resume details always come with a resume; five other event codes leave the records unchanged.

| Item | Status | Where |
|---|---|---|
| Reader `lanhe-cex` 1.1.0: second layout; pauses; stops with a restored state (every record kept, the left-out charge kept, the interval across not integrated, a warning at each); the other events checked at every occurrence; event order and restarts checked, refused otherwise | implemented, software-tested, verified on the file | `electrochem/readers/lanhe_cex.py`, P08g section 8 |
| Clock check judged interval by interval (one change of the clock no longer moves the test of the time unit), with pauses and stops added back | implemented, software-tested | P08g section 3 |
| No dQ/dE for a branch with a curve break (time going back or invalid, a missing current, an error flag), and the cycle note says so; zero-duration intervals are not breaks | implemented, software-tested | M01 section 9.3, `electrochem/segment.py`, `electrochem/differential.py`, `electrochem/cycling.py` |
| The summary names every incomplete cycle it leaves out | implemented, software-tested | M01 section 6, `electrochem/cycling.py` |
| No dQ/dE for a branch paused partway (found by the review, below); the branch keeps its completeness, efficiency and retention | implemented, software-tested, checked on the file | M01 sections 5.1 and 9.3, `Table.paused` |
| Methods text, methods record, app diagnostics, README, `HOW_TO_USE.txt`, handout (still 15 pages), STATUS, P08d; version 0.9.1 | updated | |

## An independent review before the build

A separate agent that had not written the code compared every statement about the new work (the reader's messages, the cycle notes, the methods text and record, README, `HOW_TO_USE.txt`, STATUS, P08g, M01, P08d) with the code, and tried edge cases on synthetic files. Its 18 findings, and what was done:

| Finding | Kind | Done |
|---|---|---|
| A restart going back 0 s was accepted; the engine then saw a zero-duration interval, which is not a curve break, so the dQ/dE rule did not apply | defect | a restart must go back more than 0 s (never seen at 0 s); test |
| A pause folds the potential like a stop (the current is off and the cell relaxes); the engine saw an ordinary interval | gap | checked on the real file: the potential relaxed a few millivolts at each pause. A pause inside a branch is now marked (`Table.paused`) and the branch has no dQ/dE, keeping its completeness, efficiency and retention; M01 section 9.3; tests |
| A restart in the reference cycle removes every retention, which the texts did not say and the summary did not explain | understatement | the summary says when the reference cycle is not complete; the warning, the methods paragraph, README, P08d and P08g say so; test with reference cycles 1 and 2 |
| "Checked at each" for the other events overstated: the resume details are checked for their place only, and events at step boundaries not at all | overclaim | the note now counts the events by place (inside a step, checked; elsewhere, listed; with resumes); report key `other_events_where`; P08g, STATUS and comments reworded; test |
| "Twice the step's largest other interval" refused a valid short step (10.5 s logged every 10 s) | defect | the reference is the larger of that and the file's usual logging interval; test |
| No continuity check across a pause | gap | the records must continue across a pause inside a step, as across any other event; test |
| P08g said an event between a stop's resume and the first record after it is refused, but start, end and step-change events are not checked anywhere | overclaim | P08g, the reader's docstring and comments: those three are listed, not checked, as in 0.9.0 |
| A pause or stop resumed before the first record or after the last was dropped silently | gap | a pause there is listed and added back in the clock check; a stop there is refused (nothing to check it against); the clock warning names only a change of the clock when the record time ran ahead; tests |
| When every current-carrying step has a restart, the scale-check note blamed too little current | unclear | the note and the evidence sentence say the steps with a restart were left out; test |
| The restart warning called the counter drop the records' charge, and said the counters "go back" seconds; the refusal's rule was misstated | wording | reworded: the charge the counter left out by going back; the counters return to their values of that moment; the rule as coded |
| The cycle note said branches.csv gives the reasons, and an unpaired branch with a curve break got no dQ/dE note | wording | "(settings.json lists each interval and why)"; every branch without dQ/dE is named in its pair's note with the reason |
| Five event refusals gave no remedy, unlike the documents | overclaim | each now says to export the run to Excel from the tester's software |
| "Names every incomplete cycle" though the list stops at twelve | overclaim | the note adds how many in all; the documents say so; test |
| The package version was still 0.9.0 | inconsistency | bumped to 0.9.1 with the citation file and the handout |
| "An open M01 question" that M01 did not record | inconsistency | recorded in M01 section 5.1 |
| "34 deliberate faults, 32 caught" without the list | evidence | the list and the result of each are committed under `docs/evidence/p08g_cex_1.1.0/` |
| `cex_counter_start` said "restart" for a reset | wording | "reset" |
| The end-of-file note called an unresumed stop "a stop, state restored"; `HOW_TO_USE.txt` said "no efficiency" for every interrupted cycle | wording | "ends in a stop"; "during a charge or discharge ... no efficiency or retention" |

The reviewer also confirmed, on synthetic files, the thresholds and refusal codes, the restart handling (both passes kept, the left-out charge in the capacity, in carried constant-voltage steps too), that `differential.curve` returns None exactly for the branches named, and that the two deliberate faults that survive are equivalent to the code.

## Checks

- `tests/test_readers_cex.py` 60 tests (29 in 0.9.0), `tests/test_interrupted_branches.py` 7 (new), the row-by-row reference of `tests/test_segment_speed.py` extended to curve breaks and their reasons; the app test checks the new clock line. Whole suite on Linux before the review: 1031 passed, 2 skipped, 56 subtests (7 min 40 s); after the review's fixes and the version change: 1040 passed, 2 skipped, 56 subtests (7 min 54 s). The 268 frozen reference checks pass.
- Deliberate faults: before the review, 34 in the new code, 32 caught, the two others equivalent; after the review's fixes, 50 (the new rules included), 49 caught, the other equivalent to the code (P08g section 8.4; `docs/evidence/p08g_cex_1.1.0/`).
- A census of the real files in `data/public` caught the first form of the dQ/dE rule, which counted zero-duration intervals and would have removed every dQ/dE curve of the Landt Excel example. With the rule as kept, all 23 public real files the app analyses give the same cycle values, curves and summary values under 0.9.0 and the working tree, compared value by value; only notes differ: the Landt Excel example's cycle notes now say how many intervals are not integrated, and five summaries now name the incomplete cycles they leave out (an unpaired first branch among them), where they named only an unfinished last cycle or nothing. The census also found that no cycle of that Landt export has an efficiency (time printed to 0.01 h; M01 integrates no interval without advancing time): unchanged since P08d, now written down in P08d, STATUS and the release notes, and left as an open M01 question.
- Private regression checks, beside the private files: the first `.cex` reads and analyses exactly as under 1.0.0; the second reads as established by hand; the author's own EC-Lab file gives identical cycles, curves and notes under 0.9.0 and the working tree.

## Open

- LANHE's own Excel export of either `.cex` file, for an independent row-by-row comparison.
- The meaning of events 0x1013, 0x0404, 0x2001 and 0x2004.
- An M01 rule for times shared only through print resolution (Landt Excel exports have no efficiency today).
