"""Records, answers and the questions the app asks.

A Record is one opened file. Its answers are what only the researcher can tell
(which current charges the cell, what the potential column measures, the
active-material mass...). Settings are derived from answers in one function,
`settings_for`, so the app and an exported settings.json cannot disagree.

Nothing is guessed. The header's declared mass is offered as a one-click
answer, never applied silently; an unanswered question leaves the values that
depend on it withheld, and the reason is shown wherever the value would be.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..cycling import Settings, degenerate, degenerate_note
from ..workflow import DEFAULT_CYCLES, Loaded, Run, parse_cycles

# ------------------------------------------------------------------ answers

@dataclass
class Answers:
    charge: str | None = None            # "ox" (positive current charges) or "red"
    configuration: str | None = None     # "half" (vs a reference or metal counter) or "full" (cell voltage)
    reference: str = ""                  # e.g. "Li+/Li", needed for "half"
    mass_mg: float | None = None
    no_mass: bool = False                # "no mass": capacities in mAh, or per cm2 with an area
    area_cm2: float | None = None
    molar_mass_g_mol: float | None = None
    electrons: float | None = None
    reference_cycle: int = 1
    cycle_order: str | None = None       # "charge-first" or "discharge-first"; None: not answered yet
    use_instrument_dq: bool = True

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @staticmethod
    def from_dict(d: dict) -> "Answers":
        a = Answers()
        for k, v in (d or {}).items():
            if hasattr(a, k):
                setattr(a, k, v)
        return a


def settings_for(a: Answers) -> Settings:
    half = a.configuration == "half" and bool(a.reference.strip())
    return Settings(
        charge=a.charge, cycle_order=a.cycle_order or "charge-first", terminal_voltage=(a.configuration == "full"),
        reference=a.reference.strip() if half else None, active_mass_mg=None if a.no_mass else a.mass_mg,
        area_cm2=a.area_cm2,
        molar_mass_g_mol=a.molar_mass_g_mol, electrons=a.electrons, reference_cycle=int(a.reference_cycle or 1),
        use_instrument_dq=a.use_instrument_dq)


def parse_number(text: str) -> float | None:
    """A decimal point or a decimal comma; never a thousands separator (P12 review finding 2).

    '1,5' and '1.5' are 1.5. '1,500.5' and '1.500,5' are refused rather than
    read as 1500.5 or 1.5, because either reading could be the wrong one.
    """
    s = text.strip().replace("−", "-").replace(" ", "")
    if not s:
        return None
    if s.count(",") + s.count(".") > 1:
        raise ValueError("use one decimal mark and no thousands separator")
    s = s.replace(",", ".")
    if not re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", s):
        raise ValueError("not a number")
    v = float(s)
    if not math.isfinite(v):                  # '1e400' overflows to infinity (independent review, finding r07)
        raise ValueError("too large to be a measured value")
    return v


# ------------------------------------------------------------------ questions

@dataclass
class Question:
    key: str
    title: str
    changes: str
    required: bool
    answered: bool


def first_branch_direction(a: Answers, run: Run | None) -> str | None:
    """"charge" or "discharge" for the first branch of the file, once the charging direction is given.

    Branch signs do not depend on any answer, so a run computed before the
    direction was given still tells which sign comes first."""
    if a.charge is None or run is None or not run.seg.branches:
        return None
    sign = run.seg.branches[0].sign
    charge_sign = 1 if a.charge in ("ox", "positive") else -1
    return "charge" if sign == charge_sign else "discharge"


def degenerate_start(run: Run | None) -> str | None:
    """Words for a file whose first branch has at most two rows and carries under 0.1 % of the charge of the
    branch after it, a step that ended at once (cycling.degenerate); None otherwise."""
    if run is None or len(run.seg.branches) < 2:
        return None
    b0, b1 = run.seg.branches[:2]
    results = {r.branch: r for r in run.an.branches}
    r0, r1 = results.get(b0.index), results.get(b1.index)
    if r0 is None or r1 is None or b0.sign == b1.sign or not degenerate(b0, r0.charge_mAh, r1.charge_mAh):
        return None
    return degenerate_note(b0, r0, r1)


def order_needed(a: Answers, run: Run | None) -> bool:
    """The cycle order is asked when the file starts with a discharge: the two groupings then pair
    different branches, so every efficiency and retention value depends on it (review finding 4). It is
    asked too when the first branch is a step that ended at once (for example a charge begun beyond its voltage
    limit, cycling.degenerate): the first branch of substance then decides the grouping."""
    return first_branch_direction(a, run) == "discharge" or (a.charge is not None and degenerate_start(run) is not None)


def questions(a: Answers, loaded: Loaded | None, run: Run | None = None) -> list[Question]:
    q = [
        Question("charge", "Which current direction charges the cell?",
                 "Pairs each charge with its discharge. Unlocks coulombic efficiency, retention and fade.",
                 True, a.charge is not None),
        Question("configuration", "What does the potential column measure?",
                 "Names the axis correctly. Unlocks energy, average voltage and hysteresis.",
                 True, a.configuration == "full" or (a.configuration == "half" and bool(a.reference.strip()))),
        Question("mass", "What is the active-material mass?",
                 "Unlocks specific capacity (mAh g⁻¹), specific energy and C-rate. "
                 "Without it, capacity stays in mAh.",
                 True, a.mass_mg is not None or a.no_mass),
        Question("optional", "Optional details",
                 "Electrode area gives areal capacity. Molar mass and electrons per formula unit give the "
                 "theoretical capacity, utilisation and electrons exchanged.",
                 False, any(v is not None for v in (a.area_cm2, a.molar_mass_g_mol, a.electrons))),
    ]
    if a.charge is not None:
        need = order_needed(a, run)
        q.insert(1, Question("order", "Does each cycle start with a charge or a discharge?",
                             "Decides which charge and discharge form a cycle, and so every efficiency, retention "
                             "and fade value.", need, a.cycle_order is not None or not need))
    return q


def open_questions(a: Answers, loaded: Loaded | None, run: Run | None = None) -> list[Question]:
    return [x for x in questions(a, loaded, run) if x.required and not x.answered]


# ------------------------------------------------------------------ records

@dataclass(eq=False)          # a record is one opened file: compared by identity, never field by field
class Record:                 # (field comparison reaches numpy arrays and raises; review finding r17)
    path: Path
    loaded: Loaded | None = None
    error: str | None = None
    answers: Answers = field(default_factory=Answers)
    run: Run | None = None
    run_settings: Settings | None = None
    analysing: bool = False
    analysis_error: str | None = None
    cycles_spec: str = DEFAULT_CYCLES
    focus_cycle: int | None = None
    proposal: object = None
    """A readers.Proposal while the file's columns wait to be mapped (no profile recognised it)."""
    profile: object = None
    """The readers.ImportProfile the file was read with, for a file from another instrument."""

    @property
    def label(self) -> str:
        return self.path.stem

    @property
    def needs_mapping(self) -> bool:
        return self.proposal is not None and (self.loaded is None or self.loaded.tab is None)

    @property
    def state(self) -> str:
        if self.error:
            return "could not be read"
        if self.needs_mapping:
            return "columns to map"
        if self.loaded is None:
            return "opening"
        if self.analysis_error:
            return "analysis failed"
        if self.analysing and self.run is None:
            return "analysing"
        n = len(open_questions(self.answers, self.loaded, self.run))
        if n:
            return f"{n} answer{'s' if n > 1 else ''} needed"
        return "ready to export" if self.current else "analysing"

    @property
    def current(self) -> bool:
        """A result is shown only for the inputs it was computed from (U01 decision 10)."""
        return self.run is not None and self.run_settings == settings_for(self.answers)

    def available_cycles(self) -> list[int]:
        return [p.index for p in self.run.seg.pairs] if self.run else []

    def complete_cycles(self) -> list[int]:
        return [c.cycle for c in self.run.an.cycles if c.complete] if self.run else []

    def selected_cycles(self) -> list[int]:
        av = self.available_cycles()
        sel = parse_cycles(self.cycles_spec, av)
        return sel or av[:5]


# ------------------------------------------------------------------ value states

AVAILABLE, WITHHELD = "available", "withheld"


def reason_for(field_name: str, a: Answers, run: Run | None = None) -> str | None:
    """Why a value is withheld, in words, or None when it should be available.

    With the run, reasons that depend on the file are named too: a retention
    reference cycle that is not a complete cycle of this file (review finding r22)."""
    s = settings_for(a)
    needs_charge = ("coulombic", "retention", "fade", "charge_capacity", "discharge_capacity", "efficiency",
                    "first_cycle", "last", "max_discharge", "cycle_reaching", "complete")
    needs_energy = ("energy", "average", "hysteresis", "mid_capacity")
    needs_mass = ("specific", "c_rate", "utilisation", "delta_x")
    f = field_name.lower()
    if s.charge is None and any(k in f for k in needs_charge):
        return "needs the charging current direction"
    if not s.energy_allowed and any(k in f for k in needs_energy):
        return "needs what the potential column measures"
    if s.active_mass_mg is None and any(k in f for k in needs_mass):
        return "needs the active-material mass"
    if "delta_x" in f and not s.molar_mass_g_mol:
        return "needs the molar mass"
    if ("utilisation" in f or "theoretical" in f or "c_rate" in f) and not s.theoretical_capacity_mAh_g:
        return "needs molar mass and electrons per formula unit"
    if run is not None and any(k in f for k in ("retention", "fade", "cycle_reaching")):
        complete = {c.cycle for c in run.an.cycles if c.complete}
        if s.reference_cycle not in complete:
            return f"the reference cycle, {s.reference_cycle}, is not a complete cycle of this file"
    if "areal" in f or "density" in f:
        if s.area_cm2 is None:
            return "needs the electrode area"
    return None


def state_of(field_name: str, value, a: Answers, run: Run | None = None) -> tuple[str, str | None]:
    if value is not None:
        return AVAILABLE, None
    return WITHHELD, reason_for(field_name, a, run) or "not defined for this cycle"
