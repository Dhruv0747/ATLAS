#!/bin/bash

export DISPLAY=:0
export XAUTHORITY=/run/user/1000/gdm/Xauthority
export XDG_RUNTIME_DIR=/run/user/1000
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
export SDL_VIDEODRIVER=x11

/usr/bin/xrandr --output default --mode 1920x1200 --primary >/tmp/project-atlas-xrandr.log 2>&1 || true

source /opt/ros/humble/setup.bash
if [ -f /home/jetson/project_atlas_ws/install/setup.bash ]; then
    source /home/jetson/project_atlas_ws/install/setup.bash
fi

cd /home/jetson/project_atlas/scripts
exec /usr/bin/python3 /home/jetson/project_atlas/scripts/rover_dashboard.py
