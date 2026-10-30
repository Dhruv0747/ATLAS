# Restart safety controls — offline validation PASS

Prepared for owner review, not executed on Jetson. Backend/staged manifest remains
unchanged. The old79.15% spike is still unexplained and is NOT exempted. Fresh
admission may reject this entire attempt before any web change.

## Controls implemented

* restart_safety_observer.py: independent ROS2 read-only subscriptions to existing
  /atlas/control_policy, /cmd_vel and /atlas/encoder_health. No web dependency,
  application publishers, camera subscriptions or actuator commands. Production
  safety domain is0 (existing web has no explicit ROS_DOMAIN_ID); Astra77 unchanged.
  ROS discovery/parameter middleware is still present; this is ONE additional
  temporary participant, whose startup overhead is included in resource sampling.
* Latched E-STOP, manual-only, commissioning false, STOPPED source, all six Twist
  components zero, LIVE/fresh encoder packets and four zero deltas are mandatory.
  Monotonic receipt age and packet age <=1s. Missing/malformed/stale state fails;
  after first valid observation failures latch. Supervisor validates nonce and
  observer heartbeat <=0.75s. ROS-side publication outage test fails at freshness
  expiry even with HTTP completely absent.
* Reused bounded_process_cpu.py records aggregate/PID-starttime/cgroup raw counters
  and deltas every1s; first counters precede observer launch. CPU>75%, RAM>80%,
  temperature>=70C reject. Required six Orin zones; missing zones reject. Collection
  stalls, bad intervals and stale monitor heartbeat reject. Evidence <=16MiB.
  Historical failures stay latched even if later values improve. No per-process
  attribution claim is made until actual counters are collected on Jetson.
* restart_policy.py: write-ahead reservations allow one activation restart and at
  most one recovery restart. Runtime web-only Restart=no overrides Restart=always.
  Effective policy and absence of pending jobs checked before each restart.
  No override/daemon-reload has been applied to Jetson during this work.
* web_activation_supervisor.py wraps the unchanged staged installer. User-systemd
  RuntimeMaxSec180, Restart=no and independent ExecStopPost recovery are REQUIRED.
  Recovery explicitly quiesces unresolved web activity before restoring original
  bytes/policy; it never initiates an additional restart. It is idempotent.
* Before activation, interrupted preparation restores policy/files while preserving
  the original web PID. After interrupted activation or unsafe recovery, original
  files and Restart=always are restored with web deliberately STOPPED. Restoring
  that policy does not start an explicitly stopped unit (native test verified).
  Dashboard availability is not guaranteed after failure; existing safety/control
  services continue unchanged. Owner must explicitly accept this recovery outcome.

## Focused evidence

8 new tests PASS on Windows/WSL:5 safety/nonce/freshness cases; native systemd fake
unit restart-budget test; native SIGKILL/ExecStopPost recovery at four boundaries
(policy installed, files changed, activation issued, policy restored before acceptance); real ROS2 Humble isolated
domain211 loopback-only observer test with HTTP absent, publisher loss and clean
observer termination. Native tests restored exact fixture bytes and Restart=always,
verified no uncontrolled restart, and did not touch production units.
9 existing process/cgroup accounting/75-80-70 boundary cases passed in focused
selection; previous13 installer tests reused. No full regression suite rerun.

Limits: isolated tests are not actual Jetson performance/QoS validation, power-loss
testing, or a full real-backend activation test. Faults involving unreadable files,
concurrent edits or unresponsive systemd fail closed and can require manual recovery;
no software can guarantee successful restoration despite those failures. Such
conditions are reported, never converted to PASS. No Jetson observer or profiler
has been started; no camera/model/ROS service restarted.

## Package

PC folder: `work/web-restart-controls-20261030` (four control/helper files).
SHA256SUMS SHA256:
`913afd64eb644d57a12d2b21aaaf9453244c0e9394dbd7006ca71062d805b69e`.
Supervisor SHA256:
`70de540e65979bf70d28fba5f58733eb4bd282c892194fd750b0f0ec6857c3b6`.
Reused collector SHA256 a93ae9d0a8486a843b1648f764c2e34dda84916d20750712413a81a9f25a7021,
from commit0ce6dd1f6015e60b70a2199467226286c2e4efc3,
project_atlas/tools/diagnostics/bounded_process_cpu.py, unchanged.
This control package is NOT copied to Jetson yet. Existing reviewed backend remains
at object-target-staged-7dba9bd/review with outer manifest a586c2d2… unchanged.

## Exact execution sequence — ONLY AFTER SEPARATE APPROVAL

1. Copy control folder to
   /home/jetson/project-atlas-migration/web-restart-controls-20261030. Verify manifest
   hash above, then `sha256sum -c SHA256SUMS`. Verify the existing reviewed backend
   manifest and exact current live hashes, rollback originals and protected units.
   Confirm no existing transaction/unit of the names below. No retry/reuse.
2. Perform fresh existing stationary preflight including E-STOP/zero/encoders,
   CPU/RAM/temperature, recorder OFF and independent camera-process absence.
   Do not run the command below on a failed check.
3. Launch only this supervised unit (not the old standalone installer):

```sh
systemd-run --user --unit=atlas-vision-activate-once-20261030 \
  --property=Restart=no --property=RuntimeMaxSec=180s \
  --property=TimeoutStopSec=45s --property=KillMode=control-group \
  --property='ExecStopPost=/usr/bin/python3 -B /home/jetson/project-atlas-migration/web-restart-controls-20261030/web_activation_supervisor.py --stage /home/jetson/project-atlas-migration/web-activation-once-20261030 --recover' \
  /bin/bash -lc 'source /opt/ros/humble/setup.bash && source /home/jetson/project_atlas_ws/install/setup.bash && exec /usr/bin/python3 -B /home/jetson/project-atlas-migration/web-restart-controls-20261030/web_activation_supervisor.py --stage /home/jetson/project-atlas-migration/web-activation-once-20261030'
```

4. Supervisor collects first process counters, starts the temporary observer, allows
   up to10s safety discovery with resource gates active, then15s healthy baseline.
   Existing installer rechecks full admission, exact backups/files and performs
   one web-only restart with CPU guard active throughout. HTTP readiness <=10s;
   malformed/timeout/unsafe observations fail. Existing read-only browser verifier
   must provide its PASS/hash acknowledgement within90s; no feature Start requests.
   It verifies desktop/mobile, six panels/24 disabled controls and existing preview.
   After acknowledgement,10 further guarded samples and service/hash checks finish.
5. Maximum main-unit duration180s plus up to45s bounded cleanup. Review BOTH
   controller-result.json and installer result.json, restart-policy.json,
   recovery.json if present, process-cpu.jsonl and fresh service/safety checks.
   A legacy installer PASS alone is insufficient. No automatic retry.

Abort: stop this transaction unit once; ExecStopPost performs recovery. Do not
manually restart web in parallel. For a completed/failed transaction needing
idempotent recovery, first verify its unit has finished, then run the exact
ExecStopPost Python command above. It restores only owned files/policy and may
leave web stopped. Do not issue any additional web start without approval.

## Verdict and approval

PASS for the scoped offline safety components; GO for owner review of ONE controlled
attempt, conditional on fresh exact hashes and safety admission. Not a guarantee of
successful activation or acceptable Jetson observer overhead. Separately authorize
temporary read-only safety participant, runtime web-only Restart=no/daemon-reload,
unchanged reviewed file activation, one activation restart/at most one rollback
restart, and fail-closed stopped-web recovery if interrupted or unsafe. No camera,
inference, safety-threshold exception, protected-service restart or PR merge.
