"""Deliberate faults in the reader lanhe-cex 1.1.0 and the engine changes of Cyclara 0.9.1, each run against
the tests in a copy of the repository (P08g section 8.4).

    cp -r electrochem eclab_import tests conftest.py pyproject.toml COPY/
    python3 docs/evidence/p08g_cex_1.1.0/mutate.py COPY

Each fault is written into the copy, the tests below run, and the original file is put back. A fault that no
test catches is printed SURVIVED; deliberate_faults.txt holds the run of 21 October 2026.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
HERE = Path(__file__).resolve().parents[3]                   # the repository this script belongs to
assert ROOT != HERE and HERE not in ROOT.parents, "faults are written into a copy only, never the repository"
TESTS = ["tests/test_readers_cex.py", "tests/test_interrupted_branches.py", "tests/test_degenerate_pairs.py",
         "tests/test_segment_speed.py", "tests/test_methods_text.py"]
R = "electrochem/readers/lanhe_cex.py"
M = [
    ("second layout not read", R, 'LAYOUTS = (b"\\x07\\x00\\x04\\x00", b"\\x05\\x00\\x04\\x00")', 'LAYOUTS = (b"\\x07\\x00\\x04\\x00",)'),
    ("records between pause and resume accepted", R, 'if open_break["record"] != j:', 'if False:'),
    ("orphan resume accepted", R, """            if open_break is None:
                fnd.refuse(""", """            if open_break is None:
                continue
                fnd.refuse("""),
    ("resume detail anywhere", R, "            if j not in resumed_at:", "            if False:"),
    ("no gap check at an inert event", R, "limit = 2.0 * max(float(others.max()), typical) if others.size else np.inf",
     "limit = np.inf"),
    ("the file's usual interval ignored", R, "limit = 2.0 * max(float(others.max()), typical) if others.size else np.inf",
     "limit = 2.0 * float(others.max()) if others.size else np.inf"),
    ("counter fall accepted at an event", R, "return bool(0 < t[j] - t[j - 1] <= limit and q[j] >= q[j - 1])",
     "return bool(0 < t[j] - t[j - 1] <= limit)"),
    ("records not checked across a pause", R,
     "if where is None and row_step[j] == row_step[j - 1] and not _continues(j, row_step, steps, t, q,",
     "if False and not _continues(j, row_step, steps, t, q,"),
    ("pauses at the ends dropped", R, "                    pauses.append(entry)\n",
     "                    if where is None:\n                        pauses.append(entry)\n"),
    ("stops at the ends taken as restarts", R, "                elif where is None:\n                    restarts.append(entry)",
     "                elif True:\n                    restarts.append(entry)"),
    ("restart going back 0 s accepted", R, "not 0 < back <= ROLLBACK_MAX_S", "not 0 <= back <= ROLLBACK_MAX_S"),
    ("any rollback length", R, "not 0 < back <= ROLLBACK_MAX_S", "not 0 < back"),
    ("records going forward taken as a restart", R, "not 0 < back <= ROLLBACK_MAX_S", "not back <= ROLLBACK_MAX_S"),
    ("restored counter not checked", R, "or not bracketed:", "or False:"),
    ("restart across steps accepted", R, "if row_step[j - 1] != row_step[j] or not", "if not"),
    ("second restart searched from the step start", R, "        since[k] = j\n", ""),
    ("never-resumed pause accepted", R, 'if open_break is not None and open_break["record"] < n:', "if False:"),
    ("restored record's increment kept", R, "        inc[inside] = 0.0\n", ""),
    ("counter decrease allowed anywhere", R, "drop = np.setdiff1d(np.flatnonzero(np.diff(qq) < 0), inside - 1)",
     "drop = np.array([], dtype=np.int64)"),
    ("unexplained time decrease accepted", R, "    if unexplained:\n        fnd.refuse(\"cex_time_backwards\"",
     "    if False:\n        fnd.refuse(\"cex_time_backwards\""),
    ("pause time not added back", R, "rec = np.array([p[1] for p in pts], float) + not_counted",
     "rec = np.array([p[1] for p in pts], float)"),
    ("break counted before its step start", R, "dur[at < f].sum()", "dur[at > f].sum()"),
    ("one disagreeing interval refuses", R, "2 * clock[\"intervals_agreeing\"] < clock[\"intervals\"]",
     "clock[\"intervals_agreeing\"] < clock[\"intervals\"]"),
    ("no resolution allowance", R, "CLOCK_SLOPE_TOLERANCE + 2.0 / dw", "CLOCK_SLOPE_TOLERANCE"),
    ("disagreement not reported", R, "        if excess.max() > 0:\n            k = int(np.argmax(excess))",
     "        if False:\n            k = int(np.argmax(excess))"),
    ("clock suggestion not by direction", R, 'why = ("a change of the clock, or a pause the file does not mark" if dis["seconds"] < 0',
     'why = ("a change of the clock, or a pause the file does not mark" if True'),
    ("file ending paused not said", R, "    if ends_open is not None:\n        kind_ =", "    if False:\n        kind_ ="),
    ("file ending in a stop called a pause", R, 'kind_ = "pause" if ends_open["kind"] == PAUSE else "stop"', 'kind_ = "pause"'),
    ("restart in a rest worded as a branch", R, "        if step.direction:\n            what = (", "        if True:\n            what = ("),
    ("restart not warned", R, 'fnd.warn("cex_restart"', 'fnd.note("cex_restart"'),
    ("generic time warning kept", R, 'if not (f.code == "time_goes_backwards" and not unexplained):', "if True:"),
    ("scale check includes restart steps", R, "scale = _scale_check([s for s in steps if s.seq not in restart_steps], t, i, e, q, w)",
     "scale = _scale_check(steps, t, i, e, q, w)"),
    ("scale note silent about restarts", R, "                if restart_steps else \"\")\n        fnd.note(\"cex_scale_not_checked\"",
     "                if False else \"\")\n        fnd.note(\"cex_scale_not_checked\""),
    ("other events not told apart by place", R, "            elif 0 < j < n and row_step[j] == row_step[j - 1]:\n                place = \"inside_steps\"",
     "            elif True:\n                place = \"inside_steps\""),
    ("paused rows not passed on", R, 'paused_rows=np.array([pz["record"] - 1 for pz in pauses if pz["where"] is None], dtype=np.int64))',
     "paused_rows=None)"),
    ("pauses not counted in branches", "electrochem/segment.py", "        paused[np.asarray(rows, dtype=np.int64)] = True\n",
     "        pass\n"),
    ("pauses counted over the wrong rows", "electrochem/segment.py",
     "pauses=int(paused_before[end + 1] - paused_before[start + 1]),", "pauses=int(paused_before[end] - paused_before[start]),"),
    ("dQ/dE of an interrupted branch kept", "electrochem/differential.py",
     'if getattr(branch, "curve_breaks", 0) or getattr(branch, "pauses", 0):', 'if getattr(branch, "pauses", 0):'),
    ("dQ/dE of a paused branch kept", "electrochem/differential.py",
     'if getattr(branch, "curve_breaks", 0) or getattr(branch, "pauses", 0):', 'if getattr(branch, "curve_breaks", 0):'),
    ("dQ/dE withheld at the end of data too", "electrochem/differential.py",
     'if getattr(branch, "curve_breaks", 0) or getattr(branch, "pauses", 0):',
     'if getattr(branch, "curve_breaks", 0) or getattr(branch, "pauses", 0) or not branch.complete:'),
    ("dQ/dE withheld at zero-duration edges", "electrochem/segment.py",
     "CURVE_BREAKS = (TIME_INVALID, CURRENT_INVALID, ERROR_FLAG)",
     "CURVE_BREAKS = (TIME_INVALID, ZERO_DURATION, CURRENT_INVALID, ERROR_FLAG)"),
    ("time going back not a curve break", "electrochem/segment.py",
     "CURVE_BREAKS = (TIME_INVALID, CURRENT_INVALID, ERROR_FLAG)", "CURVE_BREAKS = (CURRENT_INVALID, ERROR_FLAG)"),
    ("curve breaks counted over the wrong edges", "electrochem/segment.py",
     "curve_breaks=int(breaks_before[end] - breaks_before[start]),",
     "curve_breaks=int(breaks_before[end + 1] - breaks_before[start]) if end + 1 < len(breaks_before) else 0,"),
    ("note without the dQ/dE reason", "electrochem/cycling.py",
     'no_curve = [_no_dqde(g) for g in sides if g.curve_breaks or getattr(g, "pauses", 0)]', "no_curve = []"),
    ("cycle note: plural wrong", "electrochem/cycling.py", '("1 interval that is" if g.unsupported_edges == 1 else',
     '("1 intervals that are" if g.unsupported_edges == 1 else'),
    ("cycle note: generic", "electrochem/cycling.py", "    if not ok and not p.note and gaps:", "    if False:"),
    ("summary names only the last", "electrochem/cycling.py", "left_out = [c.cycle for c in cycles if not c.complete]",
     "left_out = [c.cycle for c in cycles[-1:] if not c.complete]"),
    ("summary hides how many", "electrochem/cycling.py", '+ (f"... ({len(left_out)} in all)" if len(left_out) > 12 else "")',
     '+ ("..." if len(left_out) > 12 else "")'),
    ("missing reference not said", "electrochem/cycling.py", "    if reference_missing:\n", "    if False:\n"),
    ("methods paragraph silent on pauses", "electrochem/methods_text.py", "    if paused:\n        parts.append(",
     "    if False:\n        parts.append("),
]


def run():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *TESTS], cwd=ROOT,
                       capture_output=True, text=True, timeout=900)
    return r.returncode, (r.stdout.strip().splitlines() or [""])[-1]


code, last = run()
assert code == 0, f"the unmutated copy fails: {last}"
print("unmutated:", last)
survived = []
for name, rel, old, new in M:
    path = ROOT / rel
    text = path.read_text()
    assert text.count(old) == 1, f"{name}: the text to mutate occurs {text.count(old)} times"
    try:
        path.write_text(text.replace(old, new))
        code, last = run()
    finally:
        path.write_text(text)
    print(f"{'killed  ' if code else 'SURVIVED'} {name}: {last}")
    if not code:
        survived.append(name)
print(f"{len(M) - len(survived)} of {len(M)} mutations killed; survived: {survived}")
