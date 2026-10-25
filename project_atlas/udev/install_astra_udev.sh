#!/bin/bash
# Install the port-independent Astra access rule. Run ON THE JETSON:  sudo bash install_astra_udev.sh
# Backs up the current rule first; touches only Orbbec 2bc5 devices; never resets or opens the camera.
set -euo pipefail
D=/home/jetson/project-atlas-migration/astra_usb_20261025
NEW=$D/99-atlas-astra-access.rules
LIVE=/etc/udev/rules.d/99-atlas-astra-access.rules
[ "$(id -u)" = 0 ] || { echo "Run with sudo"; exit 1; }
echo "6f891d6a04d146b7417115db18509d20e6677799c67e61aa290e2ce4cabfa53f  $NEW" | sha256sum -c -
mkdir -p $D/backup
[ -e $D/backup/99-atlas-astra-access.rules.orig ] || cp -p $LIVE $D/backup/99-atlas-astra-access.rules.orig
echo "Backup: $(sha256sum $D/backup/99-atlas-astra-access.rules.orig)"
install -o root -g root -m 0644 $NEW $LIVE
udevadm control --reload
udevadm trigger --action=change --subsystem-match=usb --attr-match=idVendor=2bc5
udevadm settle -t 10
echo "Installed: $(sha256sum $LIVE)"
ls -l /dev/atlas-astra-depth-usb /dev/atlas-astra-rgb-usb && ls -lL /dev/atlas-astra-depth-usb /dev/atlas-astra-rgb-usb \
  && echo "OK: Astra access links present" || { echo "FAILED: links missing — run: sudo bash $D/rollback_astra_udev.sh"; exit 2; }
