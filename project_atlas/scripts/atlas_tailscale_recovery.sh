#!/usr/bin/env bash
set -Eeo pipefail

INTERCOM_TARGET="http://127.0.0.1:8091"

# Jetson networking can appear several seconds after tailscaled. Wait for a
# usable default route before asking tailscaled to reconnect.
for _ in $(seq 1 60); do
  if ip route show default | grep -q . && getent hosts controlplane.tailscale.com >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! ip route show default | grep -q .; then
  logger -t atlas-tailscale-recovery "No default route after boot; leaving Tailscale for its normal retry loop"
  exit 0
fi

# A daemon can be active while its backend is stuck in NoState. One bounded
# restart after networking is ready recovers that condition without looping.
if ! timeout 8 tailscale status --self >/dev/null 2>&1; then
  systemctl restart tailscaled.service
fi

for _ in $(seq 1 45); do
  if timeout 8 tailscale status --self >/dev/null 2>&1; then
    tailscale serve --bg "$INTERCOM_TARGET"
    logger -t atlas-tailscale-recovery "Tailscale online; ATLAS intercom Serve route restored"
    exit 0
  fi
  sleep 2
done

logger -t atlas-tailscale-recovery "Tailscale did not reach Running state within recovery window"
exit 0
