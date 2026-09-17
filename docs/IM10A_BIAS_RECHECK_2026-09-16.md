# IM10A stationary bias recheck

The previously validated stationary bias did not remain valid in the later run.
The corrected candidate integrated -13.83 degrees over 60 seconds while raw Z
gyro was zero. A subsequent raw-only check received 602 samples at 10.017 Hz,
with zero checksum errors, maximum gap 0.122 s, and sensor Euler yaw change
-0.170 degrees. Constant zero Z gyro still requires dynamic validation.

Disabled bias correction explicitly in configuration and made the observer
require `enabled: true` before applying any saved bias. Preserved the old values
for investigation, not as an approved calibration. Deployed observer/config to
Jetson and restarted only atlas-im10a.service. Compilation passed; raw readings
continued and the service logged correction disabled. No motor command issued.
EKF fusion remains disabled. Temperature/reboot stability and physical rotation
sign/magnitude validation remain outstanding.
