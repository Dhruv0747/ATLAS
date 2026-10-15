import json,numpy as np
from s25_load import load
d=load({'/atlas/encoder_update','/atlas/encoder_health','/joy','/cmd_vel','/steering/mode'})
t0=d['/atlas/encoder_update'][0][0]
enc=[(t,json.loads(m.data)) for t,m,_ in d['/atlas/encoder_update']]
# any change in static fields
keys=['encoder_signs','counts_per_revolution','count_origins','positions','path_scales','eligible_channels','excluded_channels','fault_channels','steering_centers_deg']
for k in keys:
    vals=set(json.dumps(e.get(k)) for _,e in enc); print(k,len(vals), list(vals)[:2] if len(vals)<4 else '')
extra=[k for k in enc[0][1] if k not in keys+['raw_counts','wheel_distances_m','sequence','stamp_ns','monotonic_s','integration_dt_s','schema_version','wheel_circumference_m','wheelbase_m','track_width_m','steering_command_deg']]
print('other keys',extra)
print('--- M2 vs M1 per-interval around the flip (t rel t0, dM1,dM2,dM4 m; raw M2 counts)')
prev=None
for t,e in enc:
    r=t-t0
    if 196<=r<=216 and prev is not None:
        dW=np.array(e['wheel_distances_m'])-np.array(prev[1]['wheel_distances_m'])
        if abs(dW).max()>0.001: print('%7.2f'%r,np.round(dW,3).tolist(),e['raw_counts'],'seq',e['sequence'])
    prev=(t,e)
print('--- joy buttons near flip (changes only)')
last=None
for t,m,_ in d['/joy']:
    r=t-t0
    if 190<=r<=222:
        b=tuple(m.buttons)
        if b!=last: print('%7.2f'%r,'buttons',list(b),'axes',[round(x,2) for x in m.axes[:6]]); last=b
print('--- health fields near flip')
for t,m,_ in d['/atlas/encoder_health']:
    r=t-t0
    if 198<=r<=214 and int(r*2)%2==0:
        h=json.loads(m.data); print('%7.2f'%r,h['state'],h['consensus_state'],h['consensus_rejected_encoders'],'last_change',h['last_change_age_s'],'delta',h['encoder_interval_delta_m'],'links',h['link_stale_events'],h['link_recoveries'],'csum',h['serial_checksum_errors'])
