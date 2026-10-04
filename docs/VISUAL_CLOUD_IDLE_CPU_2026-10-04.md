# Visual Cloud stationary-load optimization — 2026-10-04

## Scope

The live audit measured `atlas_visual_cloud_agent.py` at about 22% of one CPU
core while ATLAS was stationary. The agent remained at its full collection
cadence even though the ROS graph and visualization values were mostly
unchanged. In particular, it rebuilt the full node/topic/service/action graph,
compacted high-rate scan/TF values, serialized and compressed the same large
graph, and spawned `git rev-parse` repeatedly.

This change only adapts the read-only agent's work cadence. Non-activity topics
arrive as serialized messages, so idle callbacks can record freshness without
constructing large Python scan, TF, costmap, path, or odometry objects until a
compact value is due. It does not stop a subscription, change a ROS topic,
alter QoS, publish a command, or change any safety/control component.

## Behavior

| Work | Active | Stationary/idle |
| --- | ---: | ---: |
| Snapshot build/upload | 1 Hz | 0.2 Hz |
| Full ROS graph discovery | every 5 s | every 30 s |
| Sensor deserialization/compact value | every message | at most 1 Hz/topic |
| Receive timestamp collection | every message | every message |

The original active cadence is restored immediately when the agent observes:

- nonzero `/cmd_vel` or `/cmd_vel_nav`;
- an active mapping, navigation, exploration, return, execution, or recovery
  status.

Each signal renews a 30-second active lease. This covers status publishers whose
normal rate is only 0.1 Hz. Viewer presence is not currently exposed to the
one-way ingest agent, so a stationary dashboard uses the five-second idle
snapshot; it is not disabled. `collection_mode` in every payload shows which
cadence is in effect.

The Git revision is cached once at process start. A normal deployment restarts
the service, so each process still reports the deployed revision.

## Stationary deployment gate

Keep the rover stationary with remote stop latched. Before installation, save
the current script and config for rollback. Then install the verified agent,
core helper, and config together and restart only
`atlas-visual-cloud-agent.service`.

Pass conditions:

1. Service remains active and publishes `collection_mode=IDLE` within one idle
   cycle.
2. Topic Hz and age continue changing correctly; no configured topic vanishes.
3. Idle process CPU is measured for at least 60 seconds and is below both its
   previous baseline and the existing 15% systemd quota.
4. With wheels still prevented from moving, publish a short nonzero command
   through an authorized commissioning source or start a no-motion mapping
   state. The next payload must show `ACTIVE` within one second; do not bypass
   the command mux or remote stop for this check.
5. After activity stops, the agent returns to `IDLE` after the 30-second lease.
6. Cloud/API loss still has no effect on local control or emergency stop.

The agent, core helper, and config were deployed together while ATLAS was
stationary. The service remained active with zero restarts and idle process CPU
fell from roughly 22.3% to 11.1% of one core. No control or safety topic changed.
The configured remote endpoint is still the placeholder
`atlas-visual-cloud.example`, so upload attempts correctly fail without
affecting local control; this CPU result validates the local collector, not a
production cloud destination. Rollback copies are under
`data/deploy_backups/20261004_cpu_visual_cloud/`.
