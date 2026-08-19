#!/usr/bin/env bash
set -Eeuo pipefail
python3 -m venv /home/jetson/project_atlas/venv-intercom
/home/jetson/project_atlas/venv-intercom/bin/pip install --upgrade pip
/home/jetson/project_atlas/venv-intercom/bin/pip install aiohttp aiortc pyserial
install -m 0644 /home/jetson/project_atlas/config/atlas-intercom.service /home/jetson/.config/systemd/user/atlas-intercom.service
systemctl --user daemon-reload
systemctl --user enable --now atlas-intercom.service
echo 'Publish port 8091 only through authenticated Tailscale HTTPS.'
