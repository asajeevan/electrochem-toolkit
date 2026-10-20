# Testing the Windows build without Windows

`run.sh` runs the staged Windows tree (installer/build/stage_win) under Wine 9:
the real Cyclara.exe hosting the real bundled CPython 3.12 and the real Windows
wheels. It imports everything, renders every view of the demonstration file
through scripts/studio_images.py, and with `--tests` runs the whole self-test
suite with the bundled interpreter.

Wine is not Windows. Two pieces it lacks are put into the test prefix only:

* **The Universal C Runtime.** Wine 9's own `ucrtbase` lacks `crealf`, which
  numpy's `_multiarray_umath` imports, so numpy aborts. Microsoft's UCRT is part
  of every supported Windows (10 version 1903 and later), so the installer does
  not ship it; for the test prefix it is taken from the Windows JDK inside the
  `jdk4py` wheel on PyPI (OpenJDK bundles the redistributable UCRT in `bin/`).
* **icuuc.dll.** Windows 10 1903+ carries ICU in System32 and Qt 6.12's
  `Qt6Core.dll` links to it for text codecs it has no built-in table for.
  `icuuc_stub.c` is a 20-function stub that reports every codec unavailable;
  Cyclara never asks for one.

Also, a window program started from a Unix shell under Wine cannot use the
inherited standard handles (even `pythonw.exe` fails the same way), so
`wine_run.py` captures stdout and stderr to a file first.

What this run proves: the bundle is complete (no missing DLL, no missing
Python package), the launcher's embedding works, the app opens and analyses a
file end to end on the Windows binaries. What it cannot prove: the installer's
own pages, shortcuts and registry writes, DPI behaviour on a real display, and
anything that differs between Wine and Windows. Those are checked by
installing on a Windows PC; see docs/U02_Cyclara.md.
