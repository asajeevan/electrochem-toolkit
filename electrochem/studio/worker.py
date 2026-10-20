"""Background jobs. Results come back to the main thread through queued signals;
no widget is touched from a worker thread."""
from __future__ import annotations

import gc
import threading
import time
import traceback

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, QThreadPool, QTimer, Signal


class _Signals(QObject):
    done = Signal(object, object)        # token, result
    failed = Signal(object, str, str)    # token, message, traceback
    progress = Signal(object, str)       # token, message


class Job(QRunnable):
    def __init__(self, token, fn, *args, **kwargs):
        super().__init__()
        self.token, self.fn, self.args, self.kwargs = token, fn, args, kwargs
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self):
        try:
            if "progress" in self.kwargs and self.kwargs["progress"] is True:
                self.kwargs["progress"] = lambda msg: self.signals.progress.emit(self.token, msg)
            out = self.fn(*self.args, **self.kwargs)
        except Exception as exc:                            # reported to the user in words
            self.signals.failed.emit(self.token, friendly(exc), traceback.format_exc())
            return
        self.signals.done.emit(self.token, out)


# ------------------------------------------------------------------ separate processes for reading
# Python threads share one interpreter lock: a 75 000-row file read in a thread
# makes every animation on the main thread stutter. Reading in a separate
# process keeps the window at its full frame rate. Only main() switches this on;
# tests and scripts that build the window directly read in threads, so a stray
# script without a __main__ guard can never be re-run by a child process.
_POOL = None
USE_PROCESSES = False


_START = threading.Lock()          # two files opened at once start their jobs in two pool threads together


def _pool():
    global _POOL
    with _START:
        if _POOL is None:
            import multiprocessing as mp
            from concurrent.futures import ProcessPoolExecutor
            _POOL = ProcessPoolExecutor(max_workers=2, mp_context=mp.get_context("spawn"))
        return _POOL


_MANAGER = None


def _manager():
    """One multiprocessing manager for the progress queues (a small helper process, started once)."""
    global _MANAGER
    with _START:
        if _MANAGER is None:
            import multiprocessing as mp
            _MANAGER = mp.get_context("spawn").Manager()
        return _MANAGER


class _QueueProgress:
    """The reader's progress callback inside the child process: a few updates a second onto the queue."""

    def __init__(self, queue, every=0.2):
        self.queue, self.every, self.last = queue, every, 0.0

    def __call__(self, rows, done, total):
        now = time.monotonic()
        if now - self.last >= self.every or done >= total:
            self.last = now
            try:
                self.queue.put((rows, done, total))
            except Exception:
                pass


def _call_with_queue(fn, queue, *args):
    return fn(*args, progress=_QueueProgress(queue))


def in_process(fn, *args, progress=None):
    """Run fn(*args) in a child process when enabled; fall back to this thread on any failure to do so.
    progress(message), when given, receives the reader's progress as text while the child reads (the
    child puts (rows, bytes_read, bytes_total) on a manager queue; this thread turns them into words)."""
    if not USE_PROCESSES:
        return fn(*args, progress=_text_progress(progress)) if progress else fn(*args)
    queue = None
    try:
        if progress:
            queue = _manager().Queue()
            fut = _pool().submit(_call_with_queue, fn, queue, *args)
        else:
            fut = _pool().submit(fn, *args)
    except Exception:
        return fn(*args, progress=_text_progress(progress)) if progress else fn(*args)
    try:
        if queue is not None:
            say = _text_progress(progress)
            while not fut.done():
                try:
                    rows, done, total = queue.get(timeout=0.1)
                except Exception:                 # queue.Empty, or the manager going away at shutdown
                    continue
                say(rows, done, total)
        return fut.result()
    except Exception as exc:
        from concurrent.futures.process import BrokenProcessPool
        if isinstance(exc, (BrokenProcessPool, OSError)) or "pickle" in type(exc).__name__.lower():
            return fn(*args, progress=_text_progress(progress)) if progress else fn(*args)   # the pool failed
        raise                                    # the reading failed: report it as such


def _text_progress(say):
    """(rows, bytes_read, bytes_total) -> a line of text for the reading screen, at most five a second."""
    state = {"last": 0.0}

    def cb(rows, done, total):
        now = time.monotonic()
        if now - state["last"] < 0.2 and done < total:
            return
        state["last"] = now
        pct = f"{100 * done // max(total, 1):d} %" if total else ""
        say(f"Reading: {rows:,} rows" + (f", {pct} of the file" if pct else ""))
    return cb


def shutdown():
    global _POOL, _MANAGER
    if _POOL is not None:
        _POOL.shutdown(wait=False, cancel_futures=True)
        _POOL = None
    if _MANAGER is not None:
        try:
            _MANAGER.shutdown()
        except Exception:
            pass
        _MANAGER = None


# ------------------------------------------------------------------ garbage collection on the GUI thread only
# Python's cyclic garbage collector runs in whichever thread happens to allocate when a
# threshold is crossed. When that is a worker thread (the .mpr reader allocates a lot), it can
# finalise the Python side of a widget there while the GUI thread deletes the widget, and the
# process crashes (independent review, finding r10: a segmentation fault when opening a second
# file). Automatic collection is therefore switched off and the GUI thread collects on a timer.
# The thresholds are Python's own, so collections happen as often as before, on the right thread.
class _Collector(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.threshold = gc.get_threshold()
        gc.disable()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(500)

    def check(self):
        c0, c1, c2 = gc.get_count()
        if c0 > self.threshold[0]:
            gc.collect(0)
            if c1 > self.threshold[1]:
                gc.collect(1)
                if c2 > self.threshold[2]:
                    gc.collect(2)


_COLLECTOR = None


def collect_on_gui_thread():
    """Idempotent; call from the GUI thread once a QApplication exists."""
    global _COLLECTOR
    app = QCoreApplication.instance()
    if _COLLECTOR is None and app is not None:
        _COLLECTOR = _Collector(app)
    return _COLLECTOR


def start(job: Job, done=None, failed=None, progress=None):
    if done:
        job.signals.done.connect(done)
    if failed:
        job.signals.failed.connect(failed)
    if progress:
        job.signals.progress.connect(progress)
    QThreadPool.globalInstance().start(job)
    return job


# Plain-language explanations for the errors a user is likely to meet (carried over from the 0.5 window)
FRIENDLY = [
    ("native_dependency_missing", "The .mpr reader is not installed. Export the measurement as .mpt from EC-Lab, "
                                   "or run Setup.bat again."),
    ("native_backend_unverified", "The installed .mpr reader is not the verified version. Run Setup.bat again."),
    ("native_numpy_unverified", "The .mpr reader was verified with NumPy 2.3.5 and a different version is installed. "
                                "Run Setup.bat again."),
    ("size_limit", "The file is larger than 256 MB and holds a value the fast reader could not read, so the "
                   "token-by-token reader would be needed, which stops at 256 MB. Export fewer cycles or split the experiment."),
    ("No time/s column", "The file has no time/s column. Export it again from EC-Lab with the default columns."),
    ("No current column", "The file has no current column. Export it again from EC-Lab with I/mA included."),
    ("UnsupportedTechnique", None),
    ("Permission denied", "Windows refused to write there. Close any file from a previous export that is still open "
                          "(Excel, Origin, a PDF viewer), or choose another folder."),
    ("could not convert string to float", "A number in the file could not be read. Send the file to the author if "
                                          "this persists."),
    # the importer's own codes, in words (independent review, finding r25)
    ("empty_file", "The file is empty."),
    ("no_table", "No table of numbers was found in the file. A cycler's export has a row of column names above "
                 "the rows of values; a binary file (.res, .nda, .mpr renamed) has to be exported as text or "
                 "Excel first."),
    ("binary_export", None),
    ("signature_required", "The file has no EC-Lab header: it starts directly with a table. Export it again from "
                           "EC-Lab, or open the .mpr."),
    ("settings_", "This is an EC-Lab settings (.mps) file: it holds a protocol, not measurements. Open the run's "
                  ".mpr or .mpt file."),
    ("binary_or_nul", "The file holds binary data, so it is not an EC-Lab text export. If it is an .mpr file, give it "
                      "the .mpr extension."),
    ("header_count", "The header's line count does not match the file, which may have been edited or cut short. "
                     "Export it again from EC-Lab."),
    ("row_width", "A data row has a different number of columns from the header: the file may be cut short or "
                  "edited. Export it again from EC-Lab."),
    ("delimiter", "The columns are not separated as in an EC-Lab export. Export the file again from EC-Lab."),
    ("encoding_required", "The text encoding could not be recognised. Export the file again from EC-Lab."),
    ("native_signature", "The .mpr file does not start like an EC-Lab binary file; it may be damaged or of another "
                         "format."),
    ("native_", "The .mpr file could not be decoded: it may be damaged or from an EC-Lab version not yet verified. "
                "Export it as .mpt from EC-Lab and open that."),
]


def friendly(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for key, msg in FRIENDLY:
        if key in text:
            return msg or str(exc)
    if type(exc).__name__ == "ImportFailure":
        return f"The file could not be read ({exc})."
    return text
