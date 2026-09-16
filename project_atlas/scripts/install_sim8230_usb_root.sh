#!/bin/bash
set -euo pipefail
# Restore the manufacturer-documented USB serial binding after every boot.
install -d /etc/systemd/system
cat > /etc/systemd/system/atlas-sim8230-usb.service <<'UNIT'
[Unit]
Description=ATLAS SIM8230 USB serial driver ID
After=systemd-modules-load.service
[Service]
Type=oneshot
ExecStart=/sbin/modprobe option
ExecStart=/bin/sh -c 'echo 1e0e 907b > /sys/bus/usb-serial/drivers/option1/new_id'
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable atlas-sim8230-usb.service
systemctl start atlas-sim8230-usb.service
