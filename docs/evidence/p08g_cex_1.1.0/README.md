# Evidence: the LANHE `.cex` reader 1.1.0 and the 0.9.1 engine changes

- `mutate.py`: 87 deliberate faults in the reader (event order, restarts, pauses, counters, the clock and scale
  checks, the messages), in the dQ/dE rule and its counts of curve breaks and pauses (between the curve's first and
  last row), in the cycle notes, the summary and the methods paragraph, in the peak tables of branches without a
  curve, in the figures without any curve and the figure checker, and in the dQ/dE view and its notes. It writes each into a copy
  of the repository, runs the tests, and puts the file back.
- `deliberate_faults.txt`: the run of 21 October 2026, after the fixes of all four independent reviews. 86 of the
  87 made a test fail. The one that did not drops the same-step condition of a restart, which is equivalent to the
  code: when the first record after a stop is its step's first record, no record of that step lies before it, so
  the restored counters cannot be bracketed and the stop is refused either way (P08g section 8.4). The runs before
  the second review (50 faults, 49 caught), the third (66, 65) and the fourth (77, 76), with the same survivor, are in
  this folder's git history.

What was checked on the two real files (private) is described, without their values, in P08g sections 3 and 8.
