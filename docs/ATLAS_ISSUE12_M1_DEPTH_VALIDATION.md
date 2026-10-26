# Issue #12, M1: depth validation log

Running record of M1. Raw captures stay on the owner's PC / Jetson (not committed). ATLAS was parked for every step (E-STOP latched, source STOPPED, manual-only, commissioning disarmed, zero commands); every camera session was the normal guarded Vision Lab session (≤ 60 s; 75 % CPU / 80 % RAM / 70 °C).

## Station A1 (26 Oct 22:1x IST), OLD mount (superseded geometry)
- Ground truth: IR lens to wall 0.79 m; front-left/right/centre to wall 0.67/0.67/0.67 m (square); skirting board 1–2 cm.
- Depth centre 0.800 m: **error +1.0 cm (+1.3 %), PASS** (limit max(2 %, 2 cm)).
- Frame rate at the camera (domain 77 probe): **19.2 fps** at 160×120@30 (target ≥ 25: not met). Dashboard received 13.1 fps.
- Resources: guard CPU max 71.5 %, RAM 64.1 %, 65.1 °C, GPU 0 %.
- Unevenness: a left step (~8.5 cm, a different surface) and a smooth vertical gradient, which was **camera pitch ~9.3° up**. Later confirmed physically (phone −10.3°).
- LiDAR: raw range straight ahead 0.895 m, so the LiDAR is 0.225 m behind the front edge; wall fit 3.7° (to be re-checked with a robust fit).

## Remount (26 Oct 22:48 IST)
- The owner levelled and secured the Astra (phone ≈ +0.8°). IR lens height ≈ 0.30 m by ruler. Mount final.
- **Superseded:** pitch ~10° up, height 0.275 m, lens x +0.10 / +0.13, draft TF (0.10, 0, 0.275). Must be re-measured.

## Remaining M1 acceptance items
- [x] Centre depth accuracy at 0.8 m (A1, old mount; sensor property)
- [ ] Depth accuracy at further distances (target 0.6–3.0 m), new mount
- [ ] Frame rate ≥ 25 fps at the chosen resolution (160×120 measured 19.2 fps; 320×240 A/B pending)
- [ ] LiDAR vs depth wall agreement; LiDAR position (front + rear stations) and yaw (robust fit)
- [ ] Height test (LiDAR 0.40 m vs 0.18 m) and scan-filter exclusion test
- [ ] Body vs wheel-to-wheel width


## M1: repeat station at 0.79 m with the NEW mount, plus the 160×120 vs 320×240 comparison (26 Oct 2026, 22:5x IST)

**Pre-checks (before each session):** E-STOP latched, source STOPPED, manual-only, commissioning disarmed, zero commands, drive controller DISABLED, Vision Lab OFF.

**Owner ground truth:** D_cam 0.79 m, D_front 0.67 m, corners 0.67/0.67 m (square), lens height 0.30 m (ruler), tilt ≈ +0.8° (phone), mount fixed.

Sessions:
- 160×120: 2 × 40 s (the first one's rate probe crashed on a probe-script bug, so the run was repeated) plus a 15-s full-frame capture.
- 320×240: 1 × 40 s.
- The **original setting was restored and verified** afterwards: saved depth 160×120@30, colour 320×240@15, IR 640×480@30. The settings backup on the Jetson is sha aa9ca4e9.

### Results

| | 160×120@30 (default) | 320×240@30 (test) |
|---|---|---|
| Depth at centre vs 0.79 m tape | 0.788 m (**−0.2 cm**) | 0.788 m (**−0.2 cm**) |
| Valid centre pixels | 100 % | 100 % |
| Top / bottom / right ROI | 0.798 / 0.785 / 0.781 m | 0.796 / 0.785 / 0.783 m |
| **Frames published by the camera** (domain 77, source stamps) | 19.5 fps, but **in pairs**: 189 gaps ≈ 0 ms and 200 gaps ≈ 100 ms, so only **~10 distinct moments per second** | **29.7 fps**. Gaps: 440 × 1 period, 89 × 2 periods (≈ 14 % single drops), 6 × ≈ 0 |
| Max frame gap / p95 | 0.107 / 0.102 s | 0.061 / 0.054 s |
| Received by the dashboard viewer | 12.9 fps | **29.7 fps** |
| Guard CPU max | 70.6 % | 72.1 % |
| RAM max / temp max / GPU | 64.5 % / 65.2 °C / 0 % | 64.8 % / 65.2 °C / 0 % |
| Session end | completed (client stop at 40 s) | **stopped at 37.9 s by the USB identity guard (false positive, below)** |

### Did levelling the camera help? Yes
- **Top-to-bottom gradient:** 800 → 785 mm over rows 8–96 (was 851 → 769 mm). That's a residual pitch of **≈ 1.8° up** (nominal intrinsics; phone +0.8°), down from 9.3°.
- **The skirting board now appears as a clean ~2 cm step in the bottom rows,** as expected for a level camera facing a flat wall.
- **Centre accuracy improved** from +1.0 cm (with the tilted axis) to −0.2 cm.
- **The left-side step** (~8.8 cm farther, columns 8–40) is still there. It's a feature of the room, unrelated to the mount.
- **Camera yaw relative to the wall:** ≈ 2.7° (nominal intrinsics; rover squareness ±2°). For M2 to measure precisely.
- **Floor visibility:** **not measurable at 0.79 m**. With the lens at 0.30 m and level, the floor only enters the image beyond ~0.72 m, so at 0.79 m the bottom rows reach the wall/floor junction. A station at ≥ 1.2 m is needed to see the floor and to check the 0.30 m height and the pitch from the floor plane.

### LiDAR (no configuration changed)
- **Correction to the earlier report:** with outliers rejected (raw points saved, iterative 2-cm inlier fit), the LiDAR wall angle is **0.08°** (±20° window, 2,201 points, 2.7 mm rms) and **0.4°** (±10°, 1,282 points, 1.5 mm rms). **The earlier 3.7° / 5.4° was an artifact** of the recessed area at the left of the wall. LiDAR yaw is ≈ 0° within the rover squaring accuracy (±2°). The "~3.7° LiDAR mounting yaw" hypothesis is withdrawn.
- **Raw LiDAR range straight ahead:** 0.899–0.900 m against the front edge's 0.67 m, so the **LiDAR is 0.23 m behind the front edge** (both stations agree). The absolute x (relative to the axle midpoint) still needs the rear station.

### Finding: false-positive stop in the Astra USB guard (existing safety code; not changed)
- `tools/vision3d/stationary_ros_probe.py::verify_astra_usb_access` compares the **full** `os.stat()` of `/dev/bus/usb/001/<n>` before and after its check. That includes `st_atime`/`st_mtime`, which the kernel updates on usbfs I/O.
- **Evidence:**
  - the depth node's atime/mtime read **22:58:45**, the moment the 320×240 session was stopped (22:58:06–22:58:44);
  - **no kernel USB events**;
  - same device numbers since boot (11/14);
  - the aliases are correct.
- The guard fails safe (it stops the camera), but at 320×240 the higher I/O rate makes it **randomly stop sessions**.
- **Proposed fix (needs approval):** compare only identity fields (`st_dev`, `st_ino`, `st_mode`, `st_rdev`, `st_uid`, `st_gid`) plus the existing access check, not the timestamps. Add a regression test that reproduces a timestamp change.

### Recommendation
- **Use 320×240@30 for depth obstacle detection.**
  - It delivers ~3× more distinct frames per second than 160×120 (29.7 vs ~10) and 4× the pixels, with the same accuracy.
  - Cost: about +1.5 % peak CPU.
- **Caveat:** peak guard CPU reaches 72.1 %, about 3 % below the 75 % guard. The M3 obstacle node must be very light (row/column striding, no colour stream), or the system load must come down first.
- **Do not adopt 320×240 as the saved default yet.** The default stays 160×120@30 until:
  - (a) the USB guard false positive is fixed (approval needed);
  - (b) a full 60-s 320×240 session completes with no guard trip.

### M1 acceptance status
- [x] Depth accuracy at 0.79 m: old mount +1.0 cm, **new mount −0.2 cm**. PASS.
- [ ] Depth accuracy at 0.6, 1.0, 1.5, 2.0 and 3.0 m (new mount): pending stations.
- [ ] Frame rate ≥ 25 fps: **FAIL at 160×120** (structural, ~10 distinct frames/s). **29.7 fps at 320×240** over 34 s; a full 60-s run is blocked by the USB guard false positive. Proposal: make the criterion "≥ 25 fps at the chosen operating mode (320×240)".
- [ ] Floor visibility / height / pitch from the floor plane: needs a station ≥ 1.2 m.
- [x] LiDAR yaw: ≈ 0° (robust fit); the earlier 3.7° is withdrawn.
- [ ] LiDAR absolute x: rear station pending. Height test (0.40 vs 0.18 m), scan-filter exclusion test, body vs wheel-to-wheel width: pending.

No TF, LiDAR, Nav2, navigation or safety setting was changed. **Waiting for the owner before the next station and before any guard fix.**
