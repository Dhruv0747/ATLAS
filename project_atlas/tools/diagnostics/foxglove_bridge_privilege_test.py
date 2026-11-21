#!/usr/bin/env python3
"""Isolated privilege test of a Foxglove bridge configuration (never against the rover).

Starts, on a private ROS domain and loopback only: a probe node (topic /probe_topic, service
/probe_srv, parameter probe_param) and foxglove_bridge with either the production launch defaults
or a params file. A WebSocket client (foxglove.sdk.v1; bridges 3.x reject the older foxglove.websocket.v1 with HTTP 400) then reports what a remote device
could do: advertised capabilities, readable channels, whether a client-advertised /goal_pose
creates a ROS publisher, whether parameters are readable/writable, whether services are exposed.
  foxglove_bridge_privilege_test.py defaults|<params.yaml>   -> JSON
"""
import json, os, subprocess, sys, tempfile, time
import rclpy, websocket, yaml
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

PORT = 18765
mode = sys.argv[1]
os.environ.setdefault('ROS_DOMAIN_ID', '94')
BRIDGE = '/opt/ros/humble/lib/foxglove_bridge/foxglove_bridge'
if mode == 'defaults':   # exactly the production launch values read from the live process (15 Oct)
    params = {'foxglove_bridge': {'ros__parameters': {
        'port': PORT, 'address': '127.0.0.1', 'tls': False, 'topic_whitelist': ['.*'],
        'service_whitelist': ['.*'], 'param_whitelist': ['.*'], 'client_topic_whitelist': ['.*'],
        'capabilities': ['clientPublish', 'parameters', 'parametersSubscribe', 'services', 'connectionGraph', 'assets'],
        'include_hidden': False}}}
else:
    params = yaml.safe_load(open(mode))
    p = params['foxglove_bridge']['ros__parameters']
    p['bound_address_in_file'] = p['address']; p['address'] = '127.0.0.1'; p['port'] = PORT   # loopback for the test
    del p['bound_address_in_file']
pf = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False); yaml.safe_dump(params, pf); pf.close()

rclpy.init()
probe = Node('probe'); probe.declare_parameter('probe_param', 'original')
pub = probe.create_publisher(String, '/probe_topic', 10)
probe.create_service(Trigger, '/probe_srv', lambda req, res: res)
bridge = subprocess.Popen([BRIDGE, '--ros-args', '--params-file', pf.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
result = {'config': mode}
try:
    deadline = time.time() + 15
    ws = None
    while time.time() < deadline and ws is None:
        pub.publish(String(data='x')); rclpy.spin_once(probe, timeout_sec=0.1)
        try:
            ws = websocket.create_connection(f'ws://127.0.0.1:{PORT}', subprotocols=["foxglove.sdk.v1", "foxglove.websocket.v1"], timeout=2)
        except Exception:
            time.sleep(0.5)
    if ws is None:
        raise SystemExit('bridge did not accept a connection')
    msgs = []
    def drain(sec):
        end = time.time() + sec
        while time.time() < end:
            pub.publish(String(data='x')); rclpy.spin_once(probe, timeout_sec=0.05)
            try:
                ws.settimeout(0.2); m = ws.recv()
                if isinstance(m, str): msgs.append(json.loads(m))
            except Exception:
                pass
    drain(4)
    info = next((m for m in msgs if m.get('op') == 'serverInfo'), {})
    result['capabilities'] = sorted(info.get('capabilities', []))
    result['channels_readable'] = sorted({c['topic'] for m in msgs if m.get('op') == 'advertise' for c in m['channels']})
    result['services_exposed'] = sorted({s['name'] for m in msgs if m.get('op') == 'advertiseServices' for s in m['services']})
    # 1) client publish: advertise /goal_pose; does the bridge create a ROS publisher?
    ws.send(json.dumps({'op': 'advertise', 'channels': [{'id': 7, 'topic': '/goal_pose', 'encoding': 'cdr',
                                                          'schemaName': 'geometry_msgs/msg/PoseStamped'}]}))
    drain(3)
    result['client_advertise_created_ros_publisher'] = len(probe.get_publishers_info_by_topic('/goal_pose')) > 0
    # 2) parameters: read and write probe_param
    ws.send(json.dumps({'op': 'getParameters', 'parameterNames': ['/probe.probe_param'], 'id': 'g'}))
    ws.send(json.dumps({'op': 'setParameters', 'parameters': [{'name': '/probe.probe_param', 'value': 'changed'}], 'id': 's'}))
    drain(3)
    vals = [m for m in msgs if m.get('op') == 'parameterValues']
    result['parameter_read_returned_values'] = any(m.get('parameters') for m in vals)
    result['parameter_write_took_effect'] = probe.get_parameter('probe_param').value == 'changed'
    result['server_status_messages'] = sorted({m.get('message', '')[:90] for m in msgs if m.get('op') == 'status'})
    ws.close()
finally:
    bridge.terminate(); bridge.wait(5)
print(json.dumps(result, indent=1))
