# Live Jetson snapshot — 2026-11-06

Exact bytes copied from the running rover (`~/project_atlas` on 100.87.208.71), top level of
`scripts/`, `web/v2/`, `config/` only. Purpose: make GitHub match what actually runs. Not reviewed line by line;
nothing was changed on the Jetson. Secrets scan (API keys, tokens, passwords, private keys): no hits.

Not included: models/engines, maps, logs, recordings, root-owned files under /usr/local/libexec and /etc
(e.g. the monitoring guard, now disabled), the MediaPipe venv, and subfolders deeper than one level.

## Files

```
UPDATED 	project_atlas/config/atlas_agent.yaml
NEW     	project_atlas/config/atlas_feature_on_demand.yaml
NEW     	project_atlas/config/atlas_flysky_drive.json
UPDATED 	project_atlas/config/atlas_house_semantic.json
UPDATED 	project_atlas/config/nav2_params.yaml
UPDATED 	project_atlas/scripts/Rosmaster_Lib.py
UPDATED 	project_atlas/scripts/amg8833_thermal_node.py
UPDATED 	project_atlas/scripts/atlas_agent_core.py
UPDATED 	project_atlas/scripts/atlas_agent_supervisor.py
NEW     	project_atlas/scripts/atlas_base_maintenance.py
NEW     	project_atlas/scripts/atlas_callback_probe.py
UPDATED 	project_atlas/scripts/atlas_cmd_vel_mux.py
NEW     	project_atlas/scripts/atlas_controller_input_web.py
NEW     	project_atlas/scripts/atlas_dashboard_executor.py
NEW     	project_atlas/scripts/atlas_dashboard_executor_impl.py
NEW     	project_atlas/scripts/atlas_feature_on_demand.py
NEW     	project_atlas/scripts/atlas_flysky_camera.py
NEW     	project_atlas/scripts/atlas_flysky_drive_core.py
NEW     	project_atlas/scripts/atlas_flysky_reset.py
NEW     	project_atlas/scripts/atlas_flysky_teleop.py
UPDATED 	project_atlas/scripts/atlas_fusion_bag_analyzer.py
UPDATED 	project_atlas/scripts/atlas_localization_monitor.py
NEW     	project_atlas/scripts/atlas_manual_controller_web.py
UPDATED 	project_atlas/scripts/atlas_mission_control.py
UPDATED 	project_atlas/scripts/atlas_safety_status.py
UPDATED 	project_atlas/scripts/atlas_sensor_recovery.py
UPDATED 	project_atlas/scripts/atlas_status_web.py
UPDATED 	project_atlas/scripts/atlas_steering_calibrate.py
UPDATED 	project_atlas/scripts/atlas_steering_commission.py
UPDATED 	project_atlas/scripts/atlas_steering_ui.js
UPDATED 	project_atlas/scripts/atlas_voice_companion.py
UPDATED 	project_atlas/scripts/atlas_web_v2.py
NEW     	project_atlas/scripts/hat_power_node.py
UPDATED 	project_atlas/scripts/install_atlas_uno_r4_udev_root.sh
UPDATED 	project_atlas/scripts/nav2_cmd_adapter.py
UPDATED 	project_atlas/scripts/radar_avoidance.py
UPDATED 	project_atlas/scripts/rd03d_node.py
UPDATED 	project_atlas/scripts/rover_dashboard.py
UPDATED 	project_atlas/scripts/seed_atlas_localization.py
NEW     	project_atlas/scripts/test_atlas_agent_core.py
UPDATED 	project_atlas/scripts/test_closed_loop_control.py
UPDATED 	project_atlas/scripts/test_commissioning_channel_source.py
UPDATED 	project_atlas/scripts/test_encoder_selection.py
UPDATED 	project_atlas/scripts/test_im10a_bias.py
UPDATED 	project_atlas/scripts/test_rear_ultrasonic_guard.py
UPDATED 	project_atlas/scripts/test_straight_distance_core.py
UPDATED 	project_atlas/scripts/test_voice_status.py
UPDATED 	project_atlas/scripts/tof_center_node.py
UPDATED 	project_atlas/scripts/yahboom_base.py
UPDATED 	project_atlas/web/v2/camera.html
UPDATED 	project_atlas/web/v2/classic.html
UPDATED 	project_atlas/web/v2/commissioning.html
NEW     	project_atlas/web/v2/controller-map.js
NEW     	project_atlas/web/v2/controller-viz.js
NEW     	project_atlas/web/v2/flysky-drive.html
NEW     	project_atlas/web/v2/flysky-drive.js
NEW     	project_atlas/web/v2/flysky-mapping.js
UPDATED 	project_atlas/web/v2/flysky-testlab.html
UPDATED 	project_atlas/web/v2/flysky-testlab.js
UPDATED 	project_atlas/web/v2/flysky.css
NEW     	project_atlas/web/v2/health-monitor.js
UPDATED 	project_atlas/web/v2/home.css
UPDATED 	project_atlas/web/v2/index.html
UPDATED 	project_atlas/web/v2/lidar.html
UPDATED 	project_atlas/web/v2/mapping.html
NEW     	project_atlas/web/v2/material.css
UPDATED 	project_atlas/web/v2/testlab.html
UPDATED 	project_atlas/web/v2/vision3d.js
UPDATED 	project_atlas/web/v2/vision_features.css
UPDATED 	project_atlas/web/v2/wifi.html
```
