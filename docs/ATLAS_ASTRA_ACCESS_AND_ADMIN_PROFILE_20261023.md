# Astra access recovery and bounded administrator profiling — 23 October 2026

## Confirmed cause

Both verified interfaces are present at the same previously approved topology
and nodes: depth2bc5:0403,1-2.3.1.2,/dev/bus/usb/001/014; RGB2bc5:0501,
1-2.3.1.1,/dev/bus/usb/001/011. Neither exposes a USB serial. Each is now
root:root0644, with only owner/group/other ACL entries; named jetson RW access
is absent and the service user's access check fails. Thus this occurrence is
permission loss, not device-node renumbering or proof of camera hardware failure.
A recent reboot was observed; the precise ACL-removal event was not recorded.
Temporary grants do not constitute reboot-persistent access.

Fresh read-only preflight: CPU71.7172%, RAM69.2697%, max59.218C; stop latched,
manual-only, commissioning false, STOPPED source, zero commands, recorder OFF.
No Astra driver PID found. No safety limit, camera mode, production file or
permission changed. sudo still requires the owner's authentication.

## Prepared owner command (not yet executed)

Run on Jetson, from the jetson account, with ATLAS parked. Do not Start Astra
or operate the remote during this diagnostic. Keep the dashboard workload
unchanged throughout the baseline/profile/post windows.

```sh
sudo /usr/bin/python3 -I /home/jetson/project-atlas-migration/admin-diag-20261023/astra_access_cpu_once.py
```

This command does NOT install a service or permanently change USB policy.
It performs one bounded operation, without automatic retries:

1. Hash-check deployed gate, probe, dashboard and isolated profiler executable.
2. Verify three fresh one-second safety/resource samples, camera stopped,
   healthy sensor receipts, zero four-wheel commands and protected services.
3. Require exact verified Astra topology, VID/PID, node and character-device
   numbers; abort on substitution, ambiguity or renumbering.
4. Save current ACLs in a new private evidence folder; grant only jetson RW on
   those two nodes. Test an open/close only: no device read/write/ioctl, stream
   creation or interface claim.
5. Collect5s baseline,10s py-spy thread-tagged nonblocking Python samples at20Hz,
   then5s postflight. An external12s timeout with2s kill escalation bounds the
   profiler. Resource/safety checks run each sample; deadline misses abort.
6. Verify services and retain temporary grants only on success. On failure,
   stop only the newly owned profiler and restore saved ACLs if the same
   devices are still present. If identity changed, refuse rollback onto a
   different device and report that failure for review.

CPU75%, RAM80%, temperature70C remain unchanged. No system-wide ptrace changes,
global chmod, udev installation, service restart, scheduling change, ROS
participant, calibration, image recording or movement. Administrator privileges
are used only for targeted ACL operations and bounded profiler ownership; API
and service checks run with jetson real/effective credentials.

## Evidence and interpretation

Each execution prints a unique staging `evidence-*` folder. It holds before/after
ACLs, monotonic telemetry, Linux TID ticks/birth times/scheduler counters,
observer CPU, profiler-process CPU, thread-tagged stacks, errors and result.
No locals, images, video or rosbag are captured. Files are private to jetson.
Incomplete profiles remain failure evidence, not a successful CPU diagnosis.

Nonblocking py-spy may produce inconsistent samples; counts are not CPU time.
This ARM64 build exposes Python sampling, not a native-stack option. Correlate
thread identity and tick deltas explicitly before attributing expensive native
work. Compare baseline/post intervals with profiling intervals to quantify
observer impact; do not claim entire-kernel CPU attribution from this capture.

## Verified files and tests

- Source: `project_atlas/tools/diagnostics/astra_access_cpu_once.py`.
- Tests: `project_atlas/tests/test_astra_access_cpu_once.py`.
- Staged helper SHA256: `7129baf4708d259ff08f482477a72a67f7d5b7da0b20f61907edd114d7fd5d95`.
- PyPI py-spy0.4.1 ARM64 wheel SHA256:
  `ee776b9d512a011d1ad3907ed53ae32ce2f3d9ff3e1782236554e22103b5c084`.
- Extracted executable SHA256:
  `972918b5d6af92649ec086ffdd89cefa0d725fd14844434c766f58494a1c4f8e`.
- Wheel downloaded from PyPI, hash compared with its release metadata; copied
  into isolated staging only, not installed into Python/system paths.
- ARM64 `record --help` runs on Jetson and confirms nonblocking/thread/duration
  options. Helper compiles on Jetson. No profiler attachment attempted.
-7 new offline tests plus6 existing USB-access tests pass in WSL. Covers bounded
  single-PID command, camera stopped states, stale/nonfinite sensor receipts,
  nonzero wheels, hashes, USB identity, renumbering and ambiguity.
-Privileged end-to-end execution and fault-injection rollback on actual hardware
  are NOT tested: owner authentication is still required. No access-restored or
  hot-function success claim yet.

The existing live probe hash remains
`f6321da4961482064a6d278e368efbb25540d5a3178ee14900255972b269a384`;
dashboard remains `98f3c2692e7c1c52e1285d3d91432ed521c67ff49c64508ad9a3813d1f0e5b79`.

## Rollback and permanent recovery

On successful execution the two temporary ACLs are deliberately retained so
Astra access is repaired, but no camera is activated. Saved `before.acl` is the
rollback source; verify identities again before restoring it with setfacl.
If a later CPU/profile guard fails, this combined transaction restores the old
ACLs and reports ABORTED rather than leaving an unverified partial operation.
Permanent device-specific udev access remains separately prepared/uninstalled;
it still needs reviewed deployment and reboot/reconnect validation approval.
This command does not pretend to solve that persistence milestone.

Profiler reference: https://github.com/benfred/py-spy (sampling/access and
nonblocking limitations); pinned distribution metadata:
https://pypi.org/pypi/py-spy/0.4.1/json.
