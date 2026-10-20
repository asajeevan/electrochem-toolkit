"""Typed import profile: one declaration of how to read one family of files.

Design rule: illegal states are unrepresentable. A profile cannot exist without
stating the current sign convention, where direction comes from, what the
capacity columns mean, and who verified it against a real file. There is no
default for any of those, so a profile written carelessly fails at load time
rather than producing confident wrong numbers at analysis time.

Role names follow the Battery Data Format (BDF) machine-readable vocabulary of
the LF Energy Battery Data Alliance, so a profile written here is close to a BDF
mapping sidecar and the two can be converted.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# BDF canonical roles this reader understands. Units are the BDF canonical units.
ROLE_UNITS: dict[str, str] = {
    "test_time_second": "s",
    "step_time_second": "s",
    "unix_time_second": "s",
    "current_ampere": "A",
    "voltage_volt": "V",
    "power_watt": "W",
    "charging_capacity_ah": "Ah",
    "discharging_capacity_ah": "Ah",
    "net_capacity_ah": "Ah",
    "step_cumulative_capacity_ah": "Ah",
    "cycle_cumulative_capacity_ah": "Ah",
    "ambient_temperature_celsius": "degC",
    "surface_temperature_celsius": "degC",
    # dimensionless / categorical
    "record_index": "1",
    "step_id": "1",
    "step_count": "1",
    "cycle_count": "1",
    "step_type": "",
}

# Closed unit registry: every factor is exact or a documented constant.
# Deliberately not pint: the toolkit's existing decision is a closed, versioned
# registry so that a conversion cannot change when a dependency is upgraded.
UNIT_FACTOR: dict[str, float] = {
    # time -> s. 'hh:mm:ss' is a clock-format duration ('[Nd ]H:MM:SS[.fff]', see cells.py),
    # parsed to seconds before this factor applies; only a column declared with it is parsed so
    "s": 1.0, "sec": 1.0, "second": 1.0, "ms": 1e-3, "min": 60.0, "h": 3600.0, "hr": 3600.0,
    "hh:mm:ss": 1.0,
    # current -> A
    "A": 1.0, "mA": 1e-3, "uA": 1e-6, "µA": 1e-6, "nA": 1e-9,
    # potential -> V
    "V": 1.0, "mV": 1e-3,
    # charge -> Ah
    "Ah": 1.0, "A.h": 1.0, "mAh": 1e-3, "mA.h": 1e-3, "uAh": 1e-6, "C": 1.0 / 3600.0,
    # power -> W
    "W": 1.0, "mW": 1e-3,
    # temperature -> degC (offset units are rejected below, not scaled)
    "degC": 1.0, "°C": 1.0, "C_temp": 1.0,
    # dimensionless
    "1": 1.0, "": 1.0,
}

# The physical dimension of every registered unit. A column may only be bound to
# a role whose canonical unit has the same dimension, which makes a whole class
# of mis-mapping impossible rather than merely unlikely: an impedance column
# headed '-Im(Z)/Ohm' cannot become the current, however much its name looks
# like one.
UNIT_DIMENSION: dict[str, str] = {
    "s": "time", "sec": "time", "second": "time", "ms": "time", "min": "time",
    "h": "time", "hr": "time", "hh:mm:ss": "time",
    "A": "current", "mA": "current", "uA": "current", "µA": "current", "nA": "current",
    "V": "potential", "mV": "potential",
    "Ah": "charge", "A.h": "charge", "mAh": "charge", "mA.h": "charge", "uAh": "charge",
    "C": "charge",
    "W": "power", "mW": "power",
    "degC": "temperature", "°C": "temperature", "C_temp": "temperature",
    "1": "dimensionless", "": "dimensionless",
}
assert set(UNIT_DIMENSION) == set(UNIT_FACTOR), "every unit needs a dimension"


def role_dimension(role: str) -> str:
    return UNIT_DIMENSION[ROLE_UNITS[role]]


def units_for(role: str) -> list[str]:
    """The registered units a column may carry for this role, canonical first."""
    dim = role_dimension(role)
    canon = ROLE_UNITS[role]
    rest = sorted(u for u, d in UNIT_DIMENSION.items() if d == dim and u != canon and u not in ("", "C_temp"))
    return [canon] + rest


class Binding(BaseModel):
    """How one role is obtained from the source file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: tuple[str, ...] = Field(min_length=1)
    """Candidate header strings, first match wins. '{unit}' matches a unit group,
    so 'DChg. Cap.({unit})' matches 'DChg. Cap.(mAh)' and yields source_unit mAh."""
    source_unit: str | None = None
    """Unit of the source column when the header does not carry one."""
    scale: float = 1.0
    offset: float = 0.0
    reverse_sign: bool = False
    assumed: bool = False
    """True when this binding was inferred from documentation rather than
    confirmed against a real file. Surfaced in the import report."""

    @model_validator(mode="after")
    def _unit_known(self):
        if self.source_unit is not None and self.source_unit not in UNIT_FACTOR:
            raise ValueError(f"unknown source_unit {self.source_unit!r}")
        return self


StepKind = Literal["cc_charge", "cc_discharge", "cv_charge", "cv_discharge", "rest", "ocv", "other"]


class Conventions(BaseModel):
    """What the file cannot tell us and the engine must not guess.

    None of these have defaults. BDF standardises the column vocabulary but not
    the sign convention or the capacity semantics, so they are declared here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    current_sign: Literal["charge_positive", "discharge_positive", "unsigned", "detect"]
    """'detect' is for Maccor, whose exports are signed in some configurations
    and unsigned with direction in State in others. The reader decides per file
    and refuses when the evidence is ambiguous; it never assumes."""
    direction_source: Literal["current_sign", "step_type"]
    capacity_semantics: Literal[
        "per_row_increment", "step_cumulative", "cycle_cumulative", "test_cumulative", "none"
    ]
    cycle_base: Literal[0, 1]
    evidence: str = Field(min_length=10)
    """Who checked this profile against which file. Refused if empty."""
    step_type_map: dict[str, StepKind] = Field(default_factory=dict)

    verify_capacity_semantics: bool = True
    """Measure the accumulator's behaviour at step boundaries and refuse if it
    contradicts the declaration. Arbin's reset behaviour is schedule-dependent,
    so the declaration is a claim to be checked per file, not a fact."""

    @model_validator(mode="after")
    def _coherent(self):
        if self.current_sign == "detect" and self.direction_source != "step_type":
            raise ValueError("current_sign='detect' requires direction_source='step_type': "
                             "detection may conclude the column is unsigned")
        if self.current_sign == "unsigned" and self.direction_source != "step_type":
            raise ValueError(
                "current_sign='unsigned' requires direction_source='step_type': "
                "an unsigned current column cannot establish charge from discharge"
            )
        if self.direction_source == "step_type" and not self.step_type_map:
            raise ValueError("direction_source='step_type' requires a non-empty step_type_map")
        return self


class Layout(BaseModel):
    """Where the table sits in the file. Mirrors the BDF mapping 'source_locator'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["delimited", "excel"]
    encoding: str = "utf-8"
    delimiter: str | None = None
    """None means sniff among tab, comma, semicolon on the header line."""
    decimal: Literal[".", ",", "auto"] = "auto"
    header_row: int = 1
    """1-based row holding the column names. Ignored when header_contains is set."""
    header_contains: tuple[str, ...] = ()
    """Find the header as the first row containing all of these strings. More
    robust than a row number for files with a preamble of variable length, which
    is most of them: EC-Lab declares its header length in line 2, Maccor and
    Basytec write a variable number of preamble lines."""
    skip_rows_after_header: int = 0
    """Rows between the header and the first data row, e.g. a units row."""
    unit_row: int | None = None
    """1-based row holding units, when they are not in the header."""
    sheets: tuple[str, ...] | None = None
    """Excel only. None means every sheet whose header matches, in workbook order."""
    comment: str | None = None


class ImportProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    instrument: str = Field(min_length=1)
    version: str = "0.1.0"
    layout: Layout
    conventions: Conventions
    bindings: dict[str, Binding]
    sniff_any: tuple[str, ...] = ()
    """Strings whose presence in the first kilobytes identifies this format."""

    @model_validator(mode="after")
    def _roles_known_and_sufficient(self):
        unknown = set(self.bindings) - set(ROLE_UNITS)
        if unknown:
            raise ValueError(f"unknown roles {sorted(unknown)}; use BDF machine names")
        for required in ("test_time_second", "current_ampere", "voltage_volt"):
            if required not in self.bindings:
                raise ValueError(f"profile must bind {required}")
        if self.conventions.direction_source == "step_type" and "step_type" not in self.bindings:
            raise ValueError("direction_source='step_type' but no step_type column is bound")
        if self.conventions.capacity_semantics != "none" and not any(
            r.endswith("_capacity_ah") for r in self.bindings
        ):
            raise ValueError("capacity_semantics declared but no capacity column is bound")
        # BDF defines these two counters by where they reset; a profile may not say otherwise
        for role, semantics in (("step_cumulative_capacity_ah", "step_cumulative"),
                                ("cycle_cumulative_capacity_ah", "cycle_cumulative")):
            if role in self.bindings and self.conventions.capacity_semantics != semantics:
                raise ValueError(f"{role} resets by definition ({semantics}); the profile declares "
                                 f"{self.conventions.capacity_semantics}")
        return self
