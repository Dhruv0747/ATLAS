# IM10A manual right-turn check

User reported manually positioning the whole rover approximately 90 degrees
right. Subscription-only capture; no movement commands or fusion changes.
Evidence on Jetson: `im10a_measured_turn_1789645501.jsonl` under
`/home/jetson/project-atlas-migration`.

Snapshot through 49.409 seconds, 496 IMU samples:

- Integrated sensor Z gyro: -84.445 degrees (correct sign for right turn).
- Difference from nominal 90-degree reference: 5.555 degrees. Reference is
  approximate; this is not established sensor calibration error.
- Integrated sensor X/Y rates: +9.646 / +8.970 degrees; these are component
  integrals, not Euler angles. Off-axis motion makes a yaw-only check imperfect.
- Motion occurred at approximately 22.669–25.949 seconds.
- Peak Z rate: -258.484 to +65.247 degrees/second. Repeat more slowly for a
  better angle comparison at the sensor's approximately 10 Hz output rate.
- Maximum message-stamp gap: 0.1461 seconds; no non-increasing stamps.
- Maximum recorder reception minus message stamp: 0.9325 seconds. This flags
  a delivery/scheduling delay; it does not establish where the delay originated.
- First-five and last-ten second mean Z rate: zero reported.
- Sensor Euler heading net change: +0.533 degrees, inconsistent with physical
  turn and gyro integration. Do not use that heading for navigation.
- Latest sensor status: live, checksum errors zero.

Conclusion: right-turn gyro sign and approximate response demonstrated. Full
navigation qualification not passed. Keep magnetic/Euler heading and saved
bias correction excluded; keep EKF IMU fusion disabled. Remaining checks are
a slower, level independently marked turn in both directions and investigation
of message delivery latency. Do not infer all encoder health or autonomous
readiness from this manually performed IMU test.

## Follow-up timing investigation

Completed capture: 1788 samples across 178.369 seconds. The 0.9325-second
maximum delivery age was the first sample; the following queued startup
samples decreased in age. These precede the physical turn. Delivery-age
median / p95 / p99 were 0.00129 / 0.00394 / 0.01021 seconds. Maximum reception
gap was 0.3026 seconds. This supports recorder startup backlog, not a sustained
0.93-second sensor delay. It does not establish hardware sampling latency.

A fresh stationary 60.020-second check returned 603 samples at 10.030 Hz,
maximum reception gap 0.2998 seconds, maximum delivery age 0.2010 seconds,
zero non-increasing stamps and zero reported checksum errors. Reported Z gyro
was zero throughout; Euler yaw changed -0.02747 degrees. Mean acceleration
magnitude was 9.75717 m/s². IMU service had zero restarts. Four existing
software checks passed. Occasional delivery gaps remain to be characterized
under load; no claim of hard real-time delivery is made.

The auxiliary capture script now waits for three seconds of samples with
delivery age below 0.1 seconds before announcing readiness. Syntax validated
on Jetson. No navigation driver, EKF or motion configuration changed. Slow
level left/right physical reference tests remain outstanding.
