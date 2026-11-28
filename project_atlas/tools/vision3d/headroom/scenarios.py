import json, os, subprocess, sys, tempfile, time, threading
W, FILE = sys.argv[1], sys.argv[2]
def run(name, env, flag=None, lease_for=1e9, expect=None):
    d = tempfile.mkdtemp(); state = os.path.join(d, 'atlas-vision3d-viewer.json'); flagp = os.path.join(d, 'atlas-vision3d-cpu-monitor-only.json')
    if flag is not None: open(flagp, 'w').write(json.dumps(flag))
    e = dict(os.environ, ATLAS_VISION3D_STATE_PATH=state, **{k: str(v) for k, v in env.items()})
    p = subprocess.Popen([sys.executable, os.path.join(W, 't/run_worker.py'), W, FILE], stdin=subprocess.PIPE, env=e)
    t0 = time.time(); ok_lease = True
    while p.poll() is None and time.time() - t0 < 30:
        if time.time() - t0 < lease_for:
            try: p.stdin.write(b'1\n'); p.stdin.flush()
            except OSError: pass
        time.sleep(0.5)
    if p.poll() is None: p.kill()
    s = json.load(open(state)); ev = [x['event'] for x in s.get('lifecycle', [])]
    spawned = 'driver_spawned' in ev
    res = dict(state=s['state'], reason=s.get('reason', '')[:70], policy=s.get('cpu_policy', '')[:13], spawned=spawned,
               stopped=s.get('driver_stopped'), over=s.get('cpu_over_limit_samples'), flag_left=os.path.exists(flagp),
               consumed=os.path.exists(flagp.replace('.json', '.consumed')), secs=round(time.time() - t0, 1))
    good = all(res.get(k) == v if not callable(v) else v(res.get(k)) for k, v in (expect or {}).items())
    print(('PASS ' if good else 'FAIL ') + name, res); return good, d, flagp
now = time.time(); valid = {'expires_unix': now + 900, 'sessions_allowed': 1, 'mode': 'depth'}
r = []
r.append(run('A flag+CPU90 -> runs full session, logged not blocked', {'CPU': 90}, valid,
             expect={'state': 'OFF', 'spawned': True, 'stopped': True, 'consumed': True, 'flag_left': False, 'over': lambda v: v and v >= 3,
                     'reason': lambda x: x.startswith('60-second session complete')})[0])
r.append(run('B no flag+CPU90 -> blocked before driver', {'CPU': 90}, None, expect={'state': 'RESOURCE BLOCKED', 'spawned': False})[0])
r.append(run('C flag+RAM85 -> blocked', {'CPU': 90, 'RAM': 85}, valid, expect={'state': 'RESOURCE BLOCKED', 'spawned': False})[0])
r.append(run('D flag+TEMP72 -> blocked', {'CPU': 90, 'TEMP': 72}, valid, expect={'state': 'RESOURCE BLOCKED', 'spawned': False})[0])
r.append(run('E flag+policy fails at 5 s -> stop + driver cleaned', {'CPU': 90, 'POLICY_FAIL_AFTER': 5, 'MAXS': 20}, valid,
             expect={'spawned': True, 'stopped': True, 'reason': lambda x: 'policy' in x})[0])
ok, d, fp = run('F1 flag used once', {'CPU': 90}, valid, expect={'state': 'OFF', 'consumed': True})
r.append(ok)
r.append(run('F2 second session (flag consumed) -> blocked', {'CPU': 90}, None, expect={'state': 'RESOURCE BLOCKED', 'spawned': False})[0])
r.append(run('G1 expired flag -> blocked', {'CPU': 90}, dict(valid, expires_unix=now - 5), expect={'state': 'RESOURCE BLOCKED', 'flag_left': True})[0])
r.append(run('G2 flag >30 min -> blocked', {'CPU': 90}, dict(valid, expires_unix=now + 7200), expect={'state': 'RESOURCE BLOCKED'})[0])
r.append(run('G3 sessions_allowed 2 -> blocked', {'CPU': 90}, dict(valid, sessions_allowed=2), expect={'state': 'RESOURCE BLOCKED'})[0])
r.append(run('G4 concurrent mode never uses flag', {'CPU': 90, 'MODE': 'concurrent'}, valid, expect={'state': 'RESOURCE BLOCKED', 'flag_left': True, 'consumed': False})[0])
r.append(run('H flag+lease stops at 4 s -> stop', {'CPU': 90, 'MAXS': 30}, valid, lease_for=4,
             expect={'stopped': True, 'reason': lambda x: 'lease' in x or 'paused' in x})[0])
r.append(run('I no flag CPU50 -> normal full session (unchanged)', {'CPU': 50}, None, expect={'state': 'OFF', 'spawned': True, 'policy': 'ENFORCED'})[0])
r.append(run('J flag+stalled guard (snapshot 2.5 s) -> fail closed', {'CPU': 90, 'SNAPSHOT_SLEEP': 2.5, 'MAXS': 20}, valid,
             expect={'state': 'RESOURCE BLOCKED', 'reason': lambda x: 'sampling interval' in x})[0])
print('%d/%d PASS' % (sum(r), len(r)))
