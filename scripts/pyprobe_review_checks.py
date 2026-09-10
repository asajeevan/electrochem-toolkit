"""Focused review of unmodified PyProBE backend at a supplied git checkout.

Usage: python pyprobe_review_checks.py /path/to/PyProBE
Requires Polars 1.18.0 plus backend dependencies and pytest test plugins.
Bypasses only package __init__ (which imports the GUI) via a namespace package.
No backend source is patched; this is NOT a complete installation/GUI test.
"""
import contextlib
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types

repo=Path(sys.argv[1]).resolve()
out=Path(__file__).resolve().parent
package=types.ModuleType('pyprobe')
package.__path__=[str(repo/'pyprobe')]
sys.modules['pyprobe']=package

import polars as pl
from pyprobe.cyclers.biologic import Biologic, BiologicMB
from pyprobe.filters import Experiment
from pyprobe.analysis import cycling
from pyprobe import units

findings=[]
sample=repo/'tests/sample_data/biologic/Sample_data_biologic_CA1.txt'
raw=Biologic.read_file(str(sample)).collect()
elapsed=raw['time/s'].cast(pl.Float64)
dates=raw['Date'].str.to_datetime()
dt_s=elapsed[-1]-elapsed[0]
date_s=(dates[-1]-dates[0]).total_seconds()
findings.append(dict(id='B1_timestamp',sample=sample.name,
                     elapsed_delta_s=dt_s,absolute_datetime_delta_s=date_s,
                     ratio=date_s/dt_s,expected='Approximately equal deltas; not a factor near 1e-6.'))

lf=pl.DataFrame({'Time [s]':list(map(float,range(12))),
                 'Step':[0,0,1,1]*3,'Event':[0,0,1,1,2,2,3,3,4,4,5,5],
                 'Current [A]':[1.,1.,-1.,-1.]*3,
                 'Voltage [V]':[3.]*12,
                 'Capacity [Ah]':[0.,1.,1.,0.02,0.02,1.02,1.02,0.04,0.04,1.04,1.04,0.06]}).lazy()
def exp():
    return Experiment(lf=lf,info={'Name':'Synthetic review only'},
                      step_descriptions={'Step':[0,1], 'Description':['Charge','Discharge']},
                      cycle_info=[])
for flag in [True,False]:
    r=cycling.summary(exp(),dchg_before_chg=flag).data
    findings.append(dict(id='B2_CE_'+str(flag),columns=r.columns,
                         ce_present='Coulombic Efficiency' in r.columns))

converted=pl.DataFrame({'Current [mA]':[1.]}).select(pl.col('Current [mA]').units.to_unit('V'))
findings.append(dict(id='B3_dimension_check',output=converted.to_dict(as_series=False),
                     expected='Reject conversion between current and voltage.'))

synthetic=pl.DataFrame({'Ns':['0','0'], 'time/s':['0.0','1.0'],
                       'I/mA':['1.0','1.0'],'Ewe/V':['0.1','0.2'],
                       'Q charge/mA.h':['0.0','0.0002777778'],
                       'Q discharge/mA.h':['0.0','0.0'],
                       'source_flag':['valid','overflow']})
with tempfile.TemporaryDirectory() as d:
    f=Path(d)/'ewe_only.mpt';synthetic.write_csv(f,separator='\t')
    mapped=Biologic(input_data_path=str(f)).get_pyprobe_dataframe()
    findings.append(dict(id='B4_projection',input_columns=synthetic.columns,
                         output_columns=mapped.columns,
                         voltage=mapped['Voltage [V]'].to_list(),
                         expected='Our canonical data must retain Ewe identity and source flag.'))

nullable=pl.DataFrame({'Ns':[0,1], 'MB File':[0,0], 'auxiliary':[None,2.0]})
corrected=BiologicMB.apply_step_correction(nullable)
findings.append(dict(id='B5_MB_null',input_aux=nullable['auxiliary'].to_list(),
                     output_aux=corrected['auxiliary'].to_list(),
                     expected='Missing auxiliary measurement remains null.'))

versions={}
for name in ['polars','pydantic','numpy','scipy','pytest','pytest-benchmark','loguru','pandas']:
    versions[name]=importlib.metadata.version(name)
record=dict(commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
            harness='Namespace package to omit GUI-importing __init__; unmodified backend modules.',
            python=sys.version,versions=versions,findings=findings,
            source_hashes={f:hashlib.sha256((repo/f).read_bytes()).hexdigest() for f in
                           ['pyprobe/cyclers/biologic.py','pyprobe/analysis/cycling.py','pyprobe/units.py']})
print(json.dumps(record,indent=2))

# Upstream focused tests, not the full suite or notebook/GUI tests.
import pytest
os.chdir(repo)
buffer=io.StringIO()
with contextlib.redirect_stdout(buffer),contextlib.redirect_stderr(buffer):
    code=pytest.main(['tests/cyclers/test_biologic.py','tests/analysis/test_cycling.py',
                      '-o','addopts=','-q','--benchmark-disable'])
(out/'pyprobe_upstream_test_log.txt').write_text(buffer.getvalue())
record['upstream_test_exit_code']=int(code)
record['upstream_test_scope']=['tests/cyclers/test_biologic.py','tests/analysis/test_cycling.py']
(out/'pyprobe_review_results.json').write_text(json.dumps(record,indent=2)+'\n')
print(buffer.getvalue()[-1800:])
