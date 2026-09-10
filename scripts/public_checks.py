"""Public fixture import verification. Bundled inputs retain upstream attribution."""
from pathlib import Path
from decimal import Decimal,InvalidOperation
import sys,json,hashlib,tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT)]
from eclab_import.text import parse,Options,Mapping,project_from_text
from electrochem.archive import save,load
manifest=json.loads((ROOT/'data/public/mpt_manifest.json').read_text())
results=[]
for entry in manifest:
 p=ROOT/'data/public'/entry['local_name'].replace('galvani/','mpt/').replace('beep/','mps/');blob=p.read_bytes()
 assert hashlib.sha256(blob).hexdigest()==entry['sha256']
 parsed=parse(blob,p.name,Options(**entry['options']))
 info={**entry,'record_count':len(parsed.rows),'column_count':len(parsed.source.columns),'diagnostic_count':len(parsed.diagnostics),'project_test':'not_applicable_settings'}
 if parsed.source.format!='mps':
  columns=[c.original_name for c in parsed.source.columns]
  selected={}
  for key,choices in [('time',['time/s']),('current',['I/mA','<I>/mA']),('potential',['Ewe/V','Ecell/V','<Ewe>/V'])]:
   indices=[i for i,n in enumerate(columns) if n in choices]
   if len(indices)==1:selected[key]=indices[0]
   elif key=='time':raise ValueError('Public fixture does not have a unique declared time column')
  mapping=Mapping(**selected,evidence='Public lexical/units audit; no wiring or interval support confirmed')
  project,blobs=project_from_text(parsed,blob,mapping)
  assert len(project.observations)==len(parsed.rows)
  invalid={};maxerr={}
  for obs,row in zip(project.observations,parsed.rows):
   for ch,sample in zip(project.channels,obs.samples):
    token=row.fields[ch.column_index]
    try:expected=Decimal(token.replace(parsed.options.decimal,'.'))
    except InvalidOperation:
     assert sample.validity=='invalid';invalid[ch.id]=invalid.get(ch.id,0)+1;continue
    if not expected.is_finite():assert sample.validity=='invalid';continue
    # Independent explicit SI scale for the selected public columns, not core conversion code.
    scale={'s':Decimal(1),'mA':Decimal('0.001'),'V':Decimal(1)}[ch.input_unit]
    expected*=scale
    assert sample.validity=='valid'
    error=abs(Decimal.from_float(sample.value_si)-expected)
    bound=max(Decimal('1e-15'),abs(expected)*Decimal('3e-16'))
    assert error<=bound,(p.name,ch.id,error,bound)
    maxerr[ch.id]=max(maxerr.get(ch.id,Decimal(0)),error)
  assert invalid==entry['expected_invalid_values'],(p.name,invalid,entry['expected_invalid_values'])
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'snapshot.ecproj';save(project,blobs,path);before=path.read_bytes();restored,payloads=load(path)
   assert restored==project and payloads==blobs and path.read_bytes()==before
  info.update(project_test='passed',selected_columns=selected,invalid_values=invalid,max_conversion_error_SI={k:str(v) for k,v in maxerr.items()},interval_support='all unresolved')
 results.append(info)
(ROOT/'docs/evidence/p03_import/public-compatibility.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'public_files':len(results),'measurement_exports':sum(x['project_test']=='passed' for x in results),'settings_files':sum(x['project_test']=='not_applicable_settings' for x in results),'invalid_values':sum(sum(x.get('invalid_values',{}).values()) for x in results)}))
