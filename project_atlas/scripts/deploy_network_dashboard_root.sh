#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" = 0
src="$(cd -- "$(dirname -- "$0")" && pwd)"
python3 "$src/test_network_fallback.py"
python3 -m py_compile "$src/atlas_network_fallback.py" "$src/atlas_status_web.py"
backup="$(mktemp -d /var/backups/atlas-network/dashboard-XXXXXXXX)"
for name in atlas_status_web.py atlas_diagnostics_ui.js; do
  cp -p "/home/jetson/project_atlas/scripts/$name" "$backup/"
  install -o jetson -g jetson -m 644 "$src/$name" "/home/jetson/project_atlas/scripts/$name.new"
  mv "/home/jetson/project_atlas/scripts/$name.new" "/home/jetson/project_atlas/scripts/$name"
done
cp -p /usr/local/lib/atlas-network/atlas_network_fallback.py "$backup/"
install -m 644 "$src/atlas_network_fallback.py" /usr/local/lib/atlas-network/atlas_network_fallback.py.new
mv /usr/local/lib/atlas-network/atlas_network_fallback.py.new /usr/local/lib/atlas-network/atlas_network_fallback.py
systemctl restart atlas-network-fallback.service
runuser -u jetson -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user restart rover-status-web.service
echo "Network agent and dashboard updated. Backup: $backup"
