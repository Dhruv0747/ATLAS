# IM10A turn disagreement investigation

Read-only review; no navigation configuration or hardware settings changed.
M4 encoder is not required for this investigation or for IMU commissioning.

Evidence: im10a_turn_1789568419.json, 1203 dashboard samples over 119.98 s.
Yaw change -85.67 degrees; integrated Z gyro -46.11 degrees. At elapsed
28.04..28.24 s yaw steps were -3.68, -4.13, -3.98 degrees at approximately
0.1 s intervals, while reported gyro Z was +1.28, +0.73, +2.01 degrees/s.
This is inconsistent with simple yaw integration. Samples during this segment
were spaced approximately 0.1 s apart, so the largest 0.34 s gap alone does
not explain the disagreement. Dashboard Euler values are cached from an
independent frame type and may be up to 0.3 s old; this capture is not a
synchronized raw-packet reference and cannot establish the definitive cause.

Driver uses gyro scale 2000 degrees/s and SI conversion. Hiwonder's manual
specifies +/-2000 degrees/s and describes magnetic heading fusion and the
need for magnetic calibration. Actual installed algorithm mode was not read.
Magnetic correction/interference is a hypothesis, not a confirmed diagnosis.
https://docs.hiwonder.com/projects/IMU-Module/en/latest/docs/1.User_Manual.html

Next validation must record raw gyro timestamps, Euler-frame timestamps and
magnetometer together against an independently measured rotation. Do not use
the disputed Euler angle to calibrate gyro gain. Do not enable absolute-yaw
or gyro EKF fusion until the relevant measurements pass validation. Saved
bias correction remains disabled. Normal motor service remains inhibited.
