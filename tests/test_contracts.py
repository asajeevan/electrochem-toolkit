"""Independent invariants and deliberately invalid inputs, not parser validation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from pydantic import ValidationError

from electrochem.archive import load, save
from electrochem.models import (
    Branch, Channel, Column, Experiment, Interval, MetadataRevision, MetadataValue,
    Observation, Pair, Project, Provenance, RawRow, Result, RowRef, Sample, Setting,
    Source, Uncertainty, canonical_bytes, elapsed_to_absolute, energy_gate, normalize,
)
from electrochem.units import convert

PROV = Provenance(origin="user", evidence="Synthetic fixture definition, not an instrument", revision="fixture-1")
BLOB = b"time/ms\tI/mA\tEwe/V\tflag\n0\t1\t3\tOK\n1000\t1\t3\tOK\n"
HASH = hashlib.sha256(BLOB).hexdigest()


def fixture():
    source = Source(sha256=HASH, byte_size=len(BLOB), original_name="synthetic.tsv", format="synthetic",
                    columns=(Column(original_name="time/ms", original_unit="ms"),
                             Column(original_name="I/mA", original_unit="mA"),
                             Column(original_name="Ewe/V", original_unit="V"),
                             Column(original_name="flag", original_unit=None)))
    time = Channel(id="time", source_hash=HASH, column_index=0, quantity="time", input_unit="ms", provenance=PROV)
    current = Channel(id="current", source_hash=HASH, column_index=1, quantity="current", input_unit="mA",
                      current_polarity=1, provenance=PROV)
    voltage = Channel(id="voltage", source_hash=HASH, column_index=2, quantity="potential", input_unit="V",
                      potential_role="unresolved", provenance=PROV)
    refs = tuple(RowRef(source_hash=HASH, record_index=i) for i in range(2))
    raw = (RawRow(ref=refs[0], tokens=("0", "1", "3", "OK")),
           RawRow(ref=refs[1], tokens=("1000", "1", "3", "OK")))
    observations = tuple(Observation(ref=refs[i], experiment_id="experiment", acquisition_order=i,
                                     block_id="block-1", samples=(normalize(i*1000., time), normalize(1., current), normalize(3., voltage)),
                                     absolute_time=elapsed_to_absolute(datetime(2026,1,1,tzinfo=timezone.utc), float(i)),
                                     absolute_time_provenance=PROV)
                         for i in range(2))
    exp = Experiment(id="experiment", cell_id="cell", configuration="unknown", technique="synthetic",
                     time_channel="time", current_channel="current", voltage_channel="voltage", clock_tolerance_s=1e-6)
    interval = Interval(id="interval", left=refs[0], right=refs[1], status="supported",
                        reason="Synthetic continuous signal", reconstruction="point_linear", provenance=PROV)
    mass = MetadataValue(id="mass", scope_id="positive-electrode", kind="active_mass", value=10., unit="mg",
                         confirmed=True, provenance=PROV)
    return Project(id="p01-fixture", sources=(source,), raw_rows=raw, channels=(time,current,voltage),
                   experiments=(exp,), observations=observations, intervals=(interval,),
                   metadata=(MetadataRevision(id="m1", reason="Initial synthetic metadata", entries=(mass,)),),
                   current_metadata_revision="m1")


def terminal(project):
    channel = project.channels[2].revised(potential_role="terminal", positive_node="positive", negative_node="negative")
    exp = project.experiments[0].revised(configuration="full_cell", passive_current_confirmed=True, convention_provenance=PROV)
    return project.revised(channels=project.channels[:2]+(channel,), experiments=(exp,))


class UnitsTests(unittest.TestCase):
    def test_analytic_conversions(self):
        for value, a, b, expected in [(1.,"mAh","C",3.6), (10.,"mg","kg",1e-5),
                                      (1.,"mAh/g","C/kg",3600.), (1.,"mAh/cm^2","C/m^2",36000.),
                                      (1.,"S/cm","S/m",100.), (1.,"cm^2/s","m^2/s",1e-4),
                                      (1.,"mA/cm^2","A/m^2",10.), (98.,"%","1",.98)]:
            with self.subTest(a=a,b=b):
                self.assertAlmostEqual(convert(value,a,b),expected,places=10)

    def test_temperature_offset_and_difference(self):
        self.assertAlmostEqual(convert(25.,"degC","K"),298.15)
        self.assertEqual(convert(25.,"delta_degC","delta_K"),25.)
        with self.assertRaises(ValueError): convert(25.,"degC","delta_K")
        with self.assertRaises(ValueError): convert(-274.,"degC","K")

    def test_incompatible_dimensions(self):
        for a,b in [("mA","V"),("C","degC"),("mg","cm^2"),("Ah","mAh/g")]:
            with self.subTest(a=a,b=b), self.assertRaises(ValueError): convert(1.,a,b)

    def test_no_numeric_or_unit_guessing(self):
        for value in [None,True,"1",float('nan'),float('inf')]:
            with self.subTest(value=value), self.assertRaises(ValueError): convert(value,"A","mA")
        with self.assertRaises(ValueError): convert(1.,"a","A")


class ModelTests(unittest.TestCase):
    def test_raw_tokens_and_flags_survive(self):
        p=fixture()
        self.assertEqual(p.raw_rows[1].tokens,("1000","1","3","OK"))
        self.assertEqual(p.sources[0].columns[2].original_name,"Ewe/V")
        self.assertEqual(p.channels[2].potential_role,"unresolved")
        self.assertEqual(p.observations[1].samples[0].value_si,1.)

    def test_unknown_and_duplicate_column_names_are_preserved(self):
        p=fixture();cols=p.sources[0].columns
        source=p.sources[0].revised(columns=cols[:3]+(Column(original_name="Ewe/V",original_unit="vendor-unit"),))
        p=p.revised(sources=(source,))
        self.assertEqual(p.sources[0].columns[3].original_unit,"vendor-unit")
        self.assertEqual(len(p.sources[0].columns),4)

    def test_null_is_not_zero_and_invalid_number_remains_raw(self):
        c=fixture().channels[1]
        self.assertIsNone(normalize(None,c).value_si)
        self.assertEqual(normalize(0.,c).value_si,0.)
        with self.assertRaises(ValidationError): Sample(channel_id="x",value_si=0.,validity="missing",reason="missing")
        with self.assertRaises(ValidationError): Sample(channel_id="x",value_si=float('nan'),validity="valid")
        p=fixture();raw=p.raw_rows[0].revised(tokens=("0","NaN","3","OVERFLOW"))
        invalid=Sample(channel_id="current",value_si=None,validity="invalid",reason="instrument overflow")
        o=p.observations[0].revised(samples=(p.observations[0].samples[0],invalid,p.observations[0].samples[2]))
        p=p.revised(raw_rows=(raw,p.raw_rows[1]),observations=(o,p.observations[1]))
        self.assertEqual(p.raw_rows[0].tokens[1],"NaN")

    def test_nested_immutability_and_validated_revision(self):
        p=fixture()
        with self.assertRaises(ValidationError): p.sources[0].byte_size=0
        with self.assertRaises(ValidationError): p.metadata[0].entries[0].revised(value=-1.)
        self.assertEqual(p.metadata[0].entries[0].value,10.)

    def test_extra_fields_and_string_numbers_rejected(self):
        with self.assertRaises(ValidationError): RowRef(source_hash=HASH,record_index="0")
        with self.assertRaises(ValidationError): RowRef(source_hash=HASH,record_index=0,guessed=True)

    def test_absolute_time_seconds(self):
        start=datetime(2026,1,1,tzinfo=timezone.utc)
        self.assertAlmostEqual((elapsed_to_absolute(start,139.524007)-start).total_seconds(),139.524007)
        with self.assertRaises(ValueError): elapsed_to_absolute(datetime(2026,1,1),1.)

    def test_microsecond_scaling_error_rejected(self):
        p=fixture();o=p.observations[1].revised(absolute_time=elapsed_to_absolute(p.observations[0].absolute_time,1e-6))
        with self.assertRaisesRegex(ValidationError,"time differences disagree"):
            p.revised(observations=(p.observations[0],o))

    def test_duplicate_timestamp_preserved_but_not_supported(self):
        p=fixture();o=p.observations[1].revised(samples=p.observations[0].samples, absolute_time=p.observations[0].absolute_time)
        with self.assertRaises(ValidationError): p.revised(observations=(p.observations[0],o))
        excluded=p.intervals[0].revised(status="unresolved",reason="Repeated timestamp; endpoint semantics unknown")
        q=p.revised(observations=(p.observations[0],o),intervals=(excluded,))
        self.assertEqual(len(q.observations),2)

    def test_time_reset_cannot_be_bridged(self):
        p=fixture();o=p.observations[1].revised(block_id="block-2")
        with self.assertRaises(ValidationError): p.revised(observations=(p.observations[0],o))
        q=p.revised(observations=(p.observations[0],o), intervals=(p.intervals[0].revised(status="excluded",reason="Time block reset"),))
        self.assertEqual(q.intervals[0].status,"excluded")

    def test_duplicate_intervals_and_dangling_refs_rejected(self):
        p=fixture()
        with self.assertRaises(ValidationError): p.revised(intervals=p.intervals+(p.intervals[0].revised(id="duplicate"),))
        with self.assertRaises(ValidationError): p.revised(raw_rows=p.raw_rows[:1])
        with self.assertRaises(ValidationError): p.revised(observations=tuple(reversed(p.observations)))

    def test_mass_and_area_are_distinct(self):
        mass=fixture().metadata[0].entries[0]
        for bad in [dict(value=0.),dict(value=-1.),dict(unit="cm^2"),dict(value=None)]:
            with self.subTest(bad=bad),self.assertRaises(ValidationError):mass.revised(**bad)
        self.assertIsNone(mass.revised(value=None,confirmed=False).value)

    def test_energy_requires_terminal_roles_and_current_convention(self):
        p=fixture()
        self.assertIn("unconfirmed_terminal_convention",energy_gate(p,"interval"))
        p=terminal(p)
        self.assertEqual(energy_gate(p,"interval"),())
        o=p.observations[1];s=o.samples[2].revised(value_si=None,validity="missing",reason="Not recorded")
        q=p.revised(observations=(p.observations[0],o.revised(samples=o.samples[:2]+(s,))))
        self.assertIn("missing_or_invalid_voltage",energy_gate(q,"interval"))

    def test_current_polarity_is_explicit_and_raw_unchanged(self):
        p=fixture();c=p.channels[1].revised(current_polarity=-1)
        self.assertEqual(normalize(1.,c).value_si,-.001)
        self.assertEqual(p.raw_rows[0].tokens[1],"1")

    def test_complete_branch_needs_evidence_and_supported_intervals(self):
        p=fixture()
        b=Branch(id="b",experiment_id="experiment",interval_ids=("interval",),direction="charge",
                 completeness="complete",provenance=PROV)
        with self.assertRaises(ValidationError):p.revised(branches=(b,))
        b=b.revised(termination_evidence="Synthetic termination")
        p.revised(branches=(b,))
        with self.assertRaises(ValidationError):
            p.revised(branches=(b,),intervals=(p.intervals[0].revised(status="unresolved",reason="Gap"),))

    def test_pair_does_not_guess_missing_branch(self):
        p=fixture();pair=Pair(id="pair",charge_branch="missing",discharge_branch="also-missing",policy="charge_then_discharge",provenance=PROV)
        with self.assertRaises(ValidationError):p.revised(pairs=(pair,))

    def test_pair_cannot_double_count_intervals(self):
        p=fixture()
        a=Branch(id="charge",experiment_id="experiment",interval_ids=("interval",),direction="charge",
                 completeness="partial",provenance=PROV)
        b=a.revised(id="discharge",direction="discharge")
        pair=Pair(id="pair",charge_branch="charge",discharge_branch="discharge",policy="explicit",provenance=PROV)
        with self.assertRaises(ValidationError):p.revised(branches=(a,b),pairs=(pair,))

    def test_uncertainty_and_result_states(self):
        with self.assertRaises(ValidationError):Uncertainty(standard_uncertainty=0.)
        with self.assertRaises(ValidationError):Uncertainty(status="evaluated",standard_uncertainty=1.)
        p=fixture()
        r=Result(id="r",method_id="M01.fixture",method_version="0.1",engine_version="0.1",parser_version="synthetic",
                 metadata_revision="m1",input_digest=p.input_digest(),interval_ids=("interval",),settings=(),
                 status="available",evidence_level="proposed",value=100.,unit="mAh/g",normalization_metadata_id="mass")
        p=p.revised(results=(r,));self.assertTrue(p.result_is_current(r))
        with self.assertRaises(ValidationError):r.revised(status="provisional")
        with self.assertRaises(ValidationError):r.revised(status="failed")
        with self.assertRaises(ValidationError):r.revised(normalization_metadata_id=None)
        # A result is not made experimentally validated by being available.
        self.assertEqual(r.evidence_level,"proposed")

    def test_metadata_changes_invalidate_but_styling_does_not(self):
        p=fixture();before=p.input_digest()
        self.assertEqual(p.revised(display_settings=(Setting(name="color",value="red"),)).input_digest(),before)
        revision=MetadataRevision(id="m2",parent_id="m1",reason="Correct active mass",entries=(p.metadata[0].entries[0].revised(value=12.),))
        q=p.revised(metadata=p.metadata+(revision,),current_metadata_revision="m2")
        self.assertNotEqual(q.input_digest(),before)
        self.assertEqual(q.metadata[0].entries[0].value,10.)

    def test_provisional_result_cannot_use_missing_mass(self):
        p=fixture();entry=p.metadata[0].entries[0].revised(value=None,confirmed=False)
        p=p.revised(metadata=(p.metadata[0].revised(entries=(entry,)),))
        r=Result(id="r",method_id="M01.fixture",method_version="0.1",engine_version="0.1",parser_version="synthetic",
                 metadata_revision="m1",input_digest=p.input_digest(),interval_ids=("interval",),settings=(),
                 status="provisional",evidence_level="proposed",value=100.,unit="mAh/g",normalization_metadata_id="mass",
                 assumptions=("Mass not confirmed",))
        with self.assertRaises(ValidationError):p.revised(results=(r,))

    def test_json_roundtrip_and_version_rejection(self):
        p=fixture();q=Project.model_validate_json(canonical_bytes(p))
        self.assertEqual(p,q);self.assertEqual(p.input_digest(),q.input_digest())
        obj=json.loads(canonical_bytes(p));obj['schema_version']='9.0.0'
        with self.assertRaises(ValidationError):Project.model_validate_json(json.dumps(obj))


class ArchiveTests(unittest.TestCase):
    def test_roundtrip_preserves_archive_and_source_bytes(self):
        p=fixture()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'fixture.ecproj';save(p,{HASH:BLOB},path)
            before=path.read_bytes();q,blobs=load(path)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(blobs[HASH],BLOB);self.assertEqual(p,q)
            self.assertEqual(p.input_digest(),q.input_digest())
            with self.assertRaises(FileExistsError):save(p,{HASH:BLOB},path)
            self.assertEqual(path.read_bytes(),before)

    def test_source_corruption_detected(self):
        p=fixture()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad.ecproj'
            with self.assertRaises(ValueError):save(p,{HASH:BLOB.replace(b'1000',b'9999')},path)
            self.assertFalse(path.exists())
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('project.json',canonical_bytes(p));z.writestr('sources/'+HASH,BLOB.replace(b'1000',b'9999'))
            with self.assertRaises(ValueError):load(path)

    def test_unexpected_members_never_extracted(self):
        p=fixture()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad.ecproj'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('project.json',canonical_bytes(p));z.writestr('sources/'+HASH,BLOB)
                z.writestr('../escape.txt',b'bad')
            with self.assertRaises(ValueError):load(path)
            self.assertEqual(sorted(x.name for x in Path(d).iterdir()),['bad.ecproj'])


if __name__ == '__main__':
    unittest.main()
