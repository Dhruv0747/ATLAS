#!/bin/bash
# Offline AMCL parameter variants on an ISOLATED ROS domain (77, localhost only, nice 19).
# Never touches the live stack (domain 0). Run only while the rover is parked.
set +u
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=77 ROS_LOCALHOST_ONLY=1
HERE=$(cd "$(dirname "$0")" && pwd)
W=${W:-/tmp/atlas_amcl_replay}; mkdir -p "$W"
BAG=${BAG:-/home/jetson/project_atlas/data/lidar_tests/auto5_steerfix_20261115}
T0=${T0:-405}; T1=${T1:-446}
MAP=${MAP:-/home/jetson/project_atlas/maps/atlas_latest.yaml}
LIVE=${LIVE:-/home/jetson/project_atlas_ws/src/tortoisebot_bringup/config/nav2_params.yaml}
params() {  # $1 out yaml, rest k=v overrides of the live amcl params
  python3 - "$LIVE" "$MAP" "$@" <<'EOF'
import sys, yaml
live, mp, out, kv = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
a = yaml.safe_load(open(live))['amcl']['ros__parameters']
a['use_sim_time'] = True; a['set_initial_pose'] = False
for item in kv:
    k, v = item.split('=')
    a[k] = int(float(v)) if isinstance(a.get(k), int) and not isinstance(a.get(k), bool) else float(v)
yaml.safe_dump({'amcl': {'ros__parameters': a},
                'map_server': {'ros__parameters': {'use_sim_time': True, 'yaml_filename': mp}},
                'lifecycle_manager_replay': {'ros__parameters': {'use_sim_time': True, 'autostart': True,
                                             'node_names': ['map_server', 'amcl'], 'bond_timeout': 0.0}}},
               open(out, 'w'))
EOF
}
run() {
  name=$1; shift
  params "$W/$name.yaml" "$@"
  nice -n 19 /opt/ros/humble/lib/nav2_map_server/map_server --ros-args -r __node:=map_server --params-file "$W/$name.yaml" >"$W/$name.map.log" 2>&1 & M=$!
  nice -n 19 /opt/ros/humble/lib/nav2_amcl/amcl --ros-args -r __node:=amcl --params-file "$W/$name.yaml" >"$W/$name.amcl.log" 2>&1 & A=$!
  nice -n 19 /opt/ros/humble/lib/nav2_lifecycle_manager/lifecycle_manager --ros-args -r __node:=lifecycle_manager_replay --params-file "$W/$name.yaml" >"$W/$name.lm.log" 2>&1 & L=$!
  sleep 8
  nice -n 19 python3 "$HERE/replay.py" "$BAG" "$T0" "$T1" "$W/$name.jsonl" >"$W/$name.replay.log" 2>&1
  kill -INT $L $A $M 2>/dev/null; sleep 2; kill -9 $L $A $M 2>/dev/null
  echo "$name: $(grep -c '"replay"' "$W/$name.jsonl" 2>/dev/null) replay poses"
}
if [ "${1:-}" = "one" ]; then shift; run "$@"; exit; fi
run A_live
run B_zhit z_hit=0.8 z_rand=0.2
run C_zhit_sig z_hit=0.8 z_rand=0.2 sigma_hit=0.1
run D_C_alpha z_hit=0.8 z_rand=0.2 sigma_hit=0.1 alpha1=0.1 alpha2=0.1 alpha3=0.1 alpha4=0.1
run E_D_beams z_hit=0.8 z_rand=0.2 sigma_hit=0.1 alpha1=0.1 alpha2=0.1 alpha3=0.1 alpha4=0.1 max_beams=120
nice -n 19 python3 "$HERE/score.py" "$BAG" "$MAP" "$W"/*.jsonl
