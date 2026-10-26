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
