#!/bin/bash
# Exact rollback: original manager bytes b0fb5b43 (jetson:jetson 755, original mtime) and the 8 original
# default.target.wants links. No restart, reload or reboot.
D=$(cd "$(dirname "$0")" && pwd); . "$D/common.sh"
[ "$(id -un)" = jetson ] || die 'run as jetson'
cur=$(h $S); [ "$cur" = "$NEW" ] || [ "$cur" = "$OLD" ] || die "unknown manager bytes $cur; not overwriting"
installs_ok
put "$D/backup/atlas_feature_on_demand.py.b0fb5b43" "$OLD"
for f in $FEATURES; do systemctl --user enable --no-reload "$f.service" >/dev/null 2>&1 || die "enable $f failed"; done
[ "$(links)" = "$(cat $D/backup/links.before)" ] || die 'links differ from the recorded originals'
rm -f "$D/APPLIED"
echo "ROLLED BACK: manager $OLD, 8 original autostart links restored (no restart)."
