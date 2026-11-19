# Stage 31 live deployment: Home UI, Astra private domain, one Depth test (21 Oct 2026)

Owner approval (14:24 IST) covered steps 1–3 only, in order and conditionally. Step 4 (any change to CPU accounting, pausing services or relaxing the single-sample rule) was **not approved and not done**. Package `stage31_pkg.tgz` sha256 `168f6a7cbf7250284fa3d189d73e12952b42f4a8ecb1bc234826c96ec62f1f1f`, built from commit `77c9ff2`.

## Result

| Status | Result |
|---|---|
| **UI DEPLOYED** | **YES** at 14:26:17. Live-verified in a real browser on desktop and mobile. |
| **ASTRA FIX DEPLOYED** | **YES** at 14:28:52. Only `rover-status-web` restarted. Private domain 77 was verified live during the session. |
| **LIVE DEPTH VERIFIED** | **PARTIAL, not a pass.** Real depth frames reached the Dashboard for about 11 s (screenshot below). Then one guard sample read 77.8% and the camera was stopped safely. A sustained session was **not** achieved and there was no retry. |

## Step 1: static UI

**Preflight** (`evidence/stage31_live/pre_ui.txt`):
- E-STOP latched, manual only, commissioning disarmed, source STOPPED.
- `cmd_vel` zero, mission READY.
- No Astra process running.
- All 6 baseline hashes matched.
- CPU 65.1%, RAM 67%, 60 °C.

**Backup:** `~/project_atlas/.pre_stage31_ui_20261021_142617`, with its `SHA256SUMS` re-verified OK after all steps. No service was restarted.

**Installed hashes** (sha256 prefix):

| File | Hash |
|---|---|
| index.html | `19d5bb1f114ccbab` |
| home.css | `9f93d704fef56ba9` |
| home-cards.js | `798461cf2d9ce80d` |
| classic.html | `f53d68120ecdb82e` (identical to the old Home) |
| vision3d.html | `47380d1bd2379a6c` |
| vision3d.js | `f2939d19fb2ef227` |
| vision3d.css | `339e810203a4e50d` |

**Live checks:** real Chromium through an SSH tunnel to the Jetson's own dashboard, recorded in `verify_ui.json`.
- HTTP 200 for:
  - Home, classic and the 3D Vision Lab;
  - the Test Lab, FlySky Lab and mapping pages;
  - commissioning, camera, LiDAR and Wi-Fi;
  - `/api/status`.
- All 7 cards showed real data:
  - Jetson CPU 64% / RAM 68% / 60°;
  - battery 100%, 14.10 V;
  - LiDAR 8.1 Hz, 210/360 points, nearest 0.30 m right;
  - all 4 encoders OK;
  - IMU −120°, gyro used by EKF;
  - network on Wi-Fi.
- The safety pill read "E-STOP latched · REMOTE STOP: joystick unavailable".
- Both E-STOP buttons (dock and pad) were visible. Hardware health read 13 OK / 5 WARN / 0 FAULT. The Pi camera was live at 1280 px wide.
- Every drawer opened with live content. The IMU detail opened.
- The More menu links worked, and all four shortcuts opened the right pages in one click.
- `/v2/classic.html` loaded with "ONLINE" and all 6 drive buttons.
- **No JavaScript errors, and no POST request** from loading the page, opening drawers or clicking cards.
- No drive, camera, reset, shutdown or E-STOP button was pressed live; the request equivalence of those buttons was proven offline.
- Mobile at 390 px: no sideways scroll (the old Home was 442 px wide), height 3,526 px instead of 7,847 px, E-STOP dock fixed.

Screenshots, with the Pi camera picture blurred so no room interior is committed:
- `pub_live_home_desktop.webp` and `pub_live_home_mobile.webp`;
- `pub_live_classic_*.webp`, the old layout, now at `/v2/classic.html`.

## Step 2: Astra private domain

**Preflight** (`pre_astra.txt`): same safety state, CPU 66.1%, no domain-77 user, 102 FastDDS shared-memory ports, all in domain 0.

**Backup:** `.pre_stage31_astra_20261021_142852`, with `SHA256SUMS` OK.

**Installed:** `atlas_vision3d_runtime.py` `a09fc0198e7b479c` and `atlas_vision3d_web.py` `6b9a28c5f6a159f6`.

**Restart:** `rover-status-web` only. PID 67677 → 117520, NRestarts 0. The old process logged its normal shutdown traceback.

**Protected services, PID / restart count unchanged before and after:**

| Service | PID / restarts |
|---|---|
| atlas-camera | 1982 / 0 |
| rover-base-telemetry | 3534 / 1 |
| atlas-cmd-vel-mux | 1975 / 0 |
| atlas-ekf | 3260 / 0 |
| atlas-localization | 5713 / 1 |
| atlas-lidar | 5523 / 5 |

**Health after the restart** (`post_astra.txt`):
- Encoders and drive_pid at 10 Hz, age 0.0 s; LiDAR and IMU fresh.
- Pi camera JPEG 200.
- `/api/vision3d/summary` 200.
- Localization check `INPUT_STALE` ("AMCL pose stale"). This is unchanged from the 13:57 capture, before any Stage 31 change.

Thresholds are unchanged: the summary reports 75 / 80 / 70.

## Step 3: the one Depth-only start (14:32)

- The baseline had settled at 62.8–67.8% (10 one-second samples) before the start.
- **Start was clicked once** in the real `/v2/vision3d` page, Depth only, from the PC browser (`depth_test.json`).

| t after click | Page state | CPU guard sample | Depth on Dashboard |
|---|---|---|---|
| 2 s, 4 s | Checking (3 admission samples) | 66.7% | — |
| 6 s | Streaming, driver running | 63.5% | Live, 20.0 fps, 0.13 s old |
| 8 s | Streaming | 66.0% | **image 160×120 shown**, 15.7 fps, 0.18 s old, 26 frames |
| 10 s | Streaming | 69.4% | 13.2 fps, 0.11 s old |
| 12 s | Streaming | 66.4% | 12.6 fps, 0.16 s old |
| 14 s | Streaming | 66.0% | 13.8 fps, 0.11 s old |
| 17 s | **Stopped to protect ATLAS** | **77.8%** (limit 75%) | driver stopped safely |

**Before vs after.** Under Stage 29/30, every start was rejected at the **first** sample after the driver launched (77.9%, 75.9%, 83.2%, 80.8%). This time five consecutive samples after launch passed (63.5–69.4%) and real frames were delivered.

**The driver itself was cheap.** At the last passing sample the Astra process used 4.5% of one core, with 83 MB RSS; the worker used 1.5%.

**Private domain verified live, at t ≈ 14 s:**
- driver process environment `ROS_DOMAIN_ID=77`;
- 6 FastDDS shared-memory ports in domain 77;
- the domain-0 count unchanged at 102 before, during and after;
- the driver's UDP ports are 26650/26660/26661, which are the domain-77 discovery ports;
- the dashboard's receiver holds domain-77 ports in the same process.

No participant entered the production domain.

**What caused the 77.8% sample is not proven.** It came right after my own mid-session isolation check. That check was an SSH login running `pgrep`, `ss -uanp` twice (which walks every process's open files) and `/proc` reads, at t ≈ 14–16 s. A click-to-measure request followed. The independent per-second CPU recorder I started on the Jetson produced no output (the process was ended with its SSH session), so there is no per-process attribution of that second. This is a likely observer effect, but it is unverified. The click-to-measure returned "STREAM STALE" because the camera had just stopped, so **click-to-measure is not verified**.

**After the test** (`post_depth.txt`):
- E-STOP latched, commands zero, mission READY;
- no Astra driver or worker running, no domain-77 user;
- protected identities unchanged;
- Pi camera 200, CPU 67%, RAM 69%, 60 °C.

Nothing was recorded or saved, and no point cloud was enabled.

## Screenshots (`evidence/stage31_live/`)

- `depth_1_8s.webp`: **real Astra depth image on the Dashboard**, Live, 15.7 fps, 0.18 s old.
- `depth_4_end.webp`: the RESOURCE BLOCKED explanation (77.8% vs 75%, driver stopped safely).
- `depth_0_before.webp` and `after_v2_vision3d_mobile.webp`.

## Rollback (verified ready, not needed)

Both backups pass `sha256sum -c` on the Jetson. The same script restored the same files byte-identically in the earlier rehearsal on a Jetson copy.

```
cd ~/project_atlas
OWNER_APPROVED=yes ~/project-atlas-migration/stage31-deploy-20261021/pkg/project_atlas/tools/deploy/stage31/stage31.sh rollback-astra   # restarts rover-status-web
OWNER_APPROVED=yes ~/project-atlas-migration/stage31-deploy-20261021/pkg/project_atlas/tools/deploy/stage31/stage31.sh rollback-ui      # static, no restart
```

## Next approval, if you want it

One more guarded Depth-only start, **identical** except that the observer stays passive during the session:
- no SSH, `ss` or `pgrep` while streaming;
- one lightweight per-second `/proc` recorder started beforehand under `systemd-run --user` so it survives;
- isolation checked only after the session.

The goal is a full 60-second session and a working click-to-measure. Thresholds stay unchanged and there is no retry on failure.

---

# Second guarded Depth-only test (owner approval 14:42 IST)

## Result

**BLOCKED at start-up. No frames were delivered, and LIVE DEPTH is still NOT VERIFIED.** The single Start (14:44:09 IST) was stopped by the unchanged guard at **76.0%**, 0.5 s after the driver launched. The driver was stopped safely and there was no retry. Click-to-measure could not be attempted.

## Method (as required)

- **Fresh preflight** (`evidence/stage31_live_b/pre_b.txt`): E-STOP latched, `cmd_vel` zero, recorder (stage20 capture) inactive, mission READY.
  - Encoders, drive_pid and IMU fresh; LiDAR 0.5 s old; Pi camera JPEG 200.
  - Protected identities unchanged; no Astra process; no domain-77 user. CPU 65.5%, RAM 71%, 60 °C.
- **Recorder:** `tools/vision3d/stage31_cpurec.py`, run as a transient `systemd-run --user` unit so it survives disconnects.
  - It reads only `/proc` and the Vision Lab state file once per second and writes one flushed JSON line per second, for 200 s (191 samples).
  - It started 30 s before Start and costs about 2% of one core.
- **No intrusion while streaming:** the browser reached the dashboard directly at `http://192.168.1.15:8088`, so no SSH, tunnel, `ros2`, `ss` or `pgrep` ran during the session window.
- **Limits** 75% CPU / 80% RAM / 70 °C unchanged.

## CPU trace (`evidence/stage31_live_b/s31b_trace.jsonl`)

**Overall**

| Window | Busy CPU, 1-s samples |
|---|---|
| 28 s before Start | mean 65.0%, min 62.6%, max 69.8% |
| After the session (130 s) | mean 65.4%, min 60.7%, max 69.2% |

**No one-second sample in the whole 191 s exceeded 75%.** The highest was 73.8%.

**Around Start** (t is the recorder clock)

| t | 1-s busy | Guard state (its own sample) | Main additions over the per-process baseline (% of one core) |
|---|---|---|---|
| 37.7 | 70.6% | worker starting (hashing the 458 runtime files) | Vision Lab worker +14 |
| 38.8–40.9 | 63.6–67.1% | CHECKING: 63.3%, 67.2%, 64.5% | — |
| **41.9** | **73.8%** | driver launched at 3.55 s; **guard sample at 4.06 s = 76.0% → BLOCKED** | **Astra driver start-up +29**, **kswapd0 +12** (kernel memory reclaim), **curl +10** (network fallback HTTPS probe) |
| 43.0 | 67.3% | stopped | kcompactd0 +13 (kernel memory compaction) |

The worker's own record at the rejected sample (`/run/user/1000/atlas-vision3d-viewer.json`): Astra driver 55.6% of one core and 73 MB RSS; worker 4.5%.

## What caused the spike

The failing sample was a coincidence of three short events in the same half-second. None of them exceeds the limit on its own:

1. **Astra driver start-up burst:** 55.6% of one core during the guard's window, about 9 points of the machine. This is the camera's own initialization. In the first test, the steady streaming cost was only about 4.5% of one core.
2. **Kernel memory reclaim:** kswapd0 +12% of a core, followed by kcompactd0 +13%. This was triggered as the driver allocated memory at about 70–72% RAM use.
3. **The network-fallback HTTPS probe:** `curl` launched by `atlas_network_fallback.py`. It ran 7 times in 191 s (at t = 25, 42, 107, 134, 151, 156 and 178), costing 3–10% of a core each time.

It is the guard's **sample length** that turns this into a failure:
- After launch the worker samples on a loop of up to 1 s `select` plus 0.5 s sleep. The browser's lease touches return the `select` early, so the first post-launch window was **about 0.5 s** (3.55 → 4.06 s).
- The same second averaged over 1 s was 73.8%.
- In test 1 the corresponding first sample happened to fall at 63.5% and passed.

So the remaining blocker is not discovery fan-out, which the domain-77 fix removed. It is how a sub-second sample catches the camera's own start-up burst on a 65% baseline.

Test 1's later 77.8% sample has no per-process trace (that recorder failed). The probe pattern above makes the same mechanism plausible there, alongside my own SSH check at the time. This is not proven.

## Other observations

- **Someone else started the viewer before this test.** Between 14:35 and 14:43 the Vision Lab state file shows an additional viewer session that I did not start. Its Astra driver launched at 4.08 s, with the first guard sample passing at 68.6%, and it ended `OFF`, consistent with the page being closed or hidden (lease revoked). This was probably your browser. No Astra process remained afterwards.
- **UI defect:** for about 4 s after Start, the page showed the previous session's summary ("Camera off … Stopped safely") before the new state appeared. It does not affect safety. I'll fix it before any further start.

## After shutdown (`post_b.txt`)

- E-STOP latched, commands zero, mission READY; no Astra process or worker; no domain-77 user.
- Protected identities unchanged: atlas-camera 1982/0, base 3534/1, mux 1975/0, EKF 3260/0, localization 5713/1, LiDAR 5523/5, web 117520/0.
- Pi camera 200, encoders and drive_pid at 10 Hz, IMU and LiDAR fresh. CPU 66%, RAM 68%, 60 °C.
- MemAvailable 2.48 GB of 7.80 GB, swap unused.
- XYZ / point cloud stayed disabled; nothing was recorded.

## Decisions needed (not taken)

Every remaining route changes either the guard's measurement or the background load. Each needs your separate approval:

- **(a)** Make each guard sample cover at least 1 full second. The threshold stays 75% on a single sample; only the window length changes. Every 1-s sample in this trace stayed below 75%.
- **(b)** Exclude the first ~2 s after driver launch from the single-sample rule while still enforcing a hard ceiling (for example 90%).
- **(c)** Pause the network-fallback probe and/or background AI services during a viewing session.
- **(d)** Accept that live depth is not available at the current baseline.

Without one of these, repeated starts will pass or fail depending on whether the start-up burst coincides with background bursts.
