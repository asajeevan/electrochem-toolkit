"""Author frozen synthetic fixtures. Expected values are explicit independent references.
Never invoke from the verifier or update expectations to accommodate a calculator.
"""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).parent
cases=[]
def add(id, title, rows, support, expected, derivation, **extra):
    case=dict(id=id,title=title,version='0.1.0',method='M01 v0.1',
      columns=['time/s','I/A','U/V','native_flag','counter/C'],
      rows=[[str(t),None if i is None else str(i),None if u is None else str(u),'synthetic',None] for t,i,u in rows],
      blocks=['b1']*len(rows),supported_edges=support,
      excluded_edge_reasons={str(i):'Unresolved temporal support; do not reconstruct' for i in range(len(rows)-1) if i not in support},
      current_multiplier=1,potential_role='terminal',configuration='full_cell',
      interpolation='point_linear',completeness='complete',
      uncertainty={'status':'not_evaluated','standard_uncertainty':None},
      expected=expected,derivation=derivation,
      blocked_outputs={},**{})
    case.update(extra);cases.append(case)
def e(q,qi,qo,w,wi,wo,duration):
    return dict(signed_charge_C=q,positive_charge_C=qi,negative_charge_C=qo,
      signed_energy_J=w,absorbed_energy_J=wi,delivered_energy_J=wo,supported_duration_s=duration)
add('S01','Constant current and normalization',[(0,'.001',3),(3600,'.001',3)],[0],e('18/5','18/5','0','54/5','54/5','0','3600'),
    'Rectangle: 1 mA for 1 h = 1 mAh = 18/5 C; terminal work = 3 V times charge.',
    normalization_cases=[{'basis':'active_mass','value':'10','unit':'mg','expected_mAh_g':'100'},
      {'basis':'composite_mass','value':'20','unit':'mg','expected_mAh_g':'50'},
      {'basis':'cell_mass','value':'1000','unit':'mg','expected_mAh_g':'1'},
      {'basis':'geometric_area','value':'2','unit':'cm^2','expected_mAh_cm2':'1/2'},
      {'basis':'active_mass','value':None,'unit':'mg','blocked':'missing_mass'},
      {'basis':'active_mass','value':'0','unit':'mg','blocked':'invalid_denominator'},
      {'basis':'active_mass','value':'-1','unit':'mg','blocked':'invalid_denominator'}])
add('S02','Linear voltage and current; corrected M01 benchmark',[(0,1,2),(2,3,4)],[0],e('4','4','0','38/3','38/3','0','2'),
    'I=1+t; U=2+t. Integrate 2+3t+t^2 over [0,2]: 4+6+8/3=38/3 J. Endpoint-power trapezoid is 14 J, larger by 4/3 J. Earlier draft 50/3 is erroneous.',alternative_sampled_power_J='14')
add('S03','Resolved smooth current reversal',[(0,-1,3),(2,1,3)],[0],e('0','1/2','1/2','0','3/2','3/2','2'),
    'I=t-1 crosses at 1 s. Two unit-base, unit-height current triangles each have area 1/2 C. Throughput is 1 C, not abs(net charge).',
    blocked_outputs={'single_named_branch_capacity':'must_split_current_reversal'})
add('S04','Terminal power sign reversal with constant current',[(0,1,-1),(2,1,1)],[0],e('2','2','0','0','1/2','1/2','2'),
    'U=t-1, I=1. Separate positive and negative unit triangles of power. Charge does not reverse.',
    blocked_outputs={'single_mean_directional_voltage':'mixed_power_polarity'})
add('S05','CC plus complete constant-voltage tail',[(0,'.002',3),(1,'.002',4),(3,'.001',4),(4,0,4)],[0,1,2],e('11/2000','11/2000','0','21/1000','21/1000','0','4'),
    'CC rectangle=2 mC. Tail trapezoids=3+0.5 mC. CC work=7 mJ; tail work=12+2 mJ.',
    components=[{'name':'constant_current','edges':[0],'charge_C':'1/500'}, {'name':'constant_voltage','edges':[1,2],'charge_C':'7/2000'}])
add('S06','Rest with measured nonzero current',[(0,'.000001',3),(10,'.000001',3)],[0],e('1/100000','1/100000','0','3/100000','3/100000','0','10'),
    'Recorded 1 microampere for 10 seconds passes 10 microcoulombs. A rest label cannot silently zero a valid measurement.',protocol_label='rest')
add('S07','Unexplained recording gap',[(0,1,3),(1,1,3),(10,1,3),(11,1,3)],[0,2],e('2','2','0','6','6','0','2'),
    'Only two known 1-second rectangles count. Nine seconds are unresolved; no implied zero current there.',completeness='partial',unknown_duration_s='9',blocked_outputs={'full_branch_capacity':'unresolved_interval'})
add('S08','Interrupted run and local clock reset',[(0,1,3),(1,1,3),(0,1,3),(1,1,3)],[0,2],e('2','2','0','6','6','0','2'),
    'Two independently supported, nonoverlapping 1-second acquisition blocks. Interruption duration is unknown; no absolute time fabricated.',blocks=['b1','b1','b2','b2'],completeness='partial',unknown_duration_s=None,blocked_outputs={'full_branch_capacity':'time_reset'})
add('S09','Documented same-time step endpoints',[(0,1,3),(1,1,3),(1,-1,3),(2,-1,3)],[0,2],e('0','1','1','0','3','3','2'),
    'Left endpoint ends +1 A step; right endpoint starts -1 A step at same local time. Separate one-second rectangles; no bridge or duplicate duration.',
    excluded_edge_reasons={'1':'Documented zero-duration programmed discontinuity; distinct left/right values'})
add('S10','Unexplained sign change across a programmed boundary',[(0,1,3),(1,-1,3)],[],e(None,None,None,None,None,None,'0'),
    'Endpoint semantics unresolved. No supported charge or energy integral; null is not zero.',completeness='unknown',blocked_outputs={'observed_charge':'unresolved_interval','energy':'unresolved_interval'})
add('S11','Missing current',[(0,1,3),(1,None,3),(2,1,3)],[],e(None,None,None,None,None,None,'0'),
    'Both intervals touch a missing measured current. Neither has charge support. No interpolation across missing data.',completeness='partial',blocked_outputs={'observed_charge':'missing_current','energy':'missing_current'})
add('S12','Missing voltage leaves charge available',[(0,1,None),(2,1,None)],[0],e('2','2','0',None,None,None,'2'),
    'Current rectangle is 2 C. No terminal energy can be obtained without voltage.',blocked_outputs={'energy':'missing_terminal_voltage'})
add('S13','Unresolved Ewe channel',[(0,1,3),(2,1,3)],[0],e('2','2','0',None,None,None,'2'),
    'Current rectangle is 2 C. Numerical potential values alone do not establish terminal voltage.',potential_role='unresolved',configuration='unknown',blocked_outputs={'energy':'missing_terminal_voltage','named_charge_discharge':'ambiguous_current_convention'})
add('S14','Sparse but confirmed continuous recording',[(0,'.001',3),(10000,'.001',3)],[0],e('10','10','0','30','30','0','10000'),
    'Synthetic signal explicitly constant over 10000 s. Long sampling interval alone is not proof of a gap.')
add('S15','Interrupted constant-voltage tail',[(0,'.002',3),(1,'.002',4),(3,'.001',4),(4,0,4)],[0,1,2],e('11/2000','11/2000','0','21/1000','21/1000','0','4'),
    'Observed signal is S05, but no intended termination is established; zero endpoint alone does not establish completion.',completeness='partial',blocked_outputs={'full_cycle_CE':'incomplete_branch'})
add('S16','First recorded branch is discharge',[(0,-1,3),(1,-1,3)],[0],e('-1','0','1','-3','0','3','1'),
    'One-second negative rectangle: discharge magnitude 1 C. No charge branch exists for pairing.',blocked_outputs={'full_cycle_CE':'missing_pair'})
add('S17','Instrument counter reset',[(0,1,3),(1,1,3),(2,1,3)],[0,1],e('2','2','0','6','6','0','2'),
    'Measured-current reconstruction is 2 C. Counter [0,1,0] cannot use final minus initial without reset semantics.',counter_tokens=['0','1','0'],blocked_outputs={'instrument_counter_increment':'unknown_counter_semantics'})
add('S18','Nonuniform sampling of linear current',[(0,0,3),('.5','.5',3),(2,2,3)],[0,1],e('2','2','0','6','6','0','2'),
    'I=t on [0,2]. Triangle area=2 C irrespective of interior sample at 0.5 s. Uniform-grid assumption would fail.')
add('S19','Explicit complete charge-discharge pair',[(0,1,3),(1,1,3),(1,'-.9',3),(2,'-.9',3)],[0,2],e('1/10','1','9/10','3/10','3','27/10','2'),
    'Charge rectangle 1 C; discharge rectangle 0.9 C. Explicit complete pair gives CE=9/10, energy ratio=9/10.',
    pair={'charge_edges':[0],'discharge_edges':[2],'policy':'charge_then_discharge','complete':True,'CE_fraction':'9/10','energy_efficiency_fraction':'9/10'})
add('S20','Explicit inverted instrument current convention',[(0,'-.001',3),(3600,'-.001',3)],[0],e('18/5','18/5','0','54/5','54/5','0','3600'),
    'Raw negative current maps with documented multiplier -1 to positive terminal current. Raw tokens remain unchanged.',current_multiplier=-1)
add('S21','Display decimation must not change numerical support',[(0,0,3),(1,1,3),(2,0,3)],[0,1],e('1','1','0','3','3','0','2'),
    'Two half-coulomb triangles give 1 C on full-resolution observations. Keeping only display endpoints would falsely give zero.',display_row_indices=[0,2],wrong_display_only_charge_C='0')
for case in cases:
    if 'counter_tokens' in case:
        for row,token in zip(case['rows'],case['counter_tokens']):row[4]=token
    case['tolerance']={'reference':'exact rational equality', 'future_float_absolute_floor_SI':'1e-14',
      'future_float_relative':'1e-12','rationale':'Small exact rational fixtures; allowance for binary arithmetic only, not experimental/model uncertainty.'}
    (ROOT/'fixtures'/f"{case['id']}.json").write_text(json.dumps(case,indent=2)+'\n')
policy={'version':'0.1.0','evidence':'Expected scientific policies only; no production recipe implementation.',
 'retention':{'discharge_C':['8','10','9'],'formation':[True,False,False],'reference_index':1,'expected_fraction':['4/5','1','9/10'],
   'exclude_reference_behavior':'incompatible_reference; never silently select another cycle'},
 'over_unity_CE':{'charge_C':'1','discharge_C':'11/10','expected_fraction':'11/10','behavior':'retain value with review, never clip'},
 'zero_charge_denominator':{'charge_C':'0','discharge_C':'1','status':'invalid_denominator','expected':None},
 'cell_configuration':{'symmetric':'directional charge only; no default battery CE','blocking':'passed charge only; no automatic battery-capacity interpretation','metal_half_cell':'energy is measured test-cell terminal energy, including metal electrode','three_electrode':'electrode potential alone cannot supply terminal energy'},
 'shared_mass':{'mass_g':'1/100','mass_standard_uncertainty_g':'1/1000','charge_C':'1','discharge_C':'9/10',
    'expected_CE_fraction':'9/10','mass_only_CE_standard_uncertainty':'0','note':'Algebraic cancellation only; total uncertainty remains not_evaluated.'}}
(ROOT/'fixtures'/'policies.json').write_text(json.dumps(policy,indent=2)+'\n')
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'fixtures').glob('*.json'))}
(ROOT/'fixtures'/'SHA256SUMS.json').write_text(json.dumps({k:v for k,v in manifest.items() if k!='SHA256SUMS.json'},indent=2)+'\n')
print(f'Wrote {len(cases)} observation fixtures and one policy fixture')
