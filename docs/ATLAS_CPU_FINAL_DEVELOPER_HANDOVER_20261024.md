# ATLAS CPU investigation — final developer handover

## Objective and authorization boundary

P0: reliable real Astra Depth-only Uncalibrated 3D Preview, without sacrificing
voice, offline wake word, white-glass Dashboard, reporting, sensors or safety.
Working branch: `agent/reliability-optimization-20261023` (do not merge main).
Latest diagnostic correction: `099a9730d06dad487accef9463584f2993a5a0d6`.
Owner now approved STAGING the corrected profiler and providing one admin command.
No production installation, service restart, camera start, movement or control
changes are authorized. CPU report-only applies ONLY to diagnostic capture.
Retain production CPU75%, RAM80%, temperature70 C and all freshness/stop guards.
No automatic retry. Do not start another profiling experiment without assessing
the evidence already captured. Do not claim any live CPU fix from this handover.

## Current result and what is NOT solved

Native profiles exist; Python hot-function attribution for Dashboard and base
telemetry remains missing. The attempted Python capture aborted BEFORE samples.
No permanent CPU improvement or Astra headroom has been established by the latest
work. Do not claim live 3D Preview readiness. There is no approved deployment
candidate from these last diagnostic changes.

## Confirmed evidence

- Ranked native capture: Jetson migration directory
  `ranked-cpu-20261024/evidence-33p24t_m`, perf SHA256
  `c20b5a7df7c0cc32ce3c64d2cf1a0b30430191bacd9e50374e334606fae10463`.
  Full report: `ATLAS_RANKED_CPU_RESULT_20261024.md`, commit
  `34942ccc3324fb77b035ee1070218ab21f1977b4`.
- Over its ~30.32-second observation, process CPU as percent of ONE core:
  Nav2 group47.09, Dashboard41.75, PiCamera29.91, base telemetry26.91,
  voice21.93. These are not whole-machine percentages; never sum PID and TID
  subset rows. Whole-machine CPU includes observer overhead.
- Observer itself ~42.15% of one core. This confounds the whole-Jetson baseline;
  do not subtract it mechanically and claim clean production headroom.
- Selected native sample leaf library shares: Python60.38%, rclpy11.51%, libc9.25%,
  JPEG6.42%, FastDDS3.96%. These are selected-sample attribution, NOT per-process
  whole-Jetson percentages or proof of duplicate encoding.
- Scanner optimization excludes ineligible process executable lookups only after
  retaining process totals. PC scanner microbenchmark ~47.6% cheaper; not a live
  robot optimization and not evidence of equal full-observer savings.
- Earlier native Nav2 capture `nav2-cpu-20261024/evidence-i2a4guhr` had only15
  samples. It cannot justify broad executor or heartbeat changes.

## Rejected/limited approaches — do not repeat

- Static wait-set caching: recreated subscriptions / heartbeat validation failed.
  See `ATLAS_COLLECTOR_OWNERSHIP_RESULT_20261024.md`. Approach closed; retain
  standard executor. Do not re-open merely to get a better microbenchmark.
- One-pass lookup: operation savings but six integrated pairs mixed, no reliable
  end-to-end gain. See `ATLAS_ONEPASS_SUBSCRIPTION_LOOKUP_20261024.md`, commit
  `986084ed44effaf59c00e83996fff89ebd1105e3`.
- Prior limited Dashboard/voice/safety optimizations did not establish whole-
  Jetson savings. Consult their existing reports; do not redeploy or repeat.
- Localization-monitor candidate encountered stale mission status and rollback;
  isolated startup passing did not establish a production scheduling/DDS cause.
- Compact JSON was not sufficient evidence for needed headroom.

## Exact failed Python capture and corrected staging

Jetson root: `/home/jetson/project-atlas-migration/`.
Package directory: `dashboard-telemetry-python-20261024`.
Failed evidence: `evidence-yucgejc9`: result.json364bytes, telemetry.jsonl0bytes,
no profile. Dashboard aborted; shell `&&` prevented telemetry from starting.
Cause confirmed: protected list contained `rover-status-web` while systemd Id
is `rover-status-web.service`. Strict parser correctly rejected unknown identity.
This was our wrapper defect, not proof of a failed production service.

Corrected only the protected list name; helper target's existing short-name
lookup stays unchanged. Six Linux tests pass including exact bug reproduction,
canonical ID acceptance, missing/duplicate/unknown rejection, argument validation,
helper tamper rejection and bounded 10-second20Hz GIL profiler configuration.

Owner-approved staging completed and remote `sha256sum -c SHA256SUMS` passed:

- wrapper `dashboard_telemetry_cpu_once.py`:
  `45f9e55f85af56b8c465664da096318c58cee323fa0acacf1d8d26d25ca282ab`
- unchanged helper `native_dashboard_cpu_once.py`:
  `2b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18`
- original wrapper preserved as `dashboard_telemetry_cpu_once.pre-099a973.py`,
  SHA `9310f5eca524cd02995fc6e46a194f5c450cf2ca7ee6095b8c7196a86007e870`.
  Original manifest preserved as `SHA256SUMS.pre-099a973`.
- Failed evidence preserved. No new capture run by agent.

## One owner command

Keep ATLAS stationary. Fresh checks run independently before each profile.
CPU is measured but report-only. Other safety/resource checks remain fail-closed.
Each profile10seconds, baseline/postflight5samples each, outer bound45seconds.
No audio, image, rosbag or local-variable recording; private stack evidence only.

```bash
set -o pipefail; cd /home/jetson/project-atlas-migration/dashboard-telemetry-python-20261024 && sha256sum -c SHA256SUMS && sudo /bin/bash -c '/usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B dashboard_telemetry_cpu_once.py dashboard --diagnostic-cpu-report-only && /usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B dashboard_telemetry_cpu_once.py telemetry --diagnostic-cpu-report-only' 2>&1 | tee -a launch-output.log
```

## Next developer: exact necessary work

1. Read the new launch output/results once owner runs the command. If aborted,
   inspect exact failure and any partial profile; no automatic retry or weaker
   checks. If successful, verify profile SHA256 and all service before/after
   identities, guards and target hashes before interpreting samples.
2. Analyze speedscope frames per thread and function (inclusive and leaf counts),
   durations, dropped/empty samples, thread CPU deltas and observer time. This
   GIL capture does not represent native code while the GIL is released; correlate
   retained native stacks. Separate Dashboard HTTP activity from ROS callbacks.
3. Match actual deployed source hashes before preparing a small offline patch.
   Do not infer repeated decoding/subscription duplication solely from libraries.
4. Test the demonstrated expensive operation under matched interleaved workloads;
   include realistic sensor/TF traffic, QoS, cancellation, service shutdown,
   freshness and callback deadlines. Preserve ordinary steering/HTTP/voice/UI.
5. Publish exact before/after CPU time and wall time, correctness results and
   scope of claims. A microbenchmark is not whole-Jetson savings. If no measurable
   candidate succeeds, state that clearly rather than repeating the same test.
6. Prepare minimal hash-pinned rollback package; request deployment approval.
   Production savings require a separately approved matched live comparison.
   Another camera Start needs separate approval and all unchanged guards.

## Files, access and preservation

Repo diagnostic sources under `project_atlas/tools/diagnostics/`; live repo
`/home/jetson/project_atlas`; telemetry target `scripts/yahboom_base.py` SHA
`c551be0053a43755578fc8e60b534338818a690411322c63a293376e6e560141`;
Dashboard `scripts/atlas_status_web.py` SHA
`acb9fe18d384a7e2c06c24e1ab3abd5c3ebc1b46b5d26902ec39e1a3155d7439`.
Always reverify: these are captured identities, not timeless facts.
Wi-Fi last known192.168.1.15, Tailscale100.87.208.71; use existing configured SSH.
Never commit SSH keys, raw private profiles, telemetry logs or credentials.
Repository contains unrelated untracked artifacts: preserve them. Reports,
tests, source and manifests go to GitHub; private evidence stays in existing
Jetson/local artifact directories. No active background work is left running.

Staging rollback concerns diagnostic files ONLY; never restore production files
for this correction. Backups preserve the faulty original for evidence, not for
reuse. No production service files or settings changed during this final step.
