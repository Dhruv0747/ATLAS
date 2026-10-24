# Localization monitor thread profiling — prepared, awaiting owner sudo

## Follow-up retrieval: 2026-10-24 06:32:38 +05:30

Owner reported running the command. Read-only checks on `jetsan-desktop` found
only the two staged scripts, no evidence subdirectory, result.json or saved
python-threads.json in the migration search. Both staged hashes still match
those below;directory owner jetson:jetson,mode775. A non-root launcher validation
reached the expected "Run once with sudo as jetson" refusal, without attempting
attachment or creating evidence. Thus helper loading works; the owner's actual
terminal outcome remains unknown. This does NOT prove a failed profile command,
successful capture or a CPU/resource failure. No automatic capture retry made.

Next necessary input is the exact terminal output from the owner's command.
No new runtime fix or optimization benchmark is justified without the missing
live attribution evidence. Previous tests remain valid;they were not rerun.
No production file,service,voice,UI,safety setting,camera or motor changed.

Continued from e49ffe3's rejected offline allocation candidate. No further
optimization chosen without live attribution. Read-only verification identified
`atlas-localization-monitor.service`,PID1948,active,executing the expected
`/home/jetson/project_atlas/scripts/atlas_localization_monitor.py`.
`ptrace_scope=1`;`sudo -n true` reports password required. No attachment attempted.

## Prepared diagnostic scope

One10second20Hz nonblocking Python-thread sample,5baseline and5postflight samples,
outer45second timeout. No GIL-only filter, because NumPy releases the GIL. Captures
thread names/Python call paths plus1second `/proc` native thread tick deltas.
No locals,audio,images,video,rosbag,subprocess profiling,new ROS participants,
native unwinding,network changes,services restarted or camera/control operations.

Python stack samples show the Python call site while native work occurs; they
do not identify internal NumPy/C++/BLAS functions. Thread ticks provide CPU
consumption,not precise per-frame attribution. A10second window may miss a
periodic search. Missing worker samples must NOT be interpreted as proof the
worker is cheap; inspect duty-cycle evidence before deciding the next experiment.

The hash-pinned shared helper is adapted only in a private module in this
diagnostic process:accurate ALL_THREADS labels/output filenames,additional
voice/safety-status service identity checks,and remove `--gil` from py-spy.
Shared helper/production ROS modules are not modified. The wrapper accepts NO
arguments,including no CPU exception. Actual command flags retain thread labels,
nonblocking mode,20Hz and10second duration. Existing selected-native-thread
identity checks remain; an ephemeral selected thread exiting can abort safely.

Fresh75%CPU/80%RAM/70C guards,safety/sensor freshness checks,E-STOP/manual-only,
zero commands,Astra/recorder OFF and protected identities apply when command runs.
Any failure stops capture;no automatic retry. Evidence includes profiler output,
telemetry,result and payload hash;review failures rather than rerunning blindly.

## Hashes / tests

Wrapper `localization_cpu_once.py` SHA256:
`3b92f431d7837eecdf544c0339ea5ffc38459eafe3e5ac267b5a1d37d8123318`.
Shared helper SHA256:
`2b0cd1ee5872070ee21c93780445e8296b9f1a2574b84ad3e7375e98bc959e18`.
Target source SHA256:
`cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b`.
Localization core SHA256:
`d95828a09b174d109033c4af10fdf2f65599e1c7365ca669dff3428e6e723462`.
py-spy executable verified SHA256:
`972918b5d6af92649ec086ffdd89cefa0d725fd14844434c766f58494a1c4f8e`.
Current deployed voice,safety-status,Dashboard,white-glass CSS,guard/probe hashes
are enforced by the wrapper/helper before and after capture.

27tests passed:5new wrapper tests and22shared tests. Covers strict entry,
fixed target/hash,tampered helper rejection,all-thread bounded flags,no locals,
accurate result labels,additional protected services,cleanup,UID/user-bus
transition,CPU validation,identity checks and deadline command bounds.
No live profile or new CPU savings claimed yet.

## Owner command (Jetson terminal)

```sh
sudo /usr/bin/timeout --signal=INT --kill-after=3s 45s /usr/bin/python3 -I -B /home/jetson/project-atlas-migration/localization-cpu-20261024/localization_cpu_once.py
```

Only two diagnostic files staged in that migration directory;remote hashes
matched local. No production installation. Evidence will be written to a new
`evidence-*` subdirectory there. Root is used only for attachment/owned-profiler
cleanup and evidence ownership;guard checks run as jetson with the correct user
bus. Preserve result even if ABORTED. Do not paste a sudo password into chat.

Next:retrieve/hash-check the produced evidence,correlate thread CPU with actual
call paths and sensor timing,then test a focused candidate offline if warranted.
No production rollback needed;production was not changed. Diagnostic artifacts
are inert and should be retained until analysis completes. Voice,UI and limits
remain unchanged;no Astra start or movement authorized by this command.

## 2026-10-24 06:35 IST: admission abort confirmed

Authentication succeeded on the owner's latest attempt. The saved result is
ABORTED during the first baseline sample: CPU 75.20938023450586%, exceeding
the unchanged 75% limit. The profiler did not launch; no Python call stacks
exist. This supersedes the earlier missing-evidence status, not its history.

Evidence retained on Jetson:
`/home/jetson/project-atlas-migration/localization-cpu-20261024/evidence-71fnxz1g/`.

- `result.json`: 1778 bytes, SHA256
  `117bf066aee7278730a3258cef281e250496a675fe3952355b48e7741dd894f4`.
- `telemetry.jsonl`: 1667 bytes, SHA256
  `d45ea34944647870e99e9633132436e538287c779360e5966e307c75a99a13e4`.
- Read-only retrieval confirmed these hashes and absence of a profile payload.
- One baseline sample is not a thread CPU interval or hot-function profile.
  RAM/temperature were not sampled after CPU failed; full safety/postflight
  validation is not claimed.
- No production change, service restart or camera start was performed by the
  launcher. No automatic retry, safeguard exception or speculative fix applied.

Next necessary action: a separately authorized bounded capture with passing
admission, then function attribution before selecting another offline fix.
Prior 27 passing preparation tests remain historical evidence; no code changed
or tests repeated for this documentation-only update. CPU savings are unknown.
