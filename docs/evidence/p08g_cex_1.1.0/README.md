# Evidence: the LANHE `.cex` reader 1.1.0 and the 0.9.1 engine changes

- `mutate.py`: 50 deliberate faults in the reader (event order, restarts, pauses, counters, the clock and scale
  checks, the messages), in the dQ/dE rule and its counts of curve breaks and pauses, in the cycle notes, the
  summary and the methods paragraph. It writes each into a copy of the repository, runs the tests, and puts the
  file back.
- `deliberate_faults.txt`: the run of 21 October 2026, after the independent review's fixes. 49 of the 50 made a
  test fail. The one that did not drops the same-step condition of a restart, which is equivalent to the code:
  when the first record after a stop is its step's first record, no record of that step lies before it, so the
  restored counter cannot be bracketed and the stop is refused either way (P08g section 8.4).

What was checked on the two real files (private) is described, without their values, in P08g sections 3 and 8.
