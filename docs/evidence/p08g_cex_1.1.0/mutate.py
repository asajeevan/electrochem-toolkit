"""Deliberate faults in the 0.9.1 changes, each run against the tests in a copy of the repository.

python3 mutate.py COPY      (COPY: a copy of the repository, never the working tree)
Every mutation must make at least one of the tests fail; the original file is restored after each.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
assert "scratchpad" in str(ROOT), "mutations run in a copy only"
TESTS = ["tests/test_readers_cex.py", "tests/test_interrupted_branches.py", "tests/test_degenerate_pairs.py",
         "tests/test_segment_speed.py", "tests/test_methods_text.py", "tests/test_plateaus.py",
         "tests/test_figures.py", "tests/test_studio.py::test_the_dqde_view_says_why_it_has_no_curve"]
R = "electrochem/readers/lanhe_cex.py"
S, D, W, P, V, C = ("electrochem/segment.py", "electrochem/differential.py", "electrochem/workflow.py",
                    "electrochem/plotting.py", "electrochem/studio/views.py", "electrochem/cycling.py")
MT = "electrochem/methods_text.py"
LIMIT = "limit = 2.0 * max(float(others.max()), typical.get(step.type, 0.0)) if others.size else np.inf"
M = [
    ("second layout not read", R, 'LAYOUTS = (b"\\x07\\x00\\x04\\x00", b"\\x05\\x00\\x04\\x00")', 'LAYOUTS = (b"\\x07\\x00\\x04\\x00",)'),
    ("records between pause and resume accepted", R, 'if open_break["record"] != j:', 'if False:'),
    ("orphan resume accepted", R, """            if open_break is None:
                fnd.refuse(""", """            if open_break is None:
                continue
                fnd.refuse("""),
    ("resume detail anywhere", R, "            if j not in resumed_at:", "            if False:"),
    ("no gap check at an inert event", R, LIMIT, "limit = np.inf"),
    ("the step type's usual interval ignored", R, LIMIT, "limit = 2.0 * float(others.max()) if others.size else np.inf"),
    ("the usual interval of any step type", R, "typical.get(step.type, 0.0)", "max(typical.values())"),
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
    ("restored energy counter not checked", R, "and w[went_to] - tol_w <= w[j] <= w[nxt] + tol_w)", "and True)"),
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
    ("pauses counted over the wrong rows", S, "pauses=int(paused_before[last_nc + 1] - paused_before[first_nc + 1]),",
     "pauses=int(paused_before[last_nc] - paused_before[first_nc]),"),
    ("pauses counted in constant-voltage stages", S, "pauses=int(paused_before[last_nc + 1] - paused_before[first_nc + 1]),",
     "pauses=int(paused_before[end + 1] - paused_before[start + 1]),"),
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
    ("curve breaks counted over the wrong edges", S, "curve_breaks=int(breaks_before[last_nc] - breaks_before[first_nc]),",
     "curve_breaks=int(breaks_before[last_nc + 1] - breaks_before[first_nc]) if last_nc + 1 < len(breaks_before) else 0,"),
    ("curve breaks counted in constant-voltage stages", S, "curve_breaks=int(breaks_before[last_nc] - breaks_before[first_nc]),",
     "curve_breaks=int(breaks_before[end] - breaks_before[start]),"),
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
    ("cycle note: reasons in the code's words", C, "why = [_BREAK_WORDS.get(reason, reason) for reason in",
     "why = [reason for reason in"),
    ("withheld curve reported as an absent branch", D, "if (c, other) in withheld", "if False"),
    ("cycles without a curve not listed", D, "no_curve_cycles=gaps[cv.direction]))", 'no_curve_cycles=""))'),
    ("first-cycle-only entries without their cycle", D, '{"direction": p.direction, "cycle": p.cycle, "voltage_V"',
     '{"direction": p.direction, "voltage_V"'),
    ("presence judged over every cycle", D, "evolution=evolution_text(t, analysed[cv.direction], known),",
     "evolution=evolution_text(t, cycles, known),"),
    ("seen ranges over the direction's cycles only", D, "cycles_seen=cycle_ranges(t.cycles, known),",
     "cycles_seen=cycle_ranges(t.cycles, analysed[cv.direction]),"),
    ("first-cycle-only words without the cycle", D, "    if p.cycle == 1:\n        return \"present in the first cycle only\"",
     "    if True:\n        return \"present in the first cycle only\""),
    ("withheld branches not passed to the peak tables", W,
     "cached = differential.plateau_analysis(curves, window_mV=self.peak_pair_window_mV, withheld=withheld)",
     "cached = differential.plateau_analysis(curves, window_mV=self.peak_pair_window_mV)"),
    ("3D figure without a curve drawn in 3D", P, "    if not grids:                    # the reason alone",
     "    if False:                    # the reason alone"),
    ("empty dQ/dE figure keeps its scale", P, "    if not curves:                   # the axis titles and the reason",
     "    if False:                   # the axis titles and the reason"),
    ("checker counts tick labels it does not draw", P,
     'tick_ids.update((id(t.label1), id(t.label2)))\n            if not (ax.get_visible() and axis.get_visible() and _axes_drawn(ax)):',
     'tick_ids.update((id(t.label1), id(t.label2)))\n            if not (ax.get_visible() and axis.get_visible()):'),
    ("3D axes taken as not drawn", P, 'return bool(getattr(ax, "_axis3don", True)) if is_3d(ax) else bool(getattr(ax, "axison", True))',
     'return bool(getattr(ax, "axison", True))'),
    ("dQ/dE view silent when no branch has a curve", V, "        if withheld and not curves:\n", "        if False:\n"),
    ("dQ/dE view note silent on withheld branches", V, '"discharge left, charge right.", withheld_note(run, withheld, sym)])',
     '"discharge left, charge right."])'),
    ("stale note above the empty sentence", V,
     "            self.set_note([])                        # no note of an earlier selection above the sentence\n", ""),
    ("view note without the reasons", V, 'items = [f"cycle {c} {d} ({no_curve_why(run, c, d)})" for c, d in keys[:shown]]',
     'items = [f"cycle {c} {d}" for c, d in keys[:shown]]'),
    ("view sentence without the axis symbol", V, "self.set_empty(NO_DQDE.format(sym=sym))", 'self.set_empty(NO_DQDE.format(sym="E"))'),
    ("interruption in a hold not in the paragraph", MT,
     "    interrupted = _interrupted(seg, branches)\n",
     '    interrupted = {b.index: set(getattr(b, "breaks_why", ())) for b in branches if getattr(b, "curve_breaks", 0)}\n'),
    ("interval in a hold said to remove the dQ/dE", MT, "        if m == n:\n", "        if True:\n"),
    ("reference discharge ended at once not said", MT, "        elif ref is not None and ref.capacity_retention_pct is None:",
     "        elif False:"),
    ("topic line without the cycle", MT, 'if u.get("cycle", sm["cycle"]) != sm["cycle"] else ""', 'if False else ""'),
    ("restart in a hold worded as removing the dQ/dE", R, "its dQ/dE when that hold ends it (M01 section 9.3)\" if step.mode == 2 else",
     "its dQ/dE when that hold ends it (M01 section 9.3)\" if False else"),
    ("pause note says partway", R, "A charge or discharge branch paused inside its dQ/dE curve (between its \"\n                 \"first and last record outside constant-voltage stages) keeps",
     "A charge or discharge branch paused partway keeps"),
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
