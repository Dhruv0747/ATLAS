# Native ROS entity and bond tests: static executor rejected

## Decision

Real ROS entity changes and real bondcpp failure detection were tested on PC.
The standard executor passes the fixture. The stock StaticSingleThreadedExecutor
candidate fails subscription removal and is **REJECTED for deployment**.
No safe runtime CPU patch is prepared from this failure. Do not install the
earlier GuardCondition retention prototype into RMW: it has not been integrated
or passed these real-ROS tests. These are explicitly different candidates.

No Jetson connection,installation,service restart,camera start,recording,movement
or production tuning occurred. Voice,white glass UI and75%/80%/70C policies remain
unchanged. Owner's CPU-use instruction did not modify production safeguards.

## Isolation and dependencies

WSL Ubuntu22.04 x86_64,ROS2 Humble rclcpp16.0.21,rmw_fastrtps6.2.10,
FastDDS2.6.12. Native C++ built with-O2,-Wall,-Wextra,-Werror.
Downloaded official ROS apt packages bondcpp,bond and smclib4.1.4 and extracted
them under private artifacts/native_entities_20261024/overlay. No apt/dpkg
installation,system library change or package registration was performed.
Initial temporary-directory dependencies were unavailable on a later invocation;
recreated them in the persistent artifact directory. Initial CMake prefix
resolution failed; explicit environment prefix fixed it. A run attempted while
linking failed with Text file busy before test execution; subsequent runs waited
for build completion. These were PC fixture issues,not ATLAS faults.

Runner requires x86_64 and creates a private network namespace using unshare.
Only loopback is enabled there. Clean env,ROS_LOCALHOST_ONLY=1,Domain216,
rmw_fastrtps_cpp; no production domain,network route or ROS participant on Jetson.
40-second timeout with bounded kill. Files and logs stay in private PC artifacts.

## Tests and measured result

Standard SingleThreadedExecutor:
-20 ordered messages delivered with per-message acknowledgement.
-Subscription reset/discovery removal completed.
-Subscription recreated after earlier spinning;message21 delivered.
-Dynamically created10ms timer ran;cancelled timer produced no further callbacks.
-Real bondcpp pair formed and remained healthy while both peers spun.
-Peer node removed from executor WITHOUT destroying its bond or announcing death.
-Remaining peer detected missing heartbeats in **0.387002s**.
-Fixture heartbeat period50ms,timeout400ms;acceptance200ms..1500ms.
-Cleanup removed remaining node and shut down ROS.

Those shortened heartbeat values are test-local,not production parameters or
safety certification. Same-process peer starvation is tested,not OS process
crash,network partition,or production bond deadline under Jetson load.

StaticSingleThreadedExecutor:
-Initial discovery and20 ordered deliveries passed.
-After subscription reset and2seconds of continued spinning,publisher still
reported **one subscription**,not zero. Fixture failed remove discovery.
-A focused --static-only run with added count diagnostic reproduced count1.
-Recreation,timer and bond gates for this candidate were therefore NOT reached.
-No CPU comparison executed:performance stage follows correctness and was blocked.

The standard executor passes the same2-second removal bound. Cached entity
ownership is a plausible explanation consistent with the static collector, but
the verified failure is retained subscription visibility; do not overstate an
exact internal ownership root cause without further source-level proof.

## Relation to prior microbenchmark

The FastDDS GuardCondition fixture showed lower cost when conditions were
retained with explicitly stable lifetimes. It did not include ROS subscription
destruction or bond timers. These new tests demonstrate why that microbenchmark
cannot justify a blanket cached-executor replacement. No end-to-end CPU saving
or Astra readiness is claimed. Existing standard production executor is untouched.

## Files and next engineering gate

Added tools/diagnostics/native_ros_entities/{CMakeLists.txt,main.cpp,run_isolated.sh}.
The source retains an interleaved performance stage for candidates that first
pass correctness;it was not reached and must not be reported as measured.

Next work requires a lifecycle-aware implementation at the exact RMW wait-set
ownership boundary,with explicit invalidation before entity destruction and
preserved wakeups. It must pass this failure case,real bond failure detection,
dynamic services/QoS,concurrent teardown and end-to-end performance before any
Jetson package can be proposed. No further owner physical test is needed now.
Do not work around this failure by delaying removal,reducing heartbeat rates,
changing safety limits or restarting production services.

Rollback: none needed on ATLAS. Only offline fixture and documentation changed;
private extracted dependencies/build output are not committed.
