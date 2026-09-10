import unittest,sys,json,tempfile,hashlib,struct,os,subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT)]
from eclab_import.native import inspect_native,project_from_native,backend
from eclab_import.text import Mapping,ImportFailure,Options
from eclab_import.linkage import link_settings
from electrochem.archive import save,load
DATA=ROOT/'data/public/mpr/bio_logic5.mpr'
class NativeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=DATA.read_bytes();cls.table=inspect_native(cls.data,DATA.name)
  fields=[f.backend_label for f in cls.table.fields]
  cls.mapping=Mapping(time=fields.index('time/s'),current=fields.index('I/mA'),potential=fields.index('Ewe/V'),evidence='Explicit public fixture mapping; no wiring inference')
 def fixture(self):return project_from_native(self.table,self.data,self.mapping)
 def test_exact_binary_record_provenance(self):
  t=self.table
  for row in t.rows:
   self.assertEqual(bytes.fromhex(''.join(row.field_hex)),self.data[row.byte_offset:row.byte_offset+t.record_width])
  self.assertEqual(t.source.sha256,hashlib.sha256(self.data).hexdigest());self.assertTrue(t.encoded_column_ids)
 def test_independent_struct_decode(self):
  t=self.table
  for row in t.rows:
   for field,token in zip(t.fields,row.decoded_text):
    code={'<f8':'<d','<f4':'<f','|u1':'B','<u2':'<H','<u4':'<I'}[field.dtype]
    actual=struct.unpack_from(code,self.data,row.byte_offset+field.offset)[0]
    self.assertEqual(float(token),float(actual))
 def test_module_payload_hashes_and_flags_retained(self):
  t=self.table
  self.assertTrue(t.flags)
  for m in t.modules:self.assertEqual(m.payload_sha256,hashlib.sha256(self.data[m.payload_offset:m.payload_offset+m.payload_length]).hexdigest())
 def test_no_source_names_invented(self):
  self.assertTrue(all(c.original_name.startswith('encoded_field_') and c.original_unit is None for c in self.table.source.columns))
 def test_projection_preserves_hex_and_unresolved_support(self):
  p,b=self.fixture();self.assertEqual(p.raw_rows[0].tokens,self.table.rows[0].field_hex)
  self.assertTrue(all(i.status=='unresolved' for i in p.intervals));self.assertTrue(all(o.absolute_time is None for o in p.observations))
  self.assertIsNone(p.channels[1].current_polarity)
 def test_reopen_without_backend_or_original_path(self):
  p,b=self.fixture()
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'p.ecproj';save(p,b,path);before=path.read_bytes()
   with patch('eclab_import.native.backend',side_effect=AssertionError('Backend should not load')):q,blobs=load(path)
   self.assertEqual(p,q);self.assertEqual(b,blobs);self.assertEqual(path.read_bytes(),before)
 def test_tampered_decoding_rejected(self):
  row=self.table.rows[0].revised(decoded_text=tuple('0' for f in self.table.fields));tampered=self.table.revised(rows=(row,)+self.table.rows[1:])
  with self.assertRaisesRegex(ImportFailure,'native_source_mismatch'):project_from_native(tampered,self.data,self.mapping)
 def test_wrong_magic_truncation_and_trailing_bytes(self):
  for data in [b'bad',self.data[:-1],self.data+b'junk']:
   with self.subTest(size=len(data)),self.assertRaises(ImportFailure):inspect_native(data,'x.mpr')
 def test_unknown_data_version_rejected(self):
  mod,np=backend();offset=len(mod.MPR_MAGIC)
  payload=next(m for m in self.table.modules if bytes.fromhex(m.name_hex)==b'VMP data  ')
  # Locate header from backend's exported dtype, independent of its data decoder.
  start=payload.payload_offset-mod.VMPmodule_hdr_v1.itemsize
  version_offset=mod.VMPmodule_hdr_v1.fields['version'][1]
  data=bytearray(self.data);struct.pack_into('<I',data,start+version_offset,99)
  with self.assertRaises(ImportFailure):inspect_native(bytes(data),'x.mpr')
 def test_unknown_column_id_rejected_without_heuristics(self):
  dm=next(m for m in self.table.modules if bytes.fromhex(m.name_hex)==b'VMP data  ')
  self.assertEqual(dm.version,2)
  data=bytearray(self.data);struct.pack_into('<H',data,dm.payload_offset+5,65535)
  with self.assertRaises(ImportFailure):inspect_native(bytes(data),'x.mpr')
 def test_declared_record_count_mismatch(self):
  dm=next(m for m in self.table.modules if bytes.fromhex(m.name_hex)==b'VMP data  ')
  data=bytearray(self.data);struct.pack_into('<I',data,dm.payload_offset,len(self.table.rows)+1)
  with self.assertRaises(ImportFailure):inspect_native(bytes(data),'x.mpr')
 def test_backend_fingerprint_gate(self):
  with patch('eclab_import.native.BACKEND_HASHES',{'BioLogic.py':'0'*64}):
   with self.assertRaisesRegex(ImportFailure,'native_backend_unverified'):inspect_native(self.data,'x.mpr')
 def test_native_nonfinite_preserved_as_invalid(self):
  field=self.table.fields[self.mapping.current];pos=self.table.rows[0].byte_offset+field.offset
  data=bytearray(self.data);struct.pack_into('<f' if field.width==4 else '<d',data,pos,float('nan'))
  t=inspect_native(bytes(data),'nonfinite.mpr');p,b=project_from_native(t,bytes(data),self.mapping)
  self.assertEqual(p.observations[0].samples[1].validity,'invalid');self.assertEqual(p.raw_rows[0].tokens[self.mapping.current],bytes(data[pos:pos+field.width]).hex())
 def test_sidecars_never_loaded_implicitly(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'source_LOOP.txt').write_text('CORRUPT SIDECAR')
   Path(d,'source.mpl').write_text('CORRUPT SIDECAR')
   old=os.getcwd()
   try:
    os.chdir(d);t=inspect_native(self.data,DATA.name)
   finally:os.chdir(old)
   self.assertEqual(t,self.table)
 def test_existing_text_cli_export_remains_independent(self):
  env=dict(os.environ);env.pop('PYTHONPATH',None)
  with tempfile.TemporaryDirectory() as d:
   output=Path(d)/'text.ecproj'
   cmd=[sys.executable,'-m','eclab_import','data/examples/synthetic.mpt','--mapping','data/examples/mapping.json','--output',str(output)]
   result=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr);p,b=load(output);self.assertEqual(len(p.observations),2)
 def test_numpy_version_gate(self):
  import numpy
  with patch.object(numpy,'__version__','0.0-unverified'):
   with self.assertRaisesRegex(ImportFailure,'native_numpy_unverified'):inspect_native(self.data,'x.mpr')
 def test_settings_link_is_explicit_and_not_measurements(self):
  p,b=self.fixture();settings=b'EC-LAB SETTING FILE\nTechnique : 1\nGCPL\nMass : 5 mg\n'
  q,out=link_settings(p,b,settings,'settings.mps',experiment_ids=('imported-experiment',),evidence='Synthetic link acceptance test')
  self.assertEqual(q.observations,p.observations);self.assertNotEqual(q.input_digest(),p.input_digest())
  self.assertEqual(q.metadata[-1].entries,());self.assertIn(settings,out.values())
  again,blobs=link_settings(q,out,settings,'settings.mps',experiment_ids=('imported-experiment',),evidence='Synthetic link acceptance test')
  self.assertEqual(again,q);self.assertEqual(blobs,out)
 def test_link_target_evidence_and_source_corruption(self):
  p,b=self.fixture();settings=b'EC-LAB SETTING FILE\n'
  for ids,evidence in [((),'review'),(('missing',),'review'),(('imported-experiment',),'')]:
   with self.assertRaises(ImportFailure):link_settings(p,b,settings,'s.mps',experiment_ids=ids,evidence=evidence)
  broken={**b,p.sources[0].sha256:b'bad'}
  with self.assertRaises(ImportFailure):link_settings(p,broken,settings,'s.mps',experiment_ids=('imported-experiment',),evidence='review')
 def test_nonsettings_cannot_be_linked(self):
  p,b=self.fixture()
  with self.assertRaises(ImportFailure):link_settings(p,b,b'EC-Lab ASCII FILE\nNb header lines : 3\ntime/s\tI/mA\n0\t1\n','s.mpt',experiment_ids=('imported-experiment',),evidence='review')
if __name__=='__main__':unittest.main()
