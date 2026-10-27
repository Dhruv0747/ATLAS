#!/usr/bin/env bash
# Download Yahboom's published ROS-Driver-Board firmware (source + release hex) into ./vendor_dl and
# verify the hashes recorded on 2026-10-27. Nothing is flashed. Vendor files are NOT committed to ATLAS.
# Sources (Yahboom Google Drive, linked from https://www.yahboom.net/study/ROSMASTER-A1 -> Code-Firmware
# -> "STM32 firmware expansion board", and https://www.yahboom.net/study/ROS-Driver-Board -> Code ->
# "Factory STM32 firmware").
set -Eeuo pipefail
cd "$(dirname "$0")"
mkdir -p vendor_dl
get() { curl -fsSL -m 300 "https://drive.usercontent.google.com/download?id=$1&export=download&confirm=t" -o "vendor_dl/$2"; }
get 1PcfjeBqjHqTzAm3gVLKu1r_bdFWfoIKC ROS-Driver-Board-FW-master.zip
get 1pBEAcfBIs7rrLiuH7XWZ-IntmaTJDGlF rosmaster_V3.6.5.hex
get 1qdSwsq-Z_RUO0l7AfmytXjpI0OLW9hv_ Rosmaster_V3.5.1.zip
get 18dwQO61Y85iOTOpaTxUVpVlDEyIj4hGZ rosmaster_V3.5.1.hex
(cd vendor_dl && sha256sum -c ../VENDOR.sha256)
