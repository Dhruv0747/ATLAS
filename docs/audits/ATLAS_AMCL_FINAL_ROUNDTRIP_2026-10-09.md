# ATLAS final manual round trip: wrong map pose after return (2026-10-09)

Read-only analysis of `/home/jetson/project_atlas/data/demonstrations/amcl_roundtrip_20261009_final`.
The operator manually drove Dhruv Room → Hall → Dhruv Room and confirmed the
physical endpoint. No diagnostic motor command or production parameter change
was made. This recording is about 464.5 s and contains 105,825 messages,
including AMCL poses/particles, LiDAR, wheel/EKF odometry, IM10A gyro,
steering commands, encoder health, and TF.

## New evidence

- The final dashboard pose is fresh (~2 Hz) but wrong: map→base_link remains
  near `(3.840, -0.482, 2.727 rad)`. Saved `home_pose.json` is near
  `(0.919, 0.026, -0.033 rad)`, about **2.97 m** from the live marker. The
  operator reports ATLAS physically in Dhruv Room. Therefore this is not a
  browser-refresh delay.
- After the last nonzero drive command (recording overlap offset 344.94 s),
  the stationary-jump audit finds **13** consecutive AMCL pose steps above
  0.5 m, up to **1.191 m**, through offset 387.49 s. Matched wheel-odom XY
  steps are 0.0000 m at these events. AMCL heading switches by tens of degrees,
  including repeated ~98.5° reversals. Fresh filtered scans and recorded
  particle clouds are present; a scan blackout or physical rover motion does
  not explain the switching.
- AMCL XY standard deviation exceeded 0.5 m at offset 140.41 s and 1.0 m at
  155.99 s, well before the return ended. In a 330–335 s return window, wheel
  yaw changed -11.53°, corrected IM10A gyro +25.97°, and EKF +26.36°.
  Steering topics are commanded targets, **not** measured road-wheel angles.
  This is evidence of a wheel-heading-model disagreement in that window, not
  evidence that any particular encoder or steering servo failed.
- The largest step in the full loop was **3.792 m** near the Hall stop. Its
  matched wheel-odom XY change was 0.0000 m, while the same preceding scan's
  approximate 15-cm wall-endpoint agreement changed from 39.1% to 85.1%.
  The return-end pose switches show multiple map hypotheses with substantial
  scan agreement. These diagnostic scores are not AMCL likelihood or surveyed
  ground truth.
- A fresh stationary scan at the operator-confirmed Dhruv Room endpoint had
  79.6% endpoint agreement at the incorrect live pose versus 68.0% at the
  saved named Dhruv Room pose and 80.1% at that named point with its heading
  varied over 24 candidates. This supports position/heading ambiguity in the
  available scan/map geometry; it does **not** establish why AMCL chose the
  incorrect hypothesis.
- The separate saved `home_pose.json` and named `dhruv room` entries are not
  identical: `(0.919, 0.026)` versus `(0.254, -1.539)`, about **1.70 m** apart.
  The home file was last written Oct 8 at 11:35 IST; the named-place file and
  matching localization seed were written Oct 9 at 12:20 and 12:10 IST. This
  is a reference-pose/provenance conflict that must be resolved before using
  either as a return-home accuracy target. It does not explain the observed
  stationary AMCL switching by itself.

## Decision

Verified immediate failure: AMCL/`map→odom` localization switches between
competing map poses while physical wheel odometry is stationary, and it can
settle on a wrong pose. The upstream cause of uncertainty is not yet proven:
wheel-heading modeling during turns, map/scan ambiguity, and AMCL scoring may
all contribute. Current isolated replay does not reproduce the live switches;
zero jumps in that replay cannot validate a proposed repair. No EKF/AMCL,
steering, encoder, or motor parameter was changed. Autonomous navigation must
remain gated. Do not use a mere map-marker refresh or a one-time pose seed as
proof of a permanent fix.

Next software-only step: preserve this bag and compare candidate hypotheses
against the *same* recorded scans, wheel/gyro turn windows, and saved map;
make the replay faithful enough to reproduce the stationary switching before
accepting an EKF/AMCL modification. If that cannot be done with the recorded
AMCL internal state, state the missing data and request a separately approved
stationary-only diagnostic capture. No further drive is justified yet.

## Focused closure and stationary shadow comparison

These checks used the same saved round-trip bag and one 10-second stationary,
TF-disabled shadow AMCL process. Production localization and motor commands
were untouched; Nav2 was inactive after the shadow exited.

- Three independent first/last LiDAR scan pairs aligned with 95.7–96.6% of
  filtered points within 25 cm, 5.2–5.6 cm inlier RMSE, net heading
  +4.26 to +4.51 degrees, and approximately 0.52 m translation. A roughly
  180-degree alternate fit still had 82–85% inliers, demonstrating scene
  ambiguity. This is a loop-closure estimate, not surveyed ground truth.
- Integrating recorded accepted wheel forward velocity with corrected IM10A
  gyro yielded approximately 3.004 m loop displacement and a net heading
  equivalent to +10.18 degrees. Recorded wheel odometry closed 5.699 m away
  and -177.98 degrees in heading; recorded EKF translation also closed
  5.699 m away and its heading was +168.82 degrees. The corrected gyro and
  first/last scans agree on near-zero *modulo-full-turn* heading, while the
  wheel-derived position input and EKF translation disagree. Velocity+gyro
  alone still misses scan closure by metres, so removing wheel X/Y pose from
  the EKF is **not** established as a sufficient repair.
- A LiDAR-derived candidate final pose near `(0.115, -2.021, 1.484 rad)`
  was seeded only into shadow AMCL. During 10 seconds of no-motion updates,
  shadow stayed within 0.021 m of its first estimate, ending near
  `(0.184, -2.034, 1.447 rad)`. Production AMCL simultaneously remained at
  `(3.843, -0.484, 2.734 rad)` with no displacement. The two hypotheses are
  separated by about 3.99 m. Both can be locally stable while stationary.
  On a separate crude endpoint-to-saved-map score, the candidate fit was
  only about 63% versus about 82.5% for the live wrong hypothesis; this
  metric is not AMCL likelihood and cannot select the physically correct
  hypothesis by itself.

The independently corroborated problem is a substantial wheel-motion-model
versus gyro/LiDAR heading conflict during this route, followed by AMCL
settling into a plausible but physically wrong map mode. The exact cause of
the heading conflict (unmeasured road-wheel angle, slip, wheel geometry, or
another model error) and the relative roles of map ambiguity/AMCL tuning
remain unproven. A shadow pose that stays stable for 10 seconds does **not**
prove it will track while ATLAS drives. Do not reseed production or deploy a
velocity-only EKF on this evidence. Current dashboard marker remains wrong;
the safety-appropriate outcome is to keep autonomy gated and obtain an
independent physical pose/steering reference before a production correction.
