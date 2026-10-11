# ATLAS Visual Cloud: read-only audit (2026-10-11)

Status: **audit and proposal only.** No service was stopped, restarted, enabled or disabled. No
configuration or data file was changed. All Jetson commands were reads:
- `systemctl show` and `journalctl`;
- `/proc` sampling;
- `ss` and `tailscale serve status`;
- a read-only SQLite open (`mode=ro`);
- one `GET` to the local preview API.

The token value was never read or printed; only its file mode and length were checked.

## Verdict in one paragraph

Visual Cloud has delivered **no data anywhere since 2026-10-04 15:09:11 IST**. That is the exact
second the Oct 4 CPU optimisation was deployed. That deployment replaced the Jetson config
(previously `cloud_url: http://127.0.0.1:8095/api/v1/ingest`) with the repository copy, whose
`cloud_url` is the placeholder `https://atlas-visual-cloud.example/api/v1/ingest`. The result:
- every upload has failed at DNS since then (21,349 identical warnings since journald retention
  begins on Oct 8);
- the local preview server has received nothing, and its live view (`:8443`) is empty;
- the agent still spends ~11% of a CPU core building and gzipping ~460 KB snapshots that are then
  discarded;
- a 25 GB history database from Sep 25 to Oct 4 is kept on the SSD but read by no UI.

The Oct 4 report described the failing uploads as "correctly fail without affecting local
control". The failure is harmless to control, but it was a regression of the local preview, not
an intended state.

## Evidence (Jetson, 2026-10-11 08:46 IST, up 1 h 09 m, load average 12.0 / 14.1 / 12.9)

| Question | Finding | How measured |
|---|---|---|
| Do uploads succeed? | **No.** Every attempt fails with `Name or service not known` because `atlas-visual-cloud.example` does not resolve (`getent` rc=2). No TCP connection is opened, so no payload bytes leave the Jetson. | journal: 727 of 727 agent lines in the last 2 h are this warning; 21,349 since Oct 8 |
| What was it before? | `http://127.0.0.1:8095/api/v1/ingest`, the local preview server. The topic list is identical before and after. | `data/deploy_backups/20261004_cpu_visual_cloud/atlas_visual_cloud.json.before` |
| Does the local preview receive useful data? | **No.** `GET /api/v1/robots` returns `[]`. There are 0 history rows in the last 10 min. The newest row is 581,824 s old (2026-10-04 15:09:11). The tailnet page `https://project-atlas-jetson…:8443/` therefore shows "CONNECTING" with no data. | local API GET; read-only SQLite |
| Agent CPU | **11.4% of one core** (60 s `/proc` sample), consistent with the lifetime average (457.7 s CPU / ~4,140 s uptime ≈ 11%). It runs at nice 10. The `CPUQuota=15%` is not enforced for user services (noted in the Oct 10 audit). | `/proc/<pid>/stat` |
| Agent RAM | RSS 82 MB, 17 threads, 17 ROS subscriptions (systemd `MemoryCurrent` 57 MB) | `/proc/<pid>/status` |
| Server CPU / RAM | 0.00% / 18 MB RSS (idle: nothing arrives) | same |
| Network | Upload bytes: 0. One DNS lookup per attempt: every 5 s idle, every 1 s when active. Only the tailnet `:8443` proxy and `127.0.0.1:8095` are listening; no client was connected. | `ss`, journal |
| Disk: history DB | **25 GB** (`history.sqlite3` = 26,501,885,952 bytes). Rows: 86,400 (the retention cap), Sep 25 03:18 → Oct 4 15:09. Average row 353 KB (`traffic` 345 KB, `graph` 110 KB, `mission_evidence` 9 KB). Freelist: 6,070 pages. That is **one third of all used space** on the 467 GB SSD (74 GB used). | `ls`, `du`, SQLite `pragma` |
| Disk: logs | ~720 warning lines/hour into the journal (journald total 4.1 GB system, 3.0 GB user). Small per line, but it is pure noise. | journal |
| Disk writes if re-pointed unchanged | With the current server code, restoring the old URL would persist one ~353 KB row per second while active (≈30 GB/day of SQLite writes) and keep pruning to 86,400 rows. **Do not restore it as-is.** | code: `NORMAL_PERSIST_S=1.0`, `RETENTION_ROWS=86_400` |
| Who depends on it? | Only:<br>- the command-center link "VISUAL CLOUD / ROS GRAPH" (`atlas_status_web.py:2216`, and the V2 header link);<br>- the two service names listed in `atlas_web_diagnostics.py:45-46` (log viewer).<br>No ROS node, launch file, systemd unit (reverse dependency: only `default.target`), cron job or script reads `:8095`, the DB or the agent's output. It publishes nothing to ROS. | `grep` across scripts/config/units/workspace src; `systemctl list-dependencies --reverse`; `crontab -l` |
| Does the preview UI use the 25 GB history? | **No.** The dashboard only fetches `/api/v1/robots` (latest snapshot in memory). `/api/v1/history/<robot>` has no caller; if called, it would return 600 rows ≈ 212 MB of JSON. | `atlas_visual_cloud_dashboard.html`, server code |

Evidence gaps:
- `/proc/<pid>/io` is not available on this kernel, so the agent's own disk writes were not
  measured directly. It writes only journal lines today.
- Journal retention starts Oct 8, so the first DNS failure on Oct 4 is inferred from the DB's
  last row and the backup timestamp, not observed in the log.
- The ~11% CPU was measured under high system load (load average 12). An unloaded measurement
  may differ.

## Feature value: what is useful and what duplicates the dashboard

| Visual Cloud feature | Unique? | Value for ATLAS now |
|---|---|---|
| ROS graph (nodes, topics, services, actions) | **Unique.** The dashboard has no graph view | Useful for debugging (for example DDS discovery faults, missing Nav2 nodes). Needs only a slow cadence (30 s) and only when someone is looking |
| Topic rate/age table for 17 topics, plus the "pipeline" (LiDAR → costmap → planner → controller → mux, encoders → odom → EKF → AMCL) | **Partly unique.** The health tiles cover sensors but not `/plan`, `/cmd_vel_nav`, the costmaps or `/tf` rates | Useful when Nav2 is being tested. Autonomy is disabled now, so it has little day-to-day use |
| Mission history / rosbag evidence list | Probably unique (not seen in the command center; needs confirmation) | Useful after supervised navigation trials |
| Navigation preview canvas (map, costmaps, plan, scan, odom) | **Redundant and weaker.** The page itself says frame alignment is not verified, and it draws odom pose, not map pose | Superseded by `/mapping`, which has verified localization states. Drop |
| CPU load / RAM / temperature / git KPIs | Redundant with the system panel and diagnostics | None |
| 25 GB SQLite history (Sep 25 → Oct 4) | Unique data, but no reader | Possible forensic value for the Sep 25 to Oct 4 period. Keep until you decide |
| Remote cloud upload | Not configured (placeholder) and no host exists | None today |

## Proposal (nothing implemented; each step needs your approval)

Ordered from least to most change. Steps 1 and 2 are independent of each other.

**1. Stop the futile upload work (config + small code change).**
- Add an explicit `"upload": "local"` / `"off"` / `"remote"` mode instead of relying on a URL.
- In `off` mode the agent keeps its subscriptions and freshness counters but builds no snapshot,
  runs no gzip and does no DNS.
- Expected saving: most of the 11% core. The remaining cost is serialized-message callbacks,
  which still record receive times.
- Rollback: restore the previous script and config from a backup and restart only the agent.

**2. Restore the local preview safely, on demand.**
- Point `cloud_url` back at `127.0.0.1:8095` only together with:
  - **viewer-gated publishing.** The server records when `/api/v1/robots` was last fetched and
    exposes `GET /api/v1/demand` (localhost). The agent checks it every 5 s. With a viewer in the
    last 30 s it publishes at the current 1 s / 5 s cadence; without one it builds nothing;
  - **bounded history.**
    - Persist at most one row per 60 s (plus every row whose `failure_class` ≠ NONE).
    - Strip the scan/costmap `value`s from persisted rows; keep rates and ages.
    - Cap the DB by bytes (for example 500 MB) rather than rows.
  - **a dashboard fix:** draw the map preview in the map frame or remove it in favour of a link
    to `/mapping`.
- Rollback: as for step 1, plus the server script.

**3. The existing 25 GB history: preserve, then decide.**
- Proposed: make a read-only, compressed extract:
  - every `failure_class` ≠ NONE row;
  - one row per 10 min with `traffic` values removed;
  - expected size well under 100 MB.
- Write it to `data/visual_cloud/archive_20250925_20261004.sqlite3.gz`, verify row counts, and
  only then, with your approval, delete the original or move it off the Jetson.
- No deletion is proposed now. "Unused by any current UI" does not mean you won't want it.

**4. Glass UI V2 integration.**
- Do not embed Visual Cloud in V2 until step 2 exists; today it would show an empty page.
- Afterwards, V2 could add a read-only "ROS graph & pipeline" view fed by the same local API.
- The V2 header keeps the existing link unchanged for now.

**Not proposed.** Disabling the agent or server, or deleting the DB, before you decide. Those
are reversible but would remove the only ROS-graph view.

## Corrections to earlier records

`docs/VISUAL_CLOUD_IDLE_CPU_2026-10-04.md` states the placeholder endpoint makes uploads
"correctly fail without affecting local control". The second half is true. The first half
missed that the deployment itself changed the endpoint from the working local server to the
placeholder. A dated correction note has been appended to that document; the original text is
kept.
