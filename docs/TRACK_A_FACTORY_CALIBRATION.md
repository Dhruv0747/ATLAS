# Track A: Astra calibration source (2026-11-06)

**Decision (owner instruction 2026-11-06):** accept the Astra Pro's factory / driver calibration as the baseline.
The custom 22-view checkerboard calibration and `config/astra_calibration/depth_160x120.json` are removed from the
Track A deployment path. **No custom calibration was performed** (the G1 session reached 2 of 22 views and was
stopped). No calibration metrics are claimed.

## What the device and driver actually provide (measured on ATLAS, 2026-11-06)

Isolated ROS domain, Astra serial **17122120830**, driver `astra-arm64-stage29-v2`:

| Source | Result |
|---|---|
| Device stored calibration: service `/astra/get_camera_params` | `success=True`, but **every value NaN** (`l_intr_p`, `r_intr_p`, `r2l_r`, `r2l_t`, `l_k`, `r_k`). This device has no readable per-unit factory intrinsics (matches the Stage 32 note "factory calibration reads as NaN"). |
| Depth `/astra/depth/camera_info`, 160x120 | `K = [142.586, 0, 79.5; 0, 142.586, 59.5; 0, 0, 1]`, `D = [0,0,0,0,0]`, plumb_bob, frame `astra_depth_optical_frame`. **Finite and plausible.** |
| IR `/astra/ir/camera_info`, 640x480 | `fx = fy = inf` (unusable; not used by Track A) |

The depth CameraInfo is the driver's **default pinhole model**: the driver logs "Image resolution doesn't match
calibration ... Using default parameters". fx = 142.586 px equals a horizontal field of view of 58.6 deg at 160 px,
which is the Astra's specified depth FOV (about 58-60 deg). The principal point sits exactly at the image centre, and
distortion is zero.

So the accepted baseline is the **manufacturer driver's nominal model** (FOV-derived), labelled in software as
`FACTORY_DRIVER_CAMERAINFO` with `calibration_nominal: true`. It is not a per-unit factory calibration, and not a
custom one.

## How it is loaded and checked at runtime

* `atlas_astra_obstacle_scan.py` subscribes to `/astra/depth/camera_info`. `core.validate_camera_info()` requires:
  * size 160x120 and frame `astra_depth_optical_frame`;
  * finite K and D;
  * fx and fy within 114-172 px (50-70 deg HFOV) and within 2 % of each other;
  * principal point within the middle 20 % of the image;
  * skew 0;
  * plumb_bob or rational_polynomial, with |d| <= 1.
* Until a CameraInfo passes, the node publishes **no scan** (state `NO_CALIBRATION`). If an invalid one arrives later,
  the node drops its intrinsics and stops publishing (`BAD_CALIBRATION`); it recovers when a valid one returns.
  These cases are tested end to end.
* The node logs the loaded values, and the 1 Hz status topic carries them (`calibration_source`, `fx`, `fy`, `cx`,
  `cy`, `d`). In the parked shadow run on 2026-11-06 the status reported FACTORY_DRIVER_CAMERAINFO,
  fx 142.586, cx 79.5.

## Accuracy implications (engineering assessment, not measured)

* Depth values come from the sensor's on-chip processing and are unaffected by K.
* An error in K changes only the bearing and lateral position of points. At 2 m, a 2 % fx error moves a point at the
  image edge by about 2 cm, which is well under the 5 cm costmap resolution.
* Zero distortion is assumed. Real lens distortion near the edges is unmeasured. Points at the FOV edges are the
  least certain.
* The camera's real pitch and height have **not** been cross-checked from depth: no floor was visible in the parked
  scene. This remains a G4 item, which needs open floor in front of the parked rover.

## If a real calibration is made later

The G1 tools (`tools/vision3d/astra_calibration_live.py`, `checkerboard_calibration.py`, SB detector, `--resume`)
are kept. A measured K/D could be published by the driver through a camera-info URL. The runtime validator accepts
it unchanged and reports `calibration_nominal: false`.
