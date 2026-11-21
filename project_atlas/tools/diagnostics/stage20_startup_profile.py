"""One isolated startup phase profile; no live topics, grant, bag or services."""
import json,time,resource,importlib
from stage19_contract import require_isolation
require_isolation()
rows=[]
def phase(name,fn):
    t=time.monotonic();c=time.process_time();v=fn()
    rows.append({'phase':name,'wall_s':time.monotonic()-t,'cpu_s':time.process_time()-c,
                 'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
    return v
capture=phase('capture_module_import',lambda:importlib.import_module('stage20_capture'))
ros=phase('rclpy_import',lambda:importlib.import_module('rclpy'))
phase('rosbag2_py_import',lambda:importlib.import_module('rosbag2_py'))
from rosidl_runtime_py.utilities import get_message
from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy
phase('rclpy_init',ros.init)
n=phase('node_create',lambda:ros.create_node('isolated_startup_profile',enable_rosout=False,start_parameter_services=False))
subs=[]
def subscribe():
    for t,typ in capture.KNOWN_TYPES.items():
        q=QoSProfile(depth=200,reliability=ReliabilityPolicy.RELIABLE if t=='/tf_static' else ReliabilityPolicy.BEST_EFFORT,
          durability=DurabilityPolicy.TRANSIENT_LOCAL if t=='/tf_static' else DurabilityPolicy.VOLATILE)
        subs.append(n.create_subscription(get_message(typ),t,lambda m:None,q,raw=True))
phase('known_subscriptions',subscribe)
phase('empty_graph_discovery',n.get_topic_names_and_types)
phase('node_destroy',n.destroy_node);phase('rclpy_shutdown',ros.shutdown)
print(json.dumps({'isolation':True,'live_failure_attribution':'UNKNOWN','phases':rows,
 'total_phase_cpu_s':sum(x['cpu_s'] for x in rows),'topics':len(subs),
 'live_graph_cost_included':False,'sqlite_or_capture_started':False},indent=2))
