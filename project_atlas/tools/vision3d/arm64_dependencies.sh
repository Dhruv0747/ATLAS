#!/bin/bash
# PC-only isolated apt metadata/cache. Never installs target packages into host.
set -euo pipefail
root=/root/atlas-stage29
source_dir=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$root/apt/lists/partial" "$root/apt/archives/partial"
args=(-o APT::Architecture=arm64 -o APT::Architectures=arm64
  -o Dir::Etc::sourcelist="$source_dir/arm64_ubuntu.sources.list"
  -o Dir::Etc::sourceparts=- -o Dir::State::status=/dev/null
  -o Dir::State::lists="$root/apt/lists" -o Dir::Cache::archives="$root/apt/archives")
case "${1:-}" in
  update) apt-get "${args[@]}" update ;;
  download) apt-get "${args[@]}" --download-only --no-install-recommends -y install \
    libopencv-dev libuvc-dev libgoogle-glog-dev libeigen3-dev python3-dev python3-numpy libboost-dev \
    libssl-dev libtinyxml2-dev libyaml-cpp-dev libasio-dev libconsole-bridge-dev \
    libboost-system-dev libboost-filesystem-dev libboost-thread-dev libyaml-dev libjsoncpp-dev liblz4-dev libzstd-dev \
    libspdlog-dev libfmt-dev libcurl4-openssl-dev libusb-1.0-0-dev nlohmann-json3-dev ;;
  *) echo 'Choose update or download; no install operation supported' >&2; exit 2 ;;
esac
