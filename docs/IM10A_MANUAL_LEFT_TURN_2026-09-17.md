# IM10A manual left-turn result

User completed an approximately 90-degree manual left turn after recorder
readiness. No motor commands issued. Evidence on Jetson:
`/home/jetson/project-atlas-migration/im10a_measured_turn_1789646124.jsonl`.

Snapshot at 60.074 seconds: 603 samples. Integrated sensor Z gyro +88.782
degrees, correct left-turn sign; nominal reference difference 1.218 degrees.
Reference positioning was by hand, not a precision calibration fixture.
Earlier approximate right turn measured -84.445 degrees. These demonstrate
both yaw-rate signs and approximate scale, not full navigation qualification.

Maximum stamp gap 0.12023 seconds; maximum reception gap 0.12256 seconds;
zero non-increasing stamps and reported checksum errors zero. Delivery-age
median 0.00137 seconds, p95 0.00442 seconds. Maximum 0.85414 seconds belonged
to first startup sample, before readiness and before the turn at elapsed
42.114–43.714 seconds. First-five/last-ten-second mean Z rate was zero.

Integrated X/Y component rates were -11.418/-1.330 degrees, not Euler angles.
Peak Z rate +171.204 degrees/second: this was a quick hand rotation with
off-axis motion, not the requested slow level precision test.

Sensor Euler yaw changed only +31.415 degrees. Keep absolute/magnetic heading
excluded. No correction factor should be derived from this hand reference.
EKF configuration unchanged; fusion remains disabled. Next implementation
stage is isolated gyro-only fusion validation, followed by a controlled
comparison against independently observed rover motion once encoder health
and normal movement safety requirements are met.
