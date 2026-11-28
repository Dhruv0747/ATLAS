"""Deployment safety of a partial sidecar is distinct from checkpoint fidelity.

No ROS publishers, control clients, systemd changes or deletion operations.
"""
import configparser
from pathlib import Path

PROTECTED=('atlas-cmd-vel-mux.service','rover-base-telemetry.service',
           'atlas-remote.service','atlas-safety-status.service',
           'atlas-ekf.service','atlas-localization.service')

def verify_unit(text, live_graph):
    unit=configparser.ConfigParser(interpolation=None,strict=False)
    unit.optionxform=str;unit.read_string(text)
    name='atlas-stage20-public-capture.service'
    if unit.has_section('Install'):raise ValueError('no automatic startup allowed')
    for key in ('Requires','Wants','BindsTo','PartOf','OnFailure','Upholds'):
        if unit.get('Unit',key,fallback='').strip():raise ValueError('diagnostic dependency forbidden')
    before=unit.get('Unit','Before',fallback='').split()
    after=unit.get('Unit','After',fallback='').split()
    if set(before)-{'shutdown.target'} or set(after)-{'basic.target'}:
        raise ValueError('collector must not delay production startup')
    service=unit['Service']
    expected={'Restart':'no','RuntimeMaxSec':'150','TimeoutStopSec':'25',
              'CPUQuota':'60%','LimitCPU':'75','MemoryMax':'192M','TasksMax':'48',
              'NoNewPrivileges':'yes'}
    for key,value in expected.items():
        if service.get(key)!=value:raise ValueError('resource/termination gate: '+key)
    for other,props in live_graph.items():
        for key in ('Requires','Wants','BindsTo','PartOf','After','Before','Upholds'):
            if name in props.get(key,[]):raise ValueError('live unit references optional collector: '+other)
    return {'startup_blocking_edges':[], 'control_dependency_edges':[],
            'default':'OFF','automatic_restart':False,
            'graph_units_checked':len(live_graph),'replay_fidelity_verified':False}

def partial_status(counts, required):
    missing=sorted(set(required)-{key for key,value in counts.items() if value>0})
    return {'missing_required_topics':missing,'public_inputs_present':not missing,
            'actual_consumption_proven':False,'full_ekf_checkpoint':False,
            'amcl_rng_state_available':False,'replay_fidelity_verified':False}
