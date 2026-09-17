# IM10A lifted motor disturbance screen

Operator confirmed all four wheels lifted, secure support, hands/cables clear.
Normal base remained inhibited and remote stopped. M4 was excluded due to its
unresolved encoder fault. M1, M2, M3 each received +50 PWM for 1.5 seconds,
individually, with zero commands between tests and at completion.

Encoder deltas: M1 +5832; M2 +7555; M3 -5620. Board reported 12.3 V.
Read-only IMU recording contained 1198 samples over 119.51 seconds.
Motor-test window 1789623269..1789623286: yaw span 0.0934 degrees;
gyro Z range -0.00746..+0.00639 rad/s. Post-test yaw span 0.0989 degrees;
post-test Z gyro remained zero. Overall heading change -0.0275 degrees.
Largest dashboard sample gap 0.328 seconds.

No large heading disturbance observed in this short unloaded screen. This is
not full-load magnetic/acceleration validation or proof of compass accuracy.
Only yaw and Z gyro were captured. Baseline before motor sequence was 3.6 s.
Measured turn accuracy remains unresolved; EKF fusion remains disabled.
M4 repair, motor direction/mapping commissioning and dynamic tests remain open.

Jetson evidence: /home/jetson/project-atlas-migration/im10a_turn_1789623384.json
Local evidence retained outside repository under work/atlas_migration.
