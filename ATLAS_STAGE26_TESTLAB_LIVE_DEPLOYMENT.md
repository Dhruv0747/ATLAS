# ATLAS Stage 26: Test Lab live deployment (read-only)

Status: **DEPLOYED / HTTP VERIFIED / BROWSER VERIFIED / LIVE ENCODERS VERIFIED / MOTOR PULSES LOCKED / PHYSICAL TEST PENDING**

Date: Sat 17 Oct 2026. Authorization: owner message 17:26, read-only deployment only. No motor was commanded, no pulse was run, E-STOP was never released or pressed.

## 1. Latest GitHub HEAD (at start)
Branch `agent/sync-developer-20261011` at `4e7199b` (Stage 26 build). `main` at `a6f044d`, untouched.

## 2. Cause of the 404
`/v2/testlab` returned 404 because Stage 26 had only been built and pushed; it had never been installed on the Jetson. The live `atlas_web_v2.PAGES` allow-list had no `testlab` entry and the files did not exist. It was not a routing bug.

## 3. Preflight
Preflight ran before any change; all checks passed (E-STOP latched, manual-only, no commission armed, motor commands zero, lifted flags off, base driver PID 3145 sole owner of `/dev/ttyUSB1`, `index.html` pre-state hash `61f3a12e59bf1237` matched, backup target writable, disk free). Note the repo `atlas_status_web.py` carries undeployed steering code, so it was NOT copied; the live file was patched in place with two hook lines.

## 4. Deployed files (under `~/project_atlas`)
New: `scripts/atlas_testlab_core.py`, `scripts/atlas_testlab_web.py`, `web/v2/testlab.html`, `testlab.js`, `testlab.css`.
Modified: `web/v2/index.html` (one Test Lab link), `scripts/atlas_status_web.py` (import + 2 hook lines), `scripts/atlas_web_v2.py` (`testlab` page entry).
Not installed: `base_dropin/99-testlab-lifted.conf.disabled`.

## 5. SHA256 (first 16 hex)
| File | Before | After |
|---|---|---|
| atlas_status_web.py | 1be48aa972bdf79f | 6658db9412b85b34 |
| atlas_web_v2.py | d460c9b6610ce0b7 | c3607f416d49bd9e |
| web/v2/index.html | 61f3a12e59bf1237 | 4d4dea5620c80e91 |
| atlas_testlab_core.py | absent | 6030aab00bdf7cf6 |
| atlas_testlab_web.py | absent | b0a69f3615c213a2 |
| testlab.html | absent | 05ac4a7d758be830 |
| testlab.js | absent | e9b7edf9d3ee9173 |
| testlab.css | absent | 59a3bb375f22a85a |

Unchanged after deploy: yahboom_base.py c551be0053a43755, atlas_motion_recorder.py 7110961ca9692f6b, seed_atlas_localization.py 273989b23e9ee023, atlas_localization_verify_core.py d95828a09b174d10, atlas_drive_pid_lifted.py 6fedb0a0a247cb7b, shell.js f05f6b8103af638e, motion-status.js 592daa6942011bfe.

## 6. Regression tests
Offline Test Lab suites (core, web, static) passed before the push (see the Stage 26 document). On the live unit, the Stage 21 base driver, Stage 22 recorder and Stage 24 files are byte-identical by hash (above), and `rover-base-telemetry` (PID 3145) was not restarted (active since Fri 16 Oct 11:06).

## 7. HTTP routes
`/v2/`, `/v2/testlab`, `/v2/testlab/` return 200; `/v2/` contains the Test Lab link. Existing pages `/v2/mapping`, `/commissioning`, `/camera`, `/lidar` and `/api/status` still return 200.

## 8. Browser verification
Headless Chromium on the owner's PC against the live address, at desktop and mobile width: page renders fully styled, no console errors, no broken assets, no horizontal overflow, Forward/Reverse disabled. Screenshots: `testlab_desktop.png`, `testlab_mobile.png`. Caveat: the in-app browser pane could not load subresources from a private address without per-action approval, so a separate headless browser was used. This is not the owner's own phone or Chrome.

## 9. Live M1-M4 telemetry
Real `/atlas/encoder_update` data at 10 Hz, chip "Encoders live". All four channels `ok`, direction "still", 0.0 rpm, last change hours ago: M1 -56, M2 3660, M3 1243, M4 -6322. Counts are static because the rover is stationary and the stream is fresh (10 Hz frames arriving), so this is zero movement, not stale data. This does NOT clear the earlier M2/M3 fault history; that needs the hand-rotation test.

## 10. CSV export
Read-only session recorded and exported: 244 sample rows over channels 1-4, correct motor names and timestamps, values matching live ROS counts. Saved under `~/project_atlas/data/diagnostics/testlab/` (mode 0640). A later "observe" session file is also present from verification.

## 11. Motor controls
Remain **LOCKED**. Gate shown: "Lifted raw interface enabled in the base driver: Disabled". Verified post-deploy: owner state IDLE, raw interface disabled, physical power cut unconfirmed, motor PWM 0,0,0,0, no publisher on `/atlas/drive_pid/lifted/request` (topic does not exist). Base-driver environment unchanged.

## 12. Service restart
Only `rover-status-web` restarted, 17:29:51 IST (apply.sh), NRestarts=0 since, no tracebacks or errors in its journal. Base telemetry, EKF, AMCL, Nav2, LiDAR, IM10A, mux untouched; no reboot.

## 13. CPU / RAM / temperature (Jetson)
Observed for about 2 min after a 36 min run: status-web RSS 183.5 MB, flat (183,632 to 183,496 kB, no growth). Temperature 64 C steady. System load average 15-21, available RAM about 2.4 GB. status-web CPU is **about 45-52% of one core with no browser connected**; the Test Lab ROS node is not running when idle (not in the node list). The hot threads are the existing status/control executors. Previous process averaged about 3.5% (1h03m CPU over 30 h), so this is higher than before, but I could not attribute it: Nav2/AMCL have also been running since about 15:05 and the verification itself was heavy. Not a Test Lab-caused fault as far as I can show, but unproven. See remaining issues.

## 14. Backup and rollback
Backup: `/home/jetson/project_atlas/.pre_stage26_testlab_20261017_172948` (with SHA256SUMS). Rollback: `tools/deploy/stage26_testlab/rollback.sh` then restart only `rover-status-web`. Not needed, not used.

## 15. Remaining issues
- status-web CPU (item 13) is high with no clients. If the owner wants proof it is not Test Lab, a controlled A/B (rollback, measure, reapply) is needed; I did not do it unasked.
- Physical testing needs separate owner approval after securing the lifted rover; enabling pulses would need a base-driver flag change and base restart.
- M2/M3 encoder hardware cause still open; hand-rotation test output and connector photos from the owner pending.
- Physical E-STOP tests not passed; Jetson password rotation and temporary key removal outstanding; Candidate B undeployed; Stage 17B on hold; Foxglove hardening deferred.
- Dashboard E-STOP state API was read (latched); the E-STOP button itself was deliberately not pressed.
- Temporary files left on the owner's PC `~/Downloads` (`live_status_web.py`, `stage26_pkg.tgz`, `pre*.sh`, `post.sh`, `cpu.sh`, `s26verify/`) and `/tmp` on the Jetson.

## 16. Final commit
`543878b2ed063ed047169e0206f34b7a117869da` (report commit; any later docs-only commit on the branch only records this ID).
