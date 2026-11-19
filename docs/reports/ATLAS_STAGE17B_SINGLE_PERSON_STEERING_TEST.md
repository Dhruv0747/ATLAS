# Stage 17B — single-person front steering measurement

2026-10-14. Source implementation only; NOT deployed. Autonomy remains disabled.

Owner Stage 18 directive: **ON HOLD**. Deployment and physical execution are not
authorized. Retained for history only; do not treat the earlier approval request
as approval to install or run this feature.

## What is prepared

The existing commissioning page gains an opt-in front steering sequence:
90 → 95 → 100 → 95 → 90 → 85 → 80 → 85 → 90.
Each acknowledged commanded position settles for 0.5 seconds and is held for
15 seconds. Rear steering stays at its saved centre. No calibration is saved,
no traction command is issued, and no stop-release command exists in this feature.
Command acknowledgements are software acknowledgements, not physical angle feedback.

Default mode pauses after every hold for Vernier measurements. Resume requires
hands clear. Non-contact observation mode advances automatically. Initial countdown
is 10 seconds; subsequent countdowns are 3 seconds. Absolute limits are 300 seconds
for caliper mode and 210 seconds for observation mode, including pauses.

## Phone and measurement limits

The owner's Protractor app measures phone tilt/orientation only. It cannot measure
horizontal road-wheel steering; a displayed 90 degrees is not wheel-angle evidence.
Use a rigid wheel-aligned baseline of measured length L (40–150 mm), and measure
its signed transverse endpoint difference Δy against a coplanar chassis-parallel
reference. Angle = asin(Δy/L). Measure each front wheel separately at all nine steps.
Use rigid references, not uneven tyre tread. Enter realistic placement uncertainty,
not merely the caliper's display resolution. The report propagates measurement
uncertainty and compares centre drift, repeated-step hysteresis, asymmetry and
nonlinearity. This method is invalid without the stated reference geometry.
No actual wheel angles have been measured by this implementation yet.

## Safety and ownership

Feature flag ATLAS_STAGE17B_ENABLED defaults to 0. Opening the page does nothing.
Prepare needs lifted wheels, disconnected charger, clear hands/cables and physical
power cut-off confirmation. Fresh latched-stop policy, zero motor outputs, encoder
communication, IMU, scan and steering-owner telemetry are mandatory.
Press B to latch the stop, then release the physical B button without releasing the
software stop. Another B press cancels. Existing commissioning permits steering
PWM while traction is inhibited. Emergency uses the existing stop-only endpoint.
Cancellation freezes the last command: it does not centre, remove servo torque or
prove physical motion has stopped. Keep the physical cut-off available.

Start explicitly delegates the finite sequence to the server so the same phone can
background the browser. Phone/network loss does not extend its deadline and does
not itself mean immediate cancellation. Fresh local owner/sensor safety is checked
every 0.1 seconds; loss cancels, supervision stalls over 0.75 seconds cancel, and
the existing 1.5-second owner lease freezes steering after a server failure.
Restart never resumes a sequence. Old owner software without interlock metadata
cannot start it. No rear jog, calibration save, motor output or stop release is sent.

## Recording

Prepare starts one finite 420-second diagnostic child using the existing
steering-validation profile, validated topic list and recorder lock. Start waits
for fresh health and pre-roll readiness. Existing retained-bag cap is 500 MiB;
active bags and existing evidence are not deleted. Event/status/request topics and
IM10A dashboard orientation are added only to this optional profile. Completion
allows 25 seconds for post-roll before stopping only the owned child. Session
reports retain timestamps and observations locally; ROS bag health reports drops.
Disk/process/sensor failures cancel rather than extending steering ownership.

## Validation

62 offline Python checks passed: 20 new core/adapter tests, 16 existing steering
lease tests, 6 mux stop-hold tests, 5 recorder-profile tests, 3 steering geometry
checks and 12 real-handler HTTP E-STOP regressions with mocked ROS.
The Node mock-dashboard suite and JavaScript syntax checks passed.
Coverage includes exact order/holds, opt-in permission, caliper pause, finite
duration, E-STOP, stale owner, lease loss, server stalls, recorder failure,
restart, rear preservation, unchanged calibration and rejecting tilt measurements.
These are software tests, not physical reliability or localization passes.
Jetson CPU/RAM/disk impact of the expanded Stage 17B profile has NOT been measured.
The previous Stage 17 recorder trial is not a Stage 17B performance validation.

## Installation and rollback — approval required

Preserve baseline 290fb5ad4006ed978ca765b9df93d81248eb7b1a and verify live hashes
before installation. Install the two new Python modules plus the modified web,
UI, recorder, steering owner and motor-owner metadata files as one compatible set.
Keep the flag disabled first. Only approved web/motor-owner restarts are required;
a motor-owner restart may command saved steering centres, so fresh lifted/clear
confirmation is essential. Do not restart Nav2, modify EKF or enable autonomy.
Verify fresh metadata, zero traction and E-STOP before enabling the opt-in flag.
Operator must separately Prepare and explicitly Start the supervised sequence.

Rollback: disable the flag; stop the session; restore the baseline versions of
the five modified source files and remove the two newly installed modules only
after restoring their importing web file. Restart only approved affected services
under the same safety conditions. Preserve bags and session reports. No rollback
or installation has been executed on ATLAS in this stage.

Moving-localization instability remains unresolved. This tool collects physical
steering evidence; it neither repairs AMCL nor grants autonomous driving authority.
