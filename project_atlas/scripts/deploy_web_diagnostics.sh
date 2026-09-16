#!/usr/bin/env bash
# Run as jetson. Only GNSS, web diagnostics and retired HDMI autostart change.
set -Ee -o pipefail
stage=/home/jetson/project-atlas-migration/web-diag-20260915/staging
scripts=/home/jetson/project_atlas/scripts
gnss=/home/jetson/project_atlas_ws/src/atlas_gnss_driver/atlas_gnss_driver/gnss_node.py
test -f "$stage/atlas_status_web.py"
test -f "$stage/atlas_diagnostics_ui.js"
test -f "$stage/atlas_web_diagnostics.py"
test -f "$stage/atlas_gnss_driver/gnss_node.py"
/usr/bin/python3 -m py_compile "$stage/atlas_status_web.py" "$stage/atlas_web_diagnostics.py" "$stage/atlas_gnss_driver/gnss_node.py"
/usr/bin/python3 "$stage/test_web_diagnostics.py"
/usr/bin/python3 "$stage/test_gnss_reconnect.py"
backup=$(mktemp -d /home/jetson/project-atlas-migration/web-diag-20260915/backup-XXXXXX)
cp -a "$scripts/atlas_status_web.py" "$backup/atlas_status_web.py"
cp -a "$gnss" "$backup/gnss_node.py"
cp -a /home/jetson/.config/autostart/project-atlas-dashboard.desktop "$backup/project-atlas-dashboard.desktop"
for file in atlas_web_diagnostics.py atlas_diagnostics_ui.js; do
    if test -f "$scripts/$file"; then cp -a "$scripts/$file" "$backup/$file"; fi
done
printf 'Rollback backup: %s\n' "$backup"
cp "$stage/atlas_gnss_driver/gnss_node.py" "$gnss"
source /opt/ros/humble/setup.bash
cd /home/jetson/project_atlas_ws
if ! colcon build --packages-select atlas_gnss_driver; then
    cp "$backup/gnss_node.py" "$gnss"
    echo 'GNSS build failed; source restored. No service restart performed.'
    exit 1
fi
for file in atlas_web_diagnostics.py atlas_diagnostics_ui.js atlas_status_web.py; do
    install -m 644 "$stage/$file" "$scripts/$file.new"
    mv "$scripts/$file.new" "$scripts/$file"
done
install -m 644 "$stage/project-atlas-dashboard.desktop" /home/jetson/.config/autostart/project-atlas-dashboard.desktop
systemctl --user mask --now 'app-project\x2datlas\x2ddashboard@autostart.service'
systemctl --user daemon-reload
systemctl --user enable atlas-gnss.service rover-status-web.service
systemctl --user restart atlas-gnss.service rover-status-web.service
systemctl --user is-active atlas-gnss.service rover-status-web.service
printf 'Deployed. No motor, steering, mapping or navigation commands issued.\n'
