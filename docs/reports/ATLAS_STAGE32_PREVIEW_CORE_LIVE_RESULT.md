# One guarded Depth-only attempt after97735e9

2026-10-21. Result: BLOCKED before native driver launch; real3D Preview NOT
displayed for any part of this attempt. One Start only, no retry.

## Admission

Core hash49777c0c3a3c2542107dcccba0ef26e234a31ab22729b055ca8bc260bff501a2 and
runtime hash ebaaa3c7990d982cfd8e65f217baae9a1a15c71a0aa396594cc597e5b04256b9
verified before Start.
Fresh CPU72.5086,70.0980,73.5016%; RAM68%. E-STOP latched/manual-only,
commissioning disarmed, zero motor commands/outputs, mission READY, recorder OFF.
Required sensor freshness and both Astra USB identity/access checks passed.
Browser refreshed, Depth selected, page polling active. Persistent read-only
/proc monitoring began before Start; no new ROS subscriptions or video/rosbag.

## Outcome

Worker started monotonic4112.228499083. CPU rejection4114.007094806, stopping
4114.007110776; elapsed1.77857s. CPU76.6101695% exceeded75%. No driver_spawned
event, no Astra process, zero depth frames. Last passing check71.4286%CPU,
67.5789%RAM,60.468C. Failed CPU sample does not include simultaneous RAM/temp
because the guard rejects before collecting those values.

Uncalibrated Preview checkbox remained disabled; normal enable request timed
out rather than bypassing the disabled state. Thus points,FPS,frame freshness,
redraw rate,rotate,zoom,pan and selection are unavailable/not tested.
No full60s success. No lease-expiry failure; short run cannot prove60s heartbeat
stability. Stop clicked after automatic shutdown, no second Start.

## Per-process evidence

Final monitor interval ended4114.419502181,~1.052s,aggregate75.7329%; different
window from guardian76.6102%. Top measured processes (percent of ONE core):

|Process|PID|CPU one-core %|
|---|---:|---:|
|rover-status-web Python|40386|46.58|
|camera_node|2644|29.47|
|base telemetry Python|3293|28.52|
|Python, role not established here|2045|23.76|
|command mux Python|1814|15.21|
|Python, role not established here|1891|15.21|

Nearby before-Start sample: web49.68%, camera29.62%, telemetry25.79% one core.
No clear spike in these top processes explains the aggregate rejection. Top10
is not all processes or kernel/interrupt work. Do not equate one-core percentages
with whole-machine percentages. No basis to disable an essential service.
Most importantly, zero frames means the optimized conversion code was not
exercised: actual Jetson conversion savings cannot be assessed by this attempt.

## Postflight

Astra absent/driver_stopped=true; retained RESOURCE BLOCKED reason remains visible.
E-STOP latched/manual-only/commands zero, recorder OFF; fresh Pi Camera, LiDAR,
IMU and four encoder feeds. Post RAM67.2177%, max60.5C. Protected services active,
PIDs and restart counts unchanged (all0):camera1824,telemetry3293,mux1814,
EKF2868,localization4595,LiDAR1815. No service restart,permissions,calibration,
navigation or motor changes. Domain77,75/80/70,4s lease preserved.

Evidence: `/home/jetson/project-atlas-migration/astra-20261021/preview-core-live-once.json`
PC copy artifacts/astra_concurrent_20261021/preview-core-live-once.json.
SHA25643d02452f08bfcb924698c1878baae01ea1d89ca3af080bf4e5eb92e51b1728e.
Reviewed scalar evidence above; raw logs not committed.

Next necessary work: explain parked/background aggregate headroom and pre-driver
startup load using retained evidence; do not repeat camera attempts or claim
conversion improvement fixed admission. Another Start needs new owner approval.
