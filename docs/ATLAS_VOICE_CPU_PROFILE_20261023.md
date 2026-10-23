# Targeted voice CPU profile — prepared, not captured

Owner requested bounded voice profiling and subsequently explicitly approved
CPU-report-only for this one diagnostic run. Production CPU75%, RAM80%, temp70C
and camera admission policies remain unchanged. No camera start or movement.

Read-only checks: voice service active PID2021/restarts0, Dashboard94624/0.
Voice source SHA256 `37f275ddb5e259466b909b0da2654fdaaf8a06b06cf02d969813c8affc0c2f72`.
Dashboard/private executor hashes match the deployed package. Verified py-spy
SHA256 `972918b5d6af92649ec086ffdd89cefa0d725fd14844434c766f58494a1c4f8e`.
ptrace_scope=1; sudo requires owner password. No profiler has attached yet.

## Prepared diagnostic files only

Staged in `/home/jetson/project-atlas-migration/voice-cpu-20261023/`:
- voice_cpu_once.py SHA256 `7a8c4863b7e807d35c58004d218b0b731e0651a3f55c57097f6f5f0fb894d2c0`
- native_dashboard_cpu_once.py SHA256 `2b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18`

Wrapper checks helper hash before loading; fixes target to voice service, verifies
current MainPID, UID, cmdline, start time and all reviewed file hashes. Shared
helper also tracks Dashboard and protected service identities. Defaults remain
strict; only the explicit diagnostic flag makes valid CPU observations report-only.
RAM/temperature/safety/freshness checks still run. Invalid CPU values still fail.

Five baseline samples, up to10seconds Python GIL sampling at20Hz with all-thread
labels, then five postflight samples. Native thread ticks/scheduler counters and
observer CPU are retained. One hottest stable native TID suffices for Python mode;
the Python sampler is not restricted to that TID. All native TID rows are retained.
GIL sampling cannot quantify native GIL-released work or prove native CPU
attribution; correlate counts with thread CPU before proposing a fix.

Nonblocking py-spy, no locals, idle stacks, subprocess profiling, audio recording
or production ROS participant. Stack names may still be private; raw evidence
stays in mode0600 files in a private evidence directory. Runtime source hashes
are rechecked after success. Abort preserves partial output; no automatic retry.
Cleanup signals only the profiler's own process group, never the voice service.

## Owner command

Run once in the Jetson terminal, with rover stationary and E-STOP latched:

```bash
sudo /usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B /home/jetson/project-atlas-migration/voice-cpu-20261023/voice_cpu_once.py --diagnostic-cpu-report-only
```

No global permission changes, service restart or production installation needed.
The non-root staged invocation was verified to refuse before creating evidence
or attaching. No production file changed; no rollback necessary.

## Offline tests and next action

29 tests pass:7 voice-wrapper tests plus22 shared observer tests. Cover fixed
target/hash, exact helper integrity, default strict policy, explicit scoped CPU
exception, rejected arguments, bounded privacy-conscious sampler, UID/GID bus
identity, selected thread identity, Astra OFF, error preservation and owned-group
cleanup. Production services were not restarted by preparation.

Wait for owner-run result; analyze actual voice hot functions, then implement and
test a narrowly supported candidate offline. No safe voice runtime fix or CPU
savings are claimed before this capture. Preserve white glass, wake-word,
conversation, announcements, safety and all existing features.
