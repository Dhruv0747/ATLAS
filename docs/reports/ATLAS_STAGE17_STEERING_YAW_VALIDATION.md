# Stage 17 — steering/yaw validation prepared

14 October 2026. Branch `agent/sync-developer-20261011`, continuing `042c801`.
Status: **offline preparation and isolated parked recording passed; physical
steering and moving localization validation await owner approval.**

## 1. Hardware and configuration evidence

The live `yahboom_base.py` matches source SHA-256
`0464a3a10d070b0a4df83ca3b068c37f5d1a54863a6986ebd818b5100a8fa3b4`.
It owns the Yahboom serial link and writes front PWM channel **2**, rear
channel **1**. The existing front/rear steering owner and both command topics
are active. The owner's earlier front/rear videos and observations establish
that both axles were installed and operated previously. **This read-only
session cannot certify that either linkage still moves correctly or that the
rear servo is currently physically connected.** The first approved stationary
tests must verify that independently before any rear-steering model is accepted.
No servo model label, measured linkage lengths, or physical angle sensor was
identified in current telemetry.

The live calibration matches source hash
`99084dea47f33c01144d9f0ac152530c875733c989c25ed3eaf4a1bea4d1913c`:

| Axle | PWM channel | Centre | Saved left | Saved right | Current commanded value |
|---|---:|---:|---:|---:|---:|
| Front | 2 | 90° | 121° | 50° | 90° |
| Rear | 1 | 90° | 134° | 59° | 90° |

These are servo command units, **not measured road-wheel angles**. Servo-high
is configured as physical left; normal driving counter-steers the rear. The
commissioning envelope permits front 126°, but the saved operating endpoint
remains 121°; this work changes neither. The live steering status explicitly
says `COMMANDED, NOT MEASURED`. Vendor UART-servo angle queries do not supply
feedback from these PWM outputs. M1/M2/M3/M4 remain rear-left/rear-right/
front-left/front-right. All four are current consensus candidates;
`navigation_validated=false` and `autonomy_ready=false`.

The current wheel model uses `k=(tan(front_command-centre)-tan(rear_command-
centre))/0.367`, assumes zero body lateral velocity, normalizes wheel paths
using a 0.26 m track, and integrates yaw as accepted distance × k. This assumes
commanded deflection is road-wheel deflection and effectively symmetric
counter-steering. Unequal physical front/rear angles can introduce lateral
body motion; physical angles are required to test that assumption. Working
manual steering centres, direction, limits and motor polarities are preserved.

## 2. Physical measurement method

Use a phone fixed above the axle, with **both tyres**, a directed chassis
forward edge and four measured coplanar reference points visible. Record front
and rear separately while stationary; a moving test needs both axles visible
in one wide view or synchronized cameras. Mark wheel-axis points visually on
the visible tyre top/edges; do not attach protruding pointers that could catch.
Phone compass readings are not the road-wheel reference.

`docs/stage17_angle_reference.svg` provides a 150 mm reference square. Print
at 100% and check its size with a ruler, or make an equivalent measured tape
rectangle. Plane coordinates are +X rover-forward and +Y rover-left. The
reference and picked wheel axes must be in the same measurement plane. A
sheet on a different-height chassis surface cannot silently qualify a tyre
angle. Grid placement, suspension motion and tyre deformation must be noted.

`steering_angle_measurement.py` rectifies perspective from the four grid
points and calculates each road-wheel angle relative to the chassis. It
reports a first-order point-picking error bound and explicitly lists
unmeasured coplanarity/placement/deformation errors. A bound >3° is flagged
unusable for fitting; a small pixel bound alone is not proof of physical
accuracy. A moving camera/reference needs four reference points **per frame**.

Synchronize video using two independently timestamped visible markers, before
and after each test. The prepared `stage17_visual_marker.py --emit --label
front_start` publishes only `/atlas/steering_validation/marker` and prints
the same ROS timestamp on the **local Jetson screen**, which must appear in
the phone video. Capture a readable marker line and its video PTS at each
end. Use actual video presentation timestamps, not frame number divided by
an assumed constant frame rate. The tool refuses unbracketed samples and
video/ROS clock ratios outside 0.99–1.01. Use at least 0.1 s timing uncertainty
for this screen/camera method; SSH terminal delivery requires separately
measured additional uncertainty. Software steering topics are headerless,
so their bag receipt cadence adds command-time uncertainty. Do not infer
sub-uncertainty servo lag or align clocks by wheel-motion onset—that would
erase the delay being measured.

Measurement input JSON contains `plane_reference` (four `image_xy` and
`plane_xy_m` pairs), two `sync_anchors` (`video_pts_s`, `ros_time_ns`,
`uncertainty_s`), `point_picking_error_px`, and `samples`. Each sample contains
`video_pts_s`, two directed `chassis_forward_image` points and
`wheel_forward_axes_image` keyed by physical wheel position. A sample may
override `plane_reference` when the scene moves. The developer picks points
from the supplied videos; the owner does not need an angle gauge or to edit
JSON. The output is an offline visual estimate with **no ROS control authority**.

## 3. Recorder changes and readiness

The existing asynchronous bounded recorder is reused. Its default topic list,
10 s pre/post-roll, queue, 500 MiB cap and opt-in behavior are retained.
The optional `--profile steering-validation`:

- adds raw IM10A, exact encoder update snapshots, particles, LiDAR odometry,
  steering owner status, joystick and battery data;
- triggers a capture when a received steering command changes, covering
  stationary sweeps without publishing a motion command;
- uses 10 s pre-roll and **20 s post-roll** to observe parked localization;
- requires a finite 30–600 s duration and reports warm-up/missing/stale topics;
- accommodates BMS's normal 5 s publication cadence with a 12 s freshness window.

Required Stage 17 topics are `/scan`, `/scan_raw`, `/odom`, `/yahboom/odom`,
`/amcl_pose`, `/tf`, `/atlas/encoder_health`, `/atlas/control_policy`,
`/atlas/encoder_update`, `/im10a/imu/unvalidated`,
`/im10a/imu/bias_corrected_candidate`, `/particle_cloud`, `/lidar/odom`,
`/yahboom/encoder/m1..m4`, `/steering/front_angle_deg`,
`/steering/rear_angle_deg`, and `/bms/status`. Additional context includes
`/tf_static`, `/imu/data`, all existing command-source topics,
`/steering/mode`, `/atlas/steering_calibration/status`, `/im10a/status`,
`/joy`, `/lidar/odom_raw`, `/odom/lidar_fused_candidate`, `/bms/voltage`
and the diagnostic visual marker. Full maps and camera streams are omitted
to bound load; external phone footage supplies actual wheel-angle evidence.

Each bag preserves message payloads and receive ROS timestamps. Headerless
encoder/steering messages have receive time; exact updates contain the driver's
source stamp, packet age, accepted increments and shared board state. **MCU
per-wheel acquisition timestamps are unavailable**; published times must not
be described as hardware sample times. Application and DDS-reported loss
counts are separate; zero reported loss is not proof that a publisher or MCU
never omitted a sample.

After approval, run from the tested isolated directory (no service):

```bash
source /opt/ros/humble/setup.bash
python3 /tmp/atlas-stage17-smoke-xnVKwf/atlas_motion_recorder.py \
  --record --profile steering-validation --duration 180 \
  --root /home/jetson/project_atlas/data/diagnostics/stage17_front_test
```

Use a new specific root for each axle/test session. Wait at least 12 s and for
READY with no missing/stale required topics before the first approved action.
Do not use the `--stationary-probe` flag for the real sweeps; steering changes
and real movement supply capture triggers. Keep every stop at least 20 s;
end physical activity at least 25 s before the recorder's finite exit.
Do not run a second recorder or autostart this profile.

## 4. Read-only live checks and isolated parked test

The 14 Oct 11:15–11:20 checks found E-STOP latched, commissioning unarmed,
zero `/cmd_vel`, Nav2/Explore inactive, 369 GiB free and both servo commands
90°. Joystick messages were fresh, but the latched reason still read
`REMOTE STOP: joystick unavailable`; functional remote driving/release needs
an operator check after physical-test approval. BMS was live at 78.5%,
13.5 V and **+2.7 A charging**. Disconnecting the charger remains a physical
test prerequisite.

In a 15 s parked subscription sample: scan ~7.04 Hz, raw/corrected IM10A
~10.32 Hz, wheel odom ~9.36 Hz, EKF ~10.04 Hz and LiDAR odom ~6.76 Hz.
Wheel/EKF/AMCL net displacement and heading change were zero. Raw and corrected
IM10A reported exact zero gyro Z, which does not establish underlying gyro
bias or turn accuracy. Raw LiDAR odometry wandered 8.2 mm / 0.622°, while the
existing gated `/lidar/odom` stayed still. Largest callback gaps were
~0.35–0.41 s for gyro/wheel/EKF; timing must be retained during motion rather
than treating regular average Hz as continuous source delivery.

The new profile was tested for 60 s under the latched stop from an isolated
`/tmp` source copy. No production file, service, calibration, map or actuator
changed. Evidence remains at
`~/project_atlas/data/diagnostics/stage17_parked_profile_20261014_1126/`.

| Parked profile result | Measurement |
|---|---:|
| Exit and SQLite integrity | 0 / `ok` |
| Written messages / capture span | 7,032 / 28.47 s |
| Application drops / DDS-reported losses | 0 / 0 |
| Missing or stale required topics at finish | 0 / 0 |
| Raw/corrected IM10A messages in bag | 299 / 299 |
| Exact encoder-update messages in bag | 301 |
| Recorder CPU | ~40.48% of one core (~6.75% of six cores) |
| Recorder sampled peak RSS | 84.98 MiB |
| Recorder files | 8,013,749 bytes |
| Whole-NVMe writes during trial | 28,688,384 bytes (includes other processes) |
| Whole-system CPU before / after | 72.9% / 73.1% |
| Whole-system CPU mean / sampled maximum during trial | 79.36% / 99.4% |
| Reported RAM before / after | 5,169 / 5,196 MB of 7,620 MB |
| Temperature before / after | 61°C / 61°C |

These are parked measurements; moving-workload overhead remains unmeasured.
The previous default parked recorder used 29.29% of one core and 78.27 MiB
on a different day/workload, so their difference is not a controlled A/B
measurement. The profile stopped and drained its queue; no background recorder
remains. CPU load average had fallen from 34.12 at boot to 13.78 on six cores,
but the sampled 99.4% peak and callback gaps require fresh resource/timing
checks before movement. No services were disabled to produce this result.

## 5. Ready-to-execute physical sequence — approval pending

First approve **stationary steering only**, secure all four wheels lifted,
disconnect charging, keep hands/cables clear, retain B latched and arrange the
fixed video/reference. Use the existing dashboard steering-owner lease, which
inhibits traction. Never use direct serial tools, change endpoints, or press
Mark/Save. Stop on unexpected axle/direction/strain, loss of remote/stop
status or recording.

1. Front-only: hold rear at saved 90°, observe front at 90→95→100→95→90→85→80→85→90.
   Hold each step ~2 s, repeat once to expose direction-dependent hysteresis.
   Record both front road-wheel angles and whether the rear remained still.
2. Rear-only: only after the rear linkage is visually confirmed operational,
   hold front 90° and run the same small command sequence on rear. Record both
   rear angles. If it does not operate, stop and diagnose connection/mechanics;
   do not silently assume rear steering in the motion model.
3. Return both to their existing saved centres and exit the lease without saving.
   Confirm recorded software commands and visually measured centres separately.

After those measurements and **separate owner approval for ground movement**,
verify manual stop/release, charger disconnected, measured floor and turning
clearance, fresh sensor topics and resources. The owner manually drives
~30 cm straight forward and reverse at ~0.08–0.10 m/s, then one gentle left,
one right, and one slow steering transition. Use tape-marked start/end and
heading references. Stop ~20 s after each leg, filming both axles and the
chassis heading. The exact route need not be repeated identically; compare
measured motion for each maneuver. No autonomous goal or recovery is part of
this plan, and the recorder cannot release the stop.

## 6. Diagnosis, correction gate and encoder resilience

Existing evidence establishes localized wrong wheel yaw before AMCL switching,
not a global sign fault. Current motion code was not changed. Compare synchronized
actual road angles, commanded targets/applied PWM, raw/signed wheel increments,
raw/corrected gyro, LiDAR relative motion, EKF yaw and AMCL particles. Rank
command delay/backlash, servo-to-road angle conversion, asymmetric 4WS geometry,
traction, encoder distance and timing using their earliest discrepancy and
measurement uncertainty. Accept no arbitrary angle/CPR factor from one turn.

The new **isolated** rolling-model harness uses measured road-wheel angles to
fit body forward/lateral/yaw motion and reports rolling and lateral-slip
residuals. Synthetic four-wheel left/right/reverse cases recover the known
motion. Two encoders alone cannot constrain all three components; with
independently valid gyro yaw and nonparallel wheel directions they can estimate
translation, whereas parallel directions still leave lateral motion unobserved.
This is mathematical feasibility, **not commissioning of two-encoder driving**.
The live three-of-four policy, channel recovery and fail-closed behavior remain.
No permanent M3 rejection or authority change was made. Real residuals and
uncertainty are required before designing a replacement adaptive policy.

The old `atlas_steering_calibrate.py` directly opened the shared serial port,
used obsolete 83/106° holds, and swapped current front/rear channel IDs.
No repository caller was found. It now refuses actuation in source and directs
operators to the guarded owner. A subprocess regression proves refusal before
serial imports/access. **This tooling defect is not proven to have participated
in the recorded localization failures**, and the corrected stub is not deployed.

No physically measured angles have been captured in Stage 17. Accordingly,
before/after real yaw/distance/AMCL-jump metrics are **unavailable**; the baseline
five parked jumps and 2.206 m maximum remain unresolved. The physical test will
choose a candidate, then all relevant existing/new bags must compare signed
yaw, measured distance, LiDAR fit, moving pose and post-stop stability. Use
the archived accepted map (`d957f0fe…` YAML / `4beb26d5…` PGM), not the differing
repository map. Startup thresholds 0.93/0.06 remain unchanged.

## 7. Tests, package, deployment and rollback

**27 offline regressions passed:** 6 perspective/sync/rolling-observability,
5 Stage 17/default/profile/retired-tool tests, and 16 existing recorder/queue/
storage/failure tests. Python compilation and diff checks passed. The isolated
Humble parked profile verified raw CDR/SQLite writing and required-topic
readback. It did not validate moving sensor accuracy or actual wheel response.

The tested temporary recorder SHA-256 is
`5fb8a8ec9bcb08af9d98216f8790e46ee33d1834dc49bae728fe9aa14c8cebc5`.
Production remains
`02fcaed2c4350da9a46838356bcf571b408f57dffe33c7275c4168a52d821c80`.
The isolated profile can be reused for a supervised session without replacing
production. The prepared local ZIP contains tested source, measurement tools,
reference sheet, report, SHA-256 manifest and the original recorder for rollback;
its exact committed version is recorded in the package manifest and delivery
GitHub link. No merge into `main`.

For this isolated use, rollback means terminate only the foreground recorder
and retain the completed bag; the old deployed script and all robot controls
are already intact. For a later approved persistent diagnostic installation,
back up/verify the production recorder hash, install only the tested diagnostic
file, and restore the bundled original if the recording regresses. No motor,
steering, EKF or Nav2 unit needs restart. Any future motion-estimation correction
requires its own measured replay results, exact file/config backup and owner
deployment approval.

**Remaining approval gate:** stationary front/rear steering measurement first;
ground motion and any motion-affecting deployment remain separately unapproved.
