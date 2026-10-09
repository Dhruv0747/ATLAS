# ATLAS saved-scan odometry diagnostic (2026-10-09)

This is a read-only continuation of the Hall-to-Dhruv-Room localization investigation. It does not alter production ROS services, steering, EKF, AMCL, or motor commands.

## New measurements

The recorded round trip contains 3,245 `/scan` messages over approximately 460 seconds. `project_atlas/scripts/atlas_offline_scan_odom.py` registered adjacent scans with local point-to-point ICP and integrated their relative poses. It is a diagnostic, not a production odometry source or ground truth.

| Minimum scan interval | Samples | Integrated start-to-end gap | Heading gap | Rejected steps |
| --- | ---: | ---: | ---: | ---: |
| 0.2 s | 1,647 | 4.737 m | 106.6° | 0 |
| 0.5 s | 840 | 5.600 m | 104.3° | 1 |
| 1.0 s | 436 | 9.498 m | -156.7° | 7 |

The 0.2-second run moved no more than 0.017 m or 0.1° relative to its first estimate during the final 20 seconds. Prior investigation found that raw start/end scans align within about 0.52 m and 4.5°, whereas the live AMCL estimate underwent five large stationary corrections in the original recording (and thirteen corrections over 0.5 m in the later round trip). The local scan registration therefore provides **new evidence that scans remain locally stable while stopped**, but its multi-metre accumulated route error demonstrates that chaining these matches is not a valid replacement for the current localization stack.

The interval dependence and the mismatch between chained odometry and direct start/end registration are consistent with cumulative ICP drift and/or local geometric ambiguity. They do not verify a unique AMCL root cause. The exact scan-to-map likelihood, particle history, and full live TF timing at each pose switch must be evaluated before any production parameter change. No offline scan-only path produced an acceptable whole-loop closure, so this candidate must not be deployed or used to unlock autonomous driving.

## Safe reproduction

Run the diagnostic against a copy or read-only instance of the saved bag in a ROS 2 Humble environment with NumPy/SciPy:

```bash
python3 project_atlas/scripts/atlas_offline_scan_odom.py BAG_DIRECTORY --interval 0.2
```

This reads only `/scan` from the bag and prints summary metrics. It does not publish ROS topics. The production configuration remains unchanged.
