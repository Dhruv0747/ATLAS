# Safety scan candidate: deployment rolled back, recovery verified

Owner authorized one-file installation, safety-status-only restart, unchanged
guards and rollback on failed checks. Continued from30e1c45. Candidate was
installed temporarily, then **restored to original** after restart CPU failed.
No installation retry, Astra start, recording, movement or unrelated restart.

## Admission and package

Five offline tests passed:335 callback equivalence cases, exact-source rejection,
unchanged other methods/full compilation, deployment restart scope and strict
CPU/rollback contract checks. The latter two are static tests, not simulated
hardware failure tests.

Authoritative original/current SHA256:
`57262f6e55aef3f28ba285805619a86f6131643e41cebf20dc49be86d3cf2e1e`.
Candidate SHA256:
`94f52bcc1d535378adf6d4f54f6d29fc52f0cd7b12b11a8da0df39117f510bd4`.
Exact-hash transformer SHA256:
`21e4da2b74abf8e76e9491b67f8ef791713f05baa255edce83ea995ecea1b277`.
Installer SHA256:
`f91acaa6599960e7e23ef84a54fa779caeb9f868f34ebc241becce723670eed4`.

Voice, Dashboard, white-glass CSS, stationary guard and ROS probe protected hashes
matched before installation and again in read-only recovery. Free disk394170306560
bytes. Original file backed up with metadata and hash verified before replacement.
Fresh E-STOP/manual-only/zero motor command, recorder OFF, Astra OFF, required
sensors and protected-service checks passed during baseline. No75/80/70 limit
was changed, and there was no CPU-report-only installation exception.

## Measurements and failure

20baseline health samples over23.921s:

- Whole-Jetson mean71.2085%,peak75.0000%.
- Safety-status process12.7922% of one core.
- Restart sample85.6902% over1.00228s, monotonic15597.310951234.

This last sample exceeded75% and immediately latched the deployment failure.
Candidate was restored and ONLY `atlas-safety-status.service` restarted again
to load the original. No post-candidate window completed: **no valid installed
before/after CPU savings claim is possible**. The spike coincided with restart;
this alone does not identify its per-process cause or disprove steady-state
callback savings from the prior isolated benchmark.

The automated immediate rollback check at3seconds found stale `mission_status`,
so the immutable result remains `ROLLBACK_NEEDS_ATTENTION`. Read-only follow-up
verified recovery after the original reporter finished initialization (~5s).
Do not rewrite that initial failure as an automatic clean pass.

The old original PID1889 logged `ExternalShutdownException` while stopping;
the restored process logged ready and is active/Result=success. This is not
evidence of a candidate steady-state exception.

## Final read-only recovery verification

- Original file exact hash restored; safety-status PID117734,NRestarts0,active.
- CPU69.6309%,RAM69.6035%,max temperature60.093C.
- E-STOP latched,manual-only true,commissioning false,commands zero.
- Required sensor freshness passed,mission READY,motor_speed0,recorder OFF,Astra OFF.
- Protected services unchanged:PiCamera1858/0,motor3351/1,mux1852/0,
  EKF2982/0,localization8060/7,LiDAR7887/12,Dashboard94624/0,voice108742/0.
- Voice hash `a88ff78df1ae2dded4f9984cdcf5e94d5335d1d12c77fd9c9131219725298870`.
- Dashboard hash `acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439`.
- White-glass CSS hash `ea6a213b8a7b5aa5f4777af64259a75589799ebd151e39acf4723fc6fb6368d5`.
- Guard hash `0c5ec244b238aa741f3dc2d6fe7c7f588fdd3511e2a3e2c7c36f2ab355a5bfe9`.
- Probe hash `f8a24e2a9fe92f505f52e96572a00691b0ebcfe92b092ba1c98ee052c18ed9dd`.

Follow-up sampled CPU separately and inspected safety with no operation attached;
it did not bypass a failed CPU check to install or start anything. Continuous
monitor stopped at the first breach; rollback-time continuous CPU is unavailable.

## Evidence / rollback

Directory:
`/home/jetson/project-atlas-migration/scan-cpu-deploy-20261024-hKXuQk/evidence-bhxiiopy/`

- Original backup:`atlas_safety_status.original`,hash matches current original.
- `result.json` SHA256 `4d49cb2ab7625933b0c1747ce7108684dcae236986dbbfc60637b12eb2c86601`.
- `trace.jsonl` SHA256 `da716bd1ca3f59f23fe5e727be0f1b7701833cdf9d512096b918a369bdd9343f`.
- Local evidence retained as `artifacts/safety_scan_deploy_result_20261024.json`
  and `artifacts/safety_scan_deploy_trace_20261024.jsonl`,not committed raw.

Rollback is already complete; no further restart is needed. Candidate remains
offline only. Another deployment needs separate approval and a reviewed plan
for reducing restart contention without weakening the75% guard. Do not repeat
installation hoping for a different sample. Astra readiness and overall CPU
headroom remain unresolved. White-glass UI, voice functionality and safety
configuration were not edited.
