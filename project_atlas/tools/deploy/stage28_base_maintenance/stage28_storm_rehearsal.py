#!/usr/bin/env python3
"""ATLAS Stage 28: ONE supervised DDS discovery rehearsal. PROPOSAL - requires separate explicit owner approval.

Question answered: does the independent safety observer keep FRESH E-STOP, command and telemetry evidence while the
Jetson goes through the same discovery storm that a recovery restart causes? No service is restarted, no file is
installed, no motor/steering/firmware is touched. The only new thing is atlas_dds_storm_probe.py (one participant,
32 endpoints on private topics) living <= 15 s.

Sequence (any failure -> probe SIGKILLed at once, everything recorded, FAIL, no retry):
  1. Refusals: OWNER_APPROVED=yes, explicit --cpu-rule (+ bound), no maintenance lease, no probe already running,
     base/recovery running, 14/14 web safety predicates x3, 30 s strict resources, independent observer warm-up 3 s.
  2. Continuous 1-s CPU/RAM/temperature recorder and 0.25-s observer verdicts run before, during and after.
  3. Probe spawned (own process group, UDPv4-only DDS, heartbeat-bound). Checked every 0.25 s:
       observer verdict (all 11 signals fresh <= 1.0 s; motor_speed included), verdict gap <= 1.0 s,
       RAM <= 80 and temperature < 70 on every sample, CPU <= 75 (strict) or > 75 only within the approved bound,
       production service identities unchanged, probe gone within 15 s of spawn.
  4. After the probe has left: 30 s strict CPU window with the observer still OK; 14/14 web safety x3.
  5. Cleanup verification: probe pid and process group gone, no process with the probe in its command line,
     DDS participant set (processes mapping libfastrtps) identical to before, no new /dev/shm fastrtps segment.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deploy_rc_bridge as D  # noqa: E402

PROBE = HERE / 'atlas_dds_storm_probe.py'
MAX_TEST_S = 15.0
HOLD_S = 6.0
# A PASS must come from a storm at least as strong as Stage A (5-6 samples >= 95 % within 10 s of the restart).
REPRESENTATIVE_MIN_SAMPLES, REPRESENTATIVE_PCT = 4, 95.0


class RehearsalEnv(D.Env):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.hb_period = 0.2

    def spawn_probe(self, hb, report, log):
        cmd = ('source /opt/ros/humble/setup.bash && exec python3 '
               f'{PROBE} --hold-s {HOLD_S} --hard-s 14 --heartbeat {hb} --report {report}')
        env = dict(os.environ, FASTDDS_BUILTIN_TRANSPORTS='UDPv4', PYTHONUNBUFFERED='1')
        with open(log, 'ab') as out:
            return subprocess.Popen(['bash', '-lc', cmd], stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=True, env=env)

    def dds_participants(self):
        pids = set()
        for p in Path('/proc').iterdir():
            if p.name.isdigit():
                try:
                    if 'libfastrtps' in (p / 'maps').read_text(errors='ignore'):
                        pids.add(int(p.name))
                except OSError:
                    pass
        return pids

    def shm_segments(self):
        try:
            return {n for n in os.listdir('/dev/shm') if n.startswith('fastrtps_')}
        except OSError:
            return set()

    def probe_processes(self):
        out = []
        for p in Path('/proc').iterdir():
            if p.name.isdigit() and int(p.name) != os.getpid():
                try:                                   # an argv element naming the probe file (not any mention)
                    argv = (p / 'cmdline').read_bytes().split(b'\0')
                    if any(a.endswith(b'/atlas_dds_storm_probe.py') or a == b'atlas_dds_storm_probe.py' for a in argv):
                        out.append(int(p.name))
                except OSError:
                    pass
        return out

    def lease_present(self):
        return Path(f'/run/user/{os.getuid()}/atlas-base-maintenance/lease.json').exists()


class Heartbeat:
    """Supervisor liveness for the probe: a file touched every 0.2 s. If this process dies or stalls, the probe
    exits within ~1.1 s (and PR_SET_PDEATHSIG kills it at once on supervisor death)."""

    def __init__(self, path, period):
        self.path, self.period, self._stop = Path(path), period, threading.Event()
        self.path.touch()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            os.utime(self.path)
            self._stop.wait(self.period)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()


def kill_probe(p):
    if p is not None and p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait(timeout=5)


def rehearse(env, args, ev):
    ev.log(f'storm rehearsal: rule={args.cpu_rule} bound={args.transient_bound_s} hold={HOLD_S}s max={MAX_TEST_S}s')
    if env.lease_present():
        raise D.Fail('a base maintenance lease exists; refusing')
    if env.probe_processes():
        raise D.Fail(f'a storm probe is already running: {env.probe_processes()}')
    base0 = D.require_running(env, env.base)
    D.require_running(env, env.recovery)
    watch = list(dict.fromkeys(env.protected + [env.base, env.recovery]))
    ids0 = D.identities(env, watch)
    parts0, shm0 = env.dds_participants(), env.shm_segments()
    D.require_safe(env, ev, 'R-pre')
    D.resources_strict(env, ev, 'R-pre', env.preflight_s)
    bound = 0.0 if args.cpu_rule == 'strict' else args.transient_bound_s
    probe, t0, t_probe_end, failure = None, None, None, None
    hb_path, report_path = ev.dir / 'probe.heartbeat', ev.dir / 'probe-report.json'
    with D.CpuRecorder(env) as cpu, D.ObserverRecorder(env, int(base0['MainPID'])) as safe, \
            Heartbeat(hb_path, env.hb_period):
        try:
            env.sleep(2.5)                                             # recorders running before the storm
            D.require_pre_window_ok(env, ev, 'R', cpu, safe)            # judges the observer's own warm-up too
            t0 = time.time()
            probe = env.spawn_probe(hb_path, report_path, ev.dir / 'probe.log')
            ev.log(f'probe spawned pid {probe.pid}')
            last_id_check = 0.0
            while True:
                D.early_abort(env, ev, 'R', cpu, t0, bound, safe)      # safety, gap, RAM/temp, CPU after bound
                now = time.time()
                if now - last_id_check >= 1.0:
                    last_id_check = now
                    if D.identities(env, watch) != ids0:
                        raise D.Fail('a production service identity changed during the rehearsal')
                if t_probe_end is None and probe.poll() is not None:
                    t_probe_end = now
                    ev.log(f'probe exited rc={probe.returncode} after {now - t0:.1f} s')
                if t_probe_end is None and now - t0 > MAX_TEST_S:
                    raise D.Fail(f'probe still alive {now - t0:.1f} s after spawn (limit {MAX_TEST_S} s)')
                if t_probe_end is not None:
                    judged_from = t0 + max(bound, t_probe_end - t0)
                    if len([1 for ts, _ in list(cpu.samples) if ts > judged_from]) >= env.steady_s:
                        break
                env.sleep(0.25)
            D.resources_after_restart(env, ev, 'R-post', args.cpu_rule, cpu, t0, bound, safe)
        except Exception as exc:
            if probe is None and isinstance(exc, D.Fail):
                raise                                                  # nothing was started: refusal, no change
            failure = exc
            kill_probe(probe)
            ev.log(f'REHEARSAL ABORTED: {exc!r}; probe killed')
        finally:
            kill_probe(probe)
            ev.save('cpu-recorder-R', {'t_spawn': t0, 'samples': cpu.samples, 'ram_temp': cpu.rt})
            ev.save('observer-R', {'t_spawn': t0, 'verdicts': safe.snaps})
    cleanup = verify_cleanup(env, ev, probe, parts0, shm0)
    if failure is None:
        try:
            D.require_safe(env, ev, 'R-post')
            if D.identities(env, watch) != ids0:
                raise D.Fail('a production service identity changed')
        except D.Fail as exc:
            failure = exc
    probe_report = json.loads(report_path.read_text()) if report_path.exists() else None
    storm = [x for d, x in cpu.timed_since(t0) if d <= max(bound, 10.0) and x >= REPRESENTATIVE_PCT] if t0 else []
    ok = failure is None and cleanup['ok'] and probe_report and probe_report['inventory_ok']
    verdict = 'FAIL' if not ok else ('PASS' if len(storm) >= REPRESENTATIVE_MIN_SAMPLES else 'INCONCLUSIVE')
    result = {'result': verdict, 'storm_samples_ge_95': storm,
              'representative': len(storm) >= REPRESENTATIVE_MIN_SAMPLES,
              'error': repr(failure) if failure else None, 'cleanup': cleanup,
              'probe_report': probe_report, 'probe_rc': probe.returncode if probe else None,
              'observer_summary': summarize_observer(safe.snaps, t0)}
    ev.save('result', result)
    ev.log(f'REHEARSAL {result["result"]}')
    return 0 if result['result'] == 'PASS' else 1


def verify_cleanup(env, ev, probe, parts0, shm0):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and (env.probe_processes() or (env.dds_participants() - parts0)):
        env.sleep(0.5)
    c = {'probe_processes': env.probe_processes(), 'new_dds_participants': sorted(env.dds_participants() - parts0),
         'lost_dds_participants': sorted(parts0 - env.dds_participants()),
         'new_shm_segments': sorted(env.shm_segments() - shm0)}
    if probe is not None:
        try:
            os.killpg(probe.pid, 0)
            c['probe_group_alive'] = True
        except ProcessLookupError:
            c['probe_group_alive'] = False
    c['ok'] = not (c['probe_processes'] or c['new_dds_participants'] or c['lost_dds_participants']
                   or c['new_shm_segments'] or c.get('probe_group_alive'))
    ev.save('cleanup', c)
    ev.log(f'cleanup: {"OK" if c["ok"] else "NOT CLEAN"} {c}')
    return c


def summarize_observer(snaps, t0):
    if not snaps or t0 is None:
        return None
    after = [s for s in snaps if s['wall'] >= t0]
    walls = [s['wall'] for s in after]
    gaps = [b - a for a, b in zip(walls, walls[1:])] or [0.0]
    worst = {}
    for s in after:
        for k, x in (s.get('verdict') or {}).get('signals', {}).items():
            if x.get('age_s') is not None:
                worst[k] = max(worst.get(k, 0.0), x['age_s'])
    return {'verdicts': len(after), 'not_ok': sum(1 for s in after if not s['window_ok']),
            'max_gap_s': round(max(gaps), 3), 'worst_signal_age_s': {k: round(v, 3) for k, v in sorted(worst.items())}}


def main(argv=None, env=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--cpu-rule', choices=['strict', 'transient'], required=True)
    p.add_argument('--transient-bound-s', type=float)
    p.add_argument('--evidence-root')
    a = p.parse_args(argv)
    if os.environ.get('OWNER_APPROVED') != 'yes':
        print('refused: OWNER_APPROVED=yes required (separate explicit approval of the rehearsal)')
        return 2
    if (a.cpu_rule == 'transient') != (a.transient_bound_s is not None) or (
            a.transient_bound_s is not None and not 0 < a.transient_bound_s <= 10.0):
        print('refused: transient needs --transient-bound-s in (0, 10]; strict takes none')
        return 2
    env = env or RehearsalEnv()
    if a.evidence_root:
        env.evidence_root = Path(a.evidence_root)
    ev = D.Evidence(env, 'storm-rehearsal')
    try:
        return rehearse(env, a, ev)
    except D.Fail as exc:
        ev.log(f'REFUSED (no probe started): {exc}')
        ev.save('result', {'result': 'REFUSED_NO_CHANGE', 'error': repr(exc)})
        return 3
    finally:
        ev.seal()


if __name__ == '__main__':
    raise SystemExit(main())
