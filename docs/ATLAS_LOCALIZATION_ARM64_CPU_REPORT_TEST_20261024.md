# One authorized ARM64 comparison with diagnostic CPU reporting

## Outcome

COMPLETE. The isolated original/candidate workload ran on Jetson (`aarch64`)
with owner approval to report CPU rather than abort on CPU for this ONE test.
All other checks remained enforced. Production CPU75%/RAM80%/temperature70C
policies were not changed. Nothing was installed into production or restarted.
No camera start, recording, movement or calibration change occurred.

The candidate shows a modest resource benefit in this isolated ARM64 workload,
NOT demonstrated whole-Jetson savings after deployment, nor Astra readiness.
Only two paired comparisons were authorized/run; variation is substantial.

## Changes and tests

Diagnostic supervisor now accepts exactly `--diagnostic-cpu-report-only` with
explicit owner approval. Default remains strict. CPU samples must still be finite
and within0..100; invalid values abort. Only the diagnostic call passes None for
CPU admission; actual CPU is retained in each health record. RAM, temperature,
E-STOP, manual-only, zero commands, freshness, Astra OFF, recorder OFF, timing,
service identities and file hashes remain checked. No production guard file changed.
12 focused offline tests passed, including option validation and strict default.

The fresh bundle was staged in a separate inert directory, not installed:
`/home/jetson/project-atlas-migration/localization-arm64-report-20261024-IEXVGW/`.
Archive SHA256:
`54ae59eb86f3c0e404a8e8ecb4da439a0af2f06d21f96d3851cca31333c92fed`.
Manifest SHA256:
`ea20d72f2b08c95b3e5e8f4f05fab629e8d04657c0b6fc44060479579d8505cc`.
Both verified remotely before running. Exact package/production hashes passed.

## Measured comparison

Two alternating pairs (original/candidate, then candidate/original), same six-second
saved sensor/TF window and synthetic stationary policy/command traffic as the PC
trial. Localhost-only ROS Domain213; production and Domain77 unchanged. Sensor
callback and TF coverage/limitations are detailed in ATLAS_LOCALIZATION_PACED_TRAFFIC_20261024.md.

| Pair | Original process CPU s | Candidate process CPU s | Saving |
|---|---:|---:|---:|
| 0 | .689937 | .644116 | 6.6414% |
| 1 | .663690 | .660633 | .4606% |

Median paired process CPU saving **3.5510%**; executor-thread saving **3.8172%**.
These are percent reductions in benchmark CPU time, not percentage points of
whole-Jetson CPU. The publisher/observer cost is included in process CPU; the
executor thread measurement excludes publisher-thread CPU.

All1716 expected checked callback deliveries matched; no missing, duplicate,
out-of-order or changed decoded payloads. Two TF edges verified in every run.
Timer counts24/6/24 in every run. No shutdown failures.

Original callback p95:5.698/4.724ms; candidate5.622/5.858ms. Original worst callback
24.976ms; candidate worst17.076ms. Candidate p95 worsened in the second pair, so
uniform latency improvement is NOT claimed. Maximum timer lateness7.855ms.
No hard real-time deadline or moving-localization qualification is inferred.

## Whole-system resources and postflight

32 one-second CPU samples: mean75.0866%, peak87.0370%.
Baseline3samples mean70.6841%; benchmark28samples mean75.4849%; final sample77.1429%.
The extra benchmark adds work while production continues: these phase means
are not a before/after deployment comparison. Postflight CPU did NOT meet normal
75% admission. No CPU readiness claim or camera retry follows from completion.

RAM peak67.8585%, temperature peak60.218C. All RAM/temperature and safety checks
passed. Final state: E-STOP latched, manual-only, commands/wheel outputs zero,
required sensors fresh, mission READY, Astra OFF, recorder OFF. Owned benchmark
process269783 exited0 and was stopped at completion.

Protected services remained active with identical PIDs/restart counts:
camera1858/0, telemetry3351/1, mux1852/0, EKF2982/0, AMCL8060/7,
LiDAR7887/12, Dashboard94624/0, voice108742/0, safety119178/0,
localization monitor1948/0. Postflight production hashes passed. Voice and UI
were preserved, not functionally re-exercised by this sensor benchmark.

## Evidence and remaining work

Private local copy: `artifacts/localization_arm64_cpu_report_20261024/`.

- result.json SHA256:
  `fb823907a565ddba89a534bb226e56311be85e65d01244340bc2c47bd7a1db28`
- guard-trace.jsonl SHA256:
  `f03b8b481e134e099916f0a3563e04c2d7ae1627cb1e046dc06d9c0cac1a6b4c`

Remote hashes matched retrieved files. The reused benchmark result retains a
legacy `scope` label beginning “PC paced dispatch”; execution was verified on
Jetson/aarch64, as recorded above. Raw evidence is preserved without relabeling.
Scope exclusions (no search/status writing/AMCL qualification) still apply.

Candidate remains the previously reviewed two-line spin-call substitution,
SHA256 `58e5d86b21e59546cd44e5fcc87d99df910e4e9e9220d1701e24080de393a4da`,
reusing the existing private executor. It is not a fix for all CPU contention.
No production rollback is required because nothing was installed. Retain the
test directory and earlier failed evidence; no autostart was created.

Next owner decision: whether to approve a separately reviewed one-file monitor
deployment with original backup, monitor-only restart, unchanged default guards,
matched parked measurement and rollback on regression. Do not deploy automatically.
Actual whole-system benefit and full live callback behavior remain unverified.
This one-test CPU exception is exhausted and does not authorize future tests,
deployment, camera starts or relaxing production safety limits.
