#!/usr/bin/env python3
"""atlas-camera launcher (issue #11, 25 Oct 2026). Starts the Pi camera node with the dashboard's saved, validated
settings. With no saved settings, or any problem reading/validating them, it uses exactly the parameters the unit
used before #11, so the camera always starts as it did."""
import os
import sys

FALLBACK = ['-p', 'width:=1280', '-p', 'height:=720', '-p', 'framerate:=10', '-p', 'jpeg_quality:=75',
            '-p', 'edge_enhancement:=0.60', '-p', 'noise_reduction:=0.35', '-p', 'exposure_compensation:=0.25',
            '-p', 'saturation:=1.20', '-p', 'white_balance_mode:=1']


def main():
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import atlas_camera_settings as S
        params = S.picam_ros_args()
    except Exception as exc:          # never block the camera on a settings problem
        print('atlas_camera_launch: settings unavailable (%s); using previous defaults' % exc, flush=True)
        params = FALLBACK
    print('atlas_camera_launch: ' + ' '.join(params), flush=True)
    os.execvp('ros2', ['ros2', 'run', 'atlas_camera_driver', 'camera_node', '--ros-args'] + params)


if __name__ == '__main__':
    main()
