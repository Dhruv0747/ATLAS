"""Isolated PC ROS entity-workload comparison, not a localization accuracy test.

Uses captured monitor/ManualLocationCheck entity types and QoS plus real TF listener.
No map search, reseeding, production topics or production domain connection.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
import benchmark_executor_counts as B

MONITOR_SHA = 'cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b'
MANUAL_SHA = 'eec177795434870f53102482a92b3dbc1ced4d3e4a90589e22e9fe4261681690'


def candidate(raw):
    if hashlib.sha256(raw).hexdigest() != MONITOR_SHA:
        raise ValueError('exact live monitor required')
    old = '        rclpy.spin(node)'
    text = raw.decode()
    if text.count(old) != 1:
        raise ValueError('ambiguous spin')
    text = text.replace(old, '        from atlas_dashboard_executor import spin as private_spin\n        private_spin(node)')
    compile(text, '<candidate>', 'exec')
    return text.encode()


def run(module, rounds):
    import rclpy
    from rclpy.context import Context
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, qos_profile_sensor_data
    from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
    from nav_msgs.msg import Odometry, OccupancyGrid
    from sensor_msgs.msg import LaserScan, Imu
    from std_msgs.msg import String
    from std_srvs.srv import Trigger
    from nav2_msgs.srv import SetInitialPose
    from tf2_ros import Buffer, TransformListener
    ctx = Context(); rclpy.init(context=ctx)
    node = rclpy.create_node('isolated_localization_entities', context=ctx)
    ex = module.SingleThreadedExecutor(context=ctx); ex.add_node(node)
    seen = []; pending = {}; latencies = []; timers = [0, 0, 0]
    # Map, TF and service entities exist but no location action is requested.
    buffer = Buffer(node=node); listener = TransformListener(buffer, node)
    node.create_client(SetInitialPose, '/offline/set_initial_pose')
    node.create_publisher(String, '/offline/check', 10)
    for label in ('start', 'cancel'):
        node.create_service(Trigger, '/offline/'+label, lambda req, resp: resp)
    node.create_subscription(OccupancyGrid, '/offline/map', lambda msg: None,
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                   reliability=ReliabilityPolicy.RELIABLE))
    types = [LaserScan, Odometry, PoseWithCovarianceStamped, Odometry, Imu, String, Twist]
    pubs = []; msgs = []
    def receive(index, msg):
        if index not in pending:
            raise AssertionError('unexpected or duplicate callback')
        latencies.append((time.monotonic()-pending.pop(index))*1000)
        seen.append(index)
    try:
        for i, typ in enumerate(types):
            qos = qos_profile_sensor_data if i in (0, 4) else 10
            topic = '/offline/input_'+str(i)
            node.create_subscription(typ, topic, lambda msg, i=i: receive(i, msg), qos)
            pubs.append(node.create_publisher(typ, topic, qos))
            msg = typ()
            if i == 0: msg.ranges = [1.0]*720
            if i == 5: msg.data = '{"stop_latched":true,"source":"STOPPED"}'
            msgs.append(msg)
        for i, period in enumerate((.25, 1., .25)):
            node.create_timer(period, lambda i=i: timers.__setitem__(i, timers[i]+1))
        deadline = time.monotonic()+5
        while not all(p.get_subscription_count() == 1 for p in pubs):
            if time.monotonic() > deadline: raise RuntimeError('discovery timeout')
            ex.spin_once(timeout_sec=.01)
        start = time.process_time(); wall = time.monotonic()
        for _ in range(rounds):
            for i, p in enumerate(pubs):
                pending[i] = time.monotonic(); p.publish(msgs[i])
            deadline = time.monotonic()+2
            while pending:
                if time.monotonic() > deadline: raise RuntimeError('missing callback')
                ex.spin_once(timeout_sec=.01)
        return dict(cpu_s=time.process_time()-start, wall_s=time.monotonic()-wall,
                    received=len(seen), expected=rounds*7, timers=timers,
                    p95_ms=sorted(latencies)[int(.95*(len(latencies)-1))],
                    max_ms=max(latencies))
    finally:
        assert ex.shutdown(timeout_sec=1)
        listener.unregister(); node.destroy_node(); ctx.shutdown()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('monitor', type=Path); p.add_argument('manual', type=Path)
    p.add_argument('executor', type=Path); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--pairs', type=int, default=6); p.add_argument('--rounds', type=int, default=500)
    a = p.parse_args()
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '213':
        raise RuntimeError('PC localhost domain213 required')
    if not 2 <= a.pairs <= 10 or not 100 <= a.rounds <= 2000: raise ValueError('unbounded test')
    patched = candidate(a.monitor.read_bytes())
    if hashlib.sha256(a.manual.read_bytes()).hexdigest() != MANUAL_SHA:
        raise ValueError('manual source changed')
    raw = a.executor.read_bytes(); B.candidate(raw)
    modules = {'original': B.load_executor(raw.decode(), 'localization_original'),
               'candidate': B.load_executor(B.cancellation_candidate(raw, True), 'localization_candidate')}
    rows = []; savings = []
    for pair in range(a.pairs):
        for name in (('original','candidate') if pair%2 == 0 else ('candidate','original')):
            row = dict(pair=pair, variant=name, **run(modules[name], a.rounds))
            rows.append(row); print(json.dumps(row), flush=True)
        q = {r['variant']:r for r in rows if r['pair'] == pair}
        savings.append(100*(1-q['candidate']['cpu_s']/q['original']['cpu_s']))
    result = dict(rows=rows, paired_savings_percent=savings,
                  median_savings_percent=statistics.median(savings),
                  candidate_sha256=hashlib.sha256(patched).hexdigest(), installed=False,
                  limitation='Entity workload only; no map search, live rates, AMCL accuracy or Jetson savings proved')
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'median_savings_percent': result['median_savings_percent']}))


if __name__ == '__main__': main()
