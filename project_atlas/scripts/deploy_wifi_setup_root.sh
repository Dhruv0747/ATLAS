#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0
src="$(cd -- "$(dirname -- "$0")" && pwd)"
python3 "$src/test_wifi_setup.py"
python3 "$src/test_network_fallback.py"
python3 -m py_compile "$src/atlas_status_web.py" "$src/atlas_wifi_manager.py" "$src/atlas_wifi_web.py"
backup="$(mktemp -d /var/backups/atlas-network/wifi-XXXXXXXX)"
for name in atlas_network_fallback.py atlas_wifi_manager.py; do
  test ! -f "/usr/local/lib/atlas-network/$name" || cp -p "/usr/local/lib/atlas-network/$name" "$backup/"
  install -m 644 "$src/$name" "/usr/local/lib/atlas-network/$name.new"
  mv "/usr/local/lib/atlas-network/$name.new" "/usr/local/lib/atlas-network/$name"
done
cp -p /etc/systemd/system/atlas-network-fallback.service "$backup/"
install -m 644 "$src/../services-disabled/atlas-network-fallback.service" /etc/systemd/system/
for name in atlas_wifi_web.py atlas_status_web.py; do
  test ! -f "/home/jetson/project_atlas/scripts/$name" || cp -p "/home/jetson/project_atlas/scripts/$name" "$backup/"
  install -o jetson -g jetson -m 644 "$src/$name" "/home/jetson/project_atlas/scripts/$name.new"
  mv "/home/jetson/project_atlas/scripts/$name.new" "/home/jetson/project_atlas/scripts/$name"
done
systemctl daemon-reload
systemctl restart atlas-network-fallback.service
runuser -u jetson -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user restart rover-status-web.service
echo "Wi-Fi setup deployed. Backup: $backup. No locomotion commands issued."
