#!/bin/bash
# Owner-run: also allow Dhruv's Mac (192.168.1.4) to read the monitoring exporter. PC (.7) keeps working. Run: sudo bash install.sh
set -euo pipefail
cd "$(dirname "$0")"
G=/usr/local/libexec/atlas-monitoring-guard.py; N=/etc/atlas-monitoring/atlas-monitor.nft; ST=/var/lib/atlas-monitoring
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
[ "$(sha256sum < $G | cut -d' ' -f1)" = 9a98a2eabe0865d56b5e4456b9c9cf5a88c66a775447519dd4f03183f30acc66 ] || { echo "live guard changed since review; stopping"; exit 1; }
[ "$(sha256sum < $N | cut -d' ' -f1)" = 2aec463e6b2b47bbc8c0ab029fd368be3c75ef7c9f64101a3104dcf6231d0619 ] || { echo "live firewall rule changed since review; stopping"; exit 1; }
[ "$(sha256sum < atlas-monitoring-guard.py | cut -d' ' -f1)" = 93d0796ea964d2df4b46b18e786f119b385b811ef7d1a8f3f4be511c85172e36 ] && [ "$(sha256sum < atlas-monitor.nft | cut -d' ' -f1)" = 59936ce7eefbfa68d3cdcf8b3fcccb40ed0d5afc309971777b249e6683a4ef34 ] || { echo "prepared files changed; stopping"; exit 1; }
if [ -e $ST/FAULT.json ]; then
  echo "===== Current latch (review before clearing) ====="; cat $ST/FAULT.json; echo
  read -r -p "Was any wheel movement made by you on purpose, and is the rover now parked with E-STOP latched? Clear it? [y/N] " a
  [ "$a" = y ] || [ "$a" = Y ] || { echo "Not cleared. Nothing changed."; exit 1; }
fi
systemctl stop atlas-monitoring-exporter atlas-monitoring-watchdog || true
cp -p $G $G.before-allow-mac-20261105; cp -p $N $N.before-allow-mac-20261105
install -o root -g root -m 0644 atlas-monitoring-guard.py $G
install -o root -g root -m 0644 atlas-monitor.nft $N
python3 -I -m py_compile $G
nft delete table inet atlas_monitor 2>/dev/null || true
[ -e $ST/FAULT.json ] && mv $ST/FAULT.json $ST/FAULT.reviewed-$(date +%Y%m%d-%H%M%S).json
rm -f $ST/observer-active.json
systemctl restart atlas-monitoring-firewall
systemctl restart atlas-monitoring-watchdog atlas-monitoring-exporter
sleep 6
systemctl is-active atlas-monitoring-firewall atlas-monitoring-watchdog atlas-monitoring-exporter
nft list table inet atlas_monitor | grep saddr
echo "Done. Rollback: sudo bash $(pwd)/rollback.sh"
