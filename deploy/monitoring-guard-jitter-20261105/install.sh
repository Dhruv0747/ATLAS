#!/bin/bash
# Owner-run installer: monitoring guard encoder-jitter tolerance (2026-11-05). Run: sudo bash install.sh
set -euo pipefail
cd "$(dirname "$0")"
G=/usr/local/libexec/atlas-monitoring-guard.py
ST=/var/lib/atlas-monitoring
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
[ "$(sha256sum < $G | cut -d' ' -f1)" = 188d53db127ceb49e4c1c36fed61caacd05b3ab4f70e190f08f83c3b6fba802a ] || { echo "live guard changed since review; not installing"; exit 1; }
[ "$(sha256sum < atlas-monitoring-guard.py | cut -d' ' -f1)" = ca007ee2eca9d729fdaec44cc9b7cc8f71979a4bc39008808978b7fc25e075db ] || { echo "patched file changed; not installing"; exit 1; }
if [ -e $ST/FAULT.json ]; then
  echo "===== Current latch (review before clearing) ====="; cat $ST/FAULT.json; echo
  read -r -p "Was the rover stationary (not driven or pushed) at that time? Clear this latch? [y/N] " a
  [ "$a" = y ] || [ "$a" = Y ] || { echo "Not cleared. Nothing installed."; exit 1; }
fi
cp -p $G $G.before-jitter-20261105
install -o root -g root -m 0644 atlas-monitoring-guard.py $G
python3 -I -m py_compile $G
[ -e $ST/FAULT.json ] && mv $ST/FAULT.json $ST/FAULT.reviewed-$(date +%Y%m%d-%H%M%S).json
rm -f $ST/observer-active.json
systemctl restart atlas-monitoring-firewall
systemctl restart atlas-monitoring-watchdog atlas-monitoring-exporter
sleep 6
systemctl is-active atlas-monitoring-firewall atlas-monitoring-watchdog atlas-monitoring-exporter
echo "Installed. Rollback: sudo bash $(pwd)/rollback.sh"
