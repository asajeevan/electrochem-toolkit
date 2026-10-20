"""A deterministic corpus of awkward exports for the reader-equivalence gate (P08f).

The real instrument files under data/public are the main gate. They do not, between them,
exercise every branch of the text and workbook paths (lone carriage returns, quoted fields that
span lines, comment lines, a unit row, NUL bytes, damaged encodings, 'nan' and '1_000' tokens,
grouped thousands, padded fields, headerless continuation sheets, ...). This module writes one
small file per such case, always with the same bytes, together with the profile to read it with.

scripts/capture_reader_reference.py records what the reader returned for each case (or how it
refused) and tests/test_readers_reference.py checks that the reader still returns exactly that.
Each generated file's SHA-256 is stored with its reference, so a change to this generator is
detected rather than mistaken for a change in the reader.
"""
from __future__ import annotations

import datetime as dt
import random
from pathlib import Path
from typing import Callable

from electrochem.readers.builtin import ARBIN_CSV, LANDT_XLSX, MACCOR_TXT, NEWARE_XLSX
from electrochem.readers.profile import Binding, Conventions, ImportProfile, Layout
from tests import reader_fixtures as fx

B = Binding


def _conv(**over) -> Conventions:
    base = dict(current_sign="charge_positive", direction_source="current_sign",
                capacity_semantics="none", cycle_base=1,
                evidence="synthetic corpus case for the reader-equivalence gate")
    base.update(over)
    return Conventions(**base)


def _profile(layout: Layout, bindings: dict | None = None, **conv) -> ImportProfile:
    bindings = bindings or {"test_time_second": B(source=("Test_Time",)),
                            "current_ampere": B(source=("Current",)),
                            "voltage_volt": B(source=("Voltage",)),
                            "step_id": B(source=("Step_Index",), source_unit="1")}
    return ImportProfile(name="corpus", instrument="synthetic", layout=layout,
                         conventions=_conv(**conv), bindings=bindings)


def _with_layout(p: ImportProfile, **over) -> ImportProfile:
    return p.model_copy(update={"layout": p.layout.model_copy(update=over)})


def _with_conv(p: ImportProfile, **over) -> ImportProfile:
    return p.model_copy(update={"conventions": p.conventions.model_copy(update=over)})


CSV = Layout(kind="delimited", encoding="utf-8", delimiter=",", decimal=".")
SIMPLE = _profile(CSV)


def _rows(n: int = 40, step_len: int = 10):
    """(step, t, i, v): rest, charge, rest, discharge, repeated."""
    out = []
    for k in range(n):
        step = 1 + k // step_len
        cur = (0.0, 0.002, 0.0, -0.002)[(step - 1) % 4]
        out.append((step, 10.0 * k, cur, 3.2 + 0.01 * (k % step_len) * (1 if cur >= 0 else -1)))
    return out


def _simple_text(delim=",", decimal=".", fmt=lambda x: f"{x:.6g}", rows=None, head=None) -> str:
    head = head or ["Step_Index", "Test_Time(s)", "Current(A)", "Voltage(V)"]
    lines = [delim.join(head)]
    for step, t, i, v in (rows or _rows()):
        vals = [str(step), fmt(t), fmt(i), fmt(v)]
        if decimal == ",":
            vals = [s.replace(".", ",") for s in vals]
        lines.append(delim.join(vals))
    return "\n".join(lines) + "\n"


Case = tuple[str, Callable[[Path], None], ImportProfile]


def _text(name: str, text: str, profile: ImportProfile, encoding: str = "utf-8",
          prefix: bytes = b"") -> Case:
    def write(p: Path) -> None:
        p.write_bytes(prefix + text.encode(encoding))
    return name, write, profile


def _bytes(name: str, blob: bytes, profile: ImportProfile) -> Case:
    def write(p: Path) -> None:
        p.write_bytes(blob)
    return name, write, profile


def _edit(text: str, row: int, col: int, value: str) -> str:
    """Replace one field (data row index `row`, 0-based; column `col`) of a comma file."""
    lines = text.splitlines()
    f = lines[row + 1].split(",")
    f[col] = value
    lines[row + 1] = ",".join(f)
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ text cases
def text_cases() -> list[Case]:
    base = _simple_text()
    cases: list[Case] = []
    add = cases.append

    add(_text("plain.csv", base, SIMPLE))
    add(_text("crlf.csv", base.replace("\n", "\r\n"), SIMPLE))
    add(_text("lone_cr.csv", base.replace("\n", "\r"), SIMPLE))
    add(_text("mixed_endings.csv", "".join(ln + ("\r\n", "\n", "\r")[k % 3]
                                             for k, ln in enumerate(base.splitlines())), SIMPLE))
    add(_text("no_final_newline.csv", base.rstrip("\n"), SIMPLE))
    add(_text("other_line_breaks.csv", base.replace("\n", "\x0c", 3).replace("\n", " ", 2), SIMPLE))
    add(_text("blank_lines.csv", base.replace("\n", "\n\n", 7), SIMPLE))
    add(_text("whitespace_rows.csv", base.replace("\n", "\n , ,,\n", 5), SIMPLE))
    add(_text("utf8_bom.csv", base, SIMPLE, prefix=b"\xef\xbb\xbf"))
    add(_text("utf8_bom_cp1252_profile.csv", base, _with_layout(SIMPLE, encoding="cp1252"),
              prefix=b"\xef\xbb\xbf"))
    add(_text("utf16_bom.csv", base, SIMPLE, encoding="utf-16"))
    add(_text("utf16be_bom.csv", base, SIMPLE, encoding="utf-16-be", prefix=b"\xfe\xff"))
    add(_text("utf32_bom.csv", base, SIMPLE, encoding="utf-32"))
    add(_text("utf16le_no_bom.csv", base, SIMPLE, encoding="utf-16-le"))
    add(_text("utf16_profile_no_bom.csv", base, _with_layout(SIMPLE, encoding="utf-16-le"), encoding="utf-16-le"))
    add(_text("cp1252_as_utf8.csv", base.replace("Voltage(V)", "Voltage(V) é°"), SIMPLE, encoding="cp1252"))
    add(_text("damage_late.csv", base + "".join(f"{900 + k},{9000 + 10 * k},0,3.3\n" for k in range(2500))
              + "999,99999,0,3.é3\n", SIMPLE, encoding="cp1252"))
    add(_bytes("nul_late.csv", base.encode() + b"\n" * 70000 + b"5,1,0,3\x00\n", SIMPLE))
    add(_bytes("nul_early.csv", base.encode()[:50] + b"\x00" + base.encode()[50:], SIMPLE))
    add(_text("comment_lines.csv", "# exported by nothing\n" + base.replace("\n", "\n# note\n", 4),
              _with_layout(SIMPLE, comment="#")))
    add(_text("preamble_header_row.csv", "a line\nanother; line\nthird\n" + base,
              _with_layout(SIMPLE, header_row=4)))
    add(_text("header_contains.csv", "Instrument,X\nOperator,Y\n\n" + base,
              _with_layout(SIMPLE, header_contains=("Test_Time", "Voltage"))))
    add(_text("header_contains_missing.csv", base, _with_layout(SIMPLE, header_contains=("Nope",))))
    add(_text("short_file.csv", "a,b,c\n", _with_layout(SIMPLE, header_row=5)))
    add(_text("header_only.csv", base.splitlines()[0] + "\n", SIMPLE))
    add(_text("no_delimiter.txt", "Test_Time\n1\n2\n", _with_layout(SIMPLE, delimiter=None)))
    add(_text("sniffed_tab.txt", base.replace(",", "\t"), _with_layout(SIMPLE, delimiter=None)))
    add(_text("sniffed_semicolon.txt", base.replace(",", ";"), _with_layout(SIMPLE, delimiter=None, decimal="auto")))

    # a unit row after the header, and units only there
    unit_text = ("Step_Index,Test_Time,Current,Voltage\n1,s,mA,V\n"
                 + "\n".join(base.splitlines()[1:]) + "\n")
    add(_text("unit_row.csv", unit_text, _with_layout(SIMPLE, unit_row=2, skip_rows_after_header=1)))
    add(_text("unit_row_not_skipped.csv", unit_text, _with_layout(SIMPLE, unit_row=2)))
    add(_text("unit_row_far.csv", base + "1,s,mA,V\n", _with_layout(SIMPLE, unit_row=len(base.splitlines()) + 1)))
    add(_text("unit_row_missing.csv", base, _with_layout(SIMPLE, unit_row=999)))

    # shape of the grid
    head = base.splitlines()[0]
    body = base.splitlines()[1:]
    add(_text("trailing_delim_header.csv", "\n".join([head + ","] + body) + "\n", SIMPLE))
    add(_text("trailing_delims_header_two.csv", "\n".join([head + ",,"] + body) + "\n", SIMPLE))
    add(_text("trailing_delim_header_some_rows.csv",
              "\n".join([head + ",,"] + [r + ("," if k % 7 == 0 else "") for k, r in enumerate(body)]) + "\n", SIMPLE))
    add(_text("trailing_delim_rows.csv", "\n".join([head] + [r + "," for r in body]) + "\n", SIMPLE))
    add(_text("trailing_delim_rows_some.csv", "\n".join([head] + [r + (",," if k % 3 else "") for k, r in enumerate(body)]) + "\n", SIMPLE))
    add(_text("wider_rows.csv", "\n".join([head] + [r + (",7" if k == 5 else "") for k, r in enumerate(body)]) + "\n", SIMPLE))
    add(_text("narrower_rows.csv", "\n".join([head] + [",".join(r.split(",")[:3]) if k in (3, 9) else r
                                                       for k, r in enumerate(body)]) + "\n", SIMPLE))
    add(_text("truncated_last.csv", "\n".join([head] + body[:-1] + [body[-1][:5]]) + "\n", SIMPLE))
    add(_text("nameless_index.csv", "\n".join(["," + head] + [f"{k}," + r for k, r in enumerate(body)]) + "\n", SIMPLE))
    add(_text("nameless_interleaved.csv", "\n".join(["," + head] + [("x" if k % 4 == 0 else "") + "," + r
                                                                    for k, r in enumerate(body)]) + "\n", SIMPLE))
    add(_text("nameless_middle_empty.csv", "\n".join([head.replace("Current(A)", ",Current(A)")]
                                                     + [r.replace(",", ",,", 2).replace(",,", ",", 1) for r in body]) + "\n",
              SIMPLE))
    add(_text("duplicate_names.csv", "\n".join([head + ",Notes,Notes"] + [r + ",a,b" for r in body]) + "\n", SIMPLE))
    add(_text("ambiguous_column.csv", "\n".join([head + ",Current(A)"] + [r + ",0" for r in body]) + "\n", SIMPLE))
    add(_text("channel_column.csv", "\n".join([head + ",Channel"] + [r + ",3" for r in body]) + "\n", SIMPLE))

    # quoting
    q = "\n".join([head + ",Note"] + [r + (',"a, b"' if k % 5 == 0 else ',plain') for k, r in enumerate(body)]) + "\n"
    add(_text("quoted_delimiter.csv", q, SIMPLE))
    q2 = "\n".join([head + ",Note"] + [r + (',"two\nlines"' if k == 4 else ',x') for k, r in enumerate(body)]) + "\n"
    add(_text("quoted_newline.csv", q2, SIMPLE))
    q3 = 'Preamble,"spans\ntwo lines"\n' + base
    add(_text("quoted_newline_preamble.csv", q3, _with_layout(SIMPLE, header_contains=("Test_Time",))))
    add(_text("quoted_numbers.csv", "\n".join([head] + [",".join(f'"{c}"' for c in r.split(",")) for r in body]) + "\n", SIMPLE))
    add(_text("unterminated_quote.csv", base + '9,9999,0,"3.3\n', SIMPLE))

    # number formats, one column at a time (data row k, column 2 = current, 3 = voltage, 1 = time)
    tokens = ["OVERFLOW", "", "nan", "NaN", "-inf", "Infinity", "1_000", " 0.002 ", "\u00a00.002\u2003", "0.002 ,",
              ", 0.002", "2D-03", "2d-03", "−0.002", "０.002", "٠.٢", "+.002", "2.", ".", "-",
              "2e-3", "2E+00", "0x10", "1,234.5", "1,2,3", "2e", "e3", "0.0 0", "N/A", "١٢"]
    tab = _with_layout(SIMPLE, delimiter="\t")
    tok_lines = base.replace(",", "\t").splitlines()
    for k, tok in enumerate(tokens):
        f = tok_lines[k + 2].split("\t")
        f[2] = tok
        tok_lines[k + 2] = "\t".join(f)
    add(_text("tokens_point.txt", "\n".join(tok_lines) + "\n", tab))
    add(_text("tokens_point_time.txt", "\n".join(ln.split("\t")[0] + "\t" + ln.split("\t")[2] + "\t"
                                                  + ln.split("\t")[1] + "\t" + ln.split("\t")[3]
                                                  for ln in tok_lines).replace("Current(A)\tTest_Time(s)",
                                                                               "Test_Time(s)\tCurrent(A)", 1)
              + "\n", tab))
    add(_text("tokens_comma.txt", "\n".join(ln if k < 2 else ln.replace(".", ",") for k, ln in enumerate(tok_lines))
              + "\n", _with_layout(tab, decimal=",")))
    add(_text("tokens_comma_auto.txt", "\n".join(ln if k < 2 else ln.replace(".", ",") for k, ln in enumerate(tok_lines))
              + "\n", _with_layout(tab, decimal="auto")))
    add(_text("tokens_comma_decimal.csv",
              _simple_text(";", ",").replace("0,002\n", "0.002\n", 2).replace(";0;", ";1.234,5;", 1),
              _with_layout(SIMPLE, delimiter=";", decimal=",")))
    add(_text("comma_decimal_auto.csv", _simple_text(";", ","), _with_layout(SIMPLE, delimiter=";", decimal="auto")))
    eu = _simple_text(";", ",").splitlines()
    eu[3] = eu[3].replace(";20;", ";1.234,5;")
    add(_text("european_grouping_semicolon.csv", "\n".join(eu) + "\n", _with_layout(SIMPLE, delimiter=";", decimal="auto")))
    grp = _simple_text(";", ".").splitlines()
    grp[3] = grp[3].replace(";20;", ";1,234.5;")
    add(_text("grouped_point.csv", "\n".join(grp) + "\n", _with_layout(SIMPLE, delimiter=";", decimal=".")))
    add(_text("grouped_conflict.csv", "\n".join(grp) + "\n", _with_layout(SIMPLE, delimiter=";", decimal=",")))
    late = _simple_text(";", ".", rows=_rows(400)).splitlines()
    late[300] = late[300].replace(";2990;", ";2,990.0;")
    add(_text("grouped_after_sample.csv", "\n".join(late) + "\n", _with_layout(SIMPLE, delimiter=";", decimal="auto")))
    add(_text("padded_fields.csv", _simple_text(",", ".", fmt=lambda x: f"{x:>12.6g}"), SIMPLE))
    add(_text("padded_tabs.txt", _simple_text("\t", ".", fmt=lambda x: f"  {x:.6g}  "), _with_layout(SIMPLE, delimiter="\t")))
    add(_text("fortran_exponent.csv", _simple_text(",", ".", fmt=lambda x: f"{x:.6E}".replace("E", "D")), SIMPLE))
    add(_text("unicode_minus.csv", base.replace(",-", ",−"), SIMPLE))
    add(_text("mostly_unreadable.csv", "\n".join([head] + [",".join(r.split(",")[:2] + ["XXX"] + r.split(",")[3:])
                                                           if k % 3 else r for k, r in enumerate(body)]) + "\n", SIMPLE))
    add(_text("all_invalid.csv", "\n".join([head] + [",".join(r.split(",")[:3] + ["--"]) for r in body]) + "\n", SIMPLE))
    add(_text("nan_column.csv", "\n".join([head + ",Temperature(degC)"] + [r + ",NaN" for r in body]) + "\n",
              SIMPLE.model_copy(update={"bindings": {**SIMPLE.bindings,
                                                     "surface_temperature_celsius": B(source=("Temperature",))}})))
    add(_text("scale_offset_reverse.csv", base, SIMPLE.model_copy(update={"bindings": {
        **SIMPLE.bindings, "current_ampere": B(source=("Current",), scale=2.0, offset=1e-4, reverse_sign=True)}})))

    # clock durations and step types
    dur = ["Step_Index,Test_Time,Current(A),Voltage(V),Status"]
    for k, (step, t, i, v) in enumerate(_rows(48)):
        clock = f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
        clock = {7: "61", 9: "", 11: f"1d {clock}", 13: f" 0d {clock} ", 15: "1:61:00"}.get(k, clock)
        state = {0.002: "C", -0.002: "D"}.get(i, "R") if k != 47 else ""
        dur.append(f"{step},{clock},{abs(i)},{v},{state}")
    dur_profile = _profile(CSV, {"test_time_second": B(source=("Test_Time",), source_unit="hh:mm:ss"),
                                 "current_ampere": B(source=("Current",)),
                                 "voltage_volt": B(source=("Voltage",)),
                                 "step_id": B(source=("Step_Index",), source_unit="1"),
                                 "step_type": B(source=("Status",))},
                           current_sign="unsigned", direction_source="step_type",
                           step_type_map={"C": "cc_charge", "D": "cc_discharge", "R": "rest"})
    add(_text("clock_and_state.csv", "\n".join(dur) + "\n", dur_profile))
    add(_text("clock_detect.csv", "\n".join(dur) + "\n", _with_conv(dur_profile, current_sign="detect")))
    add(_text("clock_unknown_state.csv", "\n".join(dur).replace(",D\n", ",Q\n", 1) + "\n", dur_profile))
    clock_hdr = "\n".join(dur).replace("Test_Time,", "Test_Time(hh:mm:ss),") + "\n"
    add(_text("clock_in_header.csv", clock_hdr, dur_profile.model_copy(update={"bindings": {
        **dur_profile.bindings, "test_time_second": B(source=("Test_Time",))}})))

    # step type cross-checked against a signed current
    st = ["Step_Index,Test_Time(s),Current(A),Voltage(V),Status"]
    for step, t, i, v in _rows(40):
        st.append(f"{step},{t},{i},{v},{ {0.002: ' CC_Chg', -0.002: 'CC_DChg '}.get(i, 'Rest')}")
    st_prof = _profile(CSV, {**SIMPLE.bindings, "step_type": B(source=("Status",))},
                       step_type_map={"CC_Chg": "cc_charge", "CC_DChg": "cc_discharge", "Rest": "rest"})
    add(_text("signed_with_status.csv", "\n".join(st) + "\n", st_prof))
    add(_text("signed_contradicts_status.csv", "\n".join(st).replace("CC_DChg", "TMP").replace("CC_Chg", "CC_DChg")
              .replace("TMP", "CC_Chg") + "\n", st_prof))

    # long files that cross every chunk boundary of the streaming reader
    add(("big_mixed_crlf.csv", _big_writer("utf-8", "\r\n"), _big_profile("utf-8")))
    add(("big_utf16.csv", _big_writer("utf-16", "\n"), _big_profile("utf-16")))
    add(("big_cp1252_comma.txt", _big_writer("cp1252", "\n", delim="\t", decimal=","), _big_profile("cp1252", "\t", ",")))

    # counters
    add(_text("arbin_fixture.csv", "", ARBIN_CSV))      # content written by the fixture below
    add(_text("maccor_fixture.txt", "", MACCOR_TXT))
    add(_text("maccor_fixture_point.txt", "", _with_layout(MACCOR_TXT, decimal="auto")))
    return cases


def _big_profile(encoding: str, delim: str = ",", decimal: str = ".") -> ImportProfile:
    return _profile(Layout(kind="delimited", encoding=encoding, delimiter=delim, decimal=decimal,
                           header_contains=("Test_Time",)),
                    {"test_time_second": B(source=("Test_Time",)), "current_ampere": B(source=("Current",)),
                     "voltage_volt": B(source=("Voltage",)), "step_id": B(source=("Step_Index",), source_unit="1"),
                     "cycle_count": B(source=("Cycle_Index",), source_unit="1"),
                     "charging_capacity_ah": B(source=("Charge_Capacity",)),
                     "discharging_capacity_ah": B(source=("Discharge_Capacity",)),
                     "surface_temperature_celsius": B(source=("Temperature",)),
                     "step_type": B(source=("Status",))},
                    capacity_semantics="cycle_cumulative", step_type_map={"Chg µA": "cc_charge", "DChg µA": "cc_discharge",
                                                                          "Rest": "rest"})


def _big_writer(encoding: str, newline: str, delim: str = ",", decimal: str = ".", n: int = 60000):
    """A long signed-current record with a preamble, a text column holding a multibyte character,
    blank lines, scattered unreadable tokens, a Unicode minus and padded fields, so that the
    reader's byte blocks, decoded lines and row chunks all end in awkward places."""
    def write(p: Path) -> None:
        rnd = random.Random(7)
        head = ["Data_Point", "Test_Time(s)", "Step_Index", "Cycle_Index", "Current(A)", "Voltage(V)",
                "Charge_Capacity(Ah)", "Discharge_Capacity(Ah)", "Temperature(degC)", "Status", "Note"]
        out = ["Instrument" + delim + "synthetic µ", "Operator" + delim + "nobody", "", delim.join(head)]
        t = qc = qd = 0.0
        cycle = 1
        for k in range(n):
            step = 1 + (k // 997) % 4
            if k and k % (4 * 997) == 0:
                cycle += 1
                qc = qd = 0.0
            cur = (0.0, 0.0125, 0.0, -0.0125)[step - 1]
            t += 1.0 + (k % 3) * 0.25
            if cur > 0:
                qc += cur * 1.25 / 3600
            elif cur < 0:
                qd -= cur * 1.25 / 3600
            v = 3.6 + 0.0001 * (k % 997) * (1 if cur >= 0 else -1)
            vals = [str(k + 1), f"{t:.4f}", str(step), str(cycle), f"{cur:.6f}", f"{v:.6f}", f"{qc:.9f}", f"{qd:.9f}",
                    f"{25 + rnd.random():.3f}", {1: "Rest", 2: "Chg µA", 3: "Rest", 4: "DChg µA"}[step], "é" * (k % 3)]
            if k % 20011 == 17:
                vals[5] = "OVERFLOW"
            if k % 15013 == 5:
                vals[4] = vals[4].replace("-", "−")
            if k % 9973 == 3:
                vals[8] = ""
            if k % 7919 == 11:
                vals[1] = f"  {vals[1]} "
            if decimal == ",":
                vals = [x.replace(".", ",") for x in vals]
            out.append(delim.join(vals))
            if k % 10007 == 10006:
                out.append("")
        p.write_bytes((newline.join(out) + newline).encode(encoding, errors="replace"))
    return write


def _fixture_writers() -> dict[str, Callable[[Path], None]]:
    return {
        "arbin_fixture.csv": lambda p: fx.write_arbin_like(p),
        "maccor_fixture.txt": lambda p: fx.write_maccor_like(p),
        "maccor_fixture_point.txt": lambda p: fx.write_maccor_like(p, decimal="."),
    }


# --------------------------------------------------------------- workbook cases
def _xlsx(sheets) -> Callable[[Path], None]:
    def write(p: Path) -> None:
        from openpyxl import Workbook
        wb = Workbook()
        wb.remove(wb.active)
        for name, rows in sheets:
            ws = wb.create_sheet(name)
            for r in rows:
                ws.append(list(r))
        wb.save(p)
    return write


ARBIN_HEAD = ["Date_Time", "Test_Time(s)", "Step_Index", "Cycle_Index", "Current(A)", "Voltage(V)",
              "Charge_Capacity(Ah)", "Discharge_Capacity(Ah)"]


def _arbin_rows(t0=0.0, n=60):
    out, qc, qd = [], 0.0, 0.0
    for k in range(n):
        step = 1 + k // 15
        cur = (0.0, 0.01, 0.0, -0.01)[(step - 1) % 4]
        if k and cur > 0:
            qc += cur * 10 / 3600
        elif k and cur < 0:
            qd -= cur * 10 / 3600
        out.append([dt.datetime(2026, 1, 1) + dt.timedelta(seconds=t0 + 10 * k), t0 + 10 * k, step, 1, cur,
                    3.5 + 0.001 * k * (1 if cur >= 0 else -1), qc, qd])
    return out


def xlsx_cases() -> list[Case]:
    from electrochem.readers.builtin import BUILTIN
    arbin = BUILTIN["arbin-xlsx"]
    rows = _arbin_rows()
    cases: list[Case] = [
        ("one_sheet.xlsx", _xlsx([("Channel_1_1", [ARBIN_HEAD] + rows)]), arbin),
        ("info_and_stats.xlsx", _xlsx([("Global_Info", [["Channel", "Start"], [1, "x"]]),
                                       ("Channel_1_1", [ARBIN_HEAD] + rows),
                                       ("Statistics_1-1", [["Cycle_Index", "Charge_Capacity(Ah)"], [1, 0.01]])]), arbin),
        ("continued.xlsx", _xlsx([("Channel_1_1", [ARBIN_HEAD] + rows[:30]),
                                  ("Channel_1_1_Wb_1", [ARBIN_HEAD] + rows[30:])]), arbin),
        ("two_channels.xlsx", _xlsx([("Channel_1_1", [ARBIN_HEAD] + rows[:30]),
                                     ("Channel_2_1", [ARBIN_HEAD] + rows[:30])]), arbin),
        ("different_header.xlsx", _xlsx([("Channel_1_1", [ARBIN_HEAD] + rows),
                                         ("Other", [ARBIN_HEAD[:-1] + ["X"]] + rows)]), arbin),
        ("blank_rows.xlsx", _xlsx([("Channel_1_1", [ARBIN_HEAD] + rows[:20] + [[None] * 8, [""] * 8] + rows[20:])]), arbin),
        ("short_and_wide.xlsx", _xlsx([("Channel_1_1", [ARBIN_HEAD] + rows[:20] + [rows[20][:4]] + [rows[21] + [None, 5]]
                                        + rows[22:])]), arbin),
        ("header_late.xlsx", _xlsx([("Channel_1_1", [["Report"], ["Cell", 1], []] + [ARBIN_HEAD] + rows)]), arbin),
        ("no_header.xlsx", _xlsx([("Sheet1", [["a", "b"], [1, 2]])]), arbin),
        ("missing_named_sheet.xlsx", _xlsx([("Channel_1_1", [ARBIN_HEAD] + rows)]),
         _with_layout(arbin, sheets=("Nope",))),
        ("named_sheet.xlsx", _xlsx([("A", [ARBIN_HEAD] + rows[:10]), ("B", [ARBIN_HEAD] + rows)]),
         _with_layout(arbin, sheets=("B",))),
        ("text_cells.xlsx", _xlsx([("Channel_1_1", [ARBIN_HEAD] + [r[:4] + [str(r[4]), f"{r[5]}".replace(".", ","), r[6], r[7]]
                                                                for r in rows])]), arbin),
        ("headerless_continuation.xlsx", "landt", LANDT_XLSX),
        ("neware_fixture.xlsx", "neware", NEWARE_XLSX),
        ("neware_fixture_3_sheets.xlsx", "neware3", NEWARE_XLSX),
        ("neware_time_cells.xlsx", "neware_times", NEWARE_XLSX),
        ("fixed_header_row.xlsx", _xlsx([("S", [["preamble"], ARBIN_HEAD] + rows)]),
         _with_layout(arbin, header_contains=(), header_row=2)),
        ("unit_row.xlsx", _xlsx([("S", [["Test_Time", "Current", "Voltage", "Step_Index"], ["s", "mA", "V", "1"]]
                                 + [[r[1], r[4] * 1e3, r[5], r[2]] for r in rows])]),
         _profile(Layout(kind="excel", header_contains=("Test_Time",), unit_row=2, skip_rows_after_header=1))),
    ]
    out = []
    for name, w, prof in cases:
        if w == "landt":
            w = _landt_writer()
        elif w == "neware":
            w = lambda p: fx.write_neware_like(p)
        elif w == "neware3":
            w = lambda p: fx.write_neware_like(p, sheets=3)
        elif w == "neware_times":
            w = _neware_times_writer()
        out.append((name, w, prof))
    return out


def _landt_writer():
    head = ["Index", "TestTime/h", "StepTime/h", "Voltage/V", "Current/mA", "Capacity/mAh", "State"]

    def rows(a, b):
        return [[k, k * 0.01, k * 0.01, 3.0 + 0.01 * k, 0.1 if k < 15 else -0.1, 0.001 * k,
                 "C_CC" if k < 15 else "D_CC"] for k in range(a, b)]
    return _xlsx([("Record", [head] + rows(1, 21)), ("Record1", rows(21, 31))])


def _neware_times_writer():
    head = ["DataPoint", "Date", "Cycle Index", "Step Index", "Step Type", "Time", "Total Time",
            "Current(mA)", "Voltage(V)", "Capacity(mAh)", "Chg. Cap.(mAh)", "DChg. Cap.(mAh)"]
    out, q = [head], 0.0
    for k in range(40):
        t = 86400.0 - 200 + 10 * k
        total = (dt.time(int(t // 3600), int(t % 3600 // 60), int(t % 60)) if t < 86400
                 else dt.datetime(1900, 1, 1) + dt.timedelta(seconds=t - 86400))
        cur = 1.0 if k < 20 else -1.0
        q = q + abs(cur) * 10 / 3600 if k not in (0, 20) else 0.0
        out.append([k + 1, dt.datetime(2026, 1, 1) + dt.timedelta(seconds=t), 1, 1 if k < 20 else 2,
                    "CC Chg" if k < 20 else "CC DChg", dt.timedelta(seconds=10 * (k % 20)), total, cur,
                    3.5 + 0.001 * k * (1 if k < 20 else -1), q, q if k < 20 else 0.0, 0.0 if k < 20 else q])
    return _xlsx([("record", out)])


# ------------------------------------------------------------------ fuzz cases
def fuzz_cases(n: int = 200) -> list[Case]:
    """The 200 dialects of test_readers_fuzz's randomised sweep, same seed."""
    from tests import test_readers_fuzz as fz
    rng = random.Random(20261019)
    out: list[Case] = []
    for k in range(n):
        delim = rng.choice(fz.DELIMITERS)
        decimal = rng.choice([".", ","])
        if delim == "," and decimal == ",":
            decimal = "."
        opts = dict(delim=delim, decimal=decimal, encoding=rng.choice(fz.ENCODINGS),
                    bom=rng.random() < 0.3, preamble=rng.randint(0, 12),
                    trailing=rng.random() < 0.3, t_unit=rng.choice(fz.TIME_UNITS),
                    i_unit=rng.choice(fz.CURRENT_UNITS),
                    discharge_positive=rng.random() < 0.5,
                    declare_decimal=rng.random() < 0.5)
        gen = {key: opts[key] for key in ("delim", "decimal", "encoding", "bom", "preamble",
                                          "trailing", "t_unit", "i_unit", "discharge_positive")}
        prof = fz._profile(delim=opts["delim"], decimal=opts["decimal"], encoding=opts["encoding"],
                           discharge_positive=opts["discharge_positive"], declare_decimal=opts["declare_decimal"])
        out.append((f"fuzz_{k:03d}.txt", (lambda g: (lambda p: fz._write(p, **g)))(gen), prof))
    return out


def all_cases() -> list[Case]:
    fixtures = _fixture_writers()
    out = []
    for name, write, prof in text_cases():
        out.append((name, fixtures.get(name, write), prof))
    return out + xlsx_cases() + fuzz_cases()


def _normalise_xlsx(path: Path) -> None:
    """Make a workbook's bytes independent of when it was saved: openpyxl stamps the zip entries
    and the document properties with the time of saving."""
    import re
    import zipfile
    with zipfile.ZipFile(path) as z:
        parts = [(i.filename, z.read(i)) for i in z.infolist()]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in parts:
            if name == "docProps/core.xml":
                data = re.sub(rb"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", b"2026-01-01T00:00:00Z", data)
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3                  # zipfile stamps the writing platform (0 on Windows,
            info.external_attr = 0                  # 3 on Unix) into the central directory: fix both, so
            z.writestr(info, data)                  # the bytes are the same wherever the corpus is written


def write_all(directory: Path) -> list[tuple[str, Path, ImportProfile]]:
    directory.mkdir(parents=True, exist_ok=True)
    out = []
    for name, write, prof in all_cases():
        p = directory / name
        write(p)
        if p.suffix == ".xlsx":
            _normalise_xlsx(p)
        out.append((name, p, prof))
    return out


if __name__ == "__main__":  # pragma: no cover
    import sys
    for name, p, _ in write_all(Path(sys.argv[1])):
        print(name, p.stat().st_size)
