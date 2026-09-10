"""Read-only evaluation of an external galvani checkout; not a runtime dependency.
Usage: python scripts/native_probe.py /path/to/galvani
"""
from pathlib import Path
from decimal import Decimal,InvalidOperation
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),sys.argv[1]]
from eclab_import.text import parse,Options
from galvani import BioLogic
import numpy as np
repository=Path(sys.argv[1]);base=repository/'tests/testdata';results=[]
for stem in ['bio_logic1','bio_logic2','bio_logic4','bio_logic5','bio_logic6']:
 textfile=base/(stem+'.mpt');binary=base/(stem+'.mpr')
 text=parse(textfile.read_bytes(),textfile.name,Options(encoding='cp1252'))
 native=BioLogic.MPRfile(str(binary));names=[c.original_name for c in text.source.columns]
 item={'stem':stem,'mpt_sha256':text.source.sha256,'mpr_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'text_rows':len(text.rows),'native_rows':len(native.data),'columns':[]}
 if len(text.rows)!=len(native.data):
  item['alignment']='row_count_mismatch; no pointwise comparison';results.append(item);continue
 for ascii_name,binary_name in [('time/s','time/s'),('Ewe/V','Ewe/V'),('<I>/mA','I/mA'),('I/mA','I/mA'),('dq/mA.h','dQ/mA.h'),('dq/mA.h','dq/mA.h'),('dQ/mA.h','dQ/mA.h')]:
  if ascii_name not in names or binary_name not in native.data.dtype.names:continue
  idx=names.index(ascii_name);failures=[];invalid=[];roundtrip_mismatches=0;maxerror=Decimal(0)
  if len(text.rows)!=len(native.data):raise ValueError('Row counts differ; cannot align by row')
  for row,(raw,value) in enumerate(zip(text.rows,native.data[binary_name])):
   try:exported=Decimal(raw.fields[idx])
   except InvalidOperation:
    invalid.append(row);continue
   observed=Decimal.from_float(float(value));error=abs(exported-observed)
   # Nearest rounding to the last decimal digit explicitly printed by this export.
   allowance=Decimal('0.5')*Decimal(10)**exported.as_tuple().exponent
   if error>allowance:
    failures.append(row)
    roundtrip_mismatches+=int(float(exported)!=float(value))
   maxerror=max(maxerror,error)
  item['columns'].append({'text_column':ascii_name,'native_column':binary_name,'max_absolute_error_original_unit':str(maxerror),'rounding_bound_failures':len(failures),'first_failure_rows':failures[:5],'invalid_text_rows':invalid,'rounding_failures_with_binary_roundtrip_mismatch':roundtrip_mismatches})
 for name in ['mode','ox/red','error','control changes','Ns changes','counter inc.']:
  if name in names:
   values=native.get_flag(name);idx=names.index(name)
   mismatches=sum(int(Decimal(raw.fields[idx]))!=int(v) for raw,v in zip(text.rows,values))
   item['columns'].append({'flag':name,'exact_mismatches':mismatches})
 results.append(item)
report={'scope':'Read-only public paired-file comparison; native library not integrated','numpy':np.__version__,'galvani_git_commit':'d4a5f444b16eae57d2edfad6df774ead95c92fd6','criterion':'Exact flag equality; numeric error at most half the last printed decimal digit. Discrepancies retained, never widen tolerance automatically.','pairs':results}
(ROOT/'docs/evidence/p03_import/native-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'pairs':len(results),'numeric_rounding_failures':sum(c.get('rounding_bound_failures',0) for r in results for c in r['columns']),'invalid_text_tokens':sum(len(c.get('invalid_text_rows',[])) for r in results for c in r['columns']),'flag_mismatches':sum(c.get('exact_mismatches',0) for r in results for c in r['columns'])}))
