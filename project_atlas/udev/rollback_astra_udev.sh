#!/bin/bash
# Restore the previous fixed-port Astra rule.  Run ON THE JETSON:  sudo bash rollback_astra_udev.sh
set -euo pipefail
D=/home/jetson/project-atlas-migration/astra_usb_20261025
[ "$(id -u)" = 0 ] || { echo "Run with sudo"; exit 1; }
echo "54a8bc029e21364d1d259f11ebf3cefcf10ad263c45ae98aabda880393c2e7c4  $D/backup/99-atlas-astra-access.rules.orig" | sha256sum -c -
install -o root -g root -m 0644 $D/backup/99-atlas-astra-access.rules.orig /etc/udev/rules.d/99-atlas-astra-access.rules
udevadm control --reload
udevadm trigger --action=change --subsystem-match=usb --attr-match=idVendor=2bc5
udevadm settle -t 10
echo "Restored: $(sha256sum /etc/udev/rules.d/99-atlas-astra-access.rules)"
