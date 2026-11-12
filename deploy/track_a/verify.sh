#!/bin/bash
# Track A gate check (read-only). Prints PASS / BLOCKED per gate; changes nothing.  bash deploy/track_a/verify.sh
R="$HOME/project_atlas"; ok(){ printf "PASS     %s\n" "$1"; }; bl(){ printf "BLOCKED  %s\n" "$1"; }
source /opt/ros/humble/setup.bash 2>/dev/null
[ -e "$R/scripts/atlas_astra_obstacle_scan.py" ] && ok "files installed" || bl "files not installed (run install.sh)"
if python3 "$R/scripts/atlas_astra_obstacle_scan.py" --preflight >/tmp/tracka-pre.txt 2>&1; then ok "preflight: mount + scan config valid (calibration = runtime driver CameraInfo, checked by the node)"
else bl "preflight: $(tail -1 /tmp/tracka-pre.txt | cut -c1-160)"; fi
ros2 pkg prefix domain_bridge >/dev/null 2>&1 && ok "domain_bridge installed" || bl "domain_bridge missing: sudo apt install ros-humble-domain-bridge"
for u in atlas-astra-obstacles atlas-astra-bridge atlas-astra-bridge-starter; do
  e=$(systemctl --user is-enabled $u 2>/dev/null); a=$(systemctl --user is-active $u 2>/dev/null)
  printf "INFO     %-24s enabled=%s active=%s (boot start via enable_boot.sh)\n" "$u" "${e:-not-installed}" "${a:-inactive}"
done
N=~/project_atlas_ws/src/tortoisebot_bringup/config/nav2_params.yaml
python3 "$R/tools/track_a/check_nav2_merge.py" "$N" >/tmp/tracka-nav.txt 2>&1 && ok "G5 Nav2 merge checks (dry run, LiDAR untouched)" || { bl "Nav2 merge check failed:"; cat /tmp/tracka-nav.txt; }
grep -q astra_layer "$N" && echo "INFO     nav2_params.yaml already contains astra_layer (G5 applied)" || echo "INFO     nav2_params.yaml unchanged (G5 not applied)"
