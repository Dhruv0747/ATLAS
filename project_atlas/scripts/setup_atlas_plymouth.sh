#!/usr/bin/env bash
set -euo pipefail

theme_dir=/usr/share/plymouth/themes/atlas
backup_dir=/home/jetson/project_atlas/backups/plymouth_atlas_$(date +%Y%m%d_%H%M%S)
mkdir -p "$backup_dir"

cp -a /usr/share/plymouth/themes/default.plymouth "$backup_dir/default.plymouth.before" 2>/dev/null || true
readlink -f /usr/share/plymouth/themes/default.plymouth > "$backup_dir/default_theme_target.txt" 2>/dev/null || true

sudo mkdir -p "$theme_dir"
sudo cp /home/jetson/project_atlas/scripts/atlas_boot_logo.png "$theme_dir/atlas_source.png"
sudo cp /home/jetson/project_atlas/scripts/atlas.plymouth "$theme_dir/atlas.plymouth"
sudo cp /home/jetson/project_atlas/scripts/atlas.script "$theme_dir/atlas.script"

python3 - <<'PY'
from pathlib import Path
from PIL import Image, ImageEnhance

theme = Path("/usr/share/plymouth/themes/atlas")
src = theme / "atlas_source.png"
out = theme / "atlas_logo_boot.png"
img = Image.open(src).convert("RGBA")
img.thumbnail((720, 420), Image.Resampling.LANCZOS)
img = ImageEnhance.Sharpness(img).enhance(1.12)
img.save(out)
PY

sudo chmod 644 "$theme_dir"/atlas.plymouth "$theme_dir"/atlas.script "$theme_dir"/atlas_logo_boot.png "$theme_dir"/atlas_source.png
sudo ln -sfn "$theme_dir/atlas.plymouth" /usr/share/plymouth/themes/default.plymouth
echo password | sudo -S update-initramfs -u

echo "ATLAS Plymouth theme installed."
echo "Backup: $backup_dir"
readlink -f /usr/share/plymouth/themes/default.plymouth
