# M2 permissions-corrected package — preparation only

2026-11-02: bound to all eight hashes supplied by owner after the consumed CPU rejection.
Original M2 fault and five-event history unchanged. Only rollback.json changed to
5c3d4e5e63ae80648b5d112388076107733f0694a38dc6b0c89ddf113320508d.
Existing guard.rollback writes a new timestamped rollback.json; contents not independently
read here. Exact bytes are required, parsed and archived before reset by the transaction.

Package: monitoring-recovery-m2-permissions-20261102.tar.gz
SHA256: eaa18a512705046026cc2ca90b7f31f308d3e6068b2b8cb3f2991467697e7bc3
Local artifact: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/monitoring-recovery-m2-permissions-20261102.tar.gz
New evidence directory: /var/lib/atlas-monitoring-recovery-m2-permissions-20261102
New unit: atlas-monitoring-recovery-once-m2-permissions-20261102
Old consumed transaction/evidence untouched. Reviewed CPU correction 81f5ae4 included.
Four focused identity/archive/integrity/restore tests pass; reuse 13 passing CPU checks.

## Execution only after separate owner approval

First stage the exact archive with scp from the PC to
jetson@192.168.1.16:/home/jetson/project-atlas-migration/.
No staging or execution was performed in preparation. In the local Jetson terminal:

```sh
sudo /bin/sh -c 'set -eu; umask 077; cd /home/jetson/project-atlas-migration; echo "eaa18a512705046026cc2ca90b7f31f308d3e6068b2b8cb3f2991467697e7bc3  monitoring-recovery-m2-permissions-20261102.tar.gz" | sha256sum -c -; mkdir /opt/atlas-monitoring-recovery-m2-permissions-20261102; tar --no-same-owner -xzf monitoring-recovery-m2-permissions-20261102.tar.gz -C /opt/atlas-monitoring-recovery-m2-permissions-20261102; cd /opt/atlas-monitoring-recovery-m2-permissions-20261102; sha256sum -c RECOVERY_SHA256SUMS; exec /usr/bin/python3 -I -B recover_once.py start'
```

One attempt only. Archive integrity and current exact state checked before latch reset.
Fresh E-STOP/manual-only/commission-off, zero commands, stationary encoders and telemetry
required; CPU<75%, RAM<80%, temperature<70C unchanged. Existing Windows source-only TCP9118
restriction unchanged. No Recovery/ROS/controller restart.
300-second observation, 330-second worker runtime, existing bounded cleanup/fallback unchanged.
After actual Prometheus/Grafana acceptance, follow the printed confirmation window (120–240s):

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-m2-permissions-20261102/recover_once.py confirm-client
```

Never confirm without verified fresh metrics; never confirm a failed/closed attempt.
Missing confirmation fails closed. Genuine Pulse View acceptance must be checked separately.
Automatic cleanup stops exporter/watchdog, verifies no listener before protection removal,
restores original policies and retains archived fault bytes/new rejection evidence.
Only if documented fallback cleanup is required (not a retry):

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-m2-permissions-20261102/recover_once.py cleanup
```

GO for requesting ONE execution approval, subject to fresh runtime gates. No live acceptance:
exporter UP, Prometheus fresh, pulses, reconnect remain PENDING. CPU rejection magnitude and
physical overload cause UNKNOWN; owner wheel-touch statement does not rewrite M2 history.

## Permission correction and verification

The preceding cpuevidence archive was rejected before worker startup: Windows tarfile
metadata inherited 0666. That archive and extracted Jetson files remain untouched.
This new archive uses explicit modes from git index (100644 for all seven payloads
and the checksum manifest), uid/gid 0 and regular-file members only. No payload needs
executable mode: Python entrypoints use /usr/bin/python3 and service/template/nft files
are data. Executable bits must be preserved from reviewed git modes if a future payload
requires them; no blanket chmod of live files is involved.

Archive members checked: 8/8 regular, 0644, root ownership, no group/world write.
Native Ubuntu tar extraction into TemporaryDirectory: 8/8 exactly 0644; all seven
sha256sum checks PASS. Temporary extraction cleaned automatically. Two focused new
identity/binding checks PASS, 50 deselected. Reused previous four archive/rollback and
13 CPU evidence results; unchanged implementation. No live access or deployment.
Incident hashes are those last supplied by owner; transaction must recheck all eight
before any reset. Any drift aborts. Old rejected transaction must never be reused.
