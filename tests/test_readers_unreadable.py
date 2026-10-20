"""Files the layout detection used to stumble on (found with a LANHE/LAND .cex binary sent in October 2026, which
reached the window as a raw csv error): an instrument's own binary file is refused with an instruction before any
text parsing, a text export whose rows end in a lone carriage return is read like any other, and a UTF-16 export
that keeps its byte-order mark is detected and read. All files here are synthetic. A real .cex is now read by its
own reader (tests/test_readers_cex.py); a file named .cex that is not one is refused here."""
import csv
from pathlib import Path

import pytest

from electrochem import workflow
from electrochem.cycling import Settings
from electrochem.readers import Conventions, ImportFailure, Registry, confirm, looks_tabular
from electrochem.readers.propose import detect_layout


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("ELECTROCHEM_PROFILES", str(tmp_path / "profiles"))
    return tmp_path / "profiles"


def binary_blob(n=70000):
    """Bytes that contain NUL, carriage returns, line feeds and quotes, as an instrument binary does; the stray
    carriage returns are what made csv raise 'new-line character seen in unquoted field'."""
    return bytes((k * 37 + 11) % 256 for k in range(n))


TABLE = "Elapsed Time(s),Amps(A),Volts(V),Cycle Index,Step Index\n" + "\n".join(
    f"{k * 60},{0.001 if k < 60 else -0.001},{3.5 + 0.001 * k},1,{1 if k < 60 else 2}" for k in range(120)) + "\n"
CHARGE_MAH = 0.001 * 59 * 60 / 3.6        # 59 intervals of 60 s at 1 mA, by construction


@pytest.mark.parametrize("name,code", [("hold_001_2.cex", "cex_signature"), ("run.res", "binary_export"),
                                       ("run.bin", "binary_content"), ("run.txt", "binary_content"),
                                       ("run.csv", "binary_content")])
def test_an_instrument_binary_is_refused_with_an_instruction(tmp_path, profiles, name, code):
    p = tmp_path / name
    p.write_bytes(binary_blob())
    with pytest.raises(ImportFailure) as info:
        workflow.open_file(p)
    assert info.value.code == code
    assert "Export the run as .csv, .txt or .xlsx" in str(info.value)
    if name.endswith(".cex"):                                   # a .cex that is not one (the reader: test_readers_cex)
        assert "LANHE (LAND) .cex signature" in str(info.value)
    if name.endswith(".res"):
        assert "Arbin" in str(info.value)
    assert not looks_tabular(p)                                 # and a folder scan passes over it quietly


def test_the_csv_error_that_reached_the_window_is_gone(tmp_path):
    """The layout detection itself no longer raises csv.Error on text with stray line endings."""
    p = tmp_path / "odd.txt"
    p.write_bytes(b'Time,Current,Voltage\r"a\rb",1,2\n3,4\r5,6,7\n' * 50)
    try:
        detect_layout(p)
    except csv.Error as exc:                                    # pragma: no cover - the regression
        pytest.fail(f"csv.Error escaped: {exc}")
    except ValueError:
        pass                                                    # no table found is a clean answer


def learn_and_read(path, profiles):
    first = workflow.open_file(path)
    assert first.tab is None and first.proposal is not None
    conv = Conventions(current_sign="charge_positive", direction_source="current_sign", capacity_semantics="none",
                       cycle_base=1, evidence="synthetic file, capacities known by construction")
    confirm(first.proposal, name="synthetic", instrument="Synthetic cycler", conventions=conv,
            registry=Registry(profiles))
    again = workflow.open_file(path)
    assert again.proposal is None and again.meta["profile"] == "synthetic"
    run = workflow.analyse_file(again, Settings(charge="ox", terminal_voltage=True))
    return again, {b.direction: b.charge_mAh for b in run.an.branches}


@pytest.mark.parametrize("ending", ["\r", "\r\n"])
def test_rows_ending_in_a_carriage_return_read_like_any_other(tmp_path, profiles, ending):
    p = tmp_path / "cell.csv"
    p.write_bytes(TABLE.replace("\n", ending).encode())
    lf = tmp_path / "lf.csv"
    lf.write_bytes(TABLE.encode())
    assert detect_layout(p)[1:] == detect_layout(lf)[1:]           # the same header and the same rows
    assert looks_tabular(p)
    loaded, q = learn_and_read(p, profiles)
    assert len(loaded.tab.t) == 120
    assert q["charge"] == pytest.approx(CHARGE_MAH, rel=1e-9) and q["discharge"] == pytest.approx(CHARGE_MAH, rel=1e-9)


@pytest.mark.parametrize("codec,bom", [("utf-16-le", b"\xff\xfe"), ("utf-16-be", b"\xfe\xff")])
def test_a_utf16_export_with_its_byte_order_mark_is_read(tmp_path, profiles, codec, bom):
    """Excel's "Unicode text" export is UTF-16 with a byte-order mark."""
    p = tmp_path / "cell.txt"
    p.write_bytes(bom + TABLE.replace(",", "\t").encode(codec))
    layout, header, rows = detect_layout(p)
    assert layout.encoding == "utf-16" and header[:3] == ["Elapsed Time(s)", "Amps(A)", "Volts(V)"] and len(rows) == 120
    assert looks_tabular(p)
    loaded, q = learn_and_read(p, profiles)
    assert len(loaded.tab.t) == 120
    assert q["charge"] == pytest.approx(CHARGE_MAH, rel=1e-9)


def test_a_utf16_export_without_its_byte_order_mark_is_refused_not_misread(tmp_path, profiles):
    p = tmp_path / "cell.txt"
    p.write_bytes(TABLE.replace(",", "\t").encode("utf-16-le"))
    with pytest.raises(ImportFailure) as info:
        workflow.open_file(p)
    assert info.value.code == "binary_content" and "UTF-16" in str(info.value)
