"""Independent fixture audit, never a production cycling calculator.
Uses rational midpoint/Simpson quadrature, not M01.N1's coefficient expression.
Run from repository root: python reference/verify.py
"""
from pathlib import Path
from fractions import Fraction as F
import hashlib,json,sys,tempfile,platform
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from electrochem.models import (Source,Column,Channel,Provenance,RowRef,RawRow,Observation,
    Experiment,Interval,Project,MetadataRevision,MetadataValue,Branch,Pair,Setting,normalize,energy_gate)
from electrochem.archive import save,load
from pydantic import ValidationError
checks=[]
def check(name,condition):
    if not condition:raise AssertionError(name)
    checks.append({'name':name,'passed':True})
def quadrature(c,edges=None):
    # All quantities here are synthetic exact fractions; this function is not shipped in the core.
    totals={k:F(0) for k in c['expected']}
    charge_count=energy_count=0
    for edge in c['supported_edges'] if edges is None else edges:
        a,b=c['rows'][edge:edge+2]
        t0,t1=F(a[0]),F(b[0]);h=t1-t0
        if h<=0 or c['blocks'][edge]!=c['blocks'][edge+1]:raise ValueError('Unsupported edge')
        if a[1] is None or b[1] is None:raise ValueError('Missing current on supported edge')
        i0,i1=F(a[1])*c['current_multiplier'],F(b[1])*c['current_multiplier']
        charge_count+=1;totals['supported_duration_s']+=h
        valid_u=c['potential_role']=='terminal' and a[2] is not None and b[2] is not None
        u0,u1=(F(a[2]),F(b[2])) if valid_u else (F(0),F(0))
        energy_count+=int(valid_u)
        def current(x):return i0+(i1-i0)*x
        def power(x):return current(x)*(u0+(u1-u0)*x)
        cuts={F(0),F(1)}
        for start,end in [(i0,i1),(u0,u1)]:
            if end!=start:
                root=-start/(end-start)
                if 0<root<1:cuts.add(root)
        cuts=sorted(cuts)
        for lo,hi in zip(cuts,cuts[1:]):
            mid=(lo+hi)/2;width=h*(hi-lo)
            q=width*current(mid) # midpoint exact for linear current
            w=width*(power(lo)+4*power(mid)+power(hi))/6 # Simpson exact for quadratic power
            totals['signed_charge_C']+=q
            totals['positive_charge_C' if q>=0 else 'negative_charge_C']+=abs(q)
            if valid_u:
                totals['signed_energy_J']+=w
                totals['absorbed_energy_J' if w>=0 else 'delivered_energy_J']+=abs(w)
    if not charge_count:
        for k in ['signed_charge_C','positive_charge_C','negative_charge_C']:totals[k]=None
    if not energy_count:
        for k in ['signed_energy_J','absorbed_energy_J','delivered_energy_J']:totals[k]=None
    return totals

def project(c):
    prov=Provenance(origin='user',evidence='Frozen synthetic definition '+c['id']+'; '+c['derivation'],revision='P02-0.1.0')
    blob=('\t'.join(c['columns'])+'\n'+'\n'.join('\t'.join('' if v is None else v for v in row) for row in c['rows'])+'\n').encode()
    digest=hashlib.sha256(blob).hexdigest()
    source=Source(sha256=digest,byte_size=len(blob),original_name=c['id']+'.synthetic.tsv',format='synthetic',
      columns=tuple(Column(original_name=n,original_unit=u) for n,u in zip(c['columns'],['s','A','V',None,'C'])))
    channels=(Channel(id='t',source_hash=digest,column_index=0,quantity='time',input_unit='s',provenance=prov),
      Channel(id='i',source_hash=digest,column_index=1,quantity='current',input_unit='A',current_polarity=c['current_multiplier'],provenance=prov),
      Channel(id='u',source_hash=digest,column_index=2,quantity='potential',input_unit='V',potential_role=c['potential_role'],
        positive_node='positive' if c['potential_role']=='terminal' else None,
        negative_node='negative' if c['potential_role']=='terminal' else None,provenance=prov))
    refs=tuple(RowRef(source_hash=digest,record_index=k) for k in range(len(c['rows'])))
    obs=tuple(Observation(ref=refs[k],experiment_id='exp',acquisition_order=k,block_id=c['blocks'][k],
      samples=tuple(normalize(None if v is None else float(F(v)),ch) for v,ch in zip(row[:3],channels))) for k,row in enumerate(c['rows']))
    intervals=tuple(Interval(id=f'e{k}',left=refs[k],right=refs[k+1],status='supported' if k in c['supported_edges'] else 'unresolved',
       reason='Explicit synthetic support' if k in c['supported_edges'] else c['excluded_edge_reasons'][str(k)],
       reconstruction='point_linear' if k in c['supported_edges'] else 'none',provenance=prov) for k in range(len(refs)-1))
    terminal=c['potential_role']=='terminal'
    branches=();pairs=()
    if 'pair' in c:
        spec=c['pair']
        branches=tuple(Branch(id=direction,experiment_id='exp',interval_ids=tuple('e'+str(k) for k in spec[direction+'_edges']),
          direction=direction,completeness='complete',termination_evidence='Synthetic exact process endpoints',provenance=prov) for direction in ['charge','discharge'])
        pairs=(Pair(id='pair',charge_branch='charge',discharge_branch='discharge',policy=spec['policy'],provenance=prov),)
    p=Project(id=c['id'],sources=(source,),raw_rows=tuple(RawRow(ref=r,tokens=tuple(row)) for r,row in zip(refs,c['rows'])),
      channels=channels,observations=obs,experiments=(Experiment(id='exp',cell_id='synthetic-cell',configuration=c['configuration'],technique='synthetic_cycling',
      time_channel='t',current_channel='i',voltage_channel='u',passive_current_confirmed=terminal,convention_provenance=prov if terminal else None,clock_tolerance_s=0.),),
      intervals=intervals,branches=branches,pairs=pairs,metadata=(MetadataRevision(id='m1',reason='Synthetic fixture; no implicit mass',entries=()),),current_metadata_revision='m1')
    return p,{digest:blob},prov

def run():
    manifest=json.loads((ROOT/'fixtures/SHA256SUMS.json').read_text())
    for filename,digest in manifest.items():
        check('hash:'+filename,hashlib.sha256((ROOT/'fixtures'/filename).read_bytes()).hexdigest()==digest)
    cases=[json.loads(p.read_text()) for p in sorted((ROOT/'fixtures').glob('S[0-9][0-9].json'))]
    with tempfile.TemporaryDirectory() as temp:
        for c in cases:
            actual=quadrature(c)
            for key,value in c['expected'].items():
                check(c['id']+':exact:'+key,actual[key]==(None if value is None else F(value)))
            p,blobs,prov=project(c)
            check(c['id']+':raw_tokens',tuple(r.tokens for r in p.raw_rows)==tuple(tuple(r) for r in c['rows']))
            path=Path(temp)/(c['id']+'.ecproj');save(p,blobs,path)
            before=path.read_bytes();reopened,payload=load(path)
            check(c['id']+':reopen',reopened==p and payload==blobs and path.read_bytes()==before and reopened.input_digest()==p.input_digest())
            for edge in c['supported_edges']:
                should_block=c['potential_role']!='terminal' or any(c['rows'][j][2] is None for j in [edge,edge+1])
                check(c['id']+f':energy_gate:{edge}',bool(energy_gate(p,'e'+str(edge)))==should_block)
            if c['id'] in ['S08','S09']:
                iv=p.intervals[1].revised(status='supported',reconstruction='point_linear')
                try:p.revised(intervals=(p.intervals[0],iv,p.intervals[2]))
                except ValidationError:rejected=True
                else:rejected=False
                check(c['id']+':bridge_rejected',rejected)
            if 'display_row_indices' in c:
                view=p.revised(display_settings=(Setting(name='display_row_indices',value='0,2'),))
                check(c['id']+':display_does_not_change_input',view.input_digest()==p.input_digest() and view.observations==p.observations)
                check(c['id']+':display_only_integration_detected',F(c['wrong_display_only_charge_C'])!=actual['signed_charge_C'])
            for norm in c.get('normalization_cases',[]):
                v=norm['value']
                try:MetadataValue(id='denominator',scope_id='positive-electrode',kind=norm['basis'],value=None if v is None else float(F(v)),unit=norm['unit'],confirmed=v is not None,provenance=prov)
                except ValidationError:rejected=True
                else:rejected=False
                check(c['id']+':metadata:'+str(norm),rejected==(norm.get('blocked')=='invalid_denominator'))
                if 'blocked' not in norm:
                    mah=actual['positive_charge_C']/F('3.6')
                    if norm['unit']=='mg':value=mah/(F(v)/1000);expected=norm['expected_mAh_g']
                    else:value=mah/F(v);expected=norm['expected_mAh_cm2']
                    check(c['id']+':normalization:'+norm['basis'],value==F(expected))
            for part in c.get('components',[]):
                check(c['id']+':component:'+part['name'],quadrature(c,part['edges'])['positive_charge_C']==F(part['charge_C']))
            if 'pair' in c:
                pair=c['pair'];ch=quadrature(c,pair['charge_edges']);dis=quadrature(c,pair['discharge_edges'])
                check(c['id']+':CE',dis['negative_charge_C']/ch['positive_charge_C']==F(pair['CE_fraction']))
                check(c['id']+':energy_ratio',dis['delivered_energy_J']/ch['absorbed_energy_J']==F(pair['energy_efficiency_fraction']))
    policy=json.loads((ROOT/'fixtures/policies.json').read_text())
    r=policy['retention'];ref=F(r['discharge_C'][r['reference_index']])
    check('policy:retention_explicit_reference',[F(v)/ref for v in r['discharge_C']]==[F(v) for v in r['expected_fraction']])
    ov=policy['over_unity_CE'];check('policy:over_unity_arithmetic',F(ov['discharge_C'])/F(ov['charge_C'])==F(ov['expected_fraction'])>1)
    shared=policy['shared_mass']
    for mass in [F('0.009'),F('0.010'),F('0.011')]:
        check('policy:common_mass_cancellation:'+str(mass),(F(shared['discharge_C'])/mass)/(F(shared['charge_C'])/mass)==F(shared['expected_CE_fraction']))
    # Deliberate wrong candidates must disagree with the frozen fixture, with no permissive tolerance.
    by={c['id']:c for c in cases}
    check('mutation:power_trapezoid_detected',F(by['S02']['alternative_sampled_power_J'])!=F(by['S02']['expected']['signed_energy_J']))
    check('mutation:net_absolute_hides_reversal',abs(F(by['S03']['expected']['signed_charge_C']))!=F('1'))
    check('mutation:gap_bridge_detected',F('11')!=F(by['S07']['expected']['signed_charge_C']))
    result={'package':'P02','version':'0.1.0','python':platform.python_version(),'platform':platform.platform(),
      'observation_fixtures':len(cases),'passed_checks':len(checks),'checks':checks,
      'evidence_scope':'Exact reference arithmetic and P01 contract/reopening tests. Recipe diagnostic strings are specified, not executed by a production analysis engine.',
      'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (ROOT.parent/'docs/evidence/p02_reference/verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f"PASS: {len(cases)} observation fixtures; {len(checks)} checks. No experimental validation.")
if __name__=='__main__':run()
