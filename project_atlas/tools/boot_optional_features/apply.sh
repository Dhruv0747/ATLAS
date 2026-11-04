#!/bin/bash
# Install the startup-wait manager (5bcd4f08) and remove the 8 optional AI units' boot autostart links.
# The running manager (and any running feature) is untouched; all of this takes effect at the next boot.
D=$(cd "$(dirname "$0")" && pwd); . "$D/common.sh"
[ "$(id -un)" = jetson ] || die 'run as jetson'
( cd "$D" && sha256sum -c --quiet SHA256SUMS ) || die 'package manifest'
[ "$(h $S)" = "$OLD" ] || die 'live manager drift (expected b0fb5b43)'
[ "$(stat -c '%U:%G %a' $S)" = 'jetson:jetson 755' ] || die 'manager owner/mode drift'
[ "$(h $U/atlas-feature-on-demand.service)" = "$MANAGER_UNIT" ] || die 'manager unit drift'
installs_ok
[ "$(links | wc -l)" = 8 ] || die 'expected all 8 optional autostart links before apply'
[ -e "$D/APPLIED" ] && die 'already applied'
mkdir -p "$D/backup"; cp -p "$S" "$D/backup/atlas_feature_on_demand.py.b0fb5b43"; links > "$D/backup/links.before"
[ "$(h $D/backup/atlas_feature_on_demand.py.b0fb5b43)" = "$OLD" ] || die 'backup mismatch'
put "$D/atlas_feature_on_demand.py" "$NEW"
for f in $FEATURES; do systemctl --user disable --no-reload "$f.service" || { echo 'disable failed; rolling back'; bash "$D/rollback.sh"; exit 1; }; done
[ -z "$(links)" ] || die 'autostart links remain'
date -Is > "$D/APPLIED"
echo "APPLIED: manager $NEW installed (running PID unchanged); 8 optional autostart links removed. Effective next boot."
