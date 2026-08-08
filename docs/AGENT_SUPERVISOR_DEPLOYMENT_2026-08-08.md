# ATLAS Agent Supervisor Deployment — 2026-08-08

## Deployed mode

The ATLAS agent supervisor is installed on the Jetson in **monitor-only** mode.
It can inspect rover state, prepare bounded mission plans, explain decisions, and
record bounded persistent memory. It cannot dispatch motion until an operator
explicitly enables execution and confirms a motion plan.

## Safety architecture

- The agent never publishes `Twist` messages or writes raw motor commands.
- Motion-capable tools route through the existing mission-control, Nav2, command
  mux, watchdog, and safety-monitor chain.
- The fixed allowlist contains status inspection, mapping/home operations,
  navigation cancellation, and guarded tight-recovery requests.
- Plans are limited to four steps and one motion-capable tool.
- Mapping plans save home before starting exploration.
- Recovery is available only when explicitly requested or when live telemetry
  reports a blocked/traction-fault condition.
- Fresh autonomy telemetry, required sensors, battery state, command ownership,
  and fault state are checked before any action can be dispatched.
- Any cancellation request stops the plan worker and invokes the high-level
  navigation-cancel path.

## Runtime units

- `atlas-agent-supervisor.service`
- `atlas-tight-recovery.service`
- `atlas-mission-control.service`
- `atlas-rover-status-web.service`

The two new units are enabled in the user `default.target` and were verified
active with zero restarts after deployment.

## ROS interfaces

Inputs:

- `/atlas/agent/command` (`std_msgs/String`)
- `/atlas/agent/confirmation` (`std_msgs/String`)
- `/atlas/agent/cancel_request` (`std_msgs/Empty`)

Outputs:

- `/atlas/agent/status`
- `/atlas/agent/state`
- `/atlas/agent/plan`
- `/atlas/agent/decision`
- `/atlas/agent/response`

Control services:

- `/atlas/agent/set_enabled`
- `/atlas/agent/set_execution_enabled`
- `/atlas/agent/confirm_plan`
- `/atlas/agent/cancel_plan`
- `/atlas/agent/clear_memory`

Mission-control now also provides `/atlas/cancel_navigation` as a topic and
Trigger service. The web dashboard exposes agent state and the latest decision.

## Verification performed

- Python compile checks passed for the agent core, supervisor, mission control,
  and dashboard bridge.
- Seven unit tests passed, including raw-motor rejection, plan bounds, mapping
  home injection, and recovery gating.
- A live cloud-planning request produced a safe mapping plan while exploration
  remained inactive in monitor-only mode.
- ROS graph inspection confirmed that `atlas_agent_supervisor` is not a
  publisher on `/cmd_vel` or any mux input velocity topic.
- Agent memory persisted at
  `/home/jetson/.config/project_atlas/agent_memory.json`.

## Deployment backup

The pre-deployment Jetson files are stored in:

`/home/jetson/project_atlas/backups/agentic_20260808_2310`

This contains the previous mission-control and dashboard scripts.
