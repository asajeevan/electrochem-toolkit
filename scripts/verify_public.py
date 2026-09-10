"""Frozen public MPR corpus: byte recovery, independent struct decoding and reopening."""
from pathlib import Path
from decimal import Decimal,InvalidOperation
import sys,struct,hashlib,json,tempfile,platform,math
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT)]
from eclab_import.native import inspect_native,project_from_native
from eclab_import.text import parse,Options,Mapping
from electrochem.archive import load,save
report=[]
manifest={entry['file']:entry['sha256'] for entry in json.loads((ROOT/'data/public/mpr/manifest.json').read_text())}
for path in sorted((ROOT/'data/public/mpr').glob('*.mpr')):
 data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==manifest[path.name]
 t=inspect_native(data,path.name)
 fields=[f.backend_label for f in t.fields];selected={'time':fields.index('time/s')}
 for key,choices in [('current',['I/mA','<I>/mA']),('potential',['Ewe/V'])]:
  matches=[i for i,n in enumerate(fields) if n in choices]
  if len(matches)==1:selected[key]=matches[0]
 p,b=project_from_native(t,data,Mapping(**selected,evidence='Public fixture field mapping; original wiring and support unconfirmed'))
 scalars=0
 for row in t.rows:
  assert data[row.byte_offset:row.byte_offset+t.record_width]==bytes.fromhex(''.join(row.field_hex))
  for f,value in zip(t.fields,row.decoded_text):
   code={'<f8':'<d','<f4':'<f','|u1':'B','<u2':'<H','<u4':'<I','|i1':'b','<i2':'<h','<i4':'<i'}[f.dtype]
   original=struct.unpack_from(code,data,row.byte_offset+f.offset)[0]
   assert float(original)==float(value)
   scalars+=1
 with tempfile.TemporaryDirectory() as d:
  saved=Path(d)/'native.ecproj';save(p,b,saved);before=saved.read_bytes();q,blobs=load(saved)
  assert p==q and blobs==b and saved.read_bytes()==before
 report.append({'file':path.name,'sha256':t.source.sha256,'records':len(t.rows),'data_version':t.data_module_version,'fields':fields,
  'scalar_values_independently_checked':scalars,'modules':len(t.modules),'byte_recovery':'passed','project_reopening':'passed','mapped_indices':selected})
# Compare original binary float values, not their shorter intermediate decimal repr.
def compare_fields(native,text):
 textnames=[c.original_name for c in text.source.columns];checked=[]
 for idx,field in enumerate(native.fields):
  if field.backend_label not in textnames:continue
  ti=textnames.index(field.backend_label);errors=roundtrip=invalid=0;maxerror=Decimal(0);max_ulps=0.
  for nr,tr in zip(native.rows,text.rows):
   try:expected=Decimal(tr.fields[ti])
   except InvalidOperation:invalid+=1;continue
   scalar=float(nr.decoded_text[idx])
   observed=Decimal.from_float(scalar) if 'f' in field.dtype else Decimal(nr.decoded_text[idx])
   allowance=Decimal('0.5')*Decimal(10)**expected.as_tuple().exponent
   error=abs(expected-observed);maxerror=max(maxerror,error)
   if error>allowance:
    errors+=1;roundtrip+=int(float(expected)!=scalar)
    max_ulps=max(max_ulps,abs(float(expected)-scalar)/math.ulp(scalar))
  checked.append({'field':field.backend_label,'compared_rows':min(len(text.rows),len(native.rows)),
   'invalid_export_tokens':invalid,'decimal_bound_failures':errors,'failures_with_binary_roundtrip_mismatch':roundtrip,
   'max_absolute_error_original_unit':str(maxerror),'max_binary64_ulps_among_decimal_failures':max_ulps})
 return checked
comparisons=[]
for entry in report:
 stem=Path(entry['file']).stem
 native=inspect_native((ROOT/'data/public/mpr'/entry['file']).read_bytes(),entry['file'])
 text=parse((ROOT/'data/public/mpt'/f'{stem}.mpt').read_bytes(),f'{stem}.mpt',Options(encoding='cp1252',missing_terminal_empty_field=True))
 comparisons.append({'stem':stem,'binary_rows':len(native.rows),'text_rows':len(text.rows),
  'relation':'equal record counts; compare common labels' if len(native.rows)==len(text.rows) else 'candidate prefix only; not full coverage',
  'fields':compare_fields(native,text)})
result={'adapter_version':'0.1.0','python':platform.python_version(),'platform':platform.platform(),'corpus':report,
 'native_text_comparisons':comparisons,'coverage_note':'bio_logic6 time, control, potential, cycle and counter show prefix correspondence. Export history unknown. Decimal-bound failures retained separately from binary roundtrip checks.'}
(ROOT/'docs/evidence/p03_native/public-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'native_files':len(report),'records':sum(r['records'] for r in report),'scalar_checks':sum(r['scalar_values_independently_checked'] for r in report),'numeric_bound_failures':sum(f['decimal_bound_failures'] for c in comparisons for f in c['fields']),'failures_with_roundtrip_mismatch':sum(f['failures_with_binary_roundtrip_mismatch'] for c in comparisons for f in c['fields'])}))
