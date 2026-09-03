#!/usr/bin/env bash
set -Eeuo pipefail

sketch_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
output_dir=${1:-"$sketch_dir/build-native-usb"}

arduino-cli compile \
  --fqbn arduino:renesas_uno:unor4wifi \
  --build-property 'build.defines=-DF_CPU=48000000 -DARDUINO_UNOR4_WIFI' \
  --output-dir "$output_dir" \
  "$sketch_dir"

echo "Native-USB firmware: $output_dir/atlas_uno_r4_i2c_hub.ino.bin"
