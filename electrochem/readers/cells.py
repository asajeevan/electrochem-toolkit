"""Two cell formats the generic reader has to understand before any unit applies.

1. Clock-format durations. Several instruments write elapsed time as a clock
   rather than as a number: Maccor's text export writes '0d 00:01:00.00' (and,
   in one observed configuration, unpadded seconds with float noise,
   '0d 00:00:5.05000019073486'), Neware's CSV writes '00:01:00', PEC writes
   '0:00:10.000' with an unbounded hour field. A three-field clock a:b:c is
   always hours, minutes, seconds; an optional day prefix ('0d ', '1 day, ')
   adds 86 400 s. The profile states such a column explicitly with the unit
   'hh:mm:ss', so a duration is never inferred from a number and a number is
   never read as a duration.

2. Excel cells that openpyxl has already converted. A time-formatted cell comes
   back as datetime.time below one day and as a datetime in 1899/1900 above it
   (Neware's 'Total Time' does both in the same column; observed in the PyProBE
   sample workbook at the 24 h crossing). Turning either into str() gives
   '06:00:00' and '1900-01-01 00:00:00.900000', and the second is unreadable as
   elapsed time. Both are converted back to the serial value openpyxl started
   from and written as a clock duration, so the 'hh:mm:ss' unit reads them.

   Excel's 1900 leap-year bug maps serials 60 and 59 to the same datetime, so a
   duration between 59 and 61 days cannot be recovered exactly. Such a cell is
   written as an explicit unreadable token and counted as invalid, rather than
   being placed a day out.
"""
from __future__ import annotations

import datetime as _dt
import re

DURATION = re.compile(
    r"^\s*(?:(?P<d>\d+)\s*(?:d|days?)[\s,]*)?(?P<h>\d+):(?P<m>\d{1,2}):(?P<s>\d{1,2}(?:[.,]\d*)?)\s*$")


def parse_duration(token: str) -> float | None:
    """Seconds from '[Nd ]H:MM:SS[.fff]', or None when the token is not a clock duration."""
    m = DURATION.match(token)
    if m is None:
        return None
    minutes, seconds = int(m.group("m")), float(m.group("s").replace(",", "."))
    if minutes >= 60 or seconds >= 60.0:
        return None
    return int(m.group("d") or 0) * 86400.0 + int(m.group("h")) * 3600.0 + minutes * 60.0 + seconds


def format_duration(seconds: float) -> str:
    """Seconds as 'H:MM:SS.ffffff', hours unbounded, so parse_duration reads it back."""
    sign = "-" if seconds < 0 else ""
    s = abs(seconds)
    h = int(s // 3600)
    m = int((s - h * 3600) // 60)
    sec = s - h * 3600 - m * 60
    if sec >= 59.9999995:                    # rounding would print 60.000000
        sec = 0.0
        m += 1
        if m == 60:
            m = 0
            h += 1
    return f"{sign}{h}:{m:02d}:{sec:09.6f}"


_SERIAL_AMBIGUOUS = (59.0, 61.0)          # days: Excel's fictitious 29 February 1900


def excel_cell_text(value) -> str:
    """The text the reader sees for one workbook cell."""
    if value is None:
        return ""
    if isinstance(value, _dt.timedelta):
        return format_duration(value.total_seconds())
    if isinstance(value, _dt.time):
        return format_duration(value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1e6)
    if isinstance(value, _dt.datetime) and value.year <= 1900:
        from openpyxl.utils.datetime import to_excel

        serial = float(to_excel(value))
        if _SERIAL_AMBIGUOUS[0] <= serial < _SERIAL_AMBIGUOUS[1]:
            return f"ambiguous-excel-serial:{serial:.9f}"
        return format_duration(serial * 86400.0)
    return str(value)
