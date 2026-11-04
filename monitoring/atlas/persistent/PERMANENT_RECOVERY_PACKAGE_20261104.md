# Permanent monitoring recovery package (2026-11-04): preparation only

One new single-use rearm that also installs the reviewed transient/violation guard. OFFLINE PASS only:
nothing was staged, deployed or run on the Jetson in preparation.

## Identity (new, never consumed)

- Evidence directory: `/var/lib/atlas-monitoring-recovery-m2-permanent-20261104`
- Transient unit: `atlas-monitoring-recovery-once-m2-permanent-20261104`
- Base: the last successful transaction design (`m2-absence-20261104`, commit 53342616). Consumed
  identities (20261031, -2..-5, m2-20261102, m2-permissions-20261102, m2-absence-20261104,
  m2-noreload-20261104) are untouched and must never be reused.

## Current incident binding (owner sudo read, 2026-11-04 13:51 IST)

Eight PRESENT files, full SHA256, nothing required absent (`EXPECTED_ABSENT = ()`):

| File | SHA256 |
|---|---|
| FAULT.json | 4f04831f22623fad52fa28676348153989291f37ca4b1e4f05069e26e79a7dc5 |
| observer-active.json | 3da97cb57e24c8d881e384ab440fa2baf9f5cf25371691eeee658e92a37c3249 |
| fault-events.json (11 events) | f23ce63f51d0f795272cc878790a36d44c88322d7944bbab87ec9c627947391f |
| firewall-owned.json | 2212fe537ee251d867d8d7093effd941ddf5b969b299e3266cf3782358a727e4 |
| rollback.json | 1f188cc96e99b4557a1f62503ad33a3fdc3b4cffc495c483d339576409803527 |
| last-health.json | 35bd5fc4a5fe613a1f636d3f466a4aad3f5244489c9e429c86c65f2a2b91a36a |
| two lock files | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 (empty) |

Any drift (one changed byte, a missing observer marker, a symlink, a new event) aborts before reset.
All eight files are archived byte-exact with uid/gid/mode/mtime metadata and re-verified before the
only two reviewed markers (FAULT.json, observer-active.json) are removed. The 11 events are never
modified. Failure restores the archived FAULT bytes (a newer rejection is never overwritten). The
archived observer marker is not restored live: it described a listener that is no longer running.

## Configuration installed by the transaction

| Live path | Previous (must match exactly) | Installed |
|---|---|---|
| /usr/local/libexec/atlas-monitoring-guard.py | 27d4caca… (previous-guard.py) | 188d53db… (guard.py) |
| /etc/systemd/system/atlas-monitoring-watchdog.service | 31cf0a56… | 21f8ad39… |
| /etc/systemd/system/atlas-monitoring-exporter.service | b4802dc8… template, rendered | 74b22487… template, rendered |

Firewall unit cb7f3734 and nft ruleset 64535619 unchanged. Limits unchanged (CPU <75 %, RAM <80 %,
temperature <70 C; WatchdogSec=5; firewall source restriction to the PC unchanged).

`install_config()` runs inside `prepare_override()` before its one `daemon-reload`: exact-byte backup
of each previous file plus metadata to `E/original-config/`, then an atomic same-directory replace
(O_EXCL temp, fchown/fchmod, fsync, rename, read-back). It refuses any live file that is not the
reviewed previous version and cannot run twice.

Rollback:
- Transaction FAIL (any cause, including missed confirmation): cleanup restores the previous bytes,
  then reloads once and requires the full config hash set to equal `before.json`.
- A third version found during restore is refused and retained for review (fail closed).
- After a PASS, the owner may roll back with `restore-previous-config` (monitoring must be stopped;
  one reload; the latch is not touched).

Reloads: one in `prepare_override` and one in `restore_configuration` (the reviewed 80b7e0f1 design,
both under the CPU sampler). A FAIL after the worker's own restore performs one more unsampled reload in
ExecStopPost cleanup, as in the m2 packages.

## Before any execution (separate owner approval)

1. On the PC, Prometheus and Grafana must both be READY. Do not start if either fails:

   ```powershell
   wsl -d Ubuntu-22.04 -- curl -fsS http://127.0.0.1:9090/-/ready
   wsl -d Ubuntu-22.04 -- curl -fsS http://127.0.0.1:3000/api/health
   ```

   Expected: `Prometheus Server is Ready.` and `"database": "ok"`. The ATLAS target is expected to
   show `up=0` until the transaction starts the exporter.
2. Fresh E-STOP / manual-only / commission-off, zero commands, stationary encoders (rechecked by the
   transaction). No camera, motor or servo activation; no Recovery/ROS/controller restart.
3. Stage the exact archive to `/home/jetson/project-atlas-migration/` and verify its SHA256.

Start (local Jetson terminal, one attempt only):

```sh
sudo /bin/sh -c 'set -eu; umask 077; cd /home/jetson/project-atlas-migration; echo "<ARCHIVE_SHA256>  monitoring-recovery-m2-permanent-20261104.tar.gz" | sha256sum -c -; mkdir /opt/atlas-monitoring-recovery-m2-permanent-20261104; tar --no-same-owner -xzf monitoring-recovery-m2-permanent-20261104.tar.gz -C /opt/atlas-monitoring-recovery-m2-permanent-20261104; cd /opt/atlas-monitoring-recovery-m2-permanent-20261104; sha256sum -c RECOVERY_SHA256SUMS; exec /usr/bin/python3 -I -B recover_once.py start'
```

Only after Prometheus shows fresh ATLAS samples, inside the printed 120–240 s window:

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-m2-permanent-20261104/recover_once.py confirm-client
```

Never confirm without verified fresh metrics or after the window. Missing confirmation fails closed
(previous guard/units restored, latch restored). No automatic retry.

Owner rollback after a PASS only (not a retry):

```sh
sudo systemctl stop atlas-monitoring-exporter.service atlas-monitoring-watchdog.service atlas-monitoring-firewall.service
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-m2-permanent-20261104/recover_once.py restore-previous-config
```

Documented fallback cleanup only (not a retry):

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-m2-permanent-20261104/recover_once.py cleanup
```

## Offline verification

- Focused tests: `test_monitoring_recovery_transaction.py` + `test_monitoring_present_observer.py`
  (binding, 8-file exact archive, 11 events, observer drift, archive tampering, rearm removes only the
  two markers, rollback retains new faults, install/backup/restore exact bytes, third-version
  refusal, policy from the reviewed units, end-to-end simulation PASS keeps new / FAIL restores
  previous).
- Guard tests (`test_monitoring_persistent.py`, from the reviewed neural branch): pass except the
  pre-existing 10-30 activation pin `test_package_is_exact_and_refuses_overwrite`.
- Live acceptance (exporter UP, Prometheus fresh, Grafana panels, reboot survival): PENDING.
