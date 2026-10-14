"""Validate startup ledger mechanics without granting replay/motion authority."""
def audit_events(ekf, amcl, received_sources, ready_ns, parameter_sources=None):
    errors=[]
    for name,events in (('ekf',ekf),('amcl',amcl)):
        if not events:errors.append(name+':missing');continue
        last=0;mono=ready_ns
        for e in events:
            if e.get('diagnostic_failures',0):errors.append(name+':instrumentation_failure')
            if e['seq']!=last+1:errors.append(name+':sequence_gap')
            if e['monotonic_ns']<mono:errors.append(name+':clock_or_late_start')
            last=e['seq'];mono=e['monotonic_ns']
    phases=[e['phase'] for e in ekf]
    if not phases or phases[0]!='constructed_uninitialized':errors.append('missing_ekf_construction')
    if 'relative_reference_created' not in phases:errors.append('missing_actual_reference')
    pending=[];consumed=0
    for e in ekf:
        if e['phase']=='measurement_before':
            pending.append((e['source'],e['source_ns']))
            topic=e['source'].removesuffix('_pose').removesuffix('_twist').removesuffix('_acceleration')
            if not topic.startswith('/'):
                topic=(parameter_sources or {}).get(topic)
                if not topic:errors.append('consumer_parameter_alias_unverified')
            if (topic,e['source_ns']) not in received_sources:errors.append('consumer_input_not_recorded')
        if e['phase']=='measurement_after':
            if not pending or pending.pop()!=(e['source'],e['source_ns']):errors.append('consumer_pair_mismatch')
            if len(e.get('state',[]))!=15 or len(e.get('covariance',[]))!=225:errors.append('incomplete_internal_state')
            consumed+=1
    if pending:errors.append('incomplete_consumer_pair')
    needed={'particles_initialized','initial_pose_received','scan_tf_accepted',
            'weights_before_resample_decision','resample_before','resample_after'}
    if not needed.issubset({e['phase'] for e in amcl}):errors.append('missing_amcl_phases')
    requested=[i for i,e in enumerate(amcl) if e['phase']=='initial_pose_received']
    if requested and not any(e['phase']=='particles_initialized' for e in amcl[requested[0]+1:]):
        errors.append('initial_pose_application_not_observed')
    return {'startup_ledger_mechanics_verified':not errors,'errors':sorted(set(errors)),
            'consumed_measurements':consumed,'restorable_checkpoint':False,
            'replay_fidelity_verified':False}
