# Owner-approved deployment — 11 October 2026, IST

Branch: `agent/sync-developer-20261011`. Supersedes the earlier same-day
rollback/pending status, but preserves those failed attempts as evidence.
ATLAS remained stationary, stop latched, Nav2/exploration inactive. No motor,
mux, remote, camera-driver, calibration, map or network settings changed.
Motor/mux/remote PIDs remained 1878/1872/1930, with zero restarts.

## Consolidated delivery status

| Component | Implemented | Tested | Deployed | Live verified | CPU impact | Remaining issues |
|---|---|---|---|---|---|---|
| Camera quality | Original-byte full-size viewer | JPEG attribution, page inspection, JS checks | Yes | 1280×720, about 5.1–5.2 displayed FPS observed | Web process 48.10% one core / 8.02% of six-core capacity in camera workload | Source image itself soft; optics/focus cause not proven, historical quality acceptance NOT passed |
| Wi-Fi stability | Existing safeguards preserved; A/B prepared | 120 s observation | No new network settings | 24/24 gateway responses, no disconnects | Not isolated | Timed power-save trial awaits immediate approval and local recovery access |
| BMS Bluetooth | Single retry owner, persistent healthy link, backoff | 54 focused tests previously passed | Yes, stage 8 | Stable processes; no competing restart; bounded retries | 0.70% one core, 66.25 MiB RSS | BLE connect still times out; no healthy battery samples |
| LiDAR Surround | Scan-time base_link projection, points, rings, selection, directions, stale state | 9 geometry/freshness tests; live UI | Yes | Live returns, exact-time TF, zoom, ranges visible | Web process 47.69% one core / 7.95% six-core in visible workload | Owner object-placement test pending; optional map overlay not implemented |
| Global Home | Consistent V2 navigation, Visual Cloud return link | Routes and live HTML/UI | Yes | V2 browser links and Cloud served HTML | Not separately isolated | Full desktop/mobile route matrix not completed |
| Motion recorder | Bounded async writer, opt-in CLI | Prior Humble readback and parked tests | Already installed; hashes reverified | Not running; no duplicate/autostart | Prior parked 29.29% one core, 78.27 MiB | Supervised moving capture not run; one prior DDS-reported loss |

## Camera evidence: what is and is not proved

- V1 and V2 request the same `/camera.jpg` endpoint. It returns cached JPEG
  bytes, not the CrowPanel preview or a resized browser image.
- Read-only 20-second ROS probe received 188 original and 62 AI frames. All
  **62 HTTP samples exactly matched original ROS JPEG hashes**, none matched
  AI output and none were unmatched. Original and AI frames both 1280×720.
- Actual browser image: 1280×720 source, `object-fit:contain`, CSS filter `none`.
  Data Saver was off; it changes refresh cadence, not resolution/compression.
- Live camera unit remains 1280×720 at configured 10 FPS, JPEG quality 75.
  The full-size page fetches each blob once and displays it without re-encoding.
  Hidden tabs pause requests; stale/offline text is explicit.
- Captured original JPEG is visibly soft/hazy. This is upstream of V2 rendering.
  Focus, lens condition and lighting are hypotheses, not verified causes.
  `v4l2-ctl` is unavailable; no package installation or driver change was made.
- Same-frame V1/V2 CSS comparison fixture was generated privately; browser
  policy blocked local-file rendering, so its screenshot comparison is NOT
  claimed completed. Live V2/source screenshots were inspected separately.
- Browser displayed approximately 5.1–5.2 FPS with individual request/decode
  observations 25–138 ms. These are NOT end-to-end optical/control latency.
  Driver source stamps are assigned after capture; they cannot prove exposure age.

## Measured resources and network

Each HTTP workload below lasted 30 seconds. CPU is the **whole dashboard
server**, not incremental cost attributable solely to the added feature.
Existing browser views were also open; workloads are not rigorously isolated.
Do not claim a statistically demonstrated performance improvement.

| Workload | CPU one core | CPU / six cores | Peak RSS | Payload bandwidth | Requests/errors |
|---|---:|---:|---:|---:|---:|
| Before stage 9, camera 8 requests/s | 46.44% | 7.74% | 174.23 MiB | 1.280 Mbps | 240 / 0 |
| After stage 9, camera 8 requests/s | 48.10% | 8.02% | 170.27 MiB | 1.303 Mbps | 240 / 0 |
| LiDAR endpoint, 2 requests/s | 47.69% | 7.95% | 168.70 MiB | 0.141 Mbps | 60 / 0 |

Final whole-system snapshot: CPU 70.4%, RAM 5403/7620 MB (71%), temperature
59°C. GPU utilization unavailable. Idle-vs-visible incremental browser/Jetson
cost and combined driving workload remain unmeasured.

Latest 120-second network/BMS observation: gateway median 1.64 ms, p95 2.19 ms,
max 3.5 ms, 0/24 losses. Dashboard localhost median 62.24 ms, p95 325.94 ms,
max 3872.82 ms, no request failures. That high HTTP tail remains an issue;
do not equate low ping with consistently responsive application latency.
No DHCP failure, Wi-Fi disconnection, cellular route switch, Tailscale major
change or bonding failure in this window. It does not erase historical faults.

BMS: one connect timeout, zero healthy reads in 120 seconds. Retry logs settle
at approximately 130-second intervals (120-second backoff plus transaction and
timer overhead). BMS/recovery PIDs 268412/268405 unchanged. Previous supervisor
restart loop is corrected in this observation; underlying BLE connectivity is
NOT repaired. Phone BMS app disconnected per owner. Bluetooth adapter powered.
Healthy polling remains five seconds to preserve existing 10-second safety
freshness. Requested 15-second display-only cadence is not yet implemented;
temperature is not newly available. No safety thresholds weakened.

## Deployment identity and rollback

1. **Stage 8 BMS**, source `d5d1c59e40d3c010aafacfe9485f635ac80b5022`.
   Three-file scratch apply, byte-identical rollback and live hash checks passed.
   Restarted only BMS and recovery supervisor.
   Backup: `/home/jetson/project_atlas/data/backups/2026-10-11-162142-739196150-stage8-bms-owner/`.
   Rollback: run its `ROLLBACK.sh`, then restart only `rover-daly-bms.service`
   and `atlas-sensor-recovery.service`, while stopped/latched.
2. **Stage 9b operator views**, source `bba0ad5`.
   Ten-file scratch/rollback and live hashes passed. Restarted only dashboard.
   Backup: `/home/jetson/project_atlas/data/backups/2026-10-11-162811-646621295-stage9b-operator-views/`.
   Rollback: first undo stage 9c, then run this `ROLLBACK.sh`, then restart only
   `rover-status-web.service`. Existing recordings are untouched.
3. **Stage 9c fixed visible E-STOP**, source `0ef0b9bffa1b4b1c861553c1d7910c7b51f2b343`.
   One static file, rehearsed rollback/live hash passed; no restart.
   Backup: `/home/jetson/project_atlas/data/backups/2026-10-11-163308-039488106-stage9c-view-stop/`.
   Rollback: run its `ROLLBACK.sh`, reload browser.

Initial stage-9 package generation failed on Windows encoding; it never
installed. Rebuilt with explicit UTF-8 as stage 9b; failure evidence preserved.
Visual Cloud reads its HTML per request, so its Home link needed no restart.

Recorder hashes still match installed `0c1d520` stage 6b; no repeat test or new
service. The existing explicit `--record` CLI workflow is available. Do not start
a moving recording until a supervised session and fresh safety checks are agreed.
No continuous background recorder enabled.

## Tests and evidence

9 projection/timestamp/TF/missing-data tests; 15 routing tests and 12 web safety
regressions in isolated Jetson directory; 11 idle-camera tests; JS syntax checks.
The original 54 BMS/recovery/recorder tests are retained, not physical acceptance.
Visual check: real LiDAR returns, 2/4-metre zoom, correct axis labels; no motor,
stop-release, navigation or calibration button was exercised during UI inspection.
New pages reuse the existing E-STOP handler; no new stop-authority logic.

Private evidence under `/home/jetson/atlas_recorder_smoke_KWJkzy/`:
`camera_before_stage9.json`, `camera_after_stage9.json`, `lidar_stage9.json`,
`network_stage8_owned.json`, `camera_source_attribution/result.json` and frames.
Indoor images and raw logs are not published to GitHub.

## Operator links and next necessary actions

- [Command Center](http://192.168.1.15:8088/v2/)
- [Full-size camera](http://192.168.1.15:8088/v2/camera)
- [LiDAR surround](http://192.168.1.15:8088/v2/lidar)
- [Map](http://192.168.1.15:8088/v2/mapping)
- Stable Tailscale equivalents use `http://100.87.208.71:8088` with the same paths.

Keep ATLAS parked. Place a cardboard target in front or beside it and compare
the displayed return; remove it and verify the view updates. This validates
physical direction/range presentation, not navigation readiness.
Source-camera sharpness requires an optical/focus investigation, not blind
sharpening/compression changes. Wi-Fi power-save experiment still needs immediate
owner confirmation and independent local recovery. No autonomous test authorized.
