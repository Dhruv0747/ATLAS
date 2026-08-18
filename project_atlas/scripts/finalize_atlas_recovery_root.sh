#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 2
fi

legacy_unit=/etc/systemd/system/atlas-tight-recovery.service

echo "Disabling the obsolete system-level ATLAS recovery unit..."
systemctl disable --now atlas-tight-recovery.service 2>/dev/null || true

if [[ -e ${legacy_unit} ]]; then
  echo "Removing obsolete unit: ${legacy_unit}"
  rm -- "${legacy_unit}"
fi

systemctl daemon-reload
systemctl reset-failed atlas-tight-recovery.service 2>/dev/null || true

if [[ $(systemctl show atlas-tight-recovery.service -p LoadState --value) != not-found ]]; then
  echo "ERROR: obsolete system-level atlas-tight-recovery.service still exists" >&2
  exit 1
fi

echo "System-level recovery unit removed."
echo "No motor, steering, mapping, or navigation command was issued."
