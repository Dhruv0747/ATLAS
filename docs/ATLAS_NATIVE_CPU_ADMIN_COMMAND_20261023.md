# One owner-run native Dashboard CPU profile

Prepared23 October2026 after7534178. NOT executed; no CPU fix claimed.

Run once as jetson on the Jetson terminal:

```bash
sudo /usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B /home/jetson/project-atlas-migration/native-cpu-20261023/native_dashboard_cpu_once.py
```

Do not retry if blocked. Send the printed result/evidence path back for analysis.
No production service restart, installation, USB permission change, camera Start,
ROS participant, motion, scheduling change, calibration or safety-policy change.
White-glass CSS and live Dashboard source hashes are pinned and rechecked.

## Bounded collection

- Runs existing safety probes under jetson effective credentials. No root-only
  device access is mistaken for actual service-user access.
- Five baseline samples, one10-second low-rate19Hz single-PID perf profile,
  then five postflight samples. One-second resource sampling; slow checks fail.
- Existing75% CPU/80% RAM/70C limits, manual-only/E-STOP/zero commands,
  recorder OFF, required sensors and Astra OFF checked. No report-only override.
- Native event is `cpu-clock:u`: user-space CPU stacks only, not kernel stack
  attribution. Linux TIDs and monotonic timestamps preserved by perf.
- DWARF stack4096bytes,64-page ring, no child inheritance, build-ID cache off.
- Root launches only perf against verified active dashboard PID/command/owner.
  External13s timeout plus2s escalation bounds profiler even if guardian fails;
  command-level45s timeout provides a further bound. Stop targets only owned
  profiler process group, never Dashboard or another production service.
- Guard failure aborts; no retry. Evidence may be incomplete and is not a pass.
  Native lost-sample records, symbol resolution and useful sample counts still
  require inspection after the owner run.

## Isolated tool provenance and validation

Ubuntu signed apt metadata selected arm64 `linux-tools-5.15.0-198`, version
5.15.0-198.208. Download SHA256 exactly matches metadata:
`7734d4d6e88ff21c3a4a3313507ea66456e832cd2a48e5209efdf713003aa227`.
Extracted with dpkg-deb only inside staging; no apt install or system tool change.
Binary SHA256:
`d51e7c1b3051d529e9a55c610d3d9e70e3b99ae89eebb477fae23a274e7311ca`.
`perf version --build-options` loads on Jetson, reports5.15.216, DWARF/libdw/
libunwind enabled. Local record help confirms selected options. Running kernel
is5.15.148-tegra; these versions are not identical. Actual perf_event sampling
and unwinding compatibility are **not yet proven**; failure preserves evidence
and stops without changing kernel settings or installing packages.

Staged helper SHA256:
`ce9665c9704d6c2eb642a95435822f4cf30b2662e658036c7d06e6d8580c5eb8`.
File: `project_atlas/tools/diagnostics/native_dashboard_cpu_once.py`.
Nine offline tests passed in existing WSL Ubuntu22.04: target/duration/frequency,
invalid PID, camera state, hash mismatch, scoped cleanup, escalation, exited
process, exit race, unchanged guard/control-operation contract.
Windows test import lacks POSIX pwd; native Linux test run passed, not suppressed.
Jetson import/hash validation passed before final cleanup-race-only correction;
final helper copied and SHA reverified. No profiler attached during preparation.

## Evidence and rollback

Unique `evidence-*` directory under staging contains telemetry.jsonl, perf.log,
perf.data and result.json. Directory0700/files0600, returned to jetson ownership.
Raw DWARF stack snippets can contain private application data: do not publish
perf.data or raw stacks to GitHub. Publish reviewed aggregate findings only.
Original services and files require no rollback because untouched. Keep staging
and evidence until analysis; cleanup can later remove this isolated tool package,
not production files. The white-glass rollback remains unchanged.

Reference: [upstream perf record manual](https://man7.org/linux/man-pages/man1/perf-record.1.html)
for single-PID targeting, no-inherit, frequency and DWARF callgraph options.
