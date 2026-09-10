import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eclab_import.text import parse,project_from_text,numeric,Options,Mapping,ImportFailure
from electrochem.archive import load,save
from electrochem.models import energy_gate
from pydantic import ValidationError
BASE=b'EC-Lab ASCII FILE\r\nNb header lines : 5\r\n\r\nGalvanostatic Cycling with Potential Limitation\r\ntime/s\tI/mA\tEwe/V\terror\tNs\tcycle number\r\n0\t1\t3\t0\t0\t1\r\n1\t-1\t3.1\tOVERFLOW\t1\t1\r\n'
MAP=Mapping(time=0,current=1,potential=2,native_step=4,native_cycle=5,evidence='Explicit synthetic column review')
class TextTests(unittest.TestCase):
 def test_header_count_line_refs_and_raw(self):
  p=parse(BASE,'x.mpt');self.assertEqual(p.column_line,5);self.assertEqual([r.line_number for r in p.rows],[6,7]);self.assertEqual(p.rows[1].fields[3],'OVERFLOW');self.assertEqual(p.source.sha256,hashlib.sha256(BASE).hexdigest())
 def test_lexical_unknown_duplicate_columns(self):
  p=parse(BASE.replace(b'Ewe/V',b'I/mA').replace(b'error',b'vendor/unknown'),'x.mpt');self.assertEqual(p.source.columns[1],p.source.columns[2]);self.assertEqual(p.source.columns[3].original_unit,'unknown')
 def test_headerless_requires_explicit_mode(self):
  data=b'time/s\tI/mA\n0\t1\n'
  with self.assertRaises(ImportFailure):parse(data,'x.mpt')
  self.assertEqual(len(parse(data,'x.mpt',Options(headerless=True)).rows),1)
  with self.assertRaises(ImportFailure):parse(BASE,'x.mpt',Options(headerless=True))
 def test_no_silent_legacy_encoding(self):
  data=BASE.replace(b'error',b'Temperature/\xb0C')
  with self.assertRaises(ImportFailure):parse(data,'x.mpt')
  self.assertEqual(parse(data,'x.mpt',Options(encoding='cp1252')).source.columns[3].original_unit,'°C')
 def test_bom_and_lf(self):
  self.assertEqual(parse(b'\xef\xbb\xbf'+BASE.replace(b'\r\n',b'\n'),'x.mpt').rows,parse(BASE,'x.mpt').rows)
 def test_bad_header_counts(self):
  for count in [b'0',b'2',b'999',b'-1',b'3.5']:
   with self.subTest(count=count),self.assertRaises(ImportFailure):parse(BASE.replace(b': 5',b': '+count),'x.mpt')
 def test_malformed_rows_never_skipped(self):
  for data in [BASE+b'\r\n',BASE.replace(b'\tOVERFLOW\t',b'\t'),BASE+b'1\t2\n']:
   with self.subTest(data=data[-20:]),self.assertRaises(ImportFailure):parse(data,'x.mpt')
 def test_explicit_absent_trailing_empty_column(self):
  data=b'EC-Lab ASCII FILE\nNb header lines : 3\ntime/s\tI/mA\t\n0\t1\n'
  with self.assertRaises(ImportFailure):parse(data,'x.mpt')
  p=parse(data,'x.mpt',Options(missing_terminal_empty_field=True));q,blobs=project_from_text(p,data,Mapping(time=0,current=1,evidence='Reviewed trailing field convention'))
  self.assertEqual(p.rows[0].fields,('0','1'));self.assertIsNone(q.raw_rows[0].tokens[-1]);self.assertTrue(p.diagnostics)
 def test_missing_and_invalid_numbers_not_zero(self):
  data=BASE.replace(b'0\t1\t3\t0',b'0\t\tNaN\t0');q,_=project_from_text(parse(data,'x.mpt'),data,MAP)
  self.assertEqual(q.observations[0].samples[1].validity,'missing');self.assertEqual(q.observations[0].samples[2].validity,'invalid');self.assertIsNone(q.observations[0].samples[2].value_si)
 def test_explicit_decimal_comma(self):
  data=BASE.replace(b'0\t1\t3\t0',b'0\t1,5\t3\t0')
  a,_=project_from_text(parse(data,'x.mpt'),data,MAP);b,_=project_from_text(parse(data,'x.mpt',Options(decimal=',')),data,MAP)
  self.assertEqual(a.observations[0].samples[1].validity,'invalid');self.assertEqual(b.observations[0].samples[1].value_si,.0015)
 def test_grouping_overflow_underflow_rejected(self):
  for token in [b'1,000.2',b'1e999',b'1e-999',b'1e-322',b'inf',b'--1']:
   data=BASE.replace(b'0\t1\t3\t0',b'0\t'+token+b'\t3\t0');q,_=project_from_text(parse(data,'x.mpt'),data,MAP)
   self.assertEqual(q.observations[0].samples[1].validity,'invalid')
 def test_current_raw_sign_is_not_guessed(self):
  q,_=project_from_text(parse(BASE,'x.mpt'),BASE,MAP);self.assertIsNone(q.channels[1].current_polarity);self.assertEqual(q.observations[1].samples[1].value_si,-.001)
  r,_=project_from_text(parse(BASE,'x.mpt'),BASE,MAP.revised(current_multiplier=-1));self.assertEqual(r.observations[1].samples[1].value_si,.001);self.assertEqual(r.raw_rows[1].tokens[1],'-1')
 def test_no_intervals_qualified_or_absolute_time_inferred(self):
  q,_=project_from_text(parse(BASE,'x.mpt'),BASE,MAP)
  self.assertTrue(all(i.status=='unresolved' for i in q.intervals));self.assertTrue(all(o.absolute_time is None for o in q.observations));self.assertTrue(energy_gate(q,'edge-0'))
 def test_reset_and_duplicate_rows_preserved(self):
  for t in [b'0',b'-1']:
   data=BASE.replace(b'\r\n1\t-1',b'\r\n'+t+b'\t-1');q,_=project_from_text(parse(data,'x.mpt'),data,MAP)
   self.assertEqual(len(q.observations),2);self.assertEqual(q.observations[1].samples[0].value_si,float(t));self.assertEqual(q.intervals[0].status,'unresolved')
 def test_absolute_timestamp_not_seconds(self):
  data=BASE.replace(b'0\t1\t3\t0',b'05/13/2024 11:00:00\t1\t3\t0');q,_=project_from_text(parse(data,'x.mpt'),data,MAP)
  self.assertEqual(q.observations[0].samples[0].validity,'invalid')
 def test_mps_is_context_only(self):
  data=b'EC-LAB SETTING FILE\nNumber of linked techniques : 2\nTechnique : 1\nGCPL\n';p=parse(data,'x.mps');self.assertEqual(p.source.format,'mps');self.assertEqual(p.rows,());self.assertEqual(len(p.header),4)
  with self.assertRaises(ImportFailure):project_from_text(p,data,MAP)
 def test_native_mpr_explicitly_gated(self):
  for data,name in [(b'BIO-LOGIC MODULAR FILE'+bytes(40),'x.bin'),(BASE,'x.mpr')]:
   with self.assertRaisesRegex(ImportFailure,'native_mpr_not_enabled'):parse(data,name)
 def test_bad_mapping_and_units(self):
  for m in [MAP.revised(time=100),MAP.revised(time=1),MAP.revised(time=3)]:
   with self.subTest(m=m),self.assertRaises((ImportFailure,ValidationError)):project_from_text(parse(BASE,'x.mpt'),BASE,m)
 def test_parsed_record_tampering_detected(self):
  p=parse(BASE,'x.mpt');row=p.rows[0].revised(fields=('0','99','3','0','0','1'))
  with self.assertRaisesRegex(ImportFailure,'source_mismatch'):project_from_text(p.revised(rows=(row,p.rows[1])),BASE,MAP)
 def test_project_reopens_source_and_import_settings(self):
  p=parse(BASE,'x.mpt');q,blobs=project_from_text(p,BASE,MAP)
  with tempfile.TemporaryDirectory() as d:
   target=Path(d)/'p.ecproj';save(q,blobs,target);before=target.read_bytes();r,b=load(target)
   self.assertEqual(q,r);self.assertEqual(b[p.source.sha256],BASE);self.assertEqual(target.read_bytes(),before)
   context=json.loads(b[q.sources[1].sha256]);self.assertEqual(context['parsed']['rows'][1]['line_number'],7);self.assertEqual(context['mapping']['evidence'],MAP.evidence)
 def test_settings_signature_and_nul_rejected(self):
  for data,name in [(BASE,'x.mps'),(BASE+b'\x00','x.mpt')]:
   with self.assertRaises(ImportFailure):parse(data,name)
 def test_empty_table_is_inspectable(self):
  data=b'EC-Lab ASCII FILE\nNb header lines : 3\ntime/s\tI/mA\n';p=parse(data,'x.mpt');self.assertIn('no_observations',p.diagnostics)
 def test_no_automatic_normalized_current_mapping(self):
  data=BASE.replace(b'I/mA',b'I/mA/g')
  with self.assertRaises(ValidationError):project_from_text(parse(data,'x.mpt'),data,MAP)
if __name__=='__main__':unittest.main()
