"""Built-in profiles. Each one is a declaration, not code, and each was checked against a real
instrument export (P08d). Every evidence string names the file it was checked against, where it
came from, and what the file showed; docs/P08d_Instrument_Compatibility_Matrix.md holds the
table and tests/test_readers_real_files.py re-checks each shipped file independently.

How a built-in profile claims a file (registry.claims): the same kind (text or workbook), one of
its sniff strings present, and a column for each of time, current and voltage under the names it
binds. A sniff string built with column() matches one whole column name only, which is what
keeps sibling dialects apart: Arbin's MITS Pro CSV writes 'Test_Time(s)', the .res table writes
'Test_Time', and the newer MITS export writes 'Test Time (s)'.

Wording used in the evidence strings:
- "sign test": over every programmed step carrying current of one sign, the voltage ended higher
  than it started exactly when the charge-positive current was positive (charging raises the
  terminal voltage whatever the chemistry; checks.check_sign_against_voltage).
- "counter test": the instrument's own capacity counter, converted to increments, against the
  trapezoidal integral of the sampled current over the same steps.
"""
from __future__ import annotations

from .profile import Binding, Conventions, ImportProfile, Layout

B = Binding


def column(name: str) -> str:
    """A sniff string that matches the whole column name `name` and never a longer one."""
    return f"\n{name}\n"


def column_any_unit(base: str, open_: str = "(") -> str:
    """A sniff string that matches the column `base` with whatever unit the export chose:
    'Test_Time(' matches 'Test_Time(s)' and 'Test_Time(min)' but not the unit-less 'Test_Time'
    of the .res table dialect. Instruments let the user pick units at export time (P08e)."""
    return f"\n{base}{open_}"


# Maccor's State column gives the direction only ('C' covers both the constant-current and the
# constant-voltage stage of a charge). 'C' and 'D' are mapped to a charge and a discharge kind
# for their direction; because the vocabulary names no CV stage the bridge builds no mode array
# from it, so no CC/CV split is reported for Maccor files (bridge.to_table).
MACCOR_STATE = {"R": "rest", "C": "cc_charge", "D": "cc_discharge", "O": "ocv"}

# ------------------------------------------------------------------- Arbin
ARBIN_CSV = ImportProfile(
    name="arbin-csv",
    instrument="Arbin MITS Pro (CSV export, underscore column names)",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="utf-8", delimiter=",", decimal="."),
    sniff_any=(column_any_unit("Test_Time"),),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="cycle_cumulative",
        cycle_base=1,
        evidence=(
            "Column names confirmed on galv-harvester .test-data/test-suite-small/arbin.csv "
            "(BSD-2-Clause, commit f790d1d), whose 21 rows repeat one rest row, so it shows names, "
            "not conventions. The same names, units and conventions were measured on the Arbin "
            "Excel export of the same software (profile arbin-xlsx). Cycle-cumulative counters: "
            "measured on two multi-cycle Arbin exports (arbin-res-table-csv; battetl MITS Pro 8 CSV, "
            "inspected, not shipped); this file family has no multi-cycle example, so a counter "
            "that never falls is accepted as consistent, not verified."),
    ),
    bindings={
        "record_index": B(source=("Data_Point",), source_unit="1"),
        "test_time_second": B(source=("Test_Time",)),
        "step_id": B(source=("Step_Index",), source_unit="1"),
        "cycle_count": B(source=("Cycle_Index",), source_unit="1"),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Voltage",)),
        "charging_capacity_ah": B(source=("Charge_Capacity",)),
        "discharging_capacity_ah": B(source=("Discharge_Capacity",)),
    },
)

ARBIN_XLSX = ImportProfile(
    name="arbin-xlsx",
    instrument="Arbin MITS Pro (Excel export)",
    version="0.2.0",
    layout=Layout(kind="excel", header_contains=("Test_Time", "Step_Index", "Cycle_Index")),
    sniff_any=(column_any_unit("Test_Time"),),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="cycle_cumulative",
        cycle_base=1,
        evidence=(
            "Checked on navani Example_data/bs542_004_gr_li_50ua_50mv_1v_191020_Channel_11.xlsx "
            "(MIT, commit d9892a3; MITS Pro PV7.0, graphite vs Li, 4 526 rows): data on sheet "
            "Channel_11_1 after a Global_Info report sheet; current signed, sign test 3 of 3 voting "
            "steps; Charge_Capacity and Discharge_Capacity within 1e-4 of the integral of the "
            "current; Test_Time follows the Date_Time wall clock to 0.02 s over 14 days. Cycle_Index "
            "stays 1, so test- and cycle-cumulative are both consistent; cycle-cumulative is declared "
            "from the multi-cycle Arbin files."),
    ),
    bindings=dict(ARBIN_CSV.bindings),
)

ARBIN_MITS8_CSV = ImportProfile(
    name="arbin-mits8-csv",
    instrument="Arbin MITS (CSV export, spaced column names 'Test Time (s)')",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="utf-8", delimiter=",", decimal="."),
    sniff_any=(column_any_unit("Test Time", " ("),),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="cycle_cumulative",
        cycle_base=1,
        evidence=(
            "Checked on PyProBE tests/sample_data/arbin/sample_data_arbin.csv (BSD-3-Clause, "
            "commit b5a789e; 13 rows: rest, then two rows of a charge): it is the charge counter, "
            "not the discharge counter, that grows while the current is positive, within 0.25 % of "
            "the integral over the one interval inside the step; too few rows for the voltage test. "
            "Also read, not shipped (BattSoft Community License): three battetl MITS exports "
            "(single_data_file, cccv_data_files, ict_data_files; 34 209 to 61 699 rows): sign test "
            "16/16, 5/5 and 11/11 voting steps; counters cycle-cumulative (measured, the only "
            "behaviour consistent with them), within 8e-4 of the integral of the current, and their "
            "per-cycle increments equal the vendor's StatisticByCycle export to 3e-9 (16 cycles)."),
    ),
    bindings={
        "record_index": B(source=("Data Point",), source_unit="1"),
        "test_time_second": B(source=("Test Time",)),
        "step_id": B(source=("Step Index",), source_unit="1"),
        "cycle_count": B(source=("Cycle Index",), source_unit="1"),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Voltage",)),
        "charging_capacity_ah": B(source=("Charge Capacity",)),
        "discharging_capacity_ah": B(source=("Discharge Capacity",)),
    },
)

ARBIN_RES_TABLE_CSV = ImportProfile(
    name="arbin-res-table-csv",
    instrument="Arbin .res channel table written as CSV (column names without units)",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="utf-8", delimiter=",", decimal="."),
    sniff_any=(column("Test_Time"),),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="cycle_cumulative",
        cycle_base=1,
        evidence=(
            "Checked on battery-data-toolkit tests/files/arbin_example.csv (Apache-2.0, commit "
            "19961e6): the columns of the .res Channel_Normal_Table with a Temperature column, "
            "DateTime as Unix seconds; not a direct MITS Pro export. Units are not written; s, A, "
            "V and Ah are the .res schema's and are confirmed by the counter test (within 5e-4 of "
            "the integral of the current over the edges inside each step; 0.22 % over the whole file, "
            "where the counter also counts charge across step boundaries) and by the DateTime wall "
            "clock. Sign test 6 of 6 voting steps. "
            "Charge_Capacity carries across step boundaries within a cycle and resets at the "
            "cycle 1 to 2 boundary: cycle-cumulative, measured."),
    ),
    bindings={
        "record_index": B(source=("Data_Point",), source_unit="1"),
        "test_time_second": B(source=("Test_Time",), source_unit="s"),
        "step_id": B(source=("Step_Index",), source_unit="1"),
        "cycle_count": B(source=("Cycle_Index",), source_unit="1"),
        "current_ampere": B(source=("Current",), source_unit="A"),
        "voltage_volt": B(source=("Voltage",), source_unit="V"),
        "charging_capacity_ah": B(source=("Charge_Capacity",), source_unit="Ah"),
        "discharging_capacity_ah": B(source=("Discharge_Capacity",), source_unit="Ah"),
    },
)

# ------------------------------------------------------------------ Neware
NEWARE_XLSX = ImportProfile(
    name="neware-xlsx",
    instrument="Neware BTS (Excel export, record sheet)",
    version="0.2.0",
    layout=Layout(kind="excel", header_contains=("Total Time", "Cycle Index", "Step Index")),
    sniff_any=("Chg. Cap.(", "DChg. Cap.("),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="step_cumulative",
        cycle_base=1,
        evidence=(
            "Checked on PyProBE tests/sample_data/neware/sample_data_neware.xlsx (BSD-3-Clause, "
            "commit b5a789e; 789 589 rows on sheet 'record', 10 columns), read whole and shipped "
            "as two derived workbooks (rows 2 to 25 001; rows 80 001 to 90 000, across 24 h): "
            "Current(mA) signed; Chg. Cap.(mAh) and DChg. Cap.(mAh) restart from 0 at every step "
            "(step-cumulative, measured). Whole file through this profile: sign test 21 of 21 voting "
            "steps, counters within 3e-5 of the integral of the current, Total Time continuous over "
            "6.5 days (largest interval 1.0 s). Shipped parts: 1 of 1 voting step each, counters "
            "within 1.3e-6 and 5e-8. Total Time is an Excel time cell "
            "that openpyxl returns as a time of day below 24 h and as a 1900 date above it; both "
            "are read back as elapsed seconds (cells.py). Step Type, absent from this file, is "
            "mapped with the values observed in the Neware CSV export, for the sign cross-check."),
        step_type_map={"Rest": "rest", "CC Chg": "cc_charge", "CC DChg": "cc_discharge"},
    ),
    bindings={
        "record_index": B(source=("DataPoint",), source_unit="1"),
        "step_type": B(source=("Step Type",)),
        "step_id": B(source=("Step Index",), source_unit="1"),
        "cycle_count": B(source=("Cycle Index",), source_unit="1"),
        "test_time_second": B(source=("Total Time",), source_unit="hh:mm:ss"),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Voltage",)),
        "charging_capacity_ah": B(source=("Chg. Cap.",)),
        "discharging_capacity_ah": B(source=("DChg. Cap.",)),
    },
)

NEWARE_CSV = ImportProfile(
    name="neware-csv",
    instrument="Neware BTS (flat CSV export, one row per record)",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="utf-8", delimiter=",", decimal="."),
    sniff_any=(column("Cumulative Time"),),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="step_cumulative",
        cycle_base=1,
        evidence=(
            "Checked on cellpy testdata/data/neware_uio.csv (MIT, commit 29d916c; 9 065 rows, 4 "
            "cycles): Cumulative Time and Time written as hh:mm:ss (1 s resolution, so sub-second "
            "records share a timestamp); Current(A) signed and consistent with Step Type ('CC Chg' "
            "positive, 'CC DChg' negative, 'Rest' zero) and with the sign test (16 of 16 voting "
            "steps); Chg. Cap.(Ah) and DChg. Cap.(Ah) restart at every step (step-cumulative, "
            "measured) and agree with the integral of the current to 2e-6 and 2e-5. The older "
            "hierarchical Neware CSV (cycle, step and record rows interleaved; cellpy "
            "nw_regular_export_ife_example.csv, beep raw/neware_test.csv) has no Cumulative Time "
            "column and is deliberately not claimed by this profile."),
        step_type_map={"Rest": "rest", "CC Chg": "cc_charge", "CC DChg": "cc_discharge"},
    ),
    bindings={
        "record_index": B(source=("DataPoint",), source_unit="1"),
        "step_type": B(source=("Step Type",)),
        "step_id": B(source=("Step Index",), source_unit="1"),
        "cycle_count": B(source=("Cycle Index",), source_unit="1"),
        "test_time_second": B(source=("Cumulative Time",), source_unit="hh:mm:ss"),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Voltage",)),
        "charging_capacity_ah": B(source=("Chg. Cap.",)),
        "discharging_capacity_ah": B(source=("DChg. Cap.",)),
    },
)

# ------------------------------------------------------------------ Maccor
_MACCOR_COMMON = dict(
    record_index=B(source=("Rec#",), source_unit="1"),
    cycle_count=B(source=("Cyc#",), source_unit="1"),
    step_id=B(source=("Step",), source_unit="1"),
    step_type=B(source=("State",)),
    current_ampere=B(source=("Amps",), source_unit="A"),
    voltage_volt=B(source=("Volts",), source_unit="V"),
    step_cumulative_capacity_ah=B(source=("Amp-hr",), source_unit="Ah"),
)

MACCOR_EXPORT_SEC = ImportProfile(
    name="maccor-export-sec",
    instrument="Maccor (text export, 'Test (Sec)' time column)",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="cp1252", delimiter="\t", decimal=".",
                  header_contains=("Rec#", "Test (Sec)")),
    sniff_any=(column("Test (Sec)"),),
    conventions=Conventions(
        current_sign="detect",
        direction_source="step_type",
        capacity_semantics="step_cumulative",
        cycle_base=0,
        evidence=(
            "Checked on beep tests/test_files/xTESLADIAG_000038con.078 (8 cycles) and "
            "PredictionDiagnostics_000151_test.052 (a slice from cycle 37) (Apache-2.0, commit "
            "f2b984e; Maccor testers at Stanford/TRI); PreDiag_000229_000229_truncated.034 read "
            "too, not copied. One preamble line; Amps signed in these files (detection concludes "
            "charge-positive; State C positive, D negative, R zero; sign test 16 of 16 voting "
            "steps); Amp-hr is one unsigned counter that restarts at every step, including the CC "
            "to CV step of a charge (BDF step_cumulative_capacity_ah, measured), within 3e-5 of the "
            "integral of the current. Test (Sec) follows DPt Time to 1.2e-4 (instrument clock "
            "against PC clock). Cyc# starts at 0. Detection stays on because Maccor writes unsigned "
            "Amps in other configurations (maccor-export-clock)."),
        step_type_map=MACCOR_STATE,
    ),
    bindings={**_MACCOR_COMMON, "test_time_second": B(source=("Test (Sec)",), source_unit="s")},
)

MACCOR_EXPORT_MIN = ImportProfile(
    name="maccor-export-min",
    instrument="Maccor (text export, 'Test (Min)' time column)",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="cp1252", delimiter="\t", decimal=".",
                  header_contains=("Rec#", "Test (Min)")),
    sniff_any=(column("Test (Min)"),),
    conventions=Conventions(
        current_sign="detect",
        direction_source="step_type",
        capacity_semantics="step_cumulative",
        cycle_base=0,
        evidence=(
            "Recognised and read on battery-data-toolkit tests/files/maccor_example.001 (Apache-2.0, "
            "commit 19961e6; Argonne MIMS export, 8 rows of rest, Test (Min) advancing 1/6 min per "
            "10 s of DPt Time). Rest only, so the sign and the counter cannot be measured in it: "
            "they are carried over from maccor-export-sec, which differs only in the time unit. "
            "navani Example_data/maccor_example.txt has this header but is a synthetic demo "
            "(perfectly linear voltages, a clock that wraps from 11:59 to 11:00) and was not used."),
        step_type_map=MACCOR_STATE,
    ),
    bindings={**_MACCOR_COMMON, "test_time_second": B(source=("Test (Min)",), source_unit="min")},
)

MACCOR_EXPORT_CLOCK = ImportProfile(
    name="maccor-export-clock",
    instrument="Maccor (text export, clock-format 'TestTime')",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="cp1252", delimiter="\t", decimal=".",
                  header_contains=("Rec#", "TestTime", "Amps", "State")),
    sniff_any=(column("TestTime"),),
    conventions=Conventions(
        current_sign="detect",
        direction_source="step_type",
        capacity_semantics="step_cumulative",
        cycle_base=0,
        evidence=(
            "Checked on cellpy testdata/data/maccor_001.txt (MIT, commit 29d916c; University of "
            "Birmingham, SIMBA project; 6 704 rows read, the first cycle shipped): three preamble "
            "lines; TestTime written '0d 00:00:5.05000019073486' (days, then a clock with unpadded "
            "seconds); Amps unsigned, so detection concludes unsigned and direction comes from "
            "State (C, D, R, O); sign test 9 of 9 voting steps; Amp-hr restarts at every step and "
            "agrees with the integral of the current to 2e-5, which with the DPt Time wall clock "
            "confirms the clock is in seconds. Cyc# stays 0 throughout."),
        step_type_map=MACCOR_STATE,
    ),
    bindings={**_MACCOR_COMMON, "test_time_second": B(source=("TestTime",), source_unit="hh:mm:ss")},
)

MACCOR_TXT = ImportProfile(
    name="maccor-txt",
    instrument="Maccor (text export with a 12-line header block, 'Cycle P' and 'Md' columns)",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="cp1252", delimiter="\t", decimal="auto",
                  header_contains=("Cycle P", "TestTime", "Md")),
    sniff_any=(column("Cycle P"),),
    conventions=Conventions(
        current_sign="detect",
        direction_source="step_type",
        capacity_semantics="step_cumulative",
        cycle_base=1,
        evidence=(
            "Checked on cellpy testdata/data/maccor_002.txt (decimal point) and "
            "examples/data/maccor_two.txt (decimal comma, rest only) (MIT, commit 29d916c; KIT, "
            "SIMBA project): a 12-line header block (Name, Channel, Tester, ... DisCh. max. I), "
            "the header, then a blank line. TestTime carries no unit and is in MINUTES: it "
            "advances 1.0 per 60 s of DPT Time, and only minutes make Cap. [Ah] agree with the "
            "integral of the current to 3e-6 (seconds would be 60 times too small). Current [A] is "
            "unsigned (detection concludes unsigned; direction from Md: C, D, R; sign test 4 of 4 "
            "voting steps); Cap. [Ah] restarts at every step (step-cumulative, measured). Cycle C "
            "counts charges from 1. Data rows end with a tab the header line does not have, and "
            "maccor_two.txt ends in a line cut off mid-number (kept, its current unused)."),
        step_type_map=MACCOR_STATE,
    ),
    bindings={
        "record_index": B(source=("Rec",), source_unit="1"),
        "cycle_count": B(source=("Cycle C",), source_unit="1"),
        "step_id": B(source=("Step",), source_unit="1"),
        "test_time_second": B(source=("TestTime",), source_unit="min"),
        "step_type": B(source=("Md",)),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Voltage",)),
        "step_cumulative_capacity_ah": B(source=("Cap.",)),
    },
)

MACCOR_EXPORT_SIGNED = ImportProfile(
    name="maccor-export-signed",
    instrument="Maccor (text export with units in brackets, 'TestTime(s)', signed 'Current(A)', no State)",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="cp1252", delimiter="\t", decimal=".",
                  header_contains=("Cyc#", "TestTime(s)", "Current(A)")),
    sniff_any=(column("TestTime(s)"),),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="step_cumulative",
        cycle_base=0,
        evidence=(
            "Inspected, not shipped (BattSoft Community License, not redistributable here): battetl "
            "tests/data/maccor_cycler_data/simple_data/BG_Maccor_Testdata - 079.txt (commit 9d3c7bd; "
            "141 981 rows): two preamble lines, no State column; Current(A) signed, the voltage rises "
            "under positive current in all 15 voting steps; Capacity(Ah) is one unsigned counter "
            "restarting at every step (step-cumulative, measured), within 2e-5 of the integral of the "
            "current, and its per-cycle charge and discharge totals match the export's own [STATS] "
            "file (AH-IN, AH-OUT) to 6e-5 over 8 cycles. The sibling file ResetCap_Take11 - 074.txt, "
            "whose schedule resets the counter inside steps, is refused (capacity_semantics_mismatch), "
            "as it should be. In the "
            "repository the profile is exercised only by a synthetic file in this layout "
            "(tests/test_readers_real_files.py), so it is not verified on a shipped real file."),
    ),
    bindings={
        "cycle_count": B(source=("Cyc#",), source_unit="1"),
        "step_id": B(source=("Step",), source_unit="1"),
        "test_time_second": B(source=("TestTime",)),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Voltage",)),
        "step_cumulative_capacity_ah": B(source=("Capacity",)),
    },
)

# ------------------------------------------------------------------ others
BASYTEC_TXT = ImportProfile(
    name="basytec-txt",
    instrument="BaSyTec (text result file, '~' header block)",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="cp1252", delimiter="\t", decimal=".",
                  header_contains=("~Time[s]", "U[V]", "I[A]")),
    sniff_any=("~Resultfile from Basytec", column("~Time[s]")),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="none",
        cycle_base=0,
        evidence=(
            "Checked on PyProBE tests/sample_data/basytec/sample_data_basytec.txt (BSD-3-Clause, "
            "commit b5a789e; 74 rows: Pause, then the start of a Charge): the header line is the "
            "last '~' line; I[A] is positive under Charge and the voltage rises (sign test, 1 of 1 "
            "voting step). No "
            "discharge is in the file, so negative-for-discharge is the declared convention, not a "
            "measured one; the cross-check against Command covers it for Charge only. Ah-Step and "
            "Ah[Ah] agree with the integral of the current over the charge, but their behaviour "
            "in a discharge is unobserved, so no counter is bound and capacity is integrated."),
        step_type_map={"Pause": "rest", "Charge": "cc_charge"},
    ),
    bindings={
        "record_index": B(source=("DataSet",), source_unit="1"),
        "test_time_second": B(source=("~Time",)),
        "step_id": B(source=("Line",), source_unit="1"),
        "cycle_count": B(source=("Cyc-Count",), source_unit="1"),
        "step_type": B(source=("Command",)),
        "current_ampere": B(source=("I",)),
        "voltage_volt": B(source=("U",)),
    },
)

NOVONIX_CSV = ImportProfile(
    name="novonix-csv",
    instrument="Novonix UHPC (CSV with [Summary], [Protocol] and [Data] sections)",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="utf-8", delimiter=",", decimal=".",
                  header_contains=("Date and Time", "Run Time", "Potential")),
    sniff_any=("Novonix", column("Run Time (h)")),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="none",
        cycle_base=1,
        evidence=(
            "Checked on PyProBE tests/sample_data/novonix/sample_data_novonix.csv (BSD-3-Clause, "
            "commit b5a789e; UHPC Control 2.13.0, 207 rows of one constant-current charge): the "
            "table follows the [Data] line; positive current raises the voltage (sign test, 1 of 1 "
            "voting step); Run Time (h) follows the Date and Time wall clock. One "
            "step only: Capacity (Ah) agrees with the integral of the current, but its reset "
            "behaviour and its sign in a discharge are unobserved, so it is not bound. Step Type "
            "is a numeric code (7 here) whose meaning the file does not state; it is not used. "
            "beep raw/test_Nova_Form-CH01-01_short.csv has every data line wrapped in quotes "
            "(re-saved, not as exported) and was not used."),
    ),
    bindings={
        "test_time_second": B(source=("Run Time",)),
        "step_id": B(source=("Step Number",), source_unit="1"),
        "cycle_count": B(source=("Cycle Number",), source_unit="1"),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Potential",)),
    },
)

PEC_CSV = ImportProfile(
    name="pec-csv",
    instrument="PEC (CSV export, 'Total Time (Seconds)')",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="cp1252", delimiter=",", decimal=".",
                  header_contains=("Test,Cell", "Total Time (Seconds)")),
    sniff_any=(column("Total Time (Seconds)"),),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="cycle_cumulative",
        cycle_base=0,
        evidence=(
            "Checked on cellpy testdata/data/pec.csv (MIT, commit 29d916c; 2019, a 44 Ah cell at "
            "C/25; shipped truncated after the first full cycle): about 30 preamble lines and a "
            "#RESULTS CHECK block before the table; Voltage (mV), Current (mA) signed, sign test 3 "
            "of 3 voting steps; Charge Capacity (mAh) and Discharge Capacity (mAh) carry across "
            "steps and reset when Cycle increments (cycle-cumulative, measured) and agree with the "
            "integral of the current to 8e-7. The energy columns are mislabelled 'Charge Capacity (mWh)' "
            "in this export; the binding cannot take them because mWh is not a charge unit."),
    ),
    bindings={
        "test_time_second": B(source=("Total Time (Seconds)",), source_unit="s"),
        "step_id": B(source=("Step",), source_unit="1"),
        "cycle_count": B(source=("Cycle",), source_unit="1"),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Voltage",)),
        "charging_capacity_ah": B(source=("Charge Capacity",)),
        "discharging_capacity_ah": B(source=("Discharge Capacity",)),
    },
)

PEC_CSV_CLOCK = ImportProfile(
    name="pec-csv-clock",
    instrument="PEC (CSV export, 'Total Time (Hours in hh:mm:ss.xxx)')",
    version="0.2.0",
    layout=Layout(kind="delimited", encoding="cp1252", delimiter=",", decimal=".",
                  header_contains=("Test,Cell", "Total Time (Hours in hh:mm:ss.xxx)")),
    sniff_any=(column("Total Time (Hours in hh:mm:ss.xxx)"),),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="cycle_cumulative",
        cycle_base=0,
        evidence=(
            "Recognised and read on cellpy testdata/data/pec_multiple_tests/Test25205.csv and "
            "Test25209.csv (MIT, commit 29d916c; 2026, 'Idle' only, open-circuit storage). Total "
            "Time is a clock with an unbounded hour field. The files carry no current beyond a few "
            "microamperes of noise, so neither the sign convention nor the counter behaviour can "
            "be measured in them: both are carried over from pec-csv (2019 export of the same "
            "software) and are declared, not verified."),
    ),
    bindings={
        "test_time_second": B(source=("Total Time (Hours in hh:mm:ss.xxx)",), source_unit="hh:mm:ss"),
        "step_id": B(source=("Step",), source_unit="1"),
        "cycle_count": B(source=("Cycle",), source_unit="1"),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Voltage",)),
        "charging_capacity_ah": B(source=("Charge Capacity",)),
        "discharging_capacity_ah": B(source=("Discharge Capacity",)),
    },
)

LANDT_XLSX = ImportProfile(
    name="landt-xlsx",
    instrument="Landt / LANHE (Excel export, Record sheet)",
    version="0.2.0",
    layout=Layout(kind="excel", header_contains=("TestTime/", "Voltage/", "State")),
    sniff_any=(column_any_unit("TestTime", "/"), column_any_unit("StepTime", "/")),
    conventions=Conventions(
        current_sign="charge_positive",
        direction_source="current_sign",
        capacity_semantics="none",
        cycle_base=1,
        evidence=(
            "Checked on navani Example_data/NJK_CC_156_C30_C_x30.xlsx (MIT, commit d9892a3; 30 "
            "cycles of a coin cell at about 25 uA): sheets Record (time series), Mode and Cycle "
            "(the instrument's statistics); Current/mA signed, D_CC negative and C_CC positive, "
            "sign test 60 of 60 runs. The Record sheet has no step or cycle number, so the per-state "
            "Capacity/mAh counter cannot be checked at step boundaries and is not bound; capacity "
            "is integrated. TestTime/h is written to 0.01 h (36 s) and the current to 0.0001 mA, "
            "which limits the integral: the 30 charge and 30 discharge capacities integrated here "
            "agree with the instrument's Cycle sheet to 1.6 % at worst, 0.6 % median."),
        step_type_map={"R": "rest", "C_CC": "cc_charge", "D_CC": "cc_discharge"},
    ),
    bindings={
        "record_index": B(source=("Index",), source_unit="1"),
        "test_time_second": B(source=("TestTime",)),
        "step_type": B(source=("State",)),
        "current_ampere": B(source=("Current",)),
        "voltage_volt": B(source=("Voltage",)),
    },
)

BUILTIN = {p.name: p for p in (
    ARBIN_CSV, ARBIN_XLSX, ARBIN_MITS8_CSV, ARBIN_RES_TABLE_CSV,
    NEWARE_XLSX, NEWARE_CSV,
    MACCOR_TXT, MACCOR_EXPORT_SEC, MACCOR_EXPORT_MIN, MACCOR_EXPORT_CLOCK, MACCOR_EXPORT_SIGNED,
    BASYTEC_TXT, NOVONIX_CSV, PEC_CSV, PEC_CSV_CLOCK, LANDT_XLSX,
)}
