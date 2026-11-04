# Status-cache correction for the LIVE dashboard (rover-status-web). Run on the Jetson as jetson.
# Never restarts, reloads or reboots anything: new code loads only at a separately approved Web restart.
set -u
T=$HOME/project_atlas/scripts/atlas_status_web.py
LIVE=4b5906f7728a914a01b016d501dbcf673ea364679c5f0df4f8639ab5851317b2
CAND=68f5379c1635e443d3065620b2e9a8503c570457a45dd24a5a6a9f07abe05584
MTIME='2026-10-29 14:45:58.451636026 +0530'
die(){ echo "ABORT: $*"; exit 1; }
h(){ sha256sum "$1" | cut -d' ' -f1; }
put(){ tmp=$(mktemp "$T.XXXXXX") || die mktemp; cat "$1" > "$tmp"; chmod 644 "$tmp"; touch -d "$MTIME" "$tmp"
  [ "$(h $tmp)" = "$2" ] || { rm -f "$tmp"; die 'staged bytes wrong'; }; mv -f "$tmp" "$T"; [ "$(h $T)" = "$2" ] || die 'post-write mismatch'; }
