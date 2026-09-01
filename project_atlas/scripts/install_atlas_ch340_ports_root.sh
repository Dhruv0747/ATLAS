#!/usr/bin/env bash
set -Eeuo pipefail

RULE_SOURCE=/home/jetson/project_atlas/udev/99-atlas-ch340-ports.rules
RULE_TARGET=/etc/udev/rules.d/99-atlas-ch340-ports.rules
OLD_RULE=/etc/udev/rules.d/99-project-atlas-yahboom.rules

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
if [[ ! -f ${RULE_SOURCE} ]]; then
  echo "Missing ${RULE_SOURCE}; deploy the ATLAS source first." >&2
  exit 1
fi

install -m 0644 "${RULE_SOURCE}" "${RULE_TARGET}"
rm -f "${OLD_RULE}"
udevadm control --reload-rules
udevadm trigger --subsystem-match=tty

echo "Installed fixed ATLAS CH340 port identities:"
ls -l /dev/atlas-yahboom /dev/atlas-mega 2>/dev/null || true
echo "Expected: atlas-yahboom -> USB path 2.4; atlas-mega -> USB path 2.2.3"
echo "No motor, navigation, or sensor-hub service was enabled or started."
