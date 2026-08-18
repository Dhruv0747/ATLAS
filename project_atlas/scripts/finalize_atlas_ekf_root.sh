#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 2
fi

echo "Disabling the obsolete system-level ATLAS EKF unit..."
systemctl disable --now atlas-ekf.service

if systemctl is-enabled --quiet atlas-ekf.service; then
  echo "ERROR: system-level atlas-ekf.service is still enabled" >&2
  exit 1
fi

legacy_unit=/etc/systemd/system/atlas-ekf.service
if [[ -e ${legacy_unit} ]]; then
  echo "Removing obsolete unit: ${legacy_unit}"
  rm -- "${legacy_unit}"
fi

systemctl daemon-reload
systemctl reset-failed atlas-ekf.service 2>/dev/null || true

if [[ $(systemctl show atlas-ekf.service -p LoadState --value) != not-found ]]; then
  echo "ERROR: obsolete system-level atlas-ekf.service still exists" >&2
  exit 1
fi

echo "System-level EKF removed. The commissioned user-level EKF now exclusively owns /odom."
echo "No motor, steering, mapping, or navigation command was issued."
