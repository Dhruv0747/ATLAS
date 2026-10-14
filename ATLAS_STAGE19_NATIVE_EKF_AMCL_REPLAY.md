# Stage 19 — native replay exposes an initial-state fidelity gap

14 October 2026 · `agent/sync-developer-20261011` · source baseline
`1de29623bd7a0e9d75bc7657be6f92ba46564911`.

## Executive summary

**TESTED OFFLINE on native Humble; original five-event sequence NOT REPRODUCED;
correction comparisons FIDELITY BLOCKED; DEPLOYMENT NOT AUTHORIZED.**

The native production-config EKF/AMCL baseline ran for the entire saved 295-second
Hall return. It published every selected input, emitted 382 AMCL poses versus
384 recorded, and covered all 80 post-stop updates. It did **not** recreate the
five parked jumps: it instead produced eight large corrections before stopping.
Zero parked jumps in this different trajectory is **not a fix**.

The new discriminating finding is upstream replay initialization: the recording
starts with an already-running EKF at `(18.392, −3.654 m, −128.476°)`, whereas the
cold replay first publishes `(0,0,0)`. Relative wheel-pose fusion also chooses a
new first-measurement reference. After one initial rigid alignment, native versus
recorded EKF still differs by up to **1.343 m / 18.401°**. The prior relative
reference, full filter checkpoint and parameter history were not recorded.

The harness now refuses correction comparisons without explicit baseline-fidelity
evidence. The strengthened gate was exercised in the native sandbox: Candidate B
was refused **before launching nodes or creating an output bag**. No candidate
was accepted. No rover movement, service restart, calibration or live configuration
change occurred. Stage 17B remains on HOLD.

## 1. Native environment and isolation proof

PC has no WSL installation or native `rosbag2_py`, so native work used Jetson's
existing Humble packages, without installing or upgrading them:

| Component | Installed version |
|---|---|
| robot_localization | 3.5.4-1jammy.20260605.164056 |
| nav2_amcl | 1.1.20-1jammy.20260607.130817 |
| rclpy | 3.3.21-1jammy.20260605.142610 |
| rosbag2_py | 0.15.16-1jammy.20260607.142735 |

`bubblewrap` provided private **network, PID and device namespaces**, read-only
host filesystem, private `/tmp`, and one writable isolated work directory:
`/tmp/atlas-stage19-iNrvFe9F`. Inside, no serial, USB-controller, GPIO or I²C devices
were exposed. `/dev/tty` is sandbox terminal infrastructure, not a rover UART.
The loopback interface was up; no Wi-Fi/Tailscale or production DDS network existed.

Production net/PID IDs were `net:[4026531840]` / `pid:[4026531836]`; replay IDs were
`net:[4026533831]` / `pid:[4026533830]`. Domain 187, localhost-only UDP transport,
nice 15 and CPU affinity 4/5 further bounded isolation/resource usage.
The observed graph contained only the diagnostic publisher, native EKF, AMCL,
map server, localization lifecycle manager and their TF listeners. No controller,
planner, motor driver or mission-control node was launched. No `/cmd_vel` publisher,
steering topic or serial import exists in this runner. Cleanup targets only its
private-namespace child processes; all replay nodes exited at completion.

Host preflight initially refused because E-STOP was unlatched. After the owner
pressed B, live policy confirmed latched stop and zero linear/angular command.
These conditions still held after replay. Production AMCL/EKF PIDs remained;
the replay's nice-15 processes exited. No systemd command changed any service.

## 2. Exact configuration and map identities

Preserved native input configuration hashes:

```text
EKF: 69dd4479cdf84ea9d878b1d8c4d0e5129fb894b82003126c9c5f19052afc90ed
Nav: 2411371c89751eba9f817b3e6728ab08fa3e8820f6727c08713298c18ee08631
Map YAML: d957f0fe3b8b48166751ef0226ba5f7abdd5454e6f44fac4c9e7b430f00c45e4
Map PGM: 4beb26d5a9990db537df53ba71404d549f88f717d72ca59fc03e0b72a3684a1e
```

Both complete map hashes passed before execution. Unchanged copies, not GitHub's
different map, were used. Startup thresholds 0.93/0.06 stayed untouched.
Current native EKF/nav hashes matched again after execution. These are exact
replay configuration identities, **not proof of every October 9 runtime parameter**.
The historic parameter-event/dump evidence is missing.

Candidate A retained wheel X/Y pose and X/Y velocity, corrected IM10A gyro Z,
relative wheel pose, the existing covariances and +0.2 s TF offset. Wheel yaw and
yaw-rate were not directly fused. AMCL retained current map/frame/motion/laser
settings, including DifferentialMotionModel, 60 beams and 0.05 m/rad update gates.

Native trial source hashes (before the later fail-closed comparison gate):

```text
stage19_native_replay.py: 0d2dde247c223b7e22d9bcf2364485c6830cd54f69ef5539a66d02ecf48fe3df
stage19_contract.py: 9bcb1295b10b17bbcd7f8c143261395f94aee82765e5a0c2967e3d76be8dc7b8
```

Those exact trial scripts were preserved beside the native result before updating
the private harness. The final committed code additionally blocks B behind fidelity
attestation; it does not pretend that the earlier trial already executed that gate.

## 3. Source inventory and fidelity checks

Read-only SQLite/CDR inventory covered Hall return, final roundtrip and both retry2
drives. All four contain the five native input topics below plus recorded EKF,
AMCL poses/particles, steering commands, map and all four raw count topics.
Only Hall return/final roundtrip have exact per-update encoder snapshots.
All lack raw IM10A, `/parameter_events`, original `/initialpose` and no-motion
service-event recordings. Particle output is not a full filter/RNG checkpoint.

Hall return SQLite source identity:
`c890f4d18e3fb1de11d3d432c5fe47a66de75bd309efe59c39da1594b7f64a93`.
Original global receipt interval:
`1791528775996960475 … 1791529071127574866 ns` (295.131 s).

| Native input | Published |
|---|---:|
| `/scan` | 2,054 |
| `/yahboom/odom` | 2,919 |
| `/im10a/imu/bias_corrected_candidate` | 2,920 |
| `/tf_static` | 2 |

Recorded map/odom TF was removed; no remaining auxiliary dynamic TF survived this
bag's filter. Native EKF alone owned `/odom` and `odom→base_link`; AMCL alone owned
`map→odom`. The recorded `/odom` was never played alongside regenerated odometry.
Scan/wheel/gyro payloads and header timestamps were not scaled, rotated or rewritten.
Bag receipt-time order governed publication; clock never moved backward.

Reliable input QoS was used for native sensor subscriptions; static TF used reliable
transient-local history, output subscriptions used compatible best-effort, and map
used transient-local. Publisher readiness and lifecycle ACTIVE were prerequisites.
The original offered QoS is retained by the inventory tool for inspection.
Published counts establish sender delivery, **not** proof that AMCL accepted every
scan or that DDS/receiver loss was zero. Maximum sender lateness was **0.27849 s**.
Native EKF emitted 2,586 samples versus 2,908 recorded; callback scheduling differed.

## 4. Documented replay adaptations

Simulation time; current native executable/package versions; clock paced against
wall time at 1×; localization-only YAML; private accepted-map file location;
recorded conflicting map/odom TF removed; original first AMCL mean/covariance
published at its recorded receipt time; journal-derived no-motion requests at
within-second phase 0.578 s. Neither production AMCL motion threshold was zeroed.

The AMCL seed is 4.779 s after bag start; it is **not** the actual original startup
initialization event or a restored particle state. There were 290 no-motion requests
and 290 completed responses after the seed. The older recorded-odom experiment
made 294 calls including the pre-seed period. This adaptation and its difference
are explicit, not an invented claim that service-call timing was recorded.

## 5. Baseline outcome — NOT REPRODUCED

Metric grain is the whole Hall-return recording unless explicitly post-stop.
The stop reference is the existing last nonzero `/cmd_vel_joy` receipt:
`1791528990771516061 ns`. A >0.5 m jump also requires consecutive pose-header
interval `0 < dt ≤ 2 s`. This matches the prior comparison, not a new threshold
selected after inspecting results. Last command is not surveyed physical truth;
stationary encoder/gyro/TF evidence is retained from the earlier audit.

| Metric | Recorded | Native Candidate A |
|---|---:|---:|
| AMCL poses / post-stop poses | 384 / 80 | 382 / 80 |
| >0.5 m jumps, all / post-stop | 5 / 5 | 8 / 0 |
| Maximum jump, whole run | 2.206 m | 1.002 m |
| Post-stop displacement span from first post-stop pose | 2.855 m | 0.985 m |
| Median published XY standard deviation | 0.182 m | 0.219 m |
| Median published yaw standard deviation | 7.724° | 12.397° |
| Particle clouds | 381 | 368 |
| Particle XY spread, median / maximum | 0.173 / 1.414 m | 0.207 / 1.329 m |
| Post-stop EKF displacement span | 0.01140 m | 0.01138 m |
| Backwards odom TF header transitions | 0 | 0 |
| 15 cm scan-endpoint proximity, median | 95.70% | 84.93% |
| Same endpoint proxy, final | 96.67% | 83.89% |

Endpoint proximity reuses the existing diagnostic fitter with the recorded π
laser rotation and accepted map. It is **not AMCL's likelihood or ground truth**;
383/384 recorded poses and all 382 replay poses had eligible paired scans.
Larger uncertainties and a changed moving-correction trajectory preclude a
localization-success interpretation. A different span/zero parked jumps in the
baseline cannot be advertised as a candidate improvement.

## 6. New EKF initial-reference evidence

At the recording's first wheel input, raw wheel pose was
`(18.39231355, −3.65408140 m, −111.47162087°)` at `1791528778.2320106 s`.
The first recorded EKF pose was the same XY with yaw **−128.47569203°**, at
`1791528780.3236907 s`. Native replay's first EKF output was `(0,0,0)` at the first
wheel stamp. The original estimator was not cold-started at the bag boundary.

`robot_localization` 3.5.4's
[relative-mode source](https://raw.githubusercontent.com/cra-ros-pkg/robot_localization/3.5.4/src/ros_filter.cpp)
stores the first incoming pose transform and applies its inverse to subsequent
poses. That reference includes orientation even when yaw components are not selected
for fusion. Consequently a cold restart changes X/Y pose-observation coordinates,
not simply the absolute plotted origin. A regression verifies this mathematical
behavior independently of actuator hardware.

We removed the trivial initial rigid-frame difference **for comparison only**:
subtract each first position and rotate displacement into its first heading.
No input/config was changed and no fitted angle/scale was chosen. Residual native
versus recorded EKF difference was **1.343 m maximum / 1.253 m final**, with
**18.401° maximum / −17.021° final relative heading difference**. Thus the mismatch
is not explained by an arbitrary odom origin alone.

CONFIRMED: cold native initialization and the original recorded state differ;
the original relative-input anchor/full covariance history is absent.
LIKELY: relative-reference and initial-heading history materially affect this replay.
UNPROVEN: they account for all its residual error or caused the real five AMCL jumps.
Original historic relative-mode parameters are also not proven by current YAML.
No parameter, initial state or wheel observation was invented to force a match.

## 7. Five-jump comparison and synchronized timeline

| Original event | After last remote motion command | Step | Recreated by native A? |
|---|---:|---:|---|
| 1 | 2.693 s | 0.565 m | No |
| 2 | 7.669 s | 2.206 m | No |
| 3 | 8.726 s | 1.549 m | No |
| 4 | 9.765 s | 1.549 m | No |
| 5 | 12.780 s | 1.481 m | No |

Native A's eight steps happened **8.837–1.893 s before** the last nonzero remote
command. These are not the original parked event sequence. Earlier recorded-odom
no-motion replay's two stationary switches remain **PARTIALLY REPRODUCED failure
class**, not a newly repeated experiment or the original five events.

Timeline references must not be mixed: bag start is `1791528775.996960475 s`;
Stage 18 turn windows use first exact encoder update `1791528778.2320106 s`.
The 160–162 s wheel/gyro discrepancy therefore occurs about 162.235–164.235 s
after bag start. The first original pose with displayed XY uncertainty >0.25 m
is at bag +171.087 s; the first published cloud spread >0.25 m is at receipt
+171.230 s. This display-level threshold is not a new physical confidence test.
The 174–176 / 186–188 wrong-sign windows follow; five hypothesis switches occur
after motion ends. This ordering supports an upstream inconsistency preceding
particle dispersion/switching, **not proof that wheel pose caused them**.

Last independently reliable physical pose: **UNKNOWN** (no surveyed trajectory).
First wheel/gyro disagreement: retained Stage 18 evidence, with LiDAR supporting
selected turns but rejecting others as uncertain. First true EKF physical error:
**UNKNOWN**; native-versus-recorded divergence is replay error, not ground truth.
Pre-resampling particle likelihood/cluster degradation: **UNKNOWN**; only output
clouds are saved. Actual five switches and continuing dispersed uncertainty are
recorded. Prior map-alias evidence remains a separate unresolved contributor.

## 8. Candidate A–E dispositions

Acceptance rule was saved in the contract before executing native replay: no worse
translation and improved heading across every eligible drive, credible uncertainty,
no new frame/time failures, and faithful baseline for any global improvement claim.
Missing evidence is UNKNOWN; one stochastic run cannot establish AMCL improvement.

| Candidate | Controlled change | Disposition |
|---|---|---|
| A | Existing production fusion, simulation time only | Native tested; baseline NOT REPRODUCED |
| B | Disable only wheel X/Y pose flags; retain velocity/gyro/TF offset | Prepared; native execution refused by strengthened fidelity gate |
| C | Independently validated reliability/covariance handling | FIDELITY BLOCKED; calibrated quality bounds and native covariance-response evidence absent |
| D | Gyro-heading/wheel-distance shadow | FIDELITY BLOCKED; Stage 18 translation not consistently better and observations correlated with gyro |
| E | Bounded timing/TF variant | FIDELITY BLOCKED; +0.2 s unchanged; source lateness/initial-reference gaps must not be disguised with offset tuning |

**CANDIDATE ACCEPTED: none. CANDIDATE REJECTED for deployment: all unvalidated
corrections.** This does not claim B–E were numerically tested and failed.
No before/after correction metrics exist; do not relabel baseline differences as
improvement. Other available recordings were inventoried, not subjected to a
misleading multi-recording correction campaign before fixing this mandatory gate.

## 9. Resources, delivery and process health

Four native child processes used 32.99 sampled CPU seconds over roughly 295 s:
about 11.2% of **one** core / 1.9% of six cores. Sum of each sampled peak RSS was
109.32 MiB (an upper-bound sum, not simultaneous peak). **The Python publisher,
writer and bubblewrap overhead were not included**, so these are not total replay
resource figures. The Jetson snapshots were CPU 70.9→73.5%, RAM 5,387→4,910 MB,
temperature 61→62°C and ~369 GiB free. Other running activity/cache variation means
RAM decline cannot be attributed to the trial. No service was disabled to improve
these readings. Scheduling differences remain part of the fidelity limitation.

AMCL log contained the expected pre-seed initial-pose warning; no observed AMCL
log message reported TF extrapolation, backwards-clock or message-filter drops.
This is a log check, not proof of zero internal scan rejection. TF headers were
monotonic. Native input counts matched the selected source; output counts differed.
No live graph or service was modified to remove those differences.

## 10. Code, tests and remaining necessary evidence

Added bounded native runner, sandbox/preflight launcher, source/QoS inventory,
result/fidelity summarizer and pure contracts. Reused existing endpoint-fit and
ROS test machinery rather than adding a second recorder or dashboard. Runner
refuses missing required sources, incorrect accepted map, visible serial devices,
host namespaces, unexpected replay nodes and unverified correction comparisons.

**33 unique unit/regression tests passed:** 11 Stage 19, 4 existing fusion replay
tests with actual native ROS imports, 12 related Stage 18 and 6 existing stop-hold.
Seven Stage 19 contract tests additionally passed in the native environment.
The strengthened B gate refused execution in the actual sandbox. Full A execution
completed; **baseline reproduction failed**, which is reported separately from
software-test passes. Python syntax and shell syntax are checked before commit.

The smallest necessary new evidence is **not another identical manual route**.
For regeneration, capture before normal EKF/AMCL initialization: first relative
wheel-pose reference, complete parameter/version/QoS identity, genuine initial-pose
event, source/receipt/TF timestamps and no-motion service-event schedule. Alternatively
export an explicit full EKF state/covariance/relative-reference checkpoint and AMCL
particle/RNG/cluster state. Published odometry pose/twist covariance blocks do not
contain the full EKF cross-covariance/checkpoint. Output particle clouds do not
contain pre-resampling weights or RNG state. Saved data cannot reconstruct these
uniquely. This collection needs separately approved production instrumentation or
recording from a **future normal startup**; no reboot/reseed/restart is authorized
or performed here. A stationary capture may not reproduce moving-induced ambiguity;
that limitation must remain explicit. No new drive is requested.

## 11. Status, provenance, rollback and deployment

Result stays on Jetson:
`/tmp/atlas-stage19-iNrvFe9F/hall_native_A/` and a copied PC artifact directory
`artifacts/stage19_hall_native_A/`. Preserve these diagnostics; no active/existing
bag was deleted. Trial source copies, manifest, SQLite bag and process logs are
not committed. Source commit is given in the final delivery link (the report cannot
contain its own commit hash). Branch remains dedicated; no merge into main.

Rollback requires no live action: every trial process has already exited and
production files are unchanged. Stop using the isolated tools or revert this
diagnostic commit. Keep the evidence. A later correction requires faithful native
baseline, multi-recording regression, exact live backups and **separate explicit
deployment approval**. Stage 17B stays on HOLD, E-STOP latched, no autonomous goal
issued, and moving-localization correction remains **unresolved**.
