"""M01 reference audit, not a production analysis engine. Python stdlib only.

Run: python3 cycling_reference_checks.py
Writes cycling_reference_results.json alongside this file.
Expected quantities use analytic primitives or geometric areas, independently
of the sampled quadrature candidates. Diagnostic/application tests are pending.
"""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import math
import platform

checks = []


def check(case, purpose, actual, expected, unit, derivation, tolerance=0.0):
    error = abs(float(actual) - float(expected))
    passed = actual == expected if tolerance == 0 else error <= tolerance
    checks.append(dict(id=case, purpose=purpose, actual=float(actual),
                       expected=float(expected), unit=unit,
                       exact_expected=str(expected), absolute_error=error,
                       absolute_tolerance=tolerance, passed=passed,
                       independent_reference=derivation))


def sampled_charge(t, current):
    # Audit-only candidate; assumes already valid intervals, not an importer.
    return sum((b-a)*(i+j)/2 for a,b,i,j in
               zip(t, t[1:], current, current[1:]))


check('R01', 'Constant current',
      sampled_charge([F(0),F(90),F(3600)], [F(1,1000)]*3), F(18,5), 'C',
      'Rectangle: 0.001 A times 3600 s = 3.6 C = 1 mAh.')
check('R02', 'Active-mass normalization',
      (F(18,5)/F(1,100000))/3600, F(100), 'mAh/g',
      'One mAh divided by 0.010 g = 100 mAh/g; internal mass is 1e-5 kg.')
t=[F(0),F(1,10),F(2,5),F(1)]
check('R03', 'Ramp on nonuniform timestamps',
      sampled_charge(t, [1+2*x for x in t]), F(2), 'C',
      'I=1+2t A on [0,1] s; primitive t+t^2 yields 2 C.')
check('R04', 'Constant-voltage work', F(3)*F(18,5)/3600, F(3,1000), 'Wh',
      '3 V times 1 mAh = 3 mWh; mean voltage = 3 V.')
# U=2+t V; I=1+t A, 0<=t<=2 s. Product is 2+3t+t^2.
h,U0,I0,dU,dI=map(F,[2,2,1,2,2])
linear_product=h*(U0*I0+(U0*dI+I0*dU)/2+dU*dI/3)
check('R05', 'Energy under independent linear signal interpolation',
      linear_product, F(38,3), 'J',
      'Primitive 2t+(3/2)t^2+t^3/3 at t=2 is 38/3 J. '
      'Endpoint-power trapezoid is 14 J, larger by 4/3 J.')
check('R06', 'Reversal must retain throughput',
      abs(sampled_charge([F(0),F(10)],[F(1),F(1)]))+
      abs(sampled_charge([F(10),F(20)],[F(-1),F(-1)])), F(20), 'C',
      'Two separate 10 C rectangles give 20 C throughput although net charge is zero.')
cc=sampled_charge([F(0),F(3600)], [F(1,1000)]*2)
tail=sampled_charge([F(3600),F(3900),F(4200)],
                    [F(1,1000),F(1,2000),F(0)])
check('R07', 'CC plus a linear constant-voltage tail', cc+tail, F(39,10), 'C',
      'CC rectangle 3.6 C plus tail triangle (600 s)(0.001 A)/2 = 0.3 C; '
      'total 13/12 mAh. At 3 V, energy is 11.7 J.')
ce=100*F(98,100)
eta=ce*F(3)/F(16,5)
check('R08', 'Energy efficiency differs from CE', eta, F(735,8), '%',
      '1 mAh charge at 3.2 V and 0.98 mAh discharge at 3 V: CE=98%, '
      'energy ratio 2.94/3.2 = 91.875%.')
check('R09', 'Retention uses explicit reference', 100*F(81)/F(90), F(90), '%',
      '81 mAh divided by reference 90 mAh = 0.9; not the largest observed cycle.')
FARADAY=F('96485.33212')
check('R10', 'Theoretical capacity SI/display consistency',
      FARADAY/F('0.23228')/3600,
      FARADAY/(F('3.6')*F('232.28')), 'mAh/g',
      'One mole of electrons divided by 232.28 g, then C to mAh. '
      'This is a dimensional/arithmetic audit, not experimental utilization.')
check('R11', 'Geometric areal normalization',
      (F('3.6')/F('0.0001'))/36000, F(1), 'mAh/cm^2',
      '1 mAh distributed over 1 cm^2 gives 1 mAh/cm^2.')
check('R12', 'C-rate with explicit capacity basis',
      F('0.5')*(F('2')/1000), F('0.001'), 'A',
      'Half of a 2 mAh reference delivered per hour implies 1 mA.')
# Relative variance of Q/m from two independent specified errors.
check('R13', 'Independent mass and charge uncertainties',
      math.sqrt(0.01**2+0.02**2), math.sqrt(5)/100, 'relative standard uncertainty',
      'Pythagorean combination of 1% and 2%; 2.2360679775%.', 1e-15)
# A=Q1/m, B=Q0/m; common mass uncertainty yields covariance.
A,B,u_rel=F(90),F(100),F(1,50)
varA,varB,covAB=(A*u_rel)**2,(B*u_rel)**2,A*B*u_rel**2
var_ratio=varA/B**2+A**2*varB/B**4-2*A*covAB/B**3
check('R14', 'Common mass cancels in retention', var_ratio,F(0),'ratio variance',
      '(Q1/m)/(Q0/m)=Q1/Q0. Zero here is only the mass contribution, '
      'not the total measurement uncertainty.')

# Independent numerical cross-check of the exact polynomial integral in R05.
# Composite midpoint error for p(t)=2+3t+t^2 on [0,2] is 2/(3N^2).
N=10000
dt=2/N
midpoint=math.fsum((2+(k+0.5)*dt)*(1+(k+0.5)*dt)*dt for k in range(N))
bound=2/(3*N*N)+1e-12
crosscheck=dict(method='composite midpoint on analytic U(t)*I(t)',
                intervals=N, actual_J=midpoint, expected_J=float(F(38,3)),
                absolute_error_J=abs(midpoint-float(F(38,3))),
                tolerance_J=bound,
                tolerance_reason='Analytic midpoint error 2/(3N^2) plus 1e-12 J rounding allowance')
crosscheck['passed']=crosscheck['absolute_error_J']<=bound
result=dict(package='P00 M01 reference audit / seed for P02',version='0.1',
            python_version=platform.python_version(),
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            evidence='Arithmetic and synthetic integration checks only; no production engine or EC-Lab data.',
            checks=checks, independent_energy_crosscheck=crosscheck,
            all_passed=all(c['passed'] for c in checks) and crosscheck['passed'])
Path(__file__).with_name('cycling_reference_results.json').write_text(
    json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(reference_checks=len(checks),passed=sum(c['passed'] for c in checks),
                      independent_energy_crosscheck=crosscheck,
                      all_passed=result['all_passed']),indent=2))
if not result['all_passed']:
    raise SystemExit(1)
