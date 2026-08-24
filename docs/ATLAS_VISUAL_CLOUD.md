# ATLAS Visual Cloud

ATLAS Visual Cloud is a read-only observability layer. It shows ROS graph and
message traffic, navigation evidence, system load, and mission failure context
without adding any cloud-to-motion interface.

## Safety boundary

The Jetson remains the sole owner of ROS 2, Nav2, localization, collision
avoidance, velocity multiplexing, motor control, watchdogs, and emergency stop.
The telemetry agent creates subscriptions only. The cloud API accepts telemetry
ingest and exposes read-only queries; PUT/DELETE are rejected and there is no
command endpoint. Loss of internet, Tailscale, cloud, or browser has no effect
on local safety.

## Components

- `atlas_visual_cloud_agent.py`: bounded Jetson collector; compact values only.
- `atlas_visual_cloud_server.py`: authenticated ingest, SQLite history and UI.
- `atlas_visual_cloud_dashboard.html`: live pipeline, ROS graph, TF and map view.
- `atlas_visual_cloud.json`: monitored topics and expected rates.
- `atlas-visual-cloud-agent.service`: low-priority, CPU/RAM-capped user service.
- `atlas-visual-cloud-server.service`: optional Jetson-local preview; the same
  API can later move unchanged to a separate cloud host.

## First deployment (motor power off)

1. Power the Jetson and network while keeping motor power physically off.
2. Diagnose the reported ROS CLI daemon fault:

   ```bash
   bash /home/jetson/project_atlas/scripts/check_ros_cli_discovery.sh
   ```

   This verifies graph discovery with `--no-daemon`, then resets and verifies
   the CLI daemon. It does not restart the ATLAS ROS stack.

3. On the cloud host, create a strong token and start the API behind Tailscale
   Serve or another TLS reverse proxy:

   ```bash
   export ATLAS_VISUAL_CLOUD_TOKEN='replace-with-random-secret'
   export ATLAS_VISUAL_CLOUD_DB=/var/lib/atlas-visual-cloud/history.sqlite3
   python3 atlas_visual_cloud_server.py
   ```

4. Put the same token at
   `/home/jetson/.config/project_atlas/visual_cloud.token` with mode `0600`.
5. Set `cloud_url` in `atlas_visual_cloud.json` to the authenticated HTTPS
   Tailscale endpoint. Never commit the token.
6. Install/enable the user service and verify CPU/memory limits:

   ```bash
   install -m 0644 project_atlas/systemd/user/atlas-visual-cloud-agent.service \
     ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now atlas-visual-cloud-agent.service
   systemctl --user status atlas-visual-cloud-agent.service
   ```

7. Confirm the dashboard shows traffic while motor power remains off. Only a
   later, separately authorized ground test may validate navigation visuals.

## Metric definitions

- **Hz**: receive rate over the agent's bounded timestamp window.
- **Age**: monotonic seconds since the agent received the last message.
- **Healthy**: fresh and at least 35% of configured expected rate.
- **Delayed**: late or materially below expected rate.
- **Stopped**: never observed or older than the bounded stop threshold.
- **Git version**: deployed repository commit when available, otherwise a
  deterministic navigation-config hash.

The full ROS graph refreshes every five seconds; telemetry publishes once per
second. Full camera frames, costmap grids and bags are not uploaded by this
lightweight first stage. Compact LiDAR/path/pose data is uploaded for live
visualization, while bag paths and mission evidence remain local.

## Remaining live acceptance gates

- Jetson online with motors off.
- ROS CLI discovery passes with and without daemon.
- Agent stays under its 15% CPU and 256 MB memory limits.
- Authenticated HTTPS ingest works over Tailscale.
- Breaking one noncritical test publisher changes its link to STOPPED.
- Cloud loss leaves local safety and stopping fully operational.
