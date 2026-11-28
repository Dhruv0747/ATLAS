# ATLAS Stage 26: CPU A/B findings (rover-status-web)

Question: does the Motor & Encoder Test Lab cause the ~45-50% CPU seen on `rover-status-web` at idle?

**Answer: no. The load is already there without the Test Lab. The Test Lab accounts for at most about 3 points of one core, and that figure is inflated.**

## Safety gate (18:41 IST, owner had latched E-STOP with remote B)
E-STOP latched ("B pressed"), `manual_only` true, `commission_armed` false, motor PWM 0,0,0,0, no navigation action status on `navigate_to_pose` / `follow_path`, lifted raw interface off. Before the test I saved the owner's open hand-test session (`testlab_20261017T125056Z_hand_e86ac627e872.csv`, 49,719 rows, on the Jetson) because a restart would have lost it.

## Method
`evidence/stage26_cpu_ab/measure.py`: reads `/proc` only (per-process and per-thread utime+stime, `/proc/stat` total, MemAvailable, temperature) over equal 300 s windows with 10 s sub-samples. `ab.sh` orchestrates: A1 current install, rollback with `rollback.sh` (restarts only `rover-status-web`), 120 s settle, B window, reapply with `apply.sh` (restart only `rover-status-web`), settle, A2.

## Results (6-core Jetson; % of ONE core)
| | A1: Stage 26 installed | B: rolled back (original dashboard) |
|---|---|---|
| rover-status-web CPU | **44.6** (10 s samples 25.1-48.7) | **41.5** (39.8-42.9) |
| process age | 78 min | 7 min |
| two hottest threads | 22.2 + 13.6 | 24.4 + 14.1 |
| extra thread | tid 87745 at 3.0 | none |
| RSS | 205 MB | 174 MB |
| threads | 25 | 23 |
| Jetson total CPU busy | 65.4 % | 63.0 % |
| MemAvailable | 2173-2530 MB | 2367-2439 MB |
| temp max | 65.1 C | 64.6 C |
| load1 mean | 13.2 | 8.4 |

Other processes were the same in both windows (camera driver ~36-38, base driver ~26, voice companion ~21, cmd_vel mux ~16, sensor recovery ~15, safety status ~14, rf2o ~12, AMCL ~5 in the B window).

## Conclusions
- The two threads that burn almost all of the CPU (about 22-24 and 14 points) are identical with and without the Test Lab: the existing status/control ROS executors. They are the cause of the 40+% baseline.
- The only Test Lab difference is one extra thread at 3.0 points, plus about 30 MB RSS and a little noise in A1. That extra thread is the Test Lab's lazily started ROS node, which stops itself 300 s after last use. A1 ran 1 minute after the owner's hand-test session was stopped, so it was still inside that tail. Idle Test Lab cost is therefore below 3 points (not measured separately).
- Why the previous process averaged only about 3.5% over 30 h is not explained by the Test Lab: with the Test Lab removed the service still uses 41.5%. The baseline rose for another reason (Nav2/AMCL running since 15:05 is the obvious candidate; not proven). The earlier "3.5% vs 50%" comparison was not like for like (long average vs short reading), as the owner said.
- No correction to the Test Lab is needed. A fix for the status-web executors would be a separate, unrelated change and was not attempted.

## Limits of this test
- A2 (reinstall, fresh-process measurement) was NOT completed: the Jetson rebooted at about 18:57 IST during the settle period after the reapply. It was not caused by this test (no reboot command was issued; the owner may have power-cycled it). The reapply itself finished and was verified by hash.
- One run per condition; B's process was young (7 min) and A1's was old (78 min), which is a small confound. Sub-window spread is small, so the 3-point difference is about the size of that confound.
- Re-running A2 on the rebooted system would not be comparable to B (different boot, different load).

## State after the test
Stage 26 reinstalled (apply.sh), hashes identical to the original deployment: atlas_status_web.py 6658db9412b85b34, atlas_web_v2.py c3607f416d49bd9e, atlas_testlab_core.py 6030aab00bdf7cf6, atlas_testlab_web.py b0a69f3615c213a2, testlab.html 05ac4a7d758be830, testlab.js e9b7edf9d3ee9173, testlab.css 59a3bb375f22a85a. Pulse controls still locked (raw interface disabled, PWM 0). The Home shortcut `index.html` (a03baf884e43ae1c) was redeployed at 19:26 IST after fresh checks (E-STOP latched "joystick unavailable", manual-only, PWM 0, no nav goals) because the reapply restores the original index. Backups: `.pre_stage26_testlab_20261017_172948`, `.pre_stage26_testlab_20261017_185510`, `.pre_stage26b_shortcut_20261017_183749`, `.pre_stage26b_shortcut_20261017_192622`.

## Observed after the reboot (not changed by us)
USB numbering changed: Yahboom base now holds `/dev/ttyUSB2` (CH340), `/dev/ttyUSB1` is held by `gnss_node`, `/dev/ttyUSB0` and `/dev/ttyUSB3` by other drivers. The web dashboard holds no serial port.
