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
for tty_path in /sys/class/tty/ttyACM*; do
  [[ -e ${tty_path} ]] || continue
  udevadm trigger --action=change "${tty_path}"
done
udevadm settle

echo "Installed ${target_rule}"
echo "The rule excludes only the commissioned ATLAS UNO native/debug USB identities from ModemManager."
echo "The SIMCom cellular modem remains managed normally."
