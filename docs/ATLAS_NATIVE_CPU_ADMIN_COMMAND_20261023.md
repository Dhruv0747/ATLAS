# One owner-run native Dashboard CPU profile

## Current next action: targeted Python GIL profile

Native capture is now analyzed in `ATLAS_NATIVE_CPU_RESULT_20261023.md`.
The next owner-run diagnostic targets Python functions holding the GIL in the
existing Dashboard PID: 10 seconds, 20 Hz, thread-tagged Speedscope output.
It uses the existing hash-verified py-spy binary, nonblocking sampling, no locals,
no idle-thread capture and no child-process capture. It samples all GIL-holding
threads in that PID; the two native TIDs remain monitored for identity/CPU
correlation, not a Python sampling filter. Nonblocking stacks can be inconsistent;
sample counts are not exact function CPU time or proof of a fix.

Run once, leaving ATLAS stopped and E-STOP latched:

```bash
sudo /usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B /home/jetson/project-atlas-migration/native-cpu-20261023/native_dashboard_cpu_once.py --python-gil
```

This command retains CPU 75%, RAM 80%, temperature 70 C and all freshness/safety
gates. The previous native-run CPU exception is NOT included or carried forward.
No automatic retry. No production edit, service restart, camera start or motion.
Private output: a new `evidence-*` directory under the diagnostic staging folder;
`python-gil.json`, profiler log, resource trace and result hashes stay there.

Prepared helper SHA256 (local and staged bytes verified identical):
`f1bb43e830ae221d33ae6fc40564e457b117f9e173d47facfbc1d47fbf392a76`.
Backup: same staging folder, `native_dashboard_cpu_once.pre-python-gil.py`.
Offline unittest suite: **22 passed**, including unchanged CPU policy in Python
mode, bounded command, no-local/no-idle options and invalid PID rejection.
No Python capture or runtime optimization has been executed at this checkpoint.
CPU savings remain unmeasured; select any production fix only after analysis.

## Latest checkpoint: zero-sample abort and narrower candidate

Second owner run: `evidence-4a85e42k`, ABORTED at77.142857% CPU, before
RAM/temperature/policy checks for that failing sample. Previous baseline samples
passed. Five prelaunch CPU samples:69.0476,71.2095,70.6081,71.6949,68.9713%.
Profile launch monotonic10250.822816; failed sample10251.639502 (0.817s later).
Dashboard TIDs5549/5729 used27.94/14.97% one-core in that interval, comparable to
the immediately preceding intervals. Does NOT establish cause of aggregate spike.

perf.data255928bytes, SHA256
`a84cf2dec8497ca80b93122a5a4cfd511e05aff19606f92f889811098c532675`.
Offline `perf report --stdio --header --no-children` says **data has no samples**.
The file has process/mapping/header metadata, not usable CPU call stacks.
Event header lists138IDs; proc trace has23 Dashboard threads on6 CPUs.
The file is not proof of successful profiling or a runtime CPU fix.

Prepared diagnostic-only narrowing: select two stable native TIDs with the
largest measured baseline tick deltas; verify birth IDs before/during attachment.
Use `-t`, `--per-thread`, `--no-bpf-event`, one synthesis thread. Keep19Hz,
10s, user-space CPU event, bounded DWARF stacks and existing timeouts. This
reduces target scope23->2; actual sampling overhead reduction remains unmeasured.
All options verified in staged perf help. No retry executed by the agent.

Owner subsequently explicitly requested ignoring CPU for this attempt. Added
`--diagnostic-cpu-report-only`, default OFF, limited to this stationary profiler.
It keeps measuring/recording valid CPU but passes None to the existing gate's
optional CPU argument. All RAM80%, temperature70C, freshness, callback/sampling
deadline, E-STOP/manual-only/zero-command checks remain. Production gate files,
Astra75% limit and all runtime policies remain unchanged. Invalid CPU samples
still abort. No camera start/motion/restart or production installation.

Owner's explicit-exception command, run ONCE:

```bash
sudo /usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B /home/jetson/project-atlas-migration/native-cpu-20261023/native_dashboard_cpu_once.py --diagnostic-cpu-report-only
```

Nineteen offline tests pass in WSL. Staged helper SHA256 verified:
`12c12eb51517e6d26149143f1ad0365feee65d4098cacdcb408e8da5f6578b66`.
Prior corrected helper retained as `native_dashboard_cpu_once.pre-two-thread.py`.
Fresh read-only postflight: CPU71%,RAM71.057%,max60.062C, E-STOP latched,
manual-only,zero commands,recorder off and extra-safety sensor checks pass.
Protected PIDs/restart counts equal owner-run initial identities. Astra process
absent; white-glass and Dashboard source hashes unchanged. No CPU saving claimed.

Earlier checkpoints follow for provenance; command/hash/counts above supersede them.

Prepared23 October2026 after7534178. First owner run aborted before profiling;
corrected helper staged below. No CPU fix claimed.

## Owner run failure and scoped correction

Evidence `evidence-qcvxb6uy/result.json`: ABORTED before baseline, zero-byte
telemetry.jsonl, no perf.log or perf.data. Owner terminal supplies exact error:
`Failed to connect to bus: $DBUS_SESSION_BUS_ADDRESS and $XDG_RUNTIME_DIR not defined`.
No camera, service restart or production modification occurred.

Confirmed helper defect: seteuid changed effective UID to jetson while real UID
remained root. systemctl's secure environment handling ignored the user-session
variables despite their presence. Reproduced the exact error in isolated WSL
with mixed IDs and explicitly supplied variables. Matching real/effective IDs
made systemctl use the supplied test bus address (then correctly reported the
deliberately nonexistent bus). No real user bus or robot was touched in this test.

Correction uses setresuid/setresgid to set real and effective IDs to jetson,
retaining saved root only for the owned profiler/evidence operations. Tests
verify two complete user/root cycles and executed children receiving matching
real/effective IDs on Linux. Service identity checks retain full stdout/stderr,
return code and caller IDs in fsynced evidence. Same protected-unit parser,
resource/sensor gates, durations and process cleanup are preserved.

13 unit tests pass in WSL; two isolated Linux identity/error reproductions pass.
Jetson staged helper hash verified; actual administrator user-bus access and
perf sampling still require a new owner-run attempt. No automatic retry.
Old helper retained as `native_dashboard_cpu_once.pre-uid-fix.py` in staging;
failed evidence unchanged. White-glass hash unchanged; web PID1973/restarts0.

Corrected helper SHA256:
`13da9131f257f3743e76a9a49e13e6bede04f08ee9b80c5549601e8a04dbdca9`.
The command below now invokes the corrected staged helper. It must still abort
if fresh checks fail. This corrects the profiler launcher, NOT ATLAS CPU usage.

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

Original helper SHA256 (superseded by correction above):
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
