"""Run a script or module with the bundled Windows Python under Wine, with stdout and stderr
captured to a file: Wine gives a window program (Cyclara.exe is one) no console handles it
can use, so Python's own streams cannot be relied on there.

    Cyclara.exe -X utf8 wine_run.py LOG script.py [args]
    Cyclara.exe -X utf8 wine_run.py LOG -m module [args]
    Cyclara.exe -X utf8 wine_run.py LOG -c "code"
"""
import faulthandler
import runpy
import sys

log = open(sys.argv[1], "a", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr = log
faulthandler.enable(file=log)
rest = sys.argv[2:]
code = 0
try:
    if rest and rest[0] == "-m":
        sys.argv = rest[1:]
        runpy.run_module(rest[1], run_name="__main__", alter_sys=True)
    elif rest and rest[0] == "-c":
        sys.argv = ["-c"] + rest[2:]
        exec(compile(rest[1], "<wine_run -c>", "exec"), {"__name__": "__main__"})
    else:
        sys.argv = rest
        runpy.run_path(rest[0], run_name="__main__")
except SystemExit as e:
    code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    print("SystemExit", e.code)
except BaseException:
    import traceback
    traceback.print_exc()
    code = 1
print("wine_run done, code", code)
log.close()
sys.exit(code)
