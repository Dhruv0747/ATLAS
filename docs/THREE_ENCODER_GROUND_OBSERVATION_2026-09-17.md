# Three-encoder manual ground observation — 2026-09-17

## Test and authority

Operator confirmed wheels on ground, charger disconnected, clear test space
and remote stop available. Remote stop release was verified through the mux.
The agent issued **no movement commands** and changed no control settings.
The operator manually drove forward and reverse. They explicitly reported
**40 cm forward and 40 cm back**; whether this was measured with a ruler or
estimated is not yet confirmed. Do not treat it as precision ground truth.

## Recorded evidence

19.38-second passive recording, 187 raw samples per encoder, fresh packet ages
0–0.046 s. No selected-channel fault was reported. The commanded velocity
reached +0.52 and -0.52 m/s; these are joystick commands, not measured speed.

| Channel | Position | Forward counts | Reverse counts | Magnitude difference |
|---|---|---:|---:|---:|
| M1 | Rear-left | +2174 | -2166 | 0.37% |
| M2 | Rear-right | +1942 | -1955 | 0.67% |
| M3 | Front-left | +2180 | -2174 | 0.28% |
| M4 | Front-right, excluded | +1 | -1 | Not valid movement feedback |

Signs in the table are normalized to forward-positive. M1 raw forward counts
decrease. Baselines are medians of stationary plateaus before, between and
after the two moves. All three selected encoders changed in the expected
direction and had similar forward/reverse magnitudes in this one test.
This is not an endurance qualification or proof against future dropouts.

- `/yahboom/odom`: forward 0.21228 m, reverse 0.21089 m.
- Filtered `/odom`: forward 0.22996 m, reverse 0.23679 m.
- Final odometry displacement from its starting estimate: 0.00139 m raw,
  0.00683 m filtered. These are internal odometry estimates, **not measured
  physical return-home error**.
- Encoder changes continued for approximately 0.8 s after each zero command;
  this includes reporting and drivetrain response. It does not establish
  measured physical braking distance. Stopping needs a separate check.

## Finding and next step

If the operator's 0.40 m per leg is correct, existing metric scales under-read
distance by roughly half. Retained calibration predates motor replacements.
Three-channel availability is not the blocker; trustworthy metric odometry is.

Candidate effective counts per wheel revolution, calculated from the mean
absolute forward/reverse counts and the existing 0.392699 m circumference:
M1 **2130.4**, M2 **1912.9**, M3 **2137.3**. These are *proposed effective
calibration values*, not identification of the motor's actual hardware CPR.
They have **not** been applied. Confirm the physical distance measurement
before changing calibration, then validate it on a fresh independent run.
Do not fit and validate against the same run or enable autonomous mode yet.

Raw recording and initial machine summary remain on the Jetson:
`/home/jetson/project-atlas-migration/three-encoder-20260917/manual-straight-204627.jsonl`
and its `.summary.json` companion. The summary's small net displacement reflects
the out-and-back motion, not failure to move; use the separated-leg analysis above.
