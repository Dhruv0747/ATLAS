#!/usr/bin/env python3
"""Stage 29 supervised lifted-wheel test helper (runs on the Jetson). READ ONLY: it never selects a controller, never
resets or releases the E-STOP, never publishes a command and never restarts a service.

  precheck          GO / NO-GO for the morning test (every item printed; exit 0 only when all pass)
  record [SECONDS]  start the read-only stop recorder detached (systemd-run; default 900 s, max 900 s)
  analyze [FILE]    analyse the latest (or given) recording; saves <file>.report.json; exit 0 only on PASS
"""
import glob
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = 'http://127.0.0.1:8088'
EVID = Path.home() / 'project-atlas-migration'
FEATURES = ('atlas-vision-lidar-fusion', 'atlas-person-sensor-fusion', 'atlas-experience-store', 'atlas-agent-team',
            'atlas-ai-annotator', 'atlas-follow-person', 'atlas-camera-tracker', 'atlas-active-vision')
CAPS = (0.05, 0.20)
CPU_LIMIT, RAM_LIMIT, TEMP_LIMIT = 75.0, 80.0, 70.0
STICK_DEAD = 63


def get(path, timeout=3):
    with urllib.request.urlopen(API + path, timeout=timeout) as r:
        return json.loads(r.read())


def systemctl(*a):
    return subprocess.run(['systemctl', '--user', *a], capture_output=True, text=True, timeout=10).stdout.strip()


def cpu_ram_temp(seconds=3.0):
    def snap():
        v = list(map(int, open('/proc/stat').readline().split()[1:8]))
        return sum(v), v[3] + v[4]
    t1, i1 = snap(); time.sleep(seconds); t2, i2 = snap()
    cpu = 100.0 * (1 - (i2 - i1) / max(1, t2 - t1))
    mem = {l.split(':')[0]: int(l.split()[1]) for l in open('/proc/meminfo') if l.split(':')[0] in ('MemTotal', 'MemAvailable')}
    ram = 100.0 * (1 - mem['MemAvailable'] / mem['MemTotal'])
    return cpu, ram, max_temp()


def max_temp(paths=None):
    """Hottest readable thermal zone in C; some Jetson zones refuse reads (skipped). None when none is readable."""
    temps = []
    for p in (glob.glob('/sys/class/thermal/thermal_zone*/temp') if paths is None else paths):
        try:
            temps.append(int(open(p).read().strip()) / 1000.0)
        except (OSError, ValueError, TypeError):
            continue
    return max(temps) if temps else None


def checks(get=get, systemctl=systemctl, resources=cpu_ram_temp, runtime=None, uid=None):
    """[(ok, item, detail)] for the morning test. Pure over its injected readers (unit-tested offline)."""
    uid = os.getuid() if uid is None else uid
    runtime = Path(runtime or f'/run/user/{uid}')
    out = []
    add = lambda ok, item, detail='': out.append((bool(ok), item, detail))
    get('/api/controller_inputs'); get('/api/flysky/state?history=0')          # wake the lazy read-only listeners
    time.sleep(2.0)
    mc = get('/api/manual_controller'); p = mc['policy']; drv = mc['drive']; st = drv.get('status') or {}
    cfg = st.get('config') or {}
    gate_files = [runtime / f'systemd/user/{u}.d/90-atlas-flysky-gate.conf' for u in ('atlas-cmd-vel-mux.service', 'atlas-flysky-teleop.service')]
    add(all(f.exists() for f in gate_files) and p.get('flysky_drive_enabled') is True, 'FlySky driving gate ON',
        'gate drop-ins present and policy gate true (after a reboot the gate is OFF: gate-on is needed again)')
    add(cfg.get('reviewed_by_owner') is True and not cfg.get('errors') and
        (cfg.get('max_linear_mps'), cfg.get('max_angular_radps')) == CAPS, 'reviewed config, limits 0.05 m/s / 0.20 rad/s',
        f"reviewed {cfg.get('reviewed_by_owner')}, errors {cfg.get('errors')}, limits {cfg.get('max_linear_mps')}/{cfg.get('max_angular_radps')}")
    add(p.get('fresh') is True and p.get('stop_latched') is True, 'E-STOP latched', str(p.get('stop_reason')))
    add(p.get('manual_controller') == 'XBOX', 'Xbox is the selected remote (select FlySky only at the rover)', str(p.get('manual_controller')))
    add((mc.get('can_select') or {}).get('FLYSKY') is True, 'SELECT FLYSKY available', repr(mc.get('blocked_reason')))
    add(drv.get('running') is True and st.get('state') == 'NOT_SELECTED', 'FlySky teleop running, NOT_SELECTED', str(st.get('state')))
    xb = get('/api/controller_inputs')['xbox']
    axes, btn = xb.get('axes') or [], xb.get('buttons') or []
    add(xb.get('state') == 'LIVE' and xb.get('layout_ok') is True, 'Xbox connected (stop device)', f"{xb.get('state')} {xb.get('rate_hz')} Hz")
    add(btn and not any(btn) and all(abs(a) < 0.1 for i, a in enumerate(axes) if i not in (2, 5)), 'Xbox: nothing pressed, sticks centred',
        f'buttons {btn}')
    fs = get('/api/flysky/state?history=0'); link, flags = fs.get('link', {}), fs.get('flags', {})
    raw = {c['channel']: c['raw'] for c in fs.get('channels', [])}
    add(link.get('state') == 'LIVE' and not flags.get('failsafe') and not flags.get('frame_lost'),
        'FlySky transmitter on, receiver LIVE', f"{link.get('state')} failsafe {flags.get('failsafe')}")
    add(raw.get(5, 9999) < 400, 'SwA UP (disarmed)', f'CH5 {raw.get(5)}')
    add(raw.get(6, 9999) < 400, 'SwB UP (run)', f'CH6 {raw.get(6)}')
    add(400 <= raw.get(7, 0) <= 1700, 'SwC MIDDLE (66 %) recommended', f'CH7 {raw.get(7)}')
    add(all(abs(raw.get(c, 0) - 1024) <= STICK_DEAD for c in (1, 2)), 'right stick centred', f'CH1 {raw.get(1)} CH2 {raw.get(2)}')
    s1 = get('/api/status')['ros']; time.sleep(3.0); s2 = get('/api/status')['ros']
    enc = lambda s: [s.get(f'enc_m{i}', {}).get('value') for i in (1, 2, 3, 4)]
    health = json.loads(s2['encoder_health']['value']) if isinstance(s2.get('encoder_health', {}).get('value'), str) else {}
    add(s2.get('motor_speed', {}).get('value') == 0.0 and s2.get('cmd_vel', {}).get('value') == {'lin': 0.0, 'ang': 0.0},
        'motor output 0, /cmd_vel 0', f"motor {s2.get('motor_speed', {}).get('value')} cmd {s2.get('cmd_vel', {}).get('value')}")
    add(enc(s1) == enc(s2) and health.get('state') == 'READY', 'wheels still, encoders healthy', f'{enc(s2)} {health.get("state")}')
    states = {u: systemctl('is-active', u) for u in FEATURES}
    add(all(v != 'active' for v in states.values()), 'AI / fusion features idle', ', '.join(f'{k[6:]}={v}' for k, v in states.items()))
    add(not (runtime / 'atlas-mux-maintenance' / 'lease.json').exists(), 'no restart lease left over')
    cpu, ram, temp = resources()
    add(cpu <= CPU_LIMIT and ram <= RAM_LIMIT and temp is not None and temp < TEMP_LIMIT, 'CPU / RAM / temperature within limits',
        f'cpu {cpu:.1f} % ram {ram:.1f} % temp {temp}')
    add((HERE / 'stage29_stop_recorder.py').exists(), 'stop recorder present')
    return out


def precheck():
    res = checks()
    for ok, item, detail in res:
        print(('  OK  ' if ok else ' FAIL ') + item + (f'  [{detail}]' if detail else ''))
    go = all(ok for ok, _, _ in res)
    print('PRECHECK', 'GO' if go else 'NO-GO')
    return 0 if go else 1


def record(seconds=900):
    seconds = min(900, int(seconds))
    out = EVID / f'stage29-liftedtest-{time.strftime("%Y%m%d_%H%M%S")}.jsonl'
    subprocess.run(['systemd-run', '--user', '--unit=atlas-s29-stop-recorder', '--collect',
                    f'--working-directory={HERE}', sys.executable, str(HERE / 'stage29_stop_recorder.py'),
                    'record', '--out', str(out), '--seconds', str(seconds)], check=True)
    print('recording', out, f'for up to {seconds} s (read-only); stop early: systemctl --user stop atlas-s29-stop-recorder')
    return 0


def analyze(path=None):
    path = path or max(glob.glob(str(EVID / 'stage29-liftedtest-*.jsonl')), key=os.path.getmtime)
    sys.path.insert(0, str(HERE))
    import stage29_stop_recorder as R
    rep = R.analyze(path)
    Path(path + '.report.json').write_text(json.dumps(rep, indent=1))
    for e in rep['events']:
        print('%-14s cmd0 %-6s motor0 %-6s wheels still %-6s (limit %.1f) latched %-6s %s' % (
            e['event'], e['cmd_zero_s'], e['motor_zero_s'], e['wheels_still_s'], e['limit_s'], e['latched_s'],
            'PASS' if e['pass'] else 'FAIL'))
    print('OVERALL', 'PASS' if rep['pass'] else 'FAIL', '| report', path + '.report.json')
    return 0 if rep['pass'] else 1


def main(argv=None):
    a = sys.argv[1:] if argv is None else argv
    if not a or a[0] not in ('precheck', 'record', 'analyze'):
        print(__doc__); return 2
    if a[0] == 'precheck':
        return precheck()
    if a[0] == 'record':
        return record(a[1] if len(a) > 1 else 900)
    return analyze(a[1] if len(a) > 1 else None)


if __name__ == '__main__':
    sys.exit(main())
