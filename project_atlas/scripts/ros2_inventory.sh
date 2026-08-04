#!/usr/bin/env bash
set -u

OUT="${1:-ros2_inventory_$(hostname)_$(date +%Y%m%d_%H%M%S).txt}"

section() {
  printf '\n\n===== %s =====\n' "$1" | tee -a "$OUT"
}

run() {
  local title="$1"
  shift
  section "$title"
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n'
    "$@"
  } >>"$OUT" 2>&1
}

: >"$OUT"

section "Host"
{
  echo "timestamp: $(date --iso-8601=seconds 2>/dev/null || date)"
  echo "hostname: $(hostname)"
  echo "user: $(id -un)"
  echo "kernel: $(uname -a)"
  [ -r /etc/os-release ] && cat /etc/os-release
} >>"$OUT" 2>&1

section "ROS environment"
{
  env | sort | grep -E '^(AMENT|COLCON|CYCLONEDDS|FASTRTPS|GAZEBO|IGN|RCL|RCUTILS|ROS|TURTLEBOT|AMENT_PREFIX_PATH|CMAKE_PREFIX_PATH|PYTHONPATH)=' || true
  command -v ros2 || true
  ros2 --help >/dev/null 2>&1 && ros2 doctor --report || true
} >>"$OUT" 2>&1

run "Running ROS-related processes" ps -eo pid,ppid,user,lstart,cmd
section "Filtered ROS processes"
ps -eo pid,ppid,user,lstart,cmd | grep -Ei 'ros2|ros-|dds|gazebo|ignition|rviz|nav2|slam|robot_state|joint_state|controller|micro_ros|agent' | grep -v grep >>"$OUT" 2>&1 || true

if command -v ros2 >/dev/null 2>&1; then
  run "ROS 2 daemon status" ros2 daemon status
  run "ROS 2 node list" ros2 node list
  run "ROS 2 node list all namespaces" ros2 node list --all
  run "ROS 2 topic list typed" ros2 topic list -t
  run "ROS 2 service list typed" ros2 service list -t
  run "ROS 2 action list typed" ros2 action list -t
  run "ROS 2 interface packages" ros2 interface packages

  section "ROS 2 node info"
  ros2 node list 2>/dev/null | while read -r node; do
    [ -n "$node" ] || continue
    {
      printf '\n--- %s ---\n' "$node"
      ros2 node info "$node"
    } >>"$OUT" 2>&1 || true
  done

  section "ROS 2 params"
  ros2 node list 2>/dev/null | while read -r node; do
    [ -n "$node" ] || continue
    {
      printf '\n--- %s ---\n' "$node"
      ros2 param list "$node"
    } >>"$OUT" 2>&1 || true
  done
else
  section "ROS 2 CLI missing"
  echo "ros2 command not found in this shell. Source your ROS setup first, then rerun this script." >>"$OUT"
fi

section "Common ROS workspaces"
{
  for dir in "$HOME"/ros2_ws "$HOME"/dev_ws "$HOME"/colcon_ws "$HOME"/robot_ws "$HOME"/turtlebot3_ws /opt/ros/*; do
    [ -e "$dir" ] && echo "$dir"
  done
} >>"$OUT" 2>&1

section "Package manifests under home"
find "$HOME" -maxdepth 5 -name package.xml -print 2>/dev/null >>"$OUT" || true

section "Launch/config files under home"
find "$HOME" -maxdepth 6 \( -name '*.launch.py' -o -name '*.launch.xml' -o -name '*.launch.yaml' -o -name '*.rviz' -o -name '*.yaml' -o -name '*.urdf' -o -name '*.xacro' \) -print 2>/dev/null >>"$OUT" || true

section "Systemd ROS-like services"
systemctl --type=service --state=running --no-pager 2>/dev/null | grep -Ei 'ros|robot|nav|slam|lidar|camera|dds|micro' >>"$OUT" 2>&1 || true

echo "Wrote $OUT"
