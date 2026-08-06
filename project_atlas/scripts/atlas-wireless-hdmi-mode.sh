#!/usr/bin/env bash
set -u

# Prevent GNOME/X11 power saving from blanking this portable receiver display.
xset s off 2>/dev/null || true
xset s noblank 2>/dev/null || true
xset -dpms 2>/dev/null || true

# GNOME may restore its old fallback after login. Wait for the ETZIN receiver,
# then select the physically verified CTA-861 720p60 mode. The receiver loses
# sync with both tested 1080p timings on the attached WSD110_L panel.
for _attempt in $(seq 1 20); do
    if xrandr --query | grep -q '^DP-1 connected'; then
        # Use a distinct runtime name: NVIDIA may publish the xorg.conf mode
        # globally without attaching it to DP-1, which blocks RandR addmode.
        xrandr --newmode "1280x720_ATLAS" 74.25 1280 1390 1430 1650 720 725 730 750 +HSync +VSync 2>/dev/null || true
        xrandr --addmode DP-1 "1280x720_ATLAS" 2>/dev/null || true
        xrandr --output DP-1 --mode "1280x720_ATLAS" --primary && exit 0
    fi
    sleep 1
done

exit 1
