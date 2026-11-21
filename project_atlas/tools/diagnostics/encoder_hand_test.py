#!/usr/bin/env python3
"""Guided, READ-ONLY encoder hand-rotation test (Stage 25b).

Use ONLY with the rover lifted, all four wheels clear of the floor, E-STOP latched and nobody near the steering.
This script only SUBSCRIBES to /atlas/encoder_update. It publishes nothing, sends no motor/steering/cmd_vel
command, changes no parameter and does not restart anything. You turn each wheel by hand.

For each wheel it asks for one full turn forward and one full turn backward, slowly (about 5 s) and quickly
(about 1-2 s), and compares the counted distance with one wheel circumference. It never changes polarity, CPR
or calibration; it only reports.

    source /opt/ros/humble/setup.bash
    python3 encoder_hand_test.py            # interactive
"""
import json
import sys
import time

CIRCUMFERENCE_M = 0.392699
WHEELS = {1: 'M1 rear-left', 2: 'M2 rear-right', 3: 'M3 front-left', 4: 'M4 front-right'}
PACES = (('slow', 'slowly, about 5 seconds per turn'), ('fast', 'quickly, about 1 to 2 seconds per turn'))
DIRECTIONS = ('forward', 'reverse')
PASS_LO, PASS_HI = 0.75, 1.30        # counted / expected for one hand-turned revolution (marked with tape)
CROSSTALK_WARN = 0.10                # another wheel counting more than this fraction of a turn
ASYMMETRY_WARN = 0.15                # forward and reverse ratios differing by more than this fraction


def evaluate_step(wheel, direction, deltas_m):
    """Classify one hand-turned revolution. deltas_m: signed forward-positive distance change of M1..M4."""
    expected = CIRCUMFERENCE_M * (1.0 if direction == 'forward' else -1.0)
    own = float(deltas_m[wheel - 1])
    ratio = own / expected
    cross = max(abs(float(v)) for i, v in enumerate(deltas_m) if i != wheel - 1)
    if ratio < -0.3:
        status = 'WRONG_DIRECTION'
    elif abs(ratio) < 0.10 or ratio < 0:
        status = 'NO_COUNT'
    elif ratio < PASS_LO:
        status = 'PARTIAL'
    elif ratio > PASS_HI:
        status = 'OVERCOUNT'
    else:
        status = 'PASS'
    return {'wheel': wheel, 'direction': direction, 'ratio': round(ratio, 3), 'status': status,
            'crosstalk_turns': round(cross / CIRCUMFERENCE_M, 3),
            'crosstalk_warn': cross / CIRCUMFERENCE_M > CROSSTALK_WARN}


def summarize(results):
    """results: list of evaluate_step dicts plus a 'pace' key. Returns a verdict per wheel."""
    out = {}
    for w in WHEELS:
        rs = [r for r in results if r['wheel'] == w]
        if not rs:
            out[w] = {'verdict': 'NOT_TESTED', 'notes': []}
            continue
        notes = []
        bad = [r for r in rs if r['status'] != 'PASS']
        fw = [r['ratio'] for r in rs if r['direction'] == 'forward']
        rv = [r['ratio'] for r in rs if r['direction'] == 'reverse']   # ratio is already direction-normalised (1.0 = one correct turn)
        if fw and rv:
            f, b = sum(fw) / len(fw), sum(rv) / len(rv)
            if max(f, b) > 0 and abs(f - b) / max(f, b) > ASYMMETRY_WARN:
                notes.append('DIRECTION_ASYMMETRY forward %.2f vs reverse %.2f' % (f, b))
        for pace in ('slow', 'fast'):
            ps = [r['ratio'] for r in rs if r.get('pace') == pace]
            if ps and min(ps) < PASS_LO:
                notes.append('LOSS_AT_%s_PACE min %.2f' % (pace.upper(), min(ps)))
        if any(r['crosstalk_warn'] for r in rs):
            notes.append('CROSSTALK another wheel counted while this one was turned')
        verdict = 'PASS' if not bad and not notes else 'FAIL'
        if bad:
            notes.insert(0, ', '.join('%s %s=%s' % (r.get('pace', ''), r['direction'], r['status']) for r in bad))
        out[w] = {'verdict': verdict, 'notes': notes}
    return out


def _run():  # pragma: no cover - needs ROS and a human
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    class Listener(Node):
        def __init__(self):
            super().__init__('atlas_encoder_hand_test_readonly')
            self.last = None
            self.create_subscription(String, '/atlas/encoder_update', self._cb, 10)

        def _cb(self, msg):
            try:
                self.last = json.loads(msg.data)
            except ValueError:
                pass

    rclpy.init()
    node = Listener()

    def snap():
        for _ in range(10):
            rclpy.spin_once(node, timeout_sec=0.1)
        for _ in range(20):
            rclpy.spin_once(node, timeout_sec=0.05)
        if node.last is None:
            sys.exit('No /atlas/encoder_update received. Is the base running?')
        return list(node.last['wheel_distances_m']), list(node.last['raw_counts'])

    print(__doc__)
    if input('Rover lifted, wheels clear, E-STOP latched? type YES to continue: ').strip() != 'YES':
        sys.exit('Stopped. Nothing was done.')
    results, log = [], []
    for w, name in WHEELS.items():
        print('\n=== %s ===  (mark the tyre with tape so you can count exactly one turn)' % name)
        for pace, pace_text in PACES:
            for direction in DIRECTIONS:
                input('%s: turn it ONE full turn %s, %s. Press Enter to START measuring ' % (name, direction.upper(), pace_text))
                d0, r0 = snap()
                input('   now turn it, then press Enter when the tape mark is back where it started ')
                d1, r1 = snap()
                deltas = [b - a for a, b in zip(d0, d1)]
                res = evaluate_step(w, direction, deltas)
                res['pace'] = pace
                results.append(res)
                log.append({**res, 'delta_m': deltas, 'delta_raw': [b - a for a, b in zip(r0, r1)]})
                print('   -> %s  counted %.2f of one turn  crosstalk %.2f turn' % (res['status'], res['ratio'], res['crosstalk_turns']))
    verdict = summarize(results)
    print('\n=== RESULT (no setting was changed) ===')
    for w, v in verdict.items():
        print('%-15s %-5s %s' % (WHEELS[w], v['verdict'], '; '.join(v['notes'])))
    path = '/home/jetson/project_atlas/data/diagnostics/encoder_hand_test_%s.json' % time.strftime('%Y%m%d_%H%M%S')
    try:
        with open(path, 'w') as fh:
            json.dump({'steps': log, 'verdict': verdict}, fh, indent=1)
        print('log:', path)
    except OSError as exc:
        print('could not write log:', exc)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    _run()
