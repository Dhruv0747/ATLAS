# Shared checks. Run on the Jetson as user jetson. Never restarts, reloads or reboots anything.
set -u
T=$HOME/project_atlas/scripts/atlas_sensor_recovery.py
LIVE=5f44cc1fbd7cdc65b8af17abeb9ecd41cec0a8c8f3ee8274fa9b34362633193a
CAND=4af4ddade5bf998d3fbb9012a0ebe50902c83d922a55a3a8e97ebb8f01e19e4d
MTIME='2026-11-02 15:29:54.436767674 +0530'
H=$HOME/project_atlas/tools/vision3d
die(){ echo "ABORT: $*"; exit 1; }
h(){ sha256sum "$1" | cut -d' ' -f1; }
helpers(){
  [ "$(h $H/existing_safety_snapshot.py)" = e37cfd130c716f5bc014b91b6c7cd8c5ebdae85be916718cf07949d9f68f7c9c ] || die 'existing_safety_snapshot.py drift'
  [ "$(h $H/restart_safety_observer.py)" = a26b364f85df17e4fbbe05ff3174972b42180da3d0f44809cece967065dd47c1 ] || die 'restart_safety_observer.py drift'
}
snapshot_off(){
  # The producer is opt-in only. Refuse if anything would enable it.
  systemctl --user show atlas-sensor-recovery -p Environment | grep -q 'ATLAS_RESTART_SNAPSHOT' && die 'unit environment sets ATLAS_RESTART_SNAPSHOT'
  # The unit reads EnvironmentFile=-%h/.config/project-atlas/hardware.env; services also inherit the
  # user manager environment.
  grep -rqs ATLAS_RESTART_SNAPSHOT $HOME/.config/systemd/user/atlas-sensor-recovery.service $HOME/.config/systemd/user/atlas-sensor-recovery.service.d $HOME/.config/project-atlas/hardware.env && die 'snapshot opt-in present in unit/drop-in/env file'
  systemctl --user show-environment | grep -q '^ATLAS_RESTART_SNAPSHOT=' && die 'user manager environment sets ATLAS_RESTART_SNAPSHOT'
  return 0
}
put(){ # put SRC EXPECTED_SHA : atomic same-directory replace, keep jetson:jetson 644 and original mtime
  cmp -s "$1" "$T" && return 0
  tmp=$(mktemp "$T.XXXXXX") || die mktemp
  cat "$1" > "$tmp"; chmod 644 "$tmp"; touch -d "$MTIME" "$tmp"
  [ "$(h $tmp)" = "$2" ] || { rm -f "$tmp"; die 'staged bytes wrong'; }
  mv -f "$tmp" "$T"
  [ "$(h $T)" = "$2" ] || die 'post-write hash mismatch'
}
