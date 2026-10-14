"""Predeclared replay equivalence, not a localization-accuracy estimator.

No interpolation/extrapolation: pair nearest unique source measurement stamp
within 1 ms; reject missing/duplicate/backwards stamps and incomplete states.
Covariance normalization is full-matrix Frobenius with 1e-12 denominator floor.
"""
import math
import numpy as np

AMCL_MARGINS = {'jump_count': 1., 'max_jump_m': .10, 'post_stop_drift_m': .05,
    'heading_span_rad': math.radians(2), 'particle_xy_std_m': .05,
    'competing_hypothesis_weight': .05, 'scan_fit': .02, 'pose_xy_std_m': .05}

def validate(rows):
    last = -1
    for r in rows:
        t=r['last_measurement_ns']
        if not isinstance(t,int) or t<=last: raise ValueError('nonunique/backwards source time')
        last=t
        x=np.asarray(r['state'], dtype=float);p=np.asarray(r['covariance'],dtype=float)
        if x.shape!=(15,) or p.shape!=(225,) or not np.isfinite(x).all() or not np.isfinite(p).all():
            raise ValueError('incomplete/nonfinite internal state')
        p=p.reshape(15,15)
        if not np.allclose(p,p.T,atol=1e-10,rtol=1e-8) or np.linalg.eigvalsh(p).min() < -1e-10:
            raise ValueError('invalid covariance')
    if not rows: raise ValueError('empty trajectory')

def compare_ekf(reference, replay, *, tf_errors=0):
    validate(reference);validate(replay)
    times=np.array([r['last_measurement_ns'] for r in replay],dtype=np.int64)
    used=set();position=[];heading=[];cov=[]
    for a in reference:
        t=a['last_measurement_ns'];index=int(np.searchsorted(times,t))
        options=[k for k in (index-1,index) if 0<=k<len(replay) and k not in used]
        if not options: raise ValueError('unmatched sample')
        k=min(options,key=lambda k:abs(int(times[k])-t))
        if abs(int(times[k])-t)>1000000: raise ValueError('source-time pairing exceeds 1 ms')
        used.add(k);b=replay[k];x=np.array(a['state']);y=np.array(b['state'])
        position.append(float(np.linalg.norm(x[:2]-y[:2])))
        heading.append(abs(math.atan2(math.sin(x[5]-y[5]),math.cos(x[5]-y[5]))))
        p=np.array(a['covariance']);q=np.array(b['covariance'])
        cov.append(float(np.linalg.norm(p-q)/max(np.linalg.norm(p),1e-12)))
    if len(used)!=len(replay): raise ValueError('replay has unmatched samples')
    result={'position_max_m':max(position),'yaw_max_rad':max(heading),
        'covariance_relative_max':max(cov),'matched_samples':len(used),'tf_errors':tf_errors}
    result['equivalent']=result['position_max_m']<=.01 and result['yaw_max_rad']<=math.radians(.5) and result['covariance_relative_max']<=.01 and tf_errors==0
    result['fidelity_verified']=False  # Initialization, payload/order proof remains a separate prerequisite.
    return result

def compare_amcl(reference, replay):
    """Conservative approximate 95% mean-difference CI (Welch df>=19, t<=2.094).

    All metric CIs must lie strictly inside predeclared equivalence margins.
    Underpowered/variable ensembles fail, never prove improvement. Twenty runs
    each minimum. Jump timing requires a separate aligned-event check; this
    summary alone can never certify fidelity.
    """
    if min(len(reference),len(replay))<20: raise ValueError('at least 20 runs per ensemble')
    result={}
    for key,margin in AMCL_MARGINS.items():
        a=np.array([r[key] for r in reference],float);b=np.array([r[key] for r in replay],float)
        if not np.isfinite(a).all() or not np.isfinite(b).all():raise ValueError('nonfinite ensemble')
        # Welch degrees of freedom may be as low as 19: use conservative t(19)=2.094.
        width=2.094*math.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))
        delta=float(b.mean()-a.mean());lo,hi=delta-width,delta+width
        result[key]={'difference':delta,'ci95':[lo,hi],'margin':margin,
                     'equivalent':lo>-margin and hi<margin}
    return {'metrics':result,'summary_equivalent':all(v['equivalent'] for v in result.values()),
            'jump_timing_verified':False,'fidelity_verified':False}
