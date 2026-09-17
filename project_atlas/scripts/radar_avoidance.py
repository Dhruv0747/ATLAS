#!/usr/bin/env python3
"""Retired T1-only velocity relay; compatibility entry for radar observation.

All targets are processed by atlas_radar_tracking. Only the existing mux may
enforce its optional, calibrated navigation speed constraint.
"""
from atlas_radar_tracking import main

if __name__ == '__main__':
    main()
