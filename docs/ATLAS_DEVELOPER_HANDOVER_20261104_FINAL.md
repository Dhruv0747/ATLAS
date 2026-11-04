# ATLAS final developer handover — 4 November 2026

## Executive summary and scope

Primary priorities: (1) genuine Neural directional signals, preserving Grafana's 40-panel Health Monitor and Windows startup; (2) independent Jetson Vision Lab, Object Detection and read-only Tracking first. Mux/Yahboom upgrades are ON HOLD. No LIVE claim follows from offline tests.

This handover supersedes the earlier morning operational summary, not its historical evidence. No service was restarted, camera activated, latch cleared or production file changed for this handover. Only a read-only service snapshot and Windows task query were performed. Current physical safety and resource admission were NOT remeasured; do not use earlier values to authorize execution.

## 1. Verified operational state

SSH read at **2026-11-04 12:42:25 IST**, Jetson **192.168.1.16**:

- Boot ID `962c3639-1421-4c3c-8f53-6b42ea465c81`; uptime **1118.34 s**.
- Service identities below are observations, not future restart bindings.

| Service | State | PID | NRestarts |
|---|---|---:|---:|
| rover-status-web | active | 2124 | 0 |
| atlas-sensor-recovery | active | 2027 | 0 |
| atlas-cmd-vel-mux | active | 1919 | 0 |
| rover-base-telemetry | active | 3373 | 1 |
| atlas-camera (existing CSI camera) | active | 1937 | 0 |
| atlas-monitoring-exporter | inactive | 0 | 0 |
| atlas-monitoring-watchdog | inactive | 0 | 0 |
| atlas-monitoring-firewall | failed | 0 | 0 |

Astra was OFF at the 12:28–12:30 staging check; not newly queried at 12:42. Last measured staging admission: CPU 61.15%, RAM 47.33%, maximum temperature 59.75 C; three CPU samples 60.10–62.73%. Stop latched, manual-only, commissioning disabled, commands/motor speed zero, fresh MCU, unchanged encoders [-5,4,-3,5]. These are HISTORICAL bounded observations, not current admission or electrical isolation certification.

Windows task **ATLAS Monitoring WSL Autostart** queried at 12:42:25 IST: **Running**. Installation previously PASS; actual Windows reboot acceptance UNVERIFIED. Prior container checks showed Docker active and both containers using unless-stopped. Container health was not rechecked for this handover.

Access from the Windows PC:
- Grafana: http://127.0.0.1:3000/
- Pulse View: http://127.0.0.1:3000/public/atlas-pulse/pulse-view/index.html
- Neural diagnostics: http://127.0.0.1:3000/d/atlas-live-neural-data-flow/atlas-live-neural-data-flow
- Prometheus: http://127.0.0.1:9090/ (verify existing localhost binding before use).
- Use the existing Grafana Health Monitor landing dashboard; its Pulse View link is installed. Keep authentication and all 40 panels.

## 2. Neural: completed work versus current failure

Earlier recovery completed PASS, exporter UP, Prometheus FRESH, owner-confirmed Grafana values. Archived seven evidence files matched; observer-active.json absence recorded explicitly. Recovery resource peaks: CPU72.64%, RAM58.37%, temperature63.66C. These do not describe the current boot.

PC Pulse update 5b97fa4 is installed. Directional movement was genuinely observed intermittently on **two verified paths**. Record **PARTIAL LIVE historical acceptance**, not continuous coverage. ATLAS-only Prometheus scraping changed from15s to3s and passed the approved trial; ordinary browser reconnect PASS. Exporter cache remains15s; its optimization is a separate follow-up. Never extend5s visualization freshness to conceal stale data. Current exporter inactive means current Neural live acceptance BLOCKED.

Historical a8fd494 source object was not recovered. Exported candidate was independently reconciled against5334261; **5b97fa4 is the reviewed functional source**, not a claim that a8fd494 was recovered.

### New retained incident (not the old M2 event)

- FAULT SHA256 `4f04831f22623fad52fa28676348153989291f37ca4b1e4f05069e26e79a7dc5`.
- Watchdog `TimeoutError`, stage API; endpoint `http://127.0.0.1:8088/api/status`.
- Failure **2026-11-04 10:59:42.860 IST**, epoch1793770182.86014; observation began1793770182.3525298 (~507.61ms). This includes work before HTTP, not an exact per-handler duration.
- Incident boot33363f37-3c19-4218-8d30-a01a47ac2a32, monotonic8497.763689717.
- Web logged BrokenPipeError at10:59:42.959–43.192 after client timeout; consistent with a late response, not conclusive latency attribution.
- Recovery began CSI restart at10:59:37.502; camera startup overlapped and capture resumed10:59:45.397. **Correlation only, not proven cause.**
- Last available CPU source sample10:59:34.811:60.5393%; preceding minute~60.54–62.09%. No exact-interval process/CPU evidence. Last UP scrape10:59:42.186 contained older cached evidence;10:59:45.183 UP0.
- One recorded watchdog rejection and one Web broken pipe in reviewed10:18–11:01 logs. Watchdog then stopped; whether underlying delays were isolated or repeated remains UNKNOWN.
- Current-boot firewall refused retained latch at12:23:12. Root read supplied by owner at12:34 showed nftables empty and legacy Tailscale rules. No rule changes authorized.

Original M2 evidence remains historical: FAULT hashfc5479c96fd42ee003a565b0ccb7e63caaf9d29c43a383eff5291a3c938302fd. Preserve its archive; owner reports wheel touching, but original log must not be rewritten.

### Focused API review now completed offline

**Concrete blocking defect CONFIRMED; historical incident causality UNKNOWN.** Existing snapshot holds its shared cache lock while three subprocesses (`ip` address, route query, `ss`) each permit2s, plus system reads. An expired-cache caller and concurrent watchdog requests can block well beyond0.5s. No timeout or freshness relaxation is justified.

Local uncommitted correction in ATLAS-status-cache-fix:
- `project_atlas/scripts/atlas_status_web.py`: single-flight background diagnostic collection outside reader lock; atomic publication with collection-start timestamp; failures keep expired diagnostics unavailable. ROS safety snapshot remains freshly read for every request.
- `project_atlas/tests/test_status_cache_nonblocking.py`: five focused AST-isolated tests, no ROS/camera/services. Demonstrated pre-fix~2s request block. After correction5PASS inWSL (0.111s),5PASS inWindows (0.120s after explicit UTF8 fix). Independent scoped review passed with that encoding correction.
- Refresh attempts1s versus old nominal2s; diagnostic expiry remains2s. Additional Jetson CPU cost UNKNOWN. Existing ROS lock and nested cache are outside this scoped fix.
- Code is NOT committed, packaged or deployed. Keep it intact. Behavior docs/registry reconciliation and exact-live patch preparation remain before a code milestone. This handover intentionally commits documentation only; it does not imply installation readiness.

Read-only exact live Web baseline backup: `C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/status-cache-fix-20261104/original.py`, SHA256 `4b5906f7728a914a01b016d501dbcf673ea364679c5f0df4f8639ab5851317b2`. Any future candidate must patch these verified live bytes, not replace production with the generic repository file. Recheck drift first.

## 3. Vision Lab: staged, not activated

| Feature | Verified status | Remaining requirement |
|---|---|---|
| Object Detection | OFFLINE READY | Load passive cache endpoint safely, host acceptance, real YOLO camera inference |
| Read-only Target Tracking | OFFLINE READY | Same gate; exclude old servo-commanding tracker |
| Face Recognition | BLOCKED | Enrollment storage exists; verified recognition model/threshold, consent and real matching/deletion acceptance |
| Gesture Recognition | BLOCKED | Hand-landmark/gesture runtime |
| Body/Skeleton | BLOCKED | Actual keypoint model/runtime |
| RGB-D Mapping | BLOCKED | Real calibration for Astra17122120830, registration, unchanged mounting TF and onboard map evidence |

Independent host/cache implementation0855063 passed15 focused checks and review. Staging292cce4 passed integrity/identity checks without executing payload. No ROS/DDS participant or duplicate camera driver introduced. Host uses SSH authentication/Unix peer controls, passive cached RGB, existing detector/tracker; no motion publishing. All mapping/inference/storage/viewing remain Jetson-local; Windows optional.

Running Web lacks the passive endpoint and imports its adapter normally. The cache is process-local. Copying source does not load it; old RGB route can touch leases/start transport. No safe passive no-restart export or hot-load path is verified. Do not inject code into Web.

Independent safety file `/run/user/1000/atlas-restart-safety/state.json` was absent; Recovery snapshots disabled. The host's Web-derived guard cannot supervise Web downtime. Fresh independent E-STOP/zero-command/encoder evidence throughout the loading interval is missing. Recovery snapshot restart previously exceeded CPU limits: do not repeat it or reopen Mux work implicitly. **Vision activation NO-GO.**

Real TensorRT CPU/memory/task overhead UNKNOWN;512MiB/16-task host bounds are offline configuration, not real-engine acceptance. Camera remains separately gated (maximum60s including startup; feature sessions30s), no recording/mapping/servo/movement implicit in host approval.

## 4. Packages, exact backups and rollback

All PC paths below use root `C:/Users/Dhruv/Documents/Codex/2026-07-24/h/`. Private backups remain outside Git. No rollback is to be executed merely because it is documented.

**Vision inactive package:** `tmp/vision-host-20261104/vision-host-inactive-20261104.tar.gz` SHA256 `9c1cd41e12253d67c3291acdaa6035772786bdb11f91d0e4a82f4cf92f0a1ba6`.
Jetson stage `/home/jetson/project-atlas-migration/vision-host-inactive-0855063-20261104/`;15 checksum entries,16 archive files0644, private0700 directory; STAGING_RESULT.json captures metadata/identities. Disabled config, template unit only, no registration or boot activation.
Original production adapter `/home/jetson/project_atlas/scripts/atlas_vision3d_web.py` SHA256 `2551d6578aa9429ac8f4fd5ff35f2c16a185c3cd027fafc563b7fff339857190`; backup in staged rollback directory and `tmp/vision-host-20261104/original_atlas_vision3d_web.py`. Original0644 uid/gid1000,mtime_ns1792903589200609668. Candidate SHA256 `02125b91da940e0d96d01938bc7ffde35e6e30389f9fec2c52d8c567fdec4093`. Reverse patch reproduced exact original. Inactive rollback removes only verified staged additions; production not replaced. Any later production rollback restores exact bytes/metadata without an unapproved restart.

**Pulse installed candidates / exact originals:** `tmp/pulse-live-update-20261104/`, manifest PACKAGE_SHA256SUMS.
- candidate/pulse-view/index.html `5c7c6f233d27a511358113109eed2ca2c92e4097fe63f40cf8c62607c9c6f946`
- candidate/pulse-view/view.mjs `89a978dcbb7a4457084fb3f4156895e15f657fe591e8eb95f38514c490f6bd63`
- candidate/SHA256SUMS `a7d4233a966c23acf487857c4d9b8475a6c8ac3edcb4a47b81624f097f3062a1`
- atlas-health.json `5a964a8d5526e0114b613d7e0e2e4d1d3217867b861254123eeb538024ea576f`
- original/pulse-view/index.html `186bbe3cd68208f857fdfbef389f2819692586e87ac679bbcf49bc454c759356`
- original/pulse-view/view.mjs `34296f1abc1fbd2b908c557fa5bfc7ccb5a1d648f7d8640a86f96bf6882e4c4c`
- original/SHA256SUMS `bac68f68f2ce552edd2e271a5378de5cc9aea60e1a8e67d60db6850e1db1f6e4`
- atlas-health.original.json `2b598f1c0936a0683ba69c8796760cac7a34299d8fcf78d8148be8af5bd16a3e`
Complete older tar `tmp/pulse-reconciliation-20261104/original-pulse.tar`, SHA256 `1445e585e28e84baf8125fdbca3a3b29c211ad52e1179085c470c664d2573e35`. Reviewed rollback restores only affected assets/dashboard, not containers/volumes/auth/data. Existing container-root copy requirement does not authorize permission/ownership changes.

**Prometheus3s trial:** `tmp/pulse-freshness-20261104/prometheus.exact-candidate.yml` SHA256 `e016e614d27981b91b5955edae269583e1f2ebc33d2497667cc8223542774604`; exact prior config `prometheus.exact-original.yml` SHA256 `9796b57f954f24f62df39046a114bf136f853eec02190d52add8ef90f73f083d` (both hashes rechecked locally for handover). Preserve successful config. Any later approved rollback restores only config, validates with existing Prometheus tool, reloads without recreation. No reload now.

**Consumed monitoring transactions:** roots `/var/lib/atlas-monitoring-recovery-m2-{20261102,permissions-20261102,noreload-20261104,absence-20261104}` represent historical transactions, never restart targets. Also preserve cpuevidence rejected-package evidence. Consult actual private directories before assuming execution occurred. Last successful transaction exact root `/var/lib/atlas-monitoring-recovery-m2-absence-20261104/`, original-state archive plus state-manifest.json/state-absent.json; result PASS,cleanup NOT_NEEDED,grafana OWNER_CONFIRMED. Package `monitoring-recovery-m2-absence-20261104.tar.gz`, SHA256 `ccc4a28800b05196249a0e0823ae7e6bb104e804a70f9c6bc9729d03f14c75f0`, source5334261, is CONSUMED and bound to old incident; cannot recover the new TimeoutError. Private current evidence `/var/lib/atlas-monitoring/FAULT.json` and fault-events.json must remain untouched. No fresh recovery package or execution authorized.

## 5. Repository map and unfinished work

Worktree base: `C:/Users/Dhruv/Documents/Codex/2026-07-24/h/work/` (verified with git worktree list12:42).

| Directory | Branch | Head before this handover commit |
|---|---|---|
| ATLAS-status-cache-fix | codex/status-cache-nonblocking-20261104 |292cce4; two uncommitted code/test files above |
| ATLAS-vision-host | codex/vision-host-20261104 |292cce4 |
| ATLAS-pulse-live | codex/pulse-live-acceptance-20261104 |5b97fa4 |
| ATLAS-monitoring-absence | codex/monitoring-absence-20261104 |5334261 |
| ATLAS-neural-monitor | codex/neural-monitor-20261102 |7bc3157 |
| ATLAS-onboard-map-final | codex/onboard-map-final-20261102 |e52f5ed |
| ATLAS-pr15-review | agent/dev-superpowers-20261030 |2db3844 |
| ATLAS-github | agent/reliability-optimization-20261023 |5b40b54 |

Other relevant history:4aba5cf provenance,3994fd9 integration,f95c9d2 publisher staging,e52f5ed bounded Mux controller (35 focused checks);31b4542 mapping,d315a28 installer;5c2e9f6 optional-AI boot correction;95fe413 earlier handover. Resolve objects/branches before cherry-picking; no blanket merge authorization. Detailed Vision evidence in docs/ATLAS_VISION_HOST_OFFLINE_RESULT_20261104.md and docs/ATLAS_VISION_HOST_STAGING_20261104.md; Pulse preparation in ATLAS-pulse-live/docs/PULSE_LIVE_ACCEPTANCE_20261104.md.

## 6. Boot and protected publishers: preserve, do not reopen

Previously verified optional-AI boot correction:8 starts→0, longest CPU overload149s→48s, settled~61–62%, peak still100%; baseline strict75% boot acceptance FAIL. Not retested here. Keep correction installed, Foxglove previously disabled by owner. Do not infer current Foxglove state from that history.

Original Mux/Yahboom running; upgrades inactive at `/home/jetson/project-atlas-migration/inactive-publishers-f95c9d2-20261102/`. Exact rollback retained. Owner confirms M1–M4/S1/S2 disconnected, no alternate supply; electrical isolation/USB backfeed and independent maintenance coverage remain unverified. Do not ask repeated confirmations or treat them as electrical certification. No publisher restart, redeployment or redesign in next task. AMCL offline progress is not movement permission.

## 7. Approvals and fail-closed rules

No outstanding blanket execution approval. Separate reviewed authorization needed for any Web load/restart, new host activation, camera/inference session, monitoring recovery, Windows reboot, or protected service operation. Past single-use authorizations are consumed. No new monitoring attempt until current fault review, incident binding, archive-first/rollback and fresh safety admission are complete.

CPU strictly<75%, RAM<80%, temperature<70C; original E-STOP, encoder and freshness gates unchanged. Missing/stale/disconnected evidence is unavailable, never healthy. Safety observation age≤1s, observer output≤0.75s, combined encoder age≤1s remain where required. Web cannot supervise its own downtime. No automatic retry after failure. No fabricated traffic/calibration/TF. No firmware, movement, motor/servo/navigation activation. Preserve evidence, no raw logs/backups/credentials committed.

## 8. First three actionable steps

1. **Neural:** inspect the two existing uncommitted cache-fix files and independent review findings; finish scoped behavior/registry documentation and exact-live reconciliation, then commit the offline fix. Reuse the five passing focused tests unless code changes. Measure CPU cost only under separately approved deployment/acceptance. Do not reset latch or rerun recovery; historical timeout cause remains UNKNOWN.
2. **Vision:** retain staged package unchanged; produce a narrowly scoped activation decision from the existing Web-loading/supervision gap. Without fresh independent safety coverage for the full outage, report NO-GO. Do not substitute Web-derived evidence, hot-patch, or reopen Mux/Recovery experiments. The existing host is OFFLINE READY, not LIVE.
3. Present only the concrete remaining approval/prerequisite to owner: independently supervised Web loading must be established before host activation, and camera inference is separately gated. Keep successful PC assets/3s scraping intact; when monitoring is legitimately restored, verify authentic fresh pulses rather than rerunning synthetic animation suites.

Stop unnecessary investigation loops: current Neural recovery NO-GO; current Vision activation NO-GO. The useful new result is the bounded offline API blocking correction, not a claimed historical root cause or new live acceptance.
