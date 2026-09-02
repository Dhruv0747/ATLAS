#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_rule="${script_dir}/../udev/70-project-atlas-uno-r4.rules"
target_rule=/etc/udev/rules.d/70-project-atlas-uno-r4.rules

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 1
fi
if [[ ! -f ${source_rule} ]]; then
  echo "Missing source rule: ${source_rule}" >&2
  exit 1
fi

install -m 0644 "${source_rule}" "${target_rule}"
udevadm control --reload-rules
if [[ -e /sys/class/tty/ttyACM0 ]]; then
  udevadm trigger --action=change /sys/class/tty/ttyACM0
  udevadm settle
fi

echo "Installed ${target_rule}"
echo "The rule excludes only Arduino 2341:1002 serial E4B063836708 from ModemManager."
echo "The SIMCom cellular modem remains managed normally."
