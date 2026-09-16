#!/usr/bin/env bash
# Install while Wi-Fi works. This creates, but DOES NOT activate, the hotspot.
set -euo pipefail
hotspot_password=''
if test "${1:-}" != '--existing-profile'; then
  read -r -s -p 'Hotspot password (8-63 characters): ' hotspot_password
  hotspot_password="${hotspot_password%$'\r'}"
  echo
  test "${#hotspot_password}" -ge 8 && test "${#hotspot_password}" -le 63 || { echo 'Invalid password length'; exit 1; }
fi
test "$(id -u)" = 0 || { echo 'Run with sudo.'; exit 1; }
src="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$src"
for command in python3 nmcli ip curl iw resolvectl dnsmasq; do
  command -v "$command" >/dev/null || { echo "Missing dependency: $command"; exit 1; }
done
python3 "$src/test_network_fallback.py"
python3 "$src/test_hotspot_portal.py"
wifi_if=wlP1p1s0
cell_if=usb0
wifi_uuid="$(nmcli -g GENERAL.CON-UUID device show "$wifi_if")"
test -n "$wifi_uuid" && test "$wifi_uuid" != '--'
wifi_mode="$(nmcli -g 802-11-wireless.mode connection show "$wifi_uuid")"
test "$wifi_mode" = infrastructure || { echo 'Install while connected to home Wi-Fi, not an AP.'; exit 1; }
iw list | grep -qE '^[[:space:]]+\* AP$' || { echo 'AP mode not supported'; exit 1; }
python3 -c 'import atlas_network_fallback as n; assert n.probe("wlP1p1s0")["ok"], "Wi-Fi Internet must work during installation"'
install -d -m 700 /var/backups/atlas-network
backup="$(mktemp -d /var/backups/atlas-network/install-XXXXXXXX)"
for path in /etc/atlas-network.json /etc/atlas-hotspot-dnsmasq.conf /etc/systemd/system/atlas-network-fallback.service /etc/systemd/system/atlas-hotspot-dhcp.service /usr/local/lib/atlas-network/atlas_network_fallback.py; do
  if test -f "$path"; then cp -p -- "$path" "$backup/$(basename "$path")"; fi
done
nmcli -g connection.autoconnect,connection.autoconnect-priority,ipv4.route-metric connection show "$wifi_uuid" > "$backup/wifi-prior-settings.txt"
hotspot_uuid="$(nmcli -g connection.uuid connection show ATLAS-Rescue 2>/dev/null || true)"
if test -z "$hotspot_uuid"; then
  test -n "$hotspot_password" || { echo 'Existing ATLAS-Rescue profile missing'; exit 1; }
  nmcli connection add type wifi ifname "$wifi_if" con-name ATLAS-Rescue autoconnect no ssid ATLAS-Rescue \
    802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
    802-11-wireless.powersave 2 802-11-wireless-security.key-mgmt wpa-psk \
    802-11-wireless-security.proto rsn 802-11-wireless-security.pairwise ccmp \
    802-11-wireless-security.psk "$hotspot_password" \
    ipv4.method manual ipv4.addresses 10.42.0.1/24 ipv4.never-default yes ipv6.method disabled
  unset hotspot_password
  hotspot_uuid="$(nmcli -g connection.uuid connection show ATLAS-Rescue)"
fi
unset hotspot_password
test -n "$hotspot_uuid"
install -d -m 755 /usr/local/lib/atlas-network
install -m 644 "$src/atlas_network_fallback.py" /usr/local/lib/atlas-network/
install -m 644 "$src/atlas_wifi_manager.py" /usr/local/lib/atlas-network/
install -m 644 "$src/atlas_hotspot_portal.py" /usr/local/lib/atlas-network/
install -m 644 "$src/../services-disabled/atlas-network-fallback.service" /etc/systemd/system/
install -m 644 "$src/../services-disabled/atlas-hotspot-dhcp.service" /etc/systemd/system/
install -m 644 "$src/../services-disabled/atlas-hotspot-portal.service" /etc/systemd/system/
python3 - "$wifi_uuid" "$hotspot_uuid" <<'PY'
import json, os, pathlib, sys
config = dict(wifi_interface='wlP1p1s0', cellular_interface='usb0', wifi_uuid=sys.argv[1],
              hotspot_uuid=sys.argv[2], hotspot_ssid='ATLAS-Rescue')
path = pathlib.Path('/etc/atlas-network.json')
path.write_text(json.dumps(config, indent=2)+'\n')
path.chmod(0o600)
pathlib.Path('/etc/atlas-hotspot-dnsmasq.conf').write_text('''# AP captive DNS only: never forward queries to the Internet.
port=53
no-resolv
no-hosts
address=/#/10.42.0.1
listen-address=10.42.0.1
except-interface=lo
interface=wlP1p1s0
bind-dynamic
dhcp-range=10.42.0.20,10.42.0.120,255.255.255.0,1h
dhcp-option=3,10.42.0.1
dhcp-option=6,10.42.0.1
dhcp-authoritative
dhcp-leasefile=/run/atlas-hotspot/leases
log-dhcp
''')
PY
# Existing Wi-Fi profile stays intact, and we do not bounce its connection.
nmcli connection modify "$wifi_uuid" connection.autoconnect yes connection.autoconnect-priority 100 ipv4.route-metric 50
dnsmasq --test --conf-file=/etc/atlas-hotspot-dnsmasq.conf
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/atlas-network-fallback.service /etc/systemd/system/atlas-hotspot-dhcp.service /etc/systemd/system/atlas-hotspot-portal.service
python3 /usr/local/lib/atlas-network/atlas_network_fallback.py --monitor --once
systemctl enable atlas-network-fallback.service
systemctl restart atlas-network-fallback.service
echo "Installed; backup: $backup"
echo 'Hotspot profile staged. No forced Wi-Fi disconnect, modem reset, motor, steering or navigation command issued.'
