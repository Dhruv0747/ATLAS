#!/usr/bin/env bash
set -euo pipefail

stamp="$(date +%Y%m%d_%H%M%S)"
mkdir -p /home/jetson/project_atlas/backups
tar -czf "/home/jetson/project_atlas/backups/atlas_plymouth_script_blank_${stamp}.tgz" -C /usr/share/plymouth/themes atlas
python3 /home/jetson/project_atlas/scripts/install_atlas_twostep.py
update-alternatives --set default.plymouth /usr/share/plymouth/themes/atlas/atlas.plymouth
update-initramfs -u
echo "Installed ATLAS two-step boot theme"
echo "Backup: /home/jetson/project_atlas/backups/atlas_plymouth_script_blank_${stamp}.tgz"
