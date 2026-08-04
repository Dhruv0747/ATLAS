#!/usr/bin/env bash
set -euo pipefail

stamp="$(date +%Y%m%d_%H%M%S)"
mkdir -p /home/jetson/project_atlas/backups
cp -a /usr/share/plymouth/themes/ubuntu-text "/home/jetson/project_atlas/backups/ubuntu_text_before_atlas_${stamp}"

mkdir -p /usr/share/plymouth/themes/atlas-text
cp /home/jetson/project_atlas/scripts/atlas-text.plymouth /usr/share/plymouth/themes/atlas-text/atlas-text.plymouth
chmod 644 /usr/share/plymouth/themes/atlas-text/atlas-text.plymouth

update-alternatives --install /usr/share/plymouth/themes/text.plymouth text.plymouth /usr/share/plymouth/themes/atlas-text/atlas-text.plymouth 200
update-alternatives --set text.plymouth /usr/share/plymouth/themes/atlas-text/atlas-text.plymouth
update-initramfs -u

echo "ATLAS text fallback installed"
echo "Backup: /home/jetson/project_atlas/backups/ubuntu_text_before_atlas_${stamp}"
