"""Pure Stage 19 replay contracts; no ROS/control imports."""
import copy
import hashlib
import math
from pathlib import Path

MAP_HASHES={'yaml':'d957f0fe3b8b48166751ef0226ba5f7abdd5454e6f44fac4c9e7b430f00c45e4',
            'pgm':'4beb26d5a9990db537df53ba71404d549f88f717d72ca59fc03e0b72a3684a1e'}
INPUTS={'/scan','/tf','/tf_static','/yahboom/odom','/im10a/imu/bias_corrected_candidate'}
OUTPUTS={'/odom','/amcl_pose','/particle_cloud','/tf','/map','/diagnostics'}
CRITERIA={'defined_before_comparison':True,'amcl_step_threshold_m':.5,
    'jump_dt_max_s':2,'acceptance':'No worse translation AND better heading on every eligible drive; no new frame/time failures; faithful AMCL baseline required for global claims',
    'missing_truth':'UNKNOWN, not a pass','single_stochastic_run':'cannot establish AMCL improvement',
    'production_deployment_authorized':False}


def validate_map(path):
    path=Path(path);result={}
    for ext in ('yaml','pgm'):
        item=path.with_suffix('.'+ext)
        result[ext]=hashlib.sha256(item.read_bytes()).hexdigest()
        if result[ext]!=MAP_HASHES[ext]: raise ValueError('accepted map hash mismatch: '+ext)
    return result


def variants(config):
    a=copy.deepcopy(config);p=a['atlas_ekf']['ros__parameters']
    if p['odom0']!='/yahboom/odom' or p['imu0']!='/im10a/imu/bias_corrected_candidate':
        raise ValueError('wrong native EKF sources')
    if p['odom0_config'][:2]!=[True,True] or p['odom0_config'][6:8]!=[True,True]:
        raise ValueError('baseline must contain wheel pose and velocity')
    if any(p['odom0_config'][i] for i in (5,11)) or not p['imu0_config'][11]:
        raise ValueError('unexpected yaw authority')
    p['use_sim_time']=True;b=copy.deepcopy(a)
    b['atlas_ekf']['ros__parameters']['odom0_config'][:2]=[False,False]
    return {'A':a,'B':b}


def keep_transform(parent,child):
    return not ({parent.strip('/'),child.strip('/')} & {'map','odom'})


def relative_pose_xy(pose,anchor):
    """Translation component of anchor.inverseTimes(pose), used by relative mode.

    Changing a checkpoint's anchor changes pose observations even with yaw fusion
    disabled. This diagnostic never normalizes or rewrites live input messages.
    """
    x,y=pose[:2];ax,ay,h=anchor
    if not all(math.isfinite(v) for v in (x,y,ax,ay,h)):raise ValueError('finite anchor required')
    return math.cos(h)*(x-ax)+math.sin(h)*(y-ay), -math.sin(h)*(x-ax)+math.cos(h)*(y-ay)


def candidate_gate(attestation):
    return isinstance(attestation,dict) and all(attestation.get(k) is True for k in
        ('baseline_reproduced','ekf_initial_reference_verified','amcl_initial_state_verified',
         'historical_parameters_verified','timing_fidelity_verified'))


def require_isolation():
    # Native runner is refused outside an isolated device/network/PID namespace.
    import os
    if os.environ.get('ATLAS_STAGE19_SANDBOX')!='1': raise RuntimeError('sandbox flag missing')
    if os.environ.get('ROS_DOMAIN_ID')!='187' or os.environ.get('ROS_LOCALHOST_ONLY')!='1':
        raise RuntimeError('replay domain mismatch')
    if Path('/dev/serial').exists() or list(Path('/dev').glob('ttyUSB*')) or list(Path('/dev').glob('ttyACM*')):
        raise RuntimeError('actuator devices visible')
    for namespace in ('net','pid'):
        # Host namespace identifiers captured by launcher, not user-configurable ROS parameters.
        host=os.environ.get('ATLAS_HOST_'+namespace.upper()+'_NS')
        if not host or not host.startswith(namespace+':['):
            raise RuntimeError('host namespace identity missing')
        if os.readlink('/proc/self/ns/'+namespace)==host:
            raise RuntimeError('host '+namespace+' namespace still visible')
    return {'domain':187,'loopback_only':True,'serial_devices':[],
        'network_namespace':os.readlink('/proc/self/ns/net'),'pid_namespace':os.readlink('/proc/self/ns/pid')}
