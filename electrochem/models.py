"""Strict immutable records for the P01 cycling foundation.

Raw tokens remain distinct from normalized numbers. The archive retains the
original bytes. P03 supplies parsed records; P04 supplies justified intervals.
"""
from datetime import datetime, timedelta
import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .units import convert, unit

ID = Annotated[str, Field(min_length=1)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Nonnegative = Annotated[int, Field(ge=0)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Scalar = str | int | float | bool | None


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True,
                              allow_inf_nan=False, revalidate_instances="always")

    def revised(self, **changes):
        """Unlike model_copy(update=...), revalidate all changes."""
        return type(self).model_validate({**self.model_dump(), **changes})


class Setting(Record):
    name: ID
    value: Scalar


class Provenance(Record):
    origin: Literal["file", "user", "calculation"]
    evidence: ID
    revision: ID


class Column(Record):
    original_name: str  # duplicates and empty original names are legal
    original_unit: str | None


class Source(Record):
    sha256: Digest
    byte_size: Nonnegative
    original_name: ID
    format: Literal["mpr", "mpt", "mps", "synthetic", "other"]
    columns: tuple[Column, ...] = ()


class RowRef(Record):
    source_hash: Digest
    record_index: Nonnegative  # zero-based measurement record, NOT a line number


class RawRow(Record):
    ref: RowRef
    tokens: tuple[str | None, ...]  # original lexical values; no float coercion


class Channel(Record):
    id: ID
    source_hash: Digest
    column_index: Nonnegative
    quantity: Literal["time", "current", "potential", "temperature", "charge",
                      "frequency", "resistance"]
    input_unit: ID
    potential_role: Literal["terminal", "electrode", "unresolved"] | None = None
    positive_node: str | None = None
    negative_node: str | None = None
    reference: str | None = None
    current_polarity: Literal[-1, 1] | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def conventions(self):
        if unit(self.input_unit).dimension != self.quantity:
            raise ValueError("Channel quantity and unit have incompatible dimensions")
        if self.quantity == "potential":
            if self.potential_role is None:
                raise ValueError("Potential role must be explicit, including unresolved")
            if self.potential_role == "terminal" and (
                not self.positive_node or not self.negative_node
                or self.positive_node == self.negative_node
            ):
                raise ValueError("Terminal potential requires two distinct named nodes")
        elif any(x is not None for x in (self.potential_role, self.positive_node,
                                         self.negative_node, self.reference)):
            raise ValueError("Potential conventions belong to potential channels")
        if self.quantity != "current" and self.current_polarity is not None:
            raise ValueError("Current polarity belongs only to current channels")
        return self


class Sample(Record):
    channel_id: ID
    value_si: Finite | None
    validity: Literal["valid", "missing", "invalid"]
    reason: str | None = None

    @model_validator(mode="after")
    def missing_is_not_zero(self):
        if self.validity == "valid" and self.value_si is None:
            raise ValueError("A valid measurement needs a finite value")
        if self.validity != "valid" and (self.value_si is not None or not self.reason):
            raise ValueError("Missing/invalid samples need null value and a reason")
        return self


class Observation(Record):
    ref: RowRef
    experiment_id: ID
    acquisition_order: Nonnegative
    block_id: ID
    samples: tuple[Sample, ...]
    absolute_time: datetime | None = None
    absolute_time_provenance: Provenance | None = None
    native_step: str | None = None
    native_cycle: str | None = None

    @model_validator(mode="after")
    def time_origin(self):
        if self.absolute_time is not None:
            if self.absolute_time.utcoffset() is None or self.absolute_time_provenance is None:
                raise ValueError("Absolute time needs an explicit UTC offset and provenance")
        elif self.absolute_time_provenance is not None:
            raise ValueError("Time provenance without absolute time")
        unique([s.channel_id for s in self.samples], "observation channels")
        return self


class Experiment(Record):
    id: ID
    cell_id: ID
    configuration: Literal["full_cell", "metal_half_cell", "three_electrode",
                           "symmetric", "blocking", "unknown"]
    technique: ID  # native/unresolved labels allowed; no automated identification yet
    time_channel: ID
    current_channel: ID | None = None
    voltage_channel: ID | None = None
    # Explicit confirmation links mapped current direction to the terminal nodes.
    passive_current_confirmed: bool = False
    convention_provenance: Provenance | None = None
    clock_tolerance_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class Interval(Record):
    id: ID
    left: RowRef
    right: RowRef
    status: Literal["supported", "excluded", "unresolved"]
    reason: ID
    reconstruction: Literal["point_linear", "interval_mean", "none"]
    provenance: Provenance

    @model_validator(mode="after")
    def explicit_model(self):
        if self.status == "supported" and self.reconstruction == "none":
            raise ValueError("Supported interval needs a reconstruction model")
        return self


class Branch(Record):
    id: ID
    experiment_id: ID
    interval_ids: tuple[ID, ...]
    direction: Literal["charge", "discharge", "positive_current", "negative_current", "unknown"]
    completeness: Literal["complete", "partial", "unknown"]
    termination_evidence: str | None = None
    formation: bool | None = None
    provenance: Provenance


class Pair(Record):
    id: ID
    charge_branch: ID
    discharge_branch: ID
    policy: ID
    provenance: Provenance


class MetadataValue(Record):
    id: ID
    scope_id: ID  # cell/electrode identifier; never guessed from material name
    kind: Literal["active_mass", "composite_mass", "cell_mass", "geometric_area",
                  "interfacial_area", "thickness", "temperature", "reference_capacity"]
    value: Finite | None
    unit: ID
    confirmed: bool
    provenance: Provenance

    @model_validator(mode="after")
    def physical_basis(self):
        dimension = {"active_mass": "mass", "composite_mass": "mass", "cell_mass": "mass",
                     "geometric_area": "area", "interfacial_area": "area", "thickness": "length",
                     "temperature": "temperature", "reference_capacity": "charge"}[self.kind]
        if unit(self.unit).dimension != dimension:
            raise ValueError("Metadata basis and units disagree")
        if self.value is not None:
            si = convert(self.value, self.unit, unit(self.unit).si)
            if si <= 0:
                raise ValueError("This metadata quantity must be positive")
        elif self.confirmed:
            raise ValueError("A missing numeric value cannot be confirmed")
        return self


class MetadataRevision(Record):
    id: ID
    parent_id: ID | None = None
    reason: ID
    entries: tuple[MetadataValue, ...]

    @model_validator(mode="after")
    def unique_entries(self):
        unique([e.id for e in self.entries], "metadata entries")
        return self


class Uncertainty(Record):
    status: Literal["not_evaluated", "evaluated"] = "not_evaluated"
    standard_uncertainty: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    method: str | None = None
    component: Literal["measurement", "fit", "between_cell", "combined"] | None = None
    covariance_group: str | None = None  # linkage only; P15 supplies matrices/propagation

    @model_validator(mode="after")
    def honest_uncertainty(self):
        if self.status == "not_evaluated" and self.standard_uncertainty is not None:
            raise ValueError("Unevaluated uncertainty is null, not zero")
        if self.status == "evaluated" and (
            self.standard_uncertainty is None or not self.method or self.component is None
        ):
            raise ValueError("Evaluated uncertainty needs magnitude, method and component")
        return self


class Result(Record):
    id: ID
    method_id: ID
    method_version: ID
    engine_version: ID
    parser_version: ID
    metadata_revision: ID
    input_digest: Digest
    interval_ids: tuple[ID, ...]
    settings: tuple[Setting, ...]
    status: Literal["available", "provisional", "needs_metadata", "inapplicable", "failed"]
    evidence_level: Literal["proposed", "implemented", "software_tested", "experimentally_validated"]
    value: Finite | None
    unit: ID
    normalization_metadata_id: ID | None = None
    diagnostics: tuple[ID, ...] = ()
    assumptions: tuple[ID, ...] = ()
    uncertainty: Uncertainty = Uncertainty()

    @model_validator(mode="after")
    def result_contract(self):
        unit(self.unit)
        unique([s.name for s in self.settings], "settings")
        if self.status in ("available", "provisional"):
            if self.value is None:
                raise ValueError("Available result requires a value")
        elif self.value is not None or not self.diagnostics:
            raise ValueError("Unavailable result needs null value and diagnostics")
        if self.status == "provisional" and not self.assumptions:
            raise ValueError("Provisional result needs named assumptions")
        if unit(self.unit).dimension in ("specific_charge", "areal_charge", "specific_energy"):
            if self.status in ("available", "provisional") and not self.normalization_metadata_id:
                raise ValueError("Normalized result needs an explicit denominator")
        return self


def unique(keys, label):
    if len(set(keys)) != len(keys):
        raise ValueError(f"Duplicate {label}")


def row_key(ref):
    return ref.source_hash, ref.record_index


def canonical_bytes(record: Record) -> bytes:
    return json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(record: Record) -> str:
    return hashlib.sha256(canonical_bytes(record)).hexdigest()


class Project(Record):
    schema_version: Literal["0.1.0"] = "0.1.0"
    id: ID
    sources: tuple[Source, ...]
    raw_rows: tuple[RawRow, ...]
    channels: tuple[Channel, ...]
    experiments: tuple[Experiment, ...]
    observations: tuple[Observation, ...]
    intervals: tuple[Interval, ...]
    branches: tuple[Branch, ...] = ()
    pairs: tuple[Pair, ...] = ()
    metadata: tuple[MetadataRevision, ...]
    current_metadata_revision: ID
    results: tuple[Result, ...] = ()
    display_settings: tuple[Setting, ...] = ()

    @model_validator(mode="after")
    def referential_integrity(self):
        for values, attr in ((self.sources, "sha256"), (self.channels, "id"),
                             (self.experiments, "id"), (self.intervals, "id"),
                             (self.branches, "id"), (self.pairs, "id"),
                             (self.metadata, "id"), (self.results, "id")):
            unique([getattr(x, attr) for x in values], attr)
        unique([x.name for x in self.display_settings], "display settings")
        unique([row_key(x.ref) for x in self.raw_rows], "raw row references")
        unique([row_key(x.ref) for x in self.observations], "observation references")
        src = {s.sha256: s for s in self.sources}
        channels = {c.id: c for c in self.channels}
        exps = {e.id: e for e in self.experiments}
        rows = {row_key(r.ref): r for r in self.raw_rows}
        obs = {row_key(o.ref): o for o in self.observations}
        intervals = {i.id: i for i in self.intervals}
        branches = {b.id: b for b in self.branches}
        revisions = {m.id: m for m in self.metadata}
        if self.current_metadata_revision not in revisions:
            raise ValueError("Unknown current metadata revision")
        seen = set()
        for m in self.metadata:
            if m.parent_id is not None and m.parent_id not in seen:
                raise ValueError("Metadata parents must precede their revisions")
            seen.add(m.id)
        for r in self.raw_rows:
            if r.ref.source_hash not in src or len(r.tokens) != len(src[r.ref.source_hash].columns):
                raise ValueError("Raw tokens must retain every original column")
        for c in self.channels:
            if c.source_hash not in src or c.column_index >= len(src[c.source_hash].columns):
                raise ValueError("Channel references an unknown source column")
        for e in self.experiments:
            for cid, quantity in ((e.time_channel, "time"), (e.current_channel, "current"),
                                  (e.voltage_channel, "potential")):
                if cid is not None and (cid not in channels or channels[cid].quantity != quantity):
                    raise ValueError("Experiment references incompatible channels")
            if e.passive_current_confirmed and (
                e.current_channel is None or e.voltage_channel is None
                or channels[e.voltage_channel].potential_role != "terminal"
                or channels[e.current_channel].current_polarity is None
                or e.convention_provenance is None
            ):
                raise ValueError("Passive current requires terminal-channel and polarity evidence")
        previous = {}
        for o in self.observations:
            if row_key(o.ref) not in rows or o.experiment_id not in exps:
                raise ValueError("Observation lacks raw row or experiment")
            prev = previous.get(o.experiment_id)
            if prev is not None and o.acquisition_order <= prev.acquisition_order:
                raise ValueError("Observations must retain unique acquisition order per experiment")
            previous[o.experiment_id] = o
            for s in o.samples:
                if s.channel_id not in channels or channels[s.channel_id].source_hash != o.ref.source_hash:
                    raise ValueError("Sample does not belong to the referenced source")
                if channels[s.channel_id].quantity == "temperature" and s.value_si is not None and s.value_si < 0:
                    raise ValueError("Negative absolute temperature")
            e = exps[o.experiment_id]
            # For consecutive samples in one time block, independently check datetime deltas.
            if prev is not None and prev.block_id == o.block_id and prev.absolute_time and o.absolute_time:
                t0, t1 = sample_value(prev, e.time_channel), sample_value(o, e.time_channel)
                if t0 is not None and t1 is not None:
                    error = abs((o.absolute_time - prev.absolute_time).total_seconds() - (t1 - t0))
                    if error > e.clock_tolerance_s:
                        raise ValueError("Absolute and local time differences disagree")
        used_edges = set()
        for i in self.intervals:
            if row_key(i.left) not in obs or row_key(i.right) not in obs:
                raise ValueError("Interval references missing observations")
            edge = row_key(i.left), row_key(i.right)
            if edge in used_edges:
                raise ValueError("Duplicate integration interval")
            used_edges.add(edge)
            a, b = obs[edge[0]], obs[edge[1]]
            if a.experiment_id != b.experiment_id or b.acquisition_order != a.acquisition_order + 1:
                raise ValueError("Intervals require adjacent observations in one experiment")
            if i.status == "supported":
                e = exps[a.experiment_id]
                t0, t1 = sample_value(a, e.time_channel), sample_value(b, e.time_channel)
                if a.block_id != b.block_id or t0 is None or t1 is None or t1 <= t0:
                    raise ValueError("Unsupported time reset, duplicate timestamp or missing time")
        for b in self.branches:
            unique(b.interval_ids, "branch intervals")
            if b.experiment_id not in exps:
                raise ValueError("Unknown branch experiment")
            for iid in b.interval_ids:
                if iid not in intervals or obs[row_key(intervals[iid].left)].experiment_id != b.experiment_id:
                    raise ValueError("Branch interval belongs to another experiment")
            if b.completeness == "complete" and (
                not b.interval_ids or not b.termination_evidence
                or any(intervals[i].status != "supported" for i in b.interval_ids)
            ):
                raise ValueError("Complete branch requires supported intervals and termination evidence")
        for p in self.pairs:
            if p.charge_branch not in branches or p.discharge_branch not in branches:
                raise ValueError("Unknown pair branch")
            a, b = branches[p.charge_branch], branches[p.discharge_branch]
            if a.direction != "charge" or b.direction != "discharge" or a.experiment_id != b.experiment_id:
                raise ValueError("Pair needs named charge/discharge branches in one experiment")
            if set(a.interval_ids) & set(b.interval_ids):
                raise ValueError("Charge and discharge cannot reuse the same intervals")
        for r in self.results:
            if r.metadata_revision not in revisions or any(i not in intervals for i in r.interval_ids):
                raise ValueError("Result references unknown metadata or support")
            if r.normalization_metadata_id:
                entries = {v.id: v for v in revisions[r.metadata_revision].entries}
                if r.normalization_metadata_id not in entries:
                    raise ValueError("Unknown normalization denominator")
                entry = entries[r.normalization_metadata_id]
                dim = unit(r.unit).dimension
                allowed = {"specific_charge": ("active_mass", "composite_mass", "cell_mass"),
                           "specific_energy": ("active_mass", "composite_mass", "cell_mass"),
                           "areal_charge": ("geometric_area",)}
                if dim in allowed and entry.kind not in allowed[dim]:
                    raise ValueError("Wrong normalization basis")
                if r.status in ("available", "provisional") and entry.value is None:
                    raise ValueError("A provisional result cannot invent a missing denominator")
                if r.status == "available" and not entry.confirmed:
                    raise ValueError("Available normalized result needs confirmed denominator")
        return self

    def input_digest(self) -> str:
        """Conservative scientific-input digest; styling and existing results excluded."""
        payload = self.model_dump(mode="json", exclude={"results", "display_settings", "metadata"})
        payload["metadata"] = next(m.model_dump(mode="json") for m in self.metadata
                                   if m.id == self.current_metadata_revision)
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    def result_is_current(self, result: Result) -> bool:
        return (result.metadata_revision == self.current_metadata_revision
                and result.input_digest == self.input_digest())


def sample_value(observation: Observation, channel_id: str | None):
    return next((s.value_si for s in observation.samples
                 if s.channel_id == channel_id and s.validity == "valid"), None)


def normalize(value: float | None, channel: Channel, *, missing_reason="not recorded") -> Sample:
    """Explicit unit/polarity conversion only; never parses or guesses source tokens."""
    if value is None:
        return Sample(channel_id=channel.id, value_si=None, validity="missing", reason=missing_reason)
    x = convert(value, channel.input_unit, unit(channel.input_unit).si)
    if channel.quantity == "current" and channel.current_polarity is not None:
        x *= channel.current_polarity
    return Sample(channel_id=channel.id, value_si=x, validity="valid")


def elapsed_to_absolute(start: datetime, elapsed_s: float) -> datetime:
    """Timezone stays explicit; numeric seconds are never cast to microseconds."""
    if start.utcoffset() is None:
        raise ValueError("An explicit offset is required; retain unknown local time as raw text")
    return start + timedelta(seconds=convert(elapsed_s, "s", "s"))


def energy_gate(project: Project, interval_id: str) -> tuple[str, ...]:
    """Eligibility diagnostics only, no energy calculation or mechanistic inference."""
    interval = next(i for i in project.intervals if i.id == interval_id)
    observations = {row_key(o.ref): o for o in project.observations}
    a, b = observations[row_key(interval.left)], observations[row_key(interval.right)]
    e = next(e for e in project.experiments if e.id == a.experiment_id)
    reasons = []
    if interval.status != "supported":
        reasons.append("unsupported_interval")
    if not e.passive_current_confirmed:
        reasons.append("unconfirmed_terminal_convention")
    if interval.reconstruction != "point_linear":
        reasons.append("energy_sample_semantics_not_implemented")
    for o in (a, b):
        if sample_value(o, e.current_channel) is None:
            reasons.append("missing_or_invalid_current")
        if sample_value(o, e.voltage_channel) is None:
            reasons.append("missing_or_invalid_voltage")
    return tuple(dict.fromkeys(reasons))
