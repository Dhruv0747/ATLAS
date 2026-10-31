#!/usr/bin/env python3
"""Stage 29 lifted-wheel test instrument: READ-ONLY stop-response recorder and analyser.

record : subscribes through the EXISTING foxglove_bridge (no ROS participant, nothing published) and writes one JSONL
         line per message with its receive time: Xbox /joy, receiver frames (decoded SBUS channels + flags),
         /cmd_vel_flysky, /cmd_vel, /motor_speed, /atlas/control_policy, /atlas/flysky/drive_status and the four
         /yahboom/encoder/mN counts. Every line is flushed as written, so a killed recorder keeps its data.
analyze: finds each stop event and measures event -> /cmd_vel zero -> /motor_speed zero -> wheels still
         (all four encoder counts unchanged for STILL_S), plus whether the E-STOP latched. PASS needs every
         event's wheels-still time within its limit.
Usage: stage29_stop_recorder.py record --out FILE --seconds N      (N <= 900)
       stage29_stop_recorder.py analyze FILE
"""
import argparse
import json
import math
import struct
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'stage28_base_maintenance'))
sys.path.insert(0, str(HERE.parents[2] / 'scripts'))

TOPICS = ['/joy', '/atlas/rc/frames', '/cmd_vel_flysky', '/cmd_vel', '/motor_speed', '/atlas/control_policy',
          '/atlas/flysky/drive_status'] + [f'/yahboom/encoder/m{i}' for i in (1, 2, 3, 4)]
MAX_RECORD_S = 900
STILL_S = 0.5
LATCH_WINDOW_S = 1.5        # a latch later than this is credited to a later event, not this one
DRIVING_LOOKBACK_S = 0.3    # an event is a stop test only if /cmd_vel was non-zero in this window before it
# Limits for event -> wheels still. Detection delays by design: receiver silent 0.30 s, Xbox off 0.50 s.
LIMIT_S = {'xbox_b': 1.0, 'swb_stop': 1.0, 'swa_off': 1.0, 'stick_release': 1.0, 'tx_off': 1.0,
           'rx_silent': 1.3, 'xbox_off': 1.5, 'software_stop': 1.0}
LATCHES = {'xbox_b', 'swb_stop', 'tx_off', 'rx_silent', 'xbox_off', 'software_stop'}
CH = {'throttle': 2, 'arm': 5, 'stop': 6, 'speed': 7, 'steering': 1}


# ------------------------------------------------------------------ CDR decoding
def _body(p):
    if len(p) < 4 or p[0] != 0x00 or p[1] != 0x01:
        raise ValueError('not CDR little-endian')
    return p[4:]


def decode(schema, payload):
    b = _body(payload)
    if schema == 'std_msgs/msg/Int32':
        return struct.unpack_from('<i', b, 0)[0]
    if schema == 'sensor_msgs/msg/Joy':
        o = 8                                                   # stamp: int32 sec + uint32 nanosec
        n, = struct.unpack_from('<I', b, o); o += 4 + n; o = (o + 3) & ~3
        na, = struct.unpack_from('<I', b, o); o += 4
        axes = list(struct.unpack_from('<%df' % na, b, o)); o += 4 * na
        nb, = struct.unpack_from('<I', b, o); o += 4
        return {'axes': [round(a, 3) for a in axes], 'buttons': list(struct.unpack_from('<%di' % nb, b, o))}
    import atlas_safety_observer as so
    v = so.decode(schema, payload)
    return list(v) if isinstance(v, tuple) else v


def rc_frame(text):
    """Receiver frame JSON -> {'ch': {n: raw}, 'failsafe', 'frame_lost'} for the channels the test uses."""
    import atlas_flysky_core as core
    m = json.loads(text)
    f = core.decode_sbus(bytes.fromhex(m['hex']))
    if f is None:
        return None
    return {'ch': {n: f.raw[n - 1] for n in sorted(set(CH.values()))}, 'failsafe': f.failsafe, 'frame_lost': f.frame_lost}


# ------------------------------------------------------------------ record
def record(out_path, seconds, port=8765):
    import atlas_safety_observer as so
    seconds = min(float(seconds), MAX_RECORD_S)
    ws = None
    for proto in so.SUBPROTOCOLS:
        try:
            ws = so.WebSocket('127.0.0.1', port, proto); break
        except Exception:
            continue
    if ws is None:
        raise SystemExit('foxglove bridge unreachable')
    out = open(out_path, 'a', buffering=1)
    subs, schema, counts = {}, {}, {t: 0 for t in TOPICS}

    def reader():
        try:
            while True:
                op, data = ws.recv()
                now = time.time()
                if op == 0x1:
                    m = json.loads(data)
                    if m.get('op') != 'advertise':
                        continue
                    new = []
                    for ch in m.get('channels', []):
                        t = ch.get('topic')
                        if t in counts and t not in schema:
                            schema[t] = ch.get('schemaName')
                            sid = len(subs) + 1
                            subs[sid] = t
                            new.append({'id': sid, 'channelId': ch['id']})
                    if new:
                        ws.send(0x1, json.dumps({'op': 'subscribe', 'subscriptions': new}).encode())
                elif data and data[0] == 0x01 and len(data) >= 13:
                    t = subs.get(struct.unpack_from('<I', data, 1)[0])
                    if t is None:
                        continue
                    try:
                        v = decode(schema[t], data[13:])
                        if t == '/atlas/rc/frames':
                            v = rc_frame(v)
                        elif t in ('/atlas/control_policy', '/atlas/flysky/drive_status'):
                            d = json.loads(v)
                            v = {k: d.get(k) for k in ('stop_latched', 'stop_reason', 'source', 'manual_controller',
                                                       'flysky_drive_enabled', 'state', 'armed', 'command')}
                    except Exception as exc:
                        v = {'decode_error': repr(exc)}
                    counts[t] += 1
                    out.write(json.dumps({'t': round(now, 4), 'topic': t, 'v': v}, separators=(',', ':')) + '\n')
        except Exception:
            return
    th = threading.Thread(target=reader, daemon=True)
    th.start()
    th.join(seconds)
    ws.close()
    th.join(1.0)
    out.close()
    return counts


# ------------------------------------------------------------------ analyze
def load(path):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    rows.sort(key=lambda r: r['t'])
    return rows


def events(rows):
    ev, last_joy, prev = [], None, {}
    joy_t = [r['t'] for r in rows if r['topic'] == '/joy']
    for a, b in zip(joy_t, joy_t[1:]):
        if b - a > 0.5:
            ev.append(('xbox_off', a))
    if joy_t and rows and rows[-1]['t'] - joy_t[-1] > 0.5:
        ev.append(('xbox_off', joy_t[-1]))
    fr = [r for r in rows if r['topic'] == '/atlas/rc/frames' and isinstance(r['v'], dict) and 'ch' in r['v']]
    for a, b in zip(fr, fr[1:]):
        if b['t'] - a['t'] > 0.3 and not a['v']['failsafe']:
            ev.append(('rx_silent', a['t']))
    for r in rows:
        t, v = r['topic'], r['v']
        if t == '/joy' and isinstance(v, dict):
            if len(v['buttons']) > 1 and v['buttons'][1] and not (last_joy or {}).get('b'):
                ev.append(('xbox_b', r['t']))
            last_joy = {'b': bool(len(v['buttons']) > 1 and v['buttons'][1])}
        elif t == '/atlas/rc/frames' and isinstance(v, dict) and 'ch' in v:
            ch = {int(k): x for k, x in v['ch'].items()}
            p = prev.get('rc')
            if p:
                if v['failsafe'] and not p['failsafe']:
                    ev.append(('tx_off', r['t']))
                elif not v['failsafe'] and not p['failsafe']:
                    if p['ch'][CH['stop']] < 400 <= ch[CH['stop']]:
                        ev.append(('swb_stop', r['t']))
                    if p['ch'][CH['arm']] >= 1700 and ch[CH['arm']] <= 400:
                        ev.append(('swa_off', r['t']))
                    if abs(p['ch'][CH['throttle']] - 1024) > 150 and abs(ch[CH['throttle']] - 1024) <= 63:
                        ev.append(('stick_release', r['t']))
            prev['rc'] = {'ch': ch, 'failsafe': v['failsafe']}
        elif t == '/atlas/control_policy' and isinstance(v, dict):
            reason = str(v.get('stop_reason') or '')
            if v.get('stop_latched') and 'voice stop' in reason and not prev.get('voice'):
                ev.append(('software_stop', r['t']))
            prev['voice'] = bool(v.get('stop_latched') and 'voice stop' in reason)
    return sorted(ev, key=lambda e: e[1])


def _is_cmd(r):
    return r['topic'] == '/cmd_vel' and isinstance(r['v'], list)


def _moving(v):
    return abs(v[0]) > 1e-6 or abs(v[5]) > 1e-6


def driving_before(rows, t0):
    """Was the rover being commanded to move just before the event? The last /cmd_vel at or before t0 must be
    non-zero and no older than DRIVING_LOOKBACK_S (an idle mux publishes /cmd_vel only sparsely, 2026-10-30)."""
    last = None
    for r in rows:
        if r['t'] > t0:
            break
        if _is_cmd(r):
            last = r
    if last is None or len(last['v']) != 6:
        return None  # no command evidence is not evidence of idle
    try:
        if not all(math.isfinite(float(x)) for x in last['v']):
            return None
        moving = _moving(last['v'])
    except (TypeError, ValueError):
        return None
    if moving and t0 - last['t'] > DRIVING_LOOKBACK_S:
        return None  # never discard a potentially real stop because its command is stale
    return moving



def measure(rows, kind, t0, horizon=5.0):
    after = [r for r in rows if t0 <= r['t'] <= t0 + horizon]
    driving = driving_before(rows, t0)
    cmd = next((r['t'] for r in after if r['topic'] == '/cmd_vel' and isinstance(r['v'], list)
                and r['v'][0] == 0.0 and r['v'][5] == 0.0), None)
    motor = next((r['t'] for r in after if r['topic'] == '/motor_speed' and r['v'] == 0.0), None)
    enc = {f'/yahboom/encoder/m{i}': [(r['t'], r['v']) for r in rows if r['topic'] == f'/yahboom/encoder/m{i}'
                                       and t0 - 1.0 <= r['t'] <= t0 + horizon] for i in (1, 2, 3, 4)}
    still = None
    if all(enc.values()):
        last_change = t0
        for series in enc.values():
            for (ta, va), (tb, vb) in zip(series, series[1:]):
                if vb != va and tb > t0:
                    last_change = max(last_change, tb)
        if all(any(t >= last_change + STILL_S for t, _ in s) for s in enc.values()):
            still = last_change
    latched = next((r['t'] for r in after if r['topic'] == '/atlas/control_policy' and isinstance(r['v'], dict)
                    and r['v'].get('stop_latched') and r['t'] <= t0 + LATCH_WINDOW_S), None)
    rel = lambda x: None if x is None else round(x - t0, 3)
    res = {'event': kind, 't': round(t0, 3), 'cmd_zero_s': rel(cmd), 'motor_zero_s': rel(motor),
           'wheels_still_s': rel(still), 'limit_s': LIMIT_S[kind], 'latched_s': rel(latched),
           'latch_expected': kind in LATCHES}
    # PASS = wheels still in time, /cmd_vel reached zero, and the latch behaved as specified (a latch on a
    # non-latching event is safe-direction but still a deviation that must be reported, not hidden).
    res['pass'] = (still is not None and still - t0 <= LIMIT_S[kind] and cmd is not None
                   and (latched is not None) == res['latch_expected'])
    # A switch flipped or stick moved while the rover was NOT being driven is not a stop test: it proves at most
    # that the latch works. It is reported, never counted as PASS or FAIL (2026-10-30: 42 of 48 'stick releases').
    res['driving'] = driving
    if driving is False:
        res['cmd_zero_s'] = 0.0                    # already zero; do not time the next sparse idle message
        res['pass'] = None
    if driving is None:
        res['pass'] = None
    res['result'] = ('INSUFFICIENT_EVIDENCE' if driving is None else
                     'NOT_A_STOP_TEST' if not driving else 'PASS' if res['pass'] else 'FAIL')
    return res


def analyze(path):
    rows = load(path)
    out = [measure(rows, k, t) for k, t in events(rows)]
    judged = [e for e in out if e['driving']]
    return {'events': out, 'pass': bool(judged) and all(e['pass'] for e in judged) and all(e['driving'] is not None for e in out), 'stops_under_motion': len(judged),
            'counts': {t: sum(1 for r in rows if r['topic'] == t) for t in TOPICS}}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['record', 'analyze'])
    p.add_argument('file', nargs='?')
    p.add_argument('--out'); p.add_argument('--seconds', type=float, default=600)
    a = p.parse_args(argv)
    if a.action == 'record':
        print(json.dumps(record(a.out, a.seconds)))
        return 0
    r = analyze(a.file)
    for e in r['events']:
        print('%-14s cmd0 %-6s motor0 %-6s wheels still %-6s (limit %.1f) latched %-6s %s' % (
            e['event'], e['cmd_zero_s'], e['motor_zero_s'], e['wheels_still_s'], e['limit_s'], e['latched_s'],
            e['result']))
    print('OVERALL', 'PASS' if r['pass'] else 'FAIL', json.dumps(r['counts']))
    return 0 if r['pass'] else 1


if __name__ == '__main__':
    sys.exit(main())
