# Astra calibration and point-cloud validation — 21 October 2026

Baseline `6be6fb999f70be5f9295fd436bed7b132f693a42`. No rebuild, stream
activation, recording, production restart, calibration write or navigation change.

## New verified evidence

Fresh read-only admission: CPU67.055%, RAM66.0%, hottest63.187°C, E-STOP
latched, manual-only, commissioning disarmed, source STOPPED, commands zero,
Stage20 recorder OFF. One sample is not sustained headroom or complete sensor
freshness certification. Astra is not running; USB remains0403/0501.
All458 installed manifest hashes match. Archive SHA256 remains
`8d840fb9166212ea707392e76e74cfd07aba2b4c049f6bc6608ca228118f553c`.
Camera/LiDAR/EKF/AMCL/base service PIDs/restart counts unchanged.
No calibration file found in scoped `.ros/camera_info`/isolated staging search;
this was not a filesystem-wide search.

## Calibration investigation

Pinned vendor source `f7e71d9ce806e788cb48d8580aac2c778fba4214`,
`astra_camera/include/openni2/OniCTypes.h`, defines30 floats/120 bytes:
two4-float intrinsic arrays, rotation9, translation3, two5-float distortion arrays.
Our ctypes layout matches. A simple struct-size mismatch is not supported;
deeper firmware/plugin incompatibility is not ruled out.

`src/ob_camera_info.cpp:getCameraParams()` uses property14/120 bytes for0403.
Its resolution-selecting128-byte wrapper is only for PID0659/065a. Do not try
another model's payload blindly. Prior rc0/size120/all-NaN output proves unusable
returned parameters, NOT broken hardware or corrupt EEPROM. No EEPROM write.

New source finding: property return status is unchecked before caching;
`src/utils.cpp:isValidCameraParams()` checks only four left intrinsics for NaN,
not infinity, positive focal lengths, right intrinsics or distortion. Some
CameraInfo paths consume right intrinsics. This validation weakness is confirmed,
but is NOT proven to cause the all-NaN response. No driver rebuild on speculation.

Factory recovery is NOT exhausted: supported-property/serial/firmware metadata
and a vendor-supported alternative SDK read path remain to investigate. Do not
repeat identical property14 requests or upgrade/flash firmware without evidence.
Driver supports separate `ir_info_url` and `color_info_url`, with dimension checks;
UVC RGB has its own CameraInfo manager. Finite FOV fallback K is not calibration.
Reference: [official driver](https://github.com/orbbec/ros2_astra_camera).

## Offline preparation

`project_atlas/tools/vision3d/calibration_validation.py` rejects unknown source,
missing independent evidence, wrong serial/resolution/frame, malformed K/D,
nonfinite values and invalid focal/principal data. No implicit resizing.
A valid document is not proof of physical accuracy.

Scalar depth statistics accept in-memory target ROIs and explicit measured
distance/units: median, signed/absolute error, invalid percentage, temporal
frame-median variation and scale ratio. No device access, fitting, image saving,
publisher or automatic accuracy pass. Six synthetic tests are not hardware tests.

## Next owner input / approval

Continue non-streaming supported-property investigation after fresh complete
admission; no owner target needed for that step. For actual accuracy request
separate approval for one bounded stationary depth-only scalar-statistics test,
no saved images/rosbag. Prepare a flat matte board square to the depth sensor at
a tape-measured1.00m from its optical reference, NOT bumper/Pi-camera distance.
Report reference and measurement uncertainty. Board fills centre ROI; hands out
of beam; E-STOP remains latched. Use a supported distance if1m is unavailable.
Then validate0.5/1.5/2m individually as sensor range/space permit; edge statistics
require a measured plane filling those ROIs. No accuracy claim before this.

If factory recovery fails, guided separate IR/RGB calibration needs additional
mode/capture approval, rigid checkerboard inner-corner counts, measured square
pitch, varied poses and an independent held-out target. Phone tilt cannot supply
intrinsics. Depth-scale testing and intrinsic calibration are separate.

## Cloud, resources and deployment gates

XYZ-only first: validated depth K at exact resolution, verified depth units,
rectified pixels or validated distortion handling, optical Xright/Ydown/Zforward,
invalid points rejected, matching source frame/timestamp. Validate flatness,
known dimensions and discontinuities. Color needs independently verified RGB/depth
extrinsics/registration; body fusion needs measured body extrinsics. None passed.

Existing `/v2/vision3d` partial RGB/depth manifest remains unchanged. No fallback
CameraInfo/cloud added to metric measurements. Full metric deployment package
is blocked by calibration; no dashboard restart/autostart. Repository-only tooling
requires no live rollback; isolated runtime remains OFF.

Prior concurrent mean82.586%/peak99.860% CPU, driver14.339% of one core, cannot
be compared causally to today's single67.055% sample. No matched A/B or CPU fix
claimed. Latest directive retains75% CPU/80% RAM/70°C guards; earlier CPU exception
is not silently reused. No live stream test launched. Future matched windows need
identical observer/workload/startup exclusion and sensor callback-gap reporting.

Future roadmap only: shadow depth obstacles outside LiDAR plane; measured
extrinsics/age/false-positive checks before separate Nav2 approval. RGB-D mapping
evaluation follows registration/timing/resources. Accepted LiDAR2D map remains
primary; no RTAB-Map install or costmap change in this stage.

| Gate | Status |
|---|---|
| CALIBRATION INVESTIGATED | Yes; layout/source path narrowed, root cause unknown |
| CALIBRATION VALIDATED | No |
| DEPTH ACCURACY VERIFIED | No physical reference yet |
| POINTCLOUD VERIFIED | No; blocked |
| RGB-D REGISTRATION VERIFIED | No |
| DASHBOARD READY | Partial RGB/depth only; metric3D not ready |
| PRODUCTION DEPLOYED | No |
| NAV2 INTEGRATED | No |
