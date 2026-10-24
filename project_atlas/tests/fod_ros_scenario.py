"""ROS integration scenario for atlas_feature_on_demand.py (run inside run_iso.sh; real rclpy topics, fake systemctl)."""
import json, os, signal, subprocess, sys, tempfile, threading, time
from pathlib import Path
import rclpy
from std_msgs.msg import Bool, String

ROOT = Path(__file__).resolve().parents[1]; MGR = ROOT / 'scripts/atlas_feature_on_demand.py'
work = Path(tempfile.mkdtemp()); units = work / 'units'; units.mkdir()
import importlib.util
spec = importlib.util.spec_from_file_location('fod', MGR); F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)
for u in F.MANAGED: (units / (u + '.service')).write_text('active')
(units / 'atlas-slam-fast.service').write_text('inactive')
fake = work / 'systemctl'
fake.write_text('#!/bin/bash\necho "$2 $3" >> "%s/calls"\nf="%s/$3"\ncase "$2" in is-active) cat "$f" 2>/dev/null || echo inactive;; '
                'stop) if [ "$3" = atlas-follow-person.service ]; then echo failed > "$f"; else echo inactive > "$f"; fi;; reset-failed) echo inactive > "$f";; start) echo active > "$f";; esac\n' % (units, units)); fake.chmod(0o755)
cfg = work / 'c.yaml'
cfg.write_text('timing: {boot_grace_s: 3, min_on_s: 1, state_check_s: 1, replay_delay_s: 1.5}\nfeatures:\n' +
               ''.join('  %s: {idle_s: 30}\n' % u for u in F.MANAGED))
env = dict(os.environ, ATLAS_SYSTEMCTL=str(fake))
mgr = subprocess.Popen([sys.executable, str(MGR), 'run', '--config', str(cfg)], env=env, stdout=open(work / 'mgr.log', 'w'), stderr=subprocess.STDOUT)
rclpy.init(); n = rclpy.create_node('fod_test')
pol = n.create_publisher(String, '/atlas/control_policy', 10); mis = n.create_publisher(String, '/atlas/mission_status', 10)
fol = n.create_publisher(Bool, '/atlas/follow_person/enabled', 10); seen = []
n.create_subscription(Bool, '/atlas/follow_person/enabled', lambda m: seen.append((time.monotonic(), m.data)), 10)
state = {'policy': json.dumps({'manual_only': True, 'stop_latched': True}), 'publish_policy': True}
def pub():
    if state['publish_policy']: pol.publish(String(data=state['policy']))
    mis.publish(String(data='READY'))
n.create_timer(0.2, pub)
threading.Thread(target=rclpy.spin, args=(n,), daemon=True).start()
st = lambda: {u: (units / (u + '.service')).read_text().strip() for u in F.MANAGED}
res = {}
def wait(cond, t):
    end = time.monotonic() + t
    while time.monotonic() < end and not cond(): time.sleep(0.5)
    return cond()
try:
    res['parked_all_stopped'] = wait(lambda: all(v == 'inactive' for v in st().values()), 60)   # incl. follow-person failed->reset
    t0 = time.monotonic(); fol.publish(Bool(data=True))
    need = ('atlas-follow-person', 'atlas-person-sensor-fusion', 'atlas-ai-annotator')
    res['follow_starts_its_features'] = wait(lambda: all(st()[u] == 'active' for u in need), 20)
    res['follow_others_stay_off'] = all(v == 'inactive' for u, v in st().items() if u not in need)
    res['follow_enable_replayed_after_start'] = wait(lambda: any(t > t0 + 1.0 and d for t, d in seen), 20)
    fol.publish(Bool(data=False)); state['policy'] = json.dumps({'manual_only': False, 'stop_latched': False})
    auto = ('atlas-vision-lidar-fusion', 'atlas-person-sensor-fusion', 'atlas-experience-store', 'atlas-agent-team', 'atlas-ai-annotator')
    res['autonomy_starts_fusion_features'] = wait(lambda: all(st()[u] == 'active' for u in auto), 20)
    state['policy'] = json.dumps({'manual_only': True, 'stop_latched': True})
    time.sleep(3); (units / 'atlas-agent-team.service').write_text('inactive')     # simulate one stopped later
    state['publish_policy'] = False                                                  # policy goes silent -> fail-open
    res['stale_policy_fails_open'] = wait(lambda: st()['atlas-agent-team'] == 'active', 25)
    for u in F.MANAGED: (units / (u + '.service')).write_text('inactive')
    mgr.send_signal(signal.SIGTERM); mgr.wait(10)
    subprocess.run([sys.executable, str(MGR), 'restore-all'], env=env, capture_output=True, timeout=60)  # = ExecStopPost
    res['restore_all_after_manager_stop'] = all(v == 'active' for v in st().values())
    calls = (units / 'calls').read_text().split()
    res['never_restart_enable_disable'] = not any(c in ('restart', 'enable', 'disable', 'mask') for c in calls)
finally:
    if mgr.poll() is None: mgr.kill()
print('RESULT ' + json.dumps(res)); print(open(work / 'mgr.log').read()[-1500:])
sys.stdout.flush(); os._exit(0 if all(res.values()) else 1)
