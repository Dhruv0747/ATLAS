# Boot CPU correction: optional AI features off at boot until requested. Run on the Jetson as user jetson.
# Never restarts, reloads or reboots anything; effective at the next (separately approved) boot.
set -u
S=$HOME/project_atlas/scripts/atlas_feature_on_demand.py
U=$HOME/.config/systemd/user
OLD=b0fb5b43d36e1dc95fa6dc7849f4d3783e9063c71470f1ca34545ba56468d32e
NEW=5bcd4f088e84577a4eb7fefe9020b1f6bab6bfc3a64ea94c30c7af87a36f7661
MANAGER_UNIT=4e74deeb1a153c8893d05df5ce4d4192e8bc0b05e85ca8949469c97c5f770e58
MTIME='2026-10-29 20:16:42.284951444 +0530'
FEATURES="atlas-vision-lidar-fusion atlas-person-sensor-fusion atlas-experience-store atlas-agent-team atlas-ai-annotator atlas-follow-person atlas-camera-tracker atlas-active-vision"
die(){ echo "ABORT: $*"; exit 1; }
h(){ sha256sum "$1" | cut -d' ' -f1; }
links(){ for f in $FEATURES; do l=$U/default.target.wants/$f.service; [ -L "$l" ] && echo "$f -> $(readlink "$l")"; done; }
installs_ok(){ for f in $FEATURES; do [ "$(sed -n '/^\[Install\]/,$p' $U/$f.service | grep -v '^\[Install\]' | grep .)" = 'WantedBy=default.target' ] || die "$f [Install] is not exactly WantedBy=default.target"; done; }
put(){ # put SRC SHA : atomic same-directory replace, jetson:jetson 755, original mtime
  tmp=$(mktemp "$S.XXXXXX") || die mktemp
  cat "$1" > "$tmp"; chmod 755 "$tmp"; touch -d "$MTIME" "$tmp"
  [ "$(h $tmp)" = "$2" ] || { rm -f "$tmp"; die 'staged bytes wrong'; }
  mv -f "$tmp" "$S"; [ "$(h $S)" = "$2" ] || die 'post-write hash mismatch'
}
