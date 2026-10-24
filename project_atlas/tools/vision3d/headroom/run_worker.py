"""Run the REAL worker() with fake hardware/ROS. Env: CPU, RAM, TEMP, POLICY_FAIL_AFTER, SNAPSHOT_SLEEP, MODE, MAXS."""
import os, sys, time, json, types
W = sys.argv[1]; sys.path.insert(0, W)
import importlib.util
spec = importlib.util.spec_from_file_location('atlas_vision3d_runtime', os.path.join(W, sys.argv[2]))
R = importlib.util.module_from_spec(spec); sys.modules['atlas_vision3d_runtime'] = R; spec.loader.exec_module(R)
realG = importlib.util.module_from_spec(importlib.util.spec_from_file_location('sg', os.path.join(W, 'stationary_gate.py')))
importlib.util.spec_from_file_location('sg', os.path.join(W, 'stationary_gate.py')).loader.exec_module(realG)
CPU, RAM, TEMP = float(os.environ.get('CPU', 50)), float(os.environ.get('RAM', 60)), float(os.environ.get('TEMP', 60))
PFAIL = float(os.environ.get('POLICY_FAIL_AFTER', 1e9)); SNAP = float(os.environ.get('SNAPSHOT_SLEEP', 0)); T0 = time.monotonic()
def ticks():
    t = time.monotonic() * 600; return int(t), int(t * (1 - CPU / 100))
G = types.ModuleType('stationary_gate'); G.AdmissionError = realG.AdmissionError; G.require_cpu = realG.require_cpu
G.ticks = ticks; G.cpu_delta = realG.cpu_delta; G.services = lambda: {'u': 1}
def check(cpu=None, observation=None):
    realG.require_cpu(cpu)
    if time.monotonic() - T0 > PFAIL: raise RuntimeError('stationary policy admission failed')
    if RAM > 80 or TEMP > 70 or (cpu is not None and cpu > 75):
        raise realG.AdmissionError('resource limit failed', {'cpu': cpu, 'ram': RAM, 'temp': TEMP})
    return {'cpu_percent': cpu, 'ram_percent': RAM, 'thermal_c': {'cpu-thermal': TEMP}, 'commands_zero': True}
G.check = check
P = types.ModuleType('stationary_ros_probe')
def snap():
    if SNAP: time.sleep(SNAP)
    return {'ros': {}}
P.safety_snapshot = snap; P.extra_safety = lambda ros=None: None
sys.modules['stationary_gate'] = G; sys.modules['stationary_ros_probe'] = P
R.MAX_SECONDS = float(os.environ.get('MAXS', 6)); R.verify_runtime = lambda r, c: c(); R.cloud_admission = lambda m: None
R.domain_in_use = lambda d: False; R.driver_args = lambda m: ['sleep', '120']; R.RUNTIME = R.STATE.parent
R.startup_sample = lambda: [time.monotonic(), *ticks()]
R.worker(os.environ.get('MODE', 'depth'), startup=None)
