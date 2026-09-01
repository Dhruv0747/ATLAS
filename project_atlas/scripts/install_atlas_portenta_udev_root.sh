#!/usr/bin/env bash
set -Eeuo pipefail

RULE_SOURCE=/home/jetson/project_atlas/udev/99-atlas-portenta.rules
RULE_TARGET=/etc/udev/rules.d/99-atlas-portenta.rules

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
if [[ ! -f ${RULE_SOURCE} ]]; then
  echo "Missing ${RULE_SOURCE}; deploy the ATLAS source first." >&2
  exit 1
fi

install -m 0644 "${RULE_SOURCE}" "${RULE_TARGET}"
udevadm control --reload-rules
udevadm trigger --subsystem-match=tty
udevadm trigger --subsystem-match=usb --attr-match=idVendor=2341 --attr-match=idProduct=035b

echo "Installed ${RULE_TARGET}"
echo "Reconnect the Portenta USB-C cable, then verify:"
echo "  ls -l /dev/atlas-portenta /dev/serial/by-id/*Portenta*"
echo "No sensor-hub service was enabled or started."
