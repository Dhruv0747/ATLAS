"""Offline validation of atlas_parked_camera_profile.py against REAL Nav2 1.1.20 servers (Jetson's live
nav2_params.yaml, live behaviour trees), synthetic map and fake sensors, inside a loopback-only network namespace.

usage (inside run_iso.sh): run_offline_validation.py <live nav2_params.yaml> <work_dir> <out.json>
"""
import json, os, signal, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent; TOOL = HERE.parent / 'atlas_parked_camera_profile.py'; CONFIG = HERE.parents[2] / 'config'
NAV = ('controller_server', 'planner_server', 'behavior_server', 'bt_navigator', 'waypoint_follower')
PKG = {'controller_server': 'nav2_controller', 'planner_server': 'nav2_planner', 'behavior_server': 'nav2_behaviors',
       'bt_navigator': 'nav2_bt_navigator', 'waypoint_follower': 'nav2_waypoint_follower', 'map_server': 'nav2_map_server',
       'amcl': 'nav2_amcl', 'lifecycle_manager': 'nav2_lifecycle_manager'}
PREFIX = Path(sys.executable).resolve().parents[1]
results = {'scenarios': []}


def say(name, ok, **kw):
    row = dict(scenario=name, ok=bool(ok), **kw); results['scenarios'].append(row); print(('PASS ' if ok else 'FAIL ') + name, json.dumps(kw, default=str)[:400], flush=True)


def tool(*args, env_extra=None, timeout=400):
    env = dict(os.environ, **(env_extra or {}))
    r = subprocess.run([sys.executable, str(TOOL), *args], env=env, capture_output=True, text=True, timeout=timeout)
    rows = [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
    return r.returncode, rows, r.stderr[-600:]


def main(params_live, work, out):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    subprocess.check_call([sys.executable, str(HERE / 'make_map.py'), str(work / 'map')], stdout=subprocess.DEVNULL)
    p = Path(params_live).read_text().replace('/home/jetson/project_atlas/config/', str(CONFIG) + '/')
    (work / 'nav2_params.yaml').write_text(p); params = str(work / 'nav2_params.yaml')
    ctl = work / 'dash_control.json'; ctl.write_text('{}'); stop_tf = work / 'stop_tf'
    env_tool = {'ATLAS_DASHBOARD_URL': 'http://127.0.0.1:18089', 'ATLAS_PARKED_MARKER': str(work / 'marker.json'),
                'ATLAS_VISION3D_STATE_PATH': str(work / 'vision_state.json'), 'ATLAS_PARKED_TEST_WATCHDOG': '1'}
    procs = {}
    def start(name, cmd):
        procs[name] = subprocess.Popen(cmd, stdout=open(work / (name + '.log'), 'w'), stderr=subprocess.STDOUT, start_new_session=True)
    start('dash', [sys.executable, str(HERE / 'fakes.py'), 'dashboard', '18089', str(ctl)])
    start('sensors', [sys.executable, str(HERE / 'fakes.py'), 'sensors', str(stop_tf)])
    exe = lambda pkg, bin_: str(PREFIX / 'lib' / pkg / bin_)
    start('map_server', [exe('nav2_map_server', 'map_server'), '--ros-args', '-r', '__node:=map_server', '--params-file', params,
                         '-p', 'yaml_filename:=' + str(work / 'map/synthetic.yaml'), '-p', 'use_sim_time:=false'])
    start('amcl', [exe('nav2_amcl', 'amcl'), '--ros-args', '-r', '__node:=amcl', '--params-file', params, '-p', 'use_sim_time:=false'])
    mgr = lambda name, nodes: [exe('nav2_lifecycle_manager', 'lifecycle_manager'), '--ros-args', '-r', '__node:=' + name, '-p', 'use_sim_time:=false',
                               '-p', 'autostart:=true', '-p', 'node_names:=[%s]' % ','.join("'%s'" % n for n in nodes), '-p', 'bond_timeout:=4.0',
                               '-p', 'attempt_respawn_reconnection:=true']
    start('lifecycle_manager_localization', mgr('lifecycle_manager_localization', ['map_server', 'amcl']))
    for n in NAV:
        cmd = [exe(PKG[n], n), '--ros-args', '-r', '__node:=' + n, '--params-file', params, '-p', 'use_sim_time:=false']
        if n in ('controller_server', 'behavior_server'): cmd[3:3] = ['-r', 'cmd_vel:=cmd_vel_nav']
        start(n, cmd)
    time.sleep(3); start('lifecycle_manager_navigation', mgr('lifecycle_manager_navigation', list(NAV)))
    try:
        t0 = time.monotonic(); s = None
        while time.monotonic() - t0 < 300:
            rc, rows, err = tool('status', env_extra=env_tool, timeout=120); s = rows[-1]['ros'] if rows else None
            if s and s['nav_active'] and s['loc_active']: break
            time.sleep(5)
        say('bringup_real_nav2_active', s and s['nav_active'] and s['loc_active'], seconds=round(time.monotonic() - t0), ros=s)
        if not (s and s['nav_active']): return
        pids = {n: procs[n].pid for n in NAV}
        def nav_cpu(seconds):
            def tot():
                t = 0
                for pid in pids.values():
                    f = Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split(); t += int(f[11]) + int(f[12])
                return t
            a = tot(); time.sleep(seconds); return 100.0 * (tot() - a) / os.sysconf('SC_CLK_TCK') / seconds
        def planner_probe():
            r = subprocess.run([sys.executable, str(HERE / 'planner_probe.py')], capture_output=True, text=True, timeout=90)
            return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'ERROR ' + r.stderr[-200:]
        cpu_active = nav_cpu(20); plan_active = planner_probe()
        say('planner_works_while_active', plan_active.startswith('SUCCEEDED'), probe=plan_active, nav_cpu_pct_one_core=round(cpu_active, 2))
        # --- refusals (nothing may change)
        rc, rows, _ = tool('pause', env_extra=dict(env_tool, OWNER_APPROVED=''))
        say('refuse_without_owner_approval', rc == 2 and 'approval' in rows[-1]['reason'])
        for label, c in (('estop_not_latched', {'estop': False}), ('policy_not_stopped', {'stop_latched': False}), ('mission_not_ready', {'mission': 'NAVIGATING'}),
                         ('motor_command_nonzero', {'lin': 0.1}), ('amcl_stale', {'amcl_age': 9.0})):
            ctl.write_text(json.dumps(c)); rc, rows, _ = tool('pause', env_extra=dict(env_tool, OWNER_APPROVED='yes'))
            rc2, rows2, _ = tool('status', env_extra=env_tool)
            say('refuse_' + label, rc == 2 and rows2[-1]['ros']['nav_active'] is True and not (work / 'marker.json').exists(), reason=rows[-1].get('reason'))
        ctl.write_text('{}')
        # --- pause / verify / resume
        rc, rows, err = tool('pause', env_extra=dict(env_tool, OWNER_APPROVED='yes'))
        pr = [r for r in rows if r['event'] == 'pause']
        say('pause_navigation_only', rc == 0 and pr and pr[0]['ok'], ros=pr[0]['ros'] if pr else rows, err=err[-200:])
        cpu_paused = nav_cpu(20); plan_paused = planner_probe()
        rc_s, rows_s, _ = tool('status', env_extra=env_tool)
        st = rows_s[-1]['ros']
        say('paused_state_stable_past_bond_timeout', st['nav_active'] is False and all(v == 'inactive' for v in st['nav_states'].values())
            and all(v == 'active' for v in st['loc_states'].values()), after_s=40, ros=st)
        say('planner_refuses_while_paused', not plan_paused.startswith('SUCCEEDED'), probe=plan_paused)
        say('nav_cpu_drops_when_paused', cpu_paused < cpu_active, active_pct=round(cpu_active, 2), paused_pct=round(cpu_paused, 2))
        rc, rows, _ = tool('pause', env_extra=dict(env_tool, OWNER_APPROVED='yes'))
        say('refuse_second_pause_while_marker_exists', rc == 2)
        rc, rows, err = tool('resume', env_extra=dict(env_tool, OWNER_APPROVED='yes'))
        rr = [r for r in rows if r['event'] == 'resume']
        say('resume_restores_navigation', rc == 0 and rr and rr[-1]['ok'] and not (work / 'marker.json').exists(), ros=rr[-1]['ros'] if rr else rows)
        plan_after = planner_probe(); say('planner_works_after_resume', plan_after.startswith('SUCCEEDED'), probe=plan_after)
        rc, rows, _ = tool('resume', env_extra=dict(env_tool, OWNER_APPROVED='yes'))
        say('resume_is_idempotent', rc == 0 and any(r.get('already_active') for r in rows))
        # --- watchdog: pause with a short window and walk away
        rc, rows, _ = tool('pause', '--max-pause-s', '15', env_extra=dict(env_tool, OWNER_APPROVED='yes'))
        time.sleep(45); rc_s, rows_s, _ = tool('status', env_extra=env_tool)
        say('watchdog_resumes_automatically', rc == 0 and rows_s[-1]['ros']['nav_active'] is True and not (work / 'marker.json').exists(), ros=rows_s[-1]['ros'])
        # --- resume while map->base TF is missing: must report, not restart anything; completes once TF returns
        rc, rows, _ = tool('pause', env_extra=dict(env_tool, OWNER_APPROVED='yes'))
        stop_tf.write_text('1'); time.sleep(3)
        rc, rows, err = tool('resume', '--timeout', '25', env_extra=dict(env_tool, OWNER_APPROVED='yes'))
        incomplete = rc == 3 and any(r['event'] == 'RESUME_INCOMPLETE' for r in rows)
        stop_tf.unlink(); time.sleep(10)
        rc2, rows2, _ = tool('resume', env_extra=dict(env_tool, OWNER_APPROVED='yes'))
        rc_s, rows_s, _ = tool('status', env_extra=env_tool)
        say('resume_without_tf_reports_incomplete_then_recovers', incomplete and rows_s[-1]['ros']['nav_active'] is True,
            first_rc=rc, events=[r['event'] for r in rows], second_rc=rc2, final=rows_s[-1]['ros'])
        # --- full session flow with a simulated Vision Lab state file
        vs = work / 'vision_state.json'; vs.write_text(json.dumps({'state': 'RESOURCE BLOCKED', 'worker_pid': 1}))
        env_s = dict(env_tool, OWNER_APPROVED='yes')
        proc = subprocess.Popen([sys.executable, str(TOOL), 'session', '--wait-start-s', '120'], env=dict(os.environ, **env_s), stdout=subprocess.PIPE, text=True)
        lines = []
        for line in proc.stdout:
            lines.append(line)
            if 'READY_FOR_CAMERA' in line:
                time.sleep(2); vs.write_text(json.dumps({'state': 'ACTIVE', 'worker_pid': 4242}))
                time.sleep(6); vs.write_text(json.dumps({'state': 'OFF', 'worker_pid': 4242, 'reason': '60-second session complete', 'sample_count': 60}))
        proc.wait(300); ev = [json.loads(l)['event'] for l in lines if l.startswith('{')]
        rc_s, rows_s, _ = tool('status', env_extra=env_tool)
        say('session_pause_wait_resume', proc.returncode == 0 and ev[:1] == ['pause'] and 'camera_session_started' in ev and 'camera_session_ended' in ev
            and ev[-1] == 'resume' and rows_s[-1]['ros']['nav_active'] is True, events=ev)
    finally:
        for p in procs.values():
            try: os.killpg(p.pid, signal.SIGINT)
            except OSError: pass
        time.sleep(3)
        for p in procs.values():
            try: os.killpg(p.pid, signal.SIGKILL)
            except OSError: pass
        results['passed'] = sum(r['ok'] for r in results['scenarios']); results['total'] = len(results['scenarios'])
        Path(out).write_text(json.dumps(results, indent=1, default=str)); print('RESULT %d/%d' % (results['passed'], results['total']))


if __name__ == '__main__':
    main(*sys.argv[1:4])
