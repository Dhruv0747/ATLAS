# Track A gate G2: Astra mount measurements, recovered from existing records (2026-11-06)

No new physical measurement was made. Sources searched: `docs/ATLAS_ISSUE12_M0_BASELINE.md`,
`docs/ATLAS_ISSUE12_M1_DEPTH_VALIDATION.md` (newest on `codex/status-cache-nonblocking-20261104`), all 13 comments on
GitHub issue #12, every repo branch (rover/robot/overall height, holder, lens, axle), the field manual, and the
Jetson configs. Reference point (owner-confirmed, issue #12, 26 Oct 2026 21:45 IST): **the floor point at the
midpoint between the front and rear axles**; x forward, y left, z up.

The camera holder was changed at **26 Oct 2026 22:48 IST** ("the owner states this mount is final"). The record
from that moment says everything about the camera pose measured before it is superseded.

| # | Value | Recovered | Source / date | Status |
|---|---|---|---|---|
| 1 | **x** (IR lens, forward) | +0.10 m | owner, 26 Oct 21:32, **before** remount | **REJECTED (superseded)**: record says "re-verify, the holder was moved" |
| | | +0.13 m (derived) | after remount: owner tape lens→wall 0.79 m and front edge→wall 0.67 m (26 Oct 22:5x), so the lens is 0.12 m behind the front edge; front edge at +0.25 m (owner: LiDAR at the axle midpoint, 0.25 m from the front and rear edges; body length 0.50 m) | **CANDIDATE**: a calculation from owner measurements, not a direct measurement. Needs owner confirmation. Not written to config. |
| 2 | **y** (sideways) | ≈ 0 m | owner, by eye, **before** remount | **BLOCKED**: record says "re-verify" after the remount; no later value |
| 3 | **z** (IR lens height) | **0.30 m** | owner, ruler, **after** remount (issue #12, 26 Oct 22:48 IST) | **ACCEPTED**, written to config |
| 4 | **pitch** | **+0.8°** | owner, phone inclinometer, **after** remount | **ACCEPTED** as 0.8° nose-down, written to config. Sign reasoning: the same app read −10.3° for the old mount, which depth proved was nose-up. Caveat: nominal-intrinsics depth gradient suggested ≈ 1.8° up. Tested: if that is the truth, the floor never becomes a phantom obstacle, but a 10 cm box is still detected at 1.0 m and **missed at 2.0 m** (points computed too low). G4 must measure pitch from the floor plane before G5. |
| 5 | **rover overall height** (→ `max_height_m` = top + 0.05) | none | no record anywhere (the LiDAR scan plane at 0.40 m is not the rover top) | **BLOCKED** |
| – | yaw | 0° | owner "facing straight ahead", fixed mount (unchanged by remount statement); depth suggested ≈ 2.7° to a wall (rover squared ±2°) | config default 0°, G4 cross-check |

## Frame consistency (open, separate approval-gated item)

The running LiDAR TF (`atlas-laser-tf.service`) puts the LiDAR **0.05 m behind** `base_footprint`. The owner measured
it **at** the axle midpoint (and M1 raw ranges put it 0.23 m behind the front edge, about +0.02 m). So the software
`base_link` is probably about 5 cm ahead of the physical axle midpoint. The Astra values above are physical
(axle-midpoint) values. Until the LiDAR TF is corrected (M0 "proposed correction path", needs owner approval),
Astra and LiDAR obstacles of the same object may differ by about 5 cm along x. G4 must measure this offset (box at
a tape-measured spot) before G5.

## To complete G2 (owner, at the rover; one short session)

1. Confirm or correct **x = +0.13 m** (axle midpoint to the IR lens front face).
2. Measure **y** of the IR lens from the centre line.
3. Measure the rover's **highest point** above the floor.

Then fill `x_m`, `y_m` and `max_height_m` in `config/astra_obstacles.yaml`; `verify.sh` re-checks the gate.
