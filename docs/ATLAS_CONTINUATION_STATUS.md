# ATLAS continuation status — 2026-10-11

This is a source-and-read-only-runtime reconciliation, not an autonomy release.
The handoff baseline `3ad76db` is historical. The developer branch had advanced
to `248d42c` when checked; its commits are included in review branch
`agent/sync-developer-20261011` at `249397a`. Neither branch was merged into
`main`. Unrelated untracked artifacts and the local `deploy/` directory were
left untouched.

## Evidence boundary

- Read first: `AGENTS.md`, `docs/HANDOFF_2026-10-11.md`, the current-blockers
  audit and root-cause registry, the Oct 11 reliability audit, the stage 1–5
  deployment records, and the moving-localization and local-map audits.
- At 15:18 IST, read-only Jetson checks found `rover-status-web`, the
  localization monitor, Visual Cloud agent/server and mission control active.
  Live `atlas_status_web.py` and `atlas_web_v2.py` SHA-256 prefixes matched the
  stage-5 record (`ac05831b`, `6c58e6cc`); `/` returned HTTP 200.
- The E-STOP was **latched** (`REMOTE STOP: B pressed`). The web reset reported
  available with the operator PIN configured. No reset was requested.
- A fresh map API sample reported LiDAR/AMCL **VERIFIED**, difference 0.028 m
  and 1.4°, with `suggest` relocalization mode. This parked sample does not
  supersede the recorded moving failure or authorize a route.
- No motor, steering, autonomous, reboot, network, service, seeding, map or
  calibration action was performed during this reconciliation.

## Deployed feature register

| Original stage | Source / record | Source tests | Deployment | Real-world validation / remaining |
| --- | --- | --- | --- | --- |
| 1 E-STOP latch and reboot-action removal | `c71b95d`, `a7e2299`; `docs/deploy/ATLAS_DEPLOYMENT_RECORD_2026-10-11.md` | isolated tests reported | **DEPLOYED**, live source matched stage 5 descendant | **PARTIALLY COMPLETE**: formal phone/two-finger, reconnect and stopped-motion checks C1–C5 not passed |
| 1b authenticated reset and fresh press | `3e10de4`, `e65fe67`; deployment record | isolated tests reported; operator resets observed | **DEPLOYED**; PIN configured | **PARTIALLY COMPLETE**: formal E1–E8 and release C6 need operator session |
| 2 Glass UI V2 | `adcf823`; `docs/ui/ATLAS_GLASS_UI_V2_PROTOTYPE_REPORT_2026-10-11.md` | browser/source tests reported | **DEPLOYED** | Real phone with PC off not checked |
| 3 web hot/cold executor split | `d681142`; deployment record | benchmark/status contracts reported | **DEPLOYED**, reported 55.9% → 39.4% of one core | Longer real-workload endurance not certified |
| 4 local Visual Cloud | `0cd9d95`; deployment record | local-mode tests reported | **DEPLOYED**; legacy 25 GB DB preserved | Idle CPU without viewer and history disposition open |
| 5 V2 default routing | `5b49f25`; `docs/deploy/ATLAS_V2_DEFAULT_2026-10-11.md` | 48/48 isolated safety, 220 contract comparisons reported; six V2 source tests passed in this checkout | **DEPLOYED**, live hashes and `/` confirmed | Real-phone E-STOP and connectivity checks not passed; V1 retained for rollback |

The developer's isolated tests and source checks are not a substitute for the
operator's physical safety session. The previous developer's temporary key
should be removed by its owner/administrator; this reconciliation used a
separate existing migration key for read-only SSH.

## Root-cause task register

Statuses reconcile the 19 registry IDs against the newer handoff. `UNRESOLVED`
in the registry often means a deployed mitigation lacks endurance or physical
proof. Commits and paths below identify the most relevant evidence, not every
historical attempt. “Tested” means the stated test only.

| ID and original title | Status; commit / relevant files | Tested / deployed / real-world result | Genuine remainder, dependency and next action |
| --- | --- | --- | --- |
| 001 Encoder channel response and post-replacement metric calibration | **PARTIALLY COMPLETE**; `1771b1d`, `project_atlas/scripts/yahboom_base.py`, `docs/audits/ATLAS_CORE_RELIABILITY_READONLY_2026-10-11.md` | Fresh parked M1–M4 packets; not a loaded scale/sign pass | Bounded drive recorder, then operator-approved tape-measured 2 m/4 m and turn trials; no CPR change yet |
| 002 USB role ambiguity and discovery starvation | **PARTIALLY COMPLETE**; `be25b57`, `project_atlas/udev/` and serial discovery code | Identity work exists; cold-boot and swap endurance not passed | Motor-power-off device-absence/reconnect test after approval |
| 003 ROS discovery / transport inconsistency | **PARTIALLY COMPLETE**; `f84f5d8`, ROS environment and unit files | Historical CLI daemon recovery; no load-wide qualification | Compare service ROS environment and bounded passive discovery; do not infer node failure from CLI alone |
| 004 Cached encoder freshness versus receive-thread freshness | **PENDING**; `1771b1d`, `yahboom_base.py` | Passive samples only; failure mechanism unlocalized | Common-monotonic-clock owner/receive/cache instrumentation; no motion required for first pass |
| 005 Commissioning heartbeat/readiness and observer cleanup | **PARTIALLY COMPLETE**; `475de9c`, lifted-test client and Oct 8 audit | Readiness once; later heartbeat failure | Three zero-output 60 s trials and cleanup/missed-heartbeat injection before powered pulse |
| 006 Daly partial frames and polling deadline | **PARTIALLY COMPLETE**; Daly node and freshness tests | Parser/freshness mitigations exist; current BLE endurance fails | Observe complete four-cell snapshots without changing the safety gate |
| 007 Intermittent Daly Bluetooth connection failure | **BLOCKED**; BMS unit/journals, Oct 11 reliability audit | 1,164 failed bonds in observed boot; no verified repair | Stopped BLE contention/connection-stage audit; avoid broad Bluetooth resets |
| 008 Recovery parser falsely restarted motor owner | **VERIFIED**; registry's September recovery fix | Registry marks verified fixed | Keep regression; do not reopen without new evidence |
| 009 Shared I2C/serial recovery and servo-startup interaction | **PARTIALLY COMPLETE**; UNO bridge and recovery units | Historic sensor recovery; current long-run proof incomplete | Source/live identity and endurance checks before changing wiring |
| 010 IMU authority changes and drift | **BLOCKED**; IM10A observer/EKF config, Oct 11 reliability audit | Parked zero counts confirmed; moving 0.46× turn remains | Record signed measured turns; no gyro gain/bias change yet |
| 011 Mapping startup race, stale places and pose corrections | **BLOCKED**; `atlas_localization_monitor.py`, moving-failure and map audits | Monitor deployed; verified parked, LOST about 1.05 m/24° after a short drive | Build bounded motion-triggered recorder first; then supervised evidence and corridor remap; no autonomous release |
| 012 Planner/controller contradiction and provisional calibration copies | **PARTIALLY COMPLETE**; Nav2 config and prior commissioning records | Source contradiction corrected earlier; route repeatability not passed | Validate only after safety, odometry, localization and map gates |
| 013 Remote steering regressions and commanded-angle model | **BLOCKED**; `yahboom_base.py`, steering audit | Manual steering visually works; no measured physical angle feedback | Preserve current controls; compare commands versus measured turns before model changes |
| 014 Observability overhead and overstrong success claims | **PARTIALLY COMPLETE**; `d681142`, Visual Cloud and web perf audits | Scoped CPU drop measured; no full-load certification | Benchmark with actual viewer/robot workload and report per-core CPU, RAM and message ages |
| 015 LiDAR startup recovery and boot clock chronology | **BLOCKED**; `docs/audits/ATLAS_CORE_RELIABILITY_READONLY_2026-10-11.md`, LiDAR unit | First scan delayed 20–257 s; no runtime drop once started | Operator USB 5 V cold-boot measurement; independent powered port comparison before restart-policy changes |
| 016 Visual Cloud placeholder destination and stale history | **PARTIALLY COMPLETE**; `0cd9d95`, `atlas_visual_cloud_{agent,server}.py` | Local-only bounded new history deployed; old 25 GB DB untouched | Reconcile registry wording, measure idle load, decide legacy DB retention with operator |
| 017 Failed BMS reads republish stale scalar values | **PARTIALLY COMPLETE**; `5bdce11`, Daly node/agent tests | Fix deployed, short healthy runtime; invalid-path endurance missing | During natural BLE failure confirm no fresh scalar publication and fail-closed preflight |
| 018 Unclean Jetson reboots with NVMe PCIe error storms | **BLOCKED**; Oct 11 reliability audit and boot journals | Unclean 00:55 shutdown; no proven AER/crash causal link | Preserve boot-ID/monotonic evidence; inspect power/SSD in a planned stopped session |
| 019 Multi-AP Wi-Fi roaming and cellular route flips | **BLOCKED**; Oct 11 reliability audit | Main AP DHCP 26/26; secondary/extender failures; route flips observed | Prepare rollback-backed network experiment; no live network change without approval |

The registry's old “46 roams” claim conflicts with the Oct 11 journal
correction (six associations in the reproduced hour). The newer count should
govern future work; the old claim is **unverified**, not a current KPI.

## Priority and participation

1. **Next independent engineering task:** design and offline-test a bounded,
   motion-triggered diagnostic recorder, without starting background capture.
   The Oct 10 and Oct 11 moving-localization failures lacked the needed bag.
   Deployment/background recording needs separate operator approval.
2. **Operator-supervised safety gate:** V2 phone E-STOP/reset and lifted-wheel
   fresh-press tests. Keep the stop latched except within the approved steps.
3. **Then measured motion:** 2 m/4 m straight and ±90° turns with the recorder,
   followed by evidence-based wheel/IMU/AMCL analysis. Do not retune blindly.
4. **Later:** LiDAR cold-boot power test, corridor midpoint/Hall scans and
   supervised slow local remap; network changes only with rollback access.

The current branch remains review-only. No autonomous motion, automatic
reseeding, map promotion, FlySky receiver authority or calibration change is
authorized by this status document.
