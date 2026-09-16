#!/usr/bin/env bash
# Bounded ownership correction for the installed self-dial RNDIS modem.
set -euo pipefail
test "$(id -u)" = 0
src="$(cd -- "$(dirname -- "$0")" && pwd)"
guard="atlas-network-owner-restore-$(date +%s)"
systemd-run --unit="$guard" --on-active=90s /usr/bin/python3 "$src/test_network_handover_root.py" --restore
systemctl stop atlas-network-fallback.service
trap 'systemctl start atlas-network-fallback.service' EXIT
test "$(cat /sys/class/net/usb0/device/../idVendor)" = 1e0e
test "$(basename "$(readlink -f /sys/class/net/usb0/device/driver)")" = rndis_host
rule=/etc/udev/rules.d/99-atlas-sim8230-rndis-net.rules
install -d -m 700 /var/backups/atlas-network
backup="$(mktemp -d /var/backups/atlas-network/rndis-XXXXXXXX)"
test ! -f "$rule" || cp -p "$rule" "$backup/previous.rules"
install -m 644 "$src/../config/99-atlas-sim8230-rndis-net.rules" "$rule"
if test -f /etc/udev/rules.d/78-atlas-sim8230-rndis-net.rules; then
  mv /etc/udev/rules.d/78-atlas-sim8230-rndis-net.rules "$backup/superseded-78.rules"
fi
udevadm control --reload-rules
udevadm trigger --action=change /sys/class/net/usb0
udevadm settle
udevadm info -q property /sys/class/net/usb0 | grep '^ID_MM_PORT_IGNORE=1$'
udevadm info -q property /sys/class/net/usb0 | grep '^ID_MM_CANDIDATE=0$'
systemctl restart ModemManager
# NetworkManager 1.36 does not rediscover a net port previously removed by MM
# until its inventory is rebuilt. A one-time restart uses saved autoconnect
# profiles and the independent rollback timer above.
systemctl restart NetworkManager
for _ in $(seq 1 45); do
  if nmcli -g GENERAL.TYPE device show usb0 2>/dev/null | grep -q ethernet; then break; fi
  sleep 1
done
if ! nmcli -g GENERAL.TYPE device show usb0 2>/dev/null | grep -q ethernet; then
  if test -f "$backup/previous.rules"; then
    cp -p "$backup/previous.rules" "$rule"
  else
    mv "$rule" "$backup/not-applied.rules"
  fi
  udevadm control --reload-rules
  udevadm trigger --action=change /sys/class/net/usb0
  systemctl restart ModemManager
  echo 'RNDIS ownership not verified; previous rule restored.'
  exit 1
fi
if ! nmcli connection show ATLAS-Cellular-RNDIS >/dev/null 2>&1; then
  nmcli connection add type ethernet ifname usb0 con-name ATLAS-Cellular-RNDIS \
    connection.autoconnect yes connection.autoconnect-priority 90 \
    connection.metered yes ipv4.method auto ipv4.route-metric 600 ipv6.method disabled
fi
nmcli --wait 25 connection up ATLAS-Cellular-RNDIS
sleep 30
nmcli -g GENERAL.CONNECTION device show usb0 | grep '^ATLAS-Cellular-RNDIS$'
curl -4 --noproxy '*' --interface usb0 --connect-timeout 3 --max-time 8 -fsS -o /dev/null https://1.1.1.1/cdn-cgi/trace
echo "RNDIS DHCP profile live; saved Wi-Fi profile retained; backup=$backup"
systemctl stop "$guard.timer"
