#!/usr/bin/env python3
"""ATLAS Stage 28 DDS discovery rehearsal probe. PROPOSAL; runs only under stage28_storm_rehearsal.py.

Reproduces the discovery load of an atlas_sensor_recovery restart (one new participant, 32 endpoints) WITHOUT
restarting any service and WITHOUT touching any production topic:
  * node /atlas_storm_probe/atlas_storm_probe
  * 16 subscriptions  /atlas_storm_probe/sub_00 .. sub_15   (std_msgs/String; nobody publishes there)
  * 2 publishers      /atlas_storm_probe/pub_0, pub_1       (never publish)
  * rclpy defaults    /rosout and /parameter_events publishers, 6 parameter services (12 endpoints)
  = 32 endpoints, the same count as the recovery node. No service clients, no actions, no timers that publish,
    no /cmd_vel, /atlas/control_policy or any motor/steering/E-STOP topic.

Bounded and fail-safe:
  * hard self-termination via SIGALRM at --hard-s (<= 14 s), armed before rclpy is imported;
  * PR_SET_PDEATHSIG=SIGKILL: dies with the supervisor;
  * exits within 0.1 s once the supervisor heartbeat file is older than 1.0 s;
  * holds the node for --hold-s (<= 8 s), then destroys it (participant leaves) and exits.
FastDDS is restricted to UDPv4 (FASTDDS_BUILTIN_TRANSPORTS) by the supervisor, so no /dev/shm segment can be leaked.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import signal
import sys
import time

NS = '/atlas_storm_probe'
NODE = 'atlas_storm_probe'
N_SUBS, N_PUBS = 16, 2
MAX_HOLD_S, MAX_HARD_S, HB_MAX_AGE_S = 8.0, 14.0, 1.0
FORBIDDEN = ('/cmd_vel', '/atlas/control_policy', '/atlas/estop', '/joy', '/motor', '/steer', '/yahboom', '/atlas/rc')


def die_with_parent():
    libc = ctypes.CDLL('libc.so.6', use_errno=True)
    if libc.prctl(1, signal.SIGKILL) != 0:               # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), 'prctl(PR_SET_PDEATHSIG) failed')


def heartbeat_ok(path):
    try:
        return 0 <= time.time() - os.stat(path).st_mtime <= HB_MAX_AGE_S
    except OSError:
        return False


def planned_topics():
    subs = [f'{NS}/sub_{i:02d}' for i in range(N_SUBS)]
    pubs = [f'{NS}/pub_{i}' for i in range(N_PUBS)]
    return subs, pubs


def check_isolated(names):
    bad = [n for n in names if not n.startswith(NS + '/') or any(n.startswith(f) for f in FORBIDDEN)]
    if bad:
        raise SystemExit(f'refused: non-isolated topic {bad}')


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--hold-s', type=float, default=6.0)
    p.add_argument('--hard-s', type=float, default=14.0)
    p.add_argument('--heartbeat', required=True)
    p.add_argument('--report', required=True)
    a = p.parse_args(argv)
    if not (0 < a.hold_s <= MAX_HOLD_S and 0 < a.hard_s <= MAX_HARD_S and a.hold_s < a.hard_s):
        raise SystemExit('refused: hold/hard limits')
    signal.alarm(int(a.hard_s))                         # default SIGALRM action terminates, even inside imports
    die_with_parent()
    if os.getppid() == 1 or not heartbeat_ok(a.heartbeat):
        raise SystemExit('refused: no live supervisor')
    subs, pubs = planned_topics()
    check_isolated(subs + pubs)
    t = {'process_start': time.time()}
    import rclpy                                        # noqa: E402 (deliberately after the safety arming)
    from std_msgs.msg import String
    t['imported'] = time.time()
    rclpy.init()
    node = rclpy.create_node(NODE, namespace=NS)        # defaults: rosout, parameter_events, 6 parameter services
    t['node_created'] = time.time()
    keep = [node.create_subscription(String, s, lambda m: None, 10) for s in subs]
    keep += [node.create_publisher(String, s, 10) for s in pubs]
    t['endpoints_created'] = time.time()
    inv = {
        'publishers': sorted(n for n, _ in node.get_publisher_names_and_types_by_node(NODE, NS)),
        'subscriptions': sorted(n for n, _ in node.get_subscriber_names_and_types_by_node(NODE, NS)),
        'services': sorted(n for n, _ in node.get_service_names_and_types_by_node(NODE, NS)),
        'clients': sorted(n for n, _ in node.get_client_names_and_types_by_node(NODE, NS)),
    }
    expected_pubs = sorted(pubs + ['/parameter_events', '/rosout'])
    ok = (inv['clients'] == [] and inv['publishers'] == expected_pubs and inv['subscriptions'] == sorted(subs)
          and len(inv['services']) == 6 and all(s.startswith(f'{NS}/{NODE}/') for s in inv['services']))
    inv['endpoint_count'] = len(inv['publishers']) + len(inv['subscriptions']) + 2 * len(inv['services'])
    reason = 'hold complete'
    end = time.time() + a.hold_s
    while time.time() < end:
        if not ok:
            reason = 'endpoint inventory mismatch'
            break
        if not heartbeat_ok(a.heartbeat):
            reason = 'supervisor heartbeat stale'
            break
        time.sleep(0.1)                                 # no spin: no callbacks, nothing published
    t['leaving'] = time.time()
    node.destroy_node()
    rclpy.shutdown()
    t['left'] = time.time()
    Path(a.report).write_text(json.dumps({'inventory': inv, 'inventory_ok': ok, 'times': t, 'exit_reason': reason,
                                          'pid': os.getpid(), 'keep': len(keep)}))
    return 0 if ok and reason == 'hold complete' else 3


if __name__ == '__main__':
    sys.exit(main())
