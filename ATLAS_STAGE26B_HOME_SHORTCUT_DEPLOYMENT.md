# ATLAS Stage 26b: Home Dashboard shortcut to the Test Lab (deployed)

Scope: `web/v2/index.html` only (commit `199a822`). Static file, no service restart, no motor-driver change, no pulses enabled, Test Lab page and its locks untouched.

## Safety gate before deploy (18:37 IST)
E-STOP latched ("REMOTE STOP: B pressed"), `manual_only` true, `commission_armed` false, motor PWM 0,0,0,0, no `/cmd_vel` published, lifted raw interface off. An earlier attempt at 18:32 was aborted by the script because E-STOP was then released.

## Deployment
| | sha256 (first 16) |
|---|---|
| live `index.html` before | 4d4dea5620c80e91 |
| live `index.html` after = commit file | a03baf884e43ae1c |

Backup + rollback: `/home/jetson/project_atlas/.pre_stage26b_shortcut_20261017_183749/` (`index.html`, `SHA256SUMS`, `rollback.sh`). Rollback is a file copy; no restart needed.
Unchanged (re-hashed): `testlab.js` e9b7edf9d3ee9173, `atlas_testlab_web.py` b0a69f3615c213a2, `yahboom_base.py` c551be0053a43755. `rover-status-web` still PID 64807, NRestarts 0.

## Change
The Home nav already had a small Test Lab link whose label was hidden below 1600 px (icon only). That one button now always shows "Motor & Encoder Test Lab" with an accent outline, and sits first in the nav strip on phones. No new elements. To revert, restore the backup.

## Live verification (headless Chromium on the owner's PC, real Jetson, evidence in `evidence/stage26b_home_shortcut/`)
- 1440 px, 1920 px, 390 px: button visible, labelled, fully in viewport. One click opens `/v2/testlab` (h1 "Motor & Encoder Test Lab"). No page errors, no broken assets (camera.jpg excluded, camera offline).
- Test Lab after click: "Encoders live 10 Hz", "Pulse locked", Forward/Reverse buttons disabled.
- `/v2/`, `/v2/testlab`, `/v2/testlab/`, `/v2/mapping`, `/api/status` all 200.
- Mobile Home has page-level horizontal overflow (scrollWidth 442 vs 390). The same measurement on the pre-change page gave 728, so it predates this change (not fixed here, out of scope).
- Not tested on a real phone.

## Things seen during verification (not caused by this deployment)
1. **The owner's hand-rotation session is recording.** Session `e86ac627e872` (mode hand) began about 18:21 IST and has about 43k rows; I did not touch it. Wheel 3 forward: first attempt `NO_COUNT`, second `OVERCOUNT` ratio 12.24. During that turn M2, M4 (and M3) counted: raw deltas M1 0, M2 -37345, M3 26920, M4 -108790, flagged CROSSTALK (48.8 turns of other-wheel counts). Verdict for wheel 3: FAIL. Wheels 1, 2, 4 not tested yet. Saved CSV appears only when the session is stopped.
2. **The base driver was restarted at 18:36:47 IST (PID 3145 to 95630) by `atlas_sensor_recovery`**, the existing auto-recovery, which logged "RECOVERING: encoder_health (fault: CRITICAL, M1_REAR_LEFT)". It is the production auto-restart reacting to the encoder fault during the hand test. `/dev/ttyUSB1` is still owned only by the base driver. The same recovery node also loops on the dead radar (attempt 3/3, no data for 3.5 h).
3. The planned CPU A/B was not started: it was requested while E-STOP was released, and a hand-test recording is now in progress, which would contaminate the measurement. It needs a quiet rover.

## Remaining
CPU A/B comparison pending (needs recording stopped, rover idle, E-STOP latched). Physical pulse testing still needs separate approval. Encoder fault root cause still open; hand test needs M1, M2, M4 and reverse runs.
