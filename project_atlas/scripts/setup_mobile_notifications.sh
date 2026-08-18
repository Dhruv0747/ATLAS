#!/usr/bin/env bash
set -Eeuo pipefail

config_dir="${HOME}/.config/project-atlas"
config_file="${config_dir}/notifications.env"
unit_src="/home/jetson/project_atlas/systemd/user/atlas-mobile-notifier.service"
unit_dst="${HOME}/.config/systemd/user/atlas-mobile-notifier.service"

mkdir -p "${config_dir}" "${HOME}/.config/systemd/user"
chmod 700 "${config_dir}"

if [[ ! -s "${config_file}" ]]; then
  topic="atlas-dhruv-$(tr -d '-' </proc/sys/kernel/random/uuid)"
  {
    printf 'ATLAS_NTFY_SERVER=https://ntfy.sh\n'
    printf 'ATLAS_NTFY_TOPIC=%s\n' "${topic}"
    printf 'ATLAS_DASHBOARD_URL=http://100.87.208.71:8088/\n'
    printf 'ATLAS_LOW_BATTERY_PERCENT=20\n'
    printf 'ATLAS_FULL_BATTERY_PERCENT=99\n'
  } >"${config_file}"
  chmod 600 "${config_file}"
else
  topic="$(sed -n 's/^ATLAS_NTFY_TOPIC=//p' "${config_file}" | head -n1)"
fi

install -m 0644 "${unit_src}" "${unit_dst}"
systemctl --user daemon-reload
systemctl --user enable --now atlas-mobile-notifier.service

printf '\nATLAS mobile notifications are enabled.\n'
printf 'Install the ntfy app, then subscribe to this private topic:\n\n'
printf '  %s\n\n' "${topic}"
printf 'Android direct link: ntfy://ntfy.sh/%s?display=Project+ATLAS\n' "${topic}"
printf 'Web test page: https://ntfy.sh/%s\n' "${topic}"
