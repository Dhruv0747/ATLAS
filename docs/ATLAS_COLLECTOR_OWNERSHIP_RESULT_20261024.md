# Collector ownership traced — static-cache approach closed

## Decision

Do not deploy the static-executor caching prototypes. The ownership correction
passes subscription removal/recreation, but heartbeat-loss detection is not
reliable in this fixture. Stop this line of experiments; do not request another
identical run or robot drive. Live CPU load remains unresolved. No deployment
package or whole-Jetson CPU improvement is claimed.

Everything ran on PC, in the existing network-isolated Domain216 fixture. No
Jetson connection, installation, service restart, camera start, movement, safety
policy change, voice or white-glass change occurred. Owner CPU-report exception
is confined to the offline test; production75% CPU/80% RAM/70C remain unchanged.

## Source-level cause of previous prototype failures

Inspected upstream rclcpp tag16.0.21, matching the PC fixture version:
https://github.com/ros2/rclcpp/blob/16.0.21/rclcpp/src/rclcpp/executors/static_executor_entities_collector.cpp

- `remove_node` removes automatic groups using `remove_callback_group_from_map`.
- That helper erases the map entry but does not clear the group's associated
  executor flag. `remove_node` clears only the NODE association flag.
- The collector destructor clears group flags by traversing its remaining maps.
  Removing map entries first means that destructor cannot clear those flags.
- The next collector's `add_node` skips groups whose association flag remains set.
  This explains why DDS discovery could succeed while recreated delivery failed.
- Public `remove_callback_group` searches the manually associated map. The old
  experiment passed automatically associated groups from `get_all_callback_groups`,
  explaining its `Callback group needs to be associated with executor` exception.

These findings concern our static-executor PC prototype, NOT a proven cause of
ATLAS's existing standard-executor CPU load or localization errors.

## Tested correction and limits

New `--collector-owned` mode destroys the stopped executor WITHOUT first removing
nodes, allowing its collector destructor to release ownership. It asserts group
association flags are cleared before creating the replacement executor. No manual
flag clearing, delayed safety check or exception suppression is used.

Initial native run passed21 deliveries, removal/recreation, timer cancellation
and real bondcpp failure detection: standard0.398615s, candidate0.398514s.
It reached an exploratory four-pair benchmark, but differing message counts
(99..109) and subsequent correctness failure make that insufficient evidence.

The benchmark was tightened to EXACTLY100 deliveries per variant, with separate
mutation CPU accounting and six planned AB/BA pairs. Before measurement, candidate
heartbeat detection failed the existing1.5s bound; standard passed0.390529s.
Routing peer-node removal through the same ownership-aware transaction was the
single source-supported follow-up; it ALSO failed the unchanged heartbeat gate,
while standard passed0.386059s. Final build succeeds; test exits1. Performance
stage is therefore blocked. No retry or deadline relaxation was used to obtain
a pass. The initial pass is explicitly superseded by these failures.

Reproduce only for source debugging, not as a deployment qualification:
`bash project_atlas/tools/diagnostics/native_ros_entities/run_isolated.sh --collector-owned`

## Confirmed vs uncertain

Confirmed: destructor-owned teardown fixes the prior subscription lifecycle
failure in this fixture, but does NOT establish safe heartbeat behavior. Broad
static caching is rejected. Exact source locations explain the former ownership
and wrong-map errors.

Also inspected bondcpp4.1.4 source:
https://github.com/ros/bond_core/blob/4.1.4/bondcpp/src/bond.cpp
`heartbeatTimerReset` constructs a new wall timer. Thus application-level mutation
hooks do not cover every internal timer change. This is a concrete scope gap,
but its causal role in the missed timeout and its CPU contribution remain UNPROVEN.
Do not patch bond timers or reduce their frequency based solely on this observation.

## Stop condition and future work

Close blanket/static-executor replacement as the proposed quick CPU fix. Further
work must target a measured production hot operation with preserved standard
executor semantics, or a properly integrated middleware lifetime fix—not another
wrapper rebuild. Existing15-sample native trace alone cannot certify a major
whole-Jetson CPU gain. Additional discriminating attribution may be needed before
selecting a production change; no new live profiling is authorized by this report.

No installation approval requested. No physical test needed. Rollback on ATLAS:
none, because nothing was installed. Preserve current production executors.
Only offline fixture and documentation changed; generated output not committed.
