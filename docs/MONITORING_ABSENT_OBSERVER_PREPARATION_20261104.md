# Monitoring recovery preparation — 2026-11-04

Preparation only; nothing staged on Jetson or executed. Branch codex/monitoring-absence-20261104.

## Prior cleanup and incident
Owner supplied private result.json: FAIL, cleanup VERIFIED, original cause UNKNOWN.
Failure was missing client-confirmation.json, not CPU admission; final CPU 62.6486%, RAM 57.9461%, maximum temperature 61.875 C. This is historical evidence, not fresh admission.
The original archive included observer-active.json. Journal shows exporter then watchdog cleanly stopped at 09:27:13 IST. The reviewed guard removes the observer marker on clean watchdog stop when the exporter is absent and the fault has not yet been restored. Cleanup then restores the original fault. The observed absent marker is consistent with this intentional path; no separate unlink audit event exists.
Owner-reported wheel handling remains separate from original UNKNOWN M2 cause; historical evidence is not rewritten.

## New transaction
Package: monitoring-recovery-m2-absence-20261104.tar.gz
SHA256: ccc4a28800b05196249a0e0823ae7e6bb104e804a70f9c6bc9729d03f14c75f0
Local artifact: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/monitoring-recovery-m2-absence-20261104.tar.gz
Evidence directory: /var/lib/atlas-monitoring-recovery-m2-absence-20261104
Unit: atlas-monitoring-recovery-once-m2-absence-20261104

Seven present hashes are pinned in recover_once.py; observer-active.json must be ABSENT (including no dangling symlink). No hash is assigned to absence. A separate state-absent.json records this in the archive. Exact state is checked again before reset. Archive membership, hashes and absence metadata are checked before rollback; original fault is restored only if no newer fault exists. Observer evidence is never fabricated.

Based on verified previous package dc1b174a300aeed1193dc47a155c0b40dce6f4a2c8dff8b3484b3954b77a15ab. Other six payloads are byte-identical. Existing no-reload correction, CPU evidence, limits, expiry and cleanup behavior preserved.

Validation: 10 focused absent-state archive/rollback tests PASS in WSL; seven Linux sha256sum checks PASS; all eight extracted members regular, non-symlink, mode 0644. Independent scoped review PASS. No live acceptance claimed.

## Execution ONLY after separate owner approval
First transfer the exact archive to /home/jetson/project-atlas-migration using the existing approved SSH path. Do not overwrite any old attempt. Authenticate locally on Jetson and execute ONCE:

```sh
sudo /bin/sh -c 'set -eu; umask 077; cd /home/jetson/project-atlas-migration; echo "ccc4a28800b05196249a0e0823ae7e6bb104e804a70f9c6bc9729d03f14c75f0  monitoring-recovery-m2-absence-20261104.tar.gz" | sha256sum -c -; mkdir /opt/atlas-monitoring-recovery-m2-absence-20261104; tar --no-same-owner -xzf monitoring-recovery-m2-absence-20261104.tar.gz -C /opt/atlas-monitoring-recovery-m2-absence-20261104; cd /opt/atlas-monitoring-recovery-m2-absence-20261104; for f in *; do test -f "$f" && test ! -L "$f" && test "$(stat -c %a "$f")" = 644; done; sha256sum -c RECOVERY_SHA256SUMS; exec /usr/bin/python3 -I -B recover_once.py start'
```

Existing fresh safety admission is mandatory: E-STOP, zero commands, stationary encoders, fresh telemetry, CPU <75%, RAM <80%, temperature <70 C. Drift or failed admission consumes the attempt; no retry.
Observe for 300 seconds. Existing bounds remain RuntimeMaxSec=330, TimeoutStopSec=30 and independent fallback at 410 seconds with 30-second cleanup allowance; not a 330-second total guarantee.
Have an authenticated Grafana browser ready BEFORE execution. Verify Prometheus fresh data and current Grafana values before issuing the existing client confirmation in its printed 120–240 second window. Do not confirm on stale data or after expiry:

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-m2-absence-20261104/recover_once.py confirm-client
```

Rollback is automatic ExecStopPost plus existing expiry fallback: stop monitoring, verify no exporter listener/owned firewall table remains, preserve unrelated rules/protected services, restore latch and original monitoring restart/enabled configuration. If automatic cleanup reports failure, preserve evidence and STOP; no new start. The same reviewed cleanup entry point is the manual fallback, not a recovery retry:

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-m2-absence-20261104/recover_once.py cleanup
```

## Pulse View reconciliation
Installed bundle matches its own SHA256SUMS. Candidate installer differs in four files:
- source.mjs: CRLF/LF only, same authenticated query/parser.
- neural_topology.json: CRLF/LF only, identical JSON, 19 nodes/eight verified paths/12 unverified paths.
- index.html: updated status/direction/rate legend, plus line endings.
- view.mjs: direction arrows, LIVE/DISCONNECTED display labels, bounded log-rate pulse speed, live-age details, epoch/single-flight reconnect protection, plus line endings. gates.mjs unchanged.
Exact a8fd494 object was not found in available shared Git worktrees, unreachable objects, fetched relevant remote branches, WSL home/opt repositories, or the available exported bundle reference. Candidate checksums do not establish commit provenance. Source revision remains MISSING; deployment BLOCKED.
Exact installed tar backup: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/pulse-reconciliation-20261104/original-pulse.tar
SHA256: 1445e585e28e84baf8125fdbca3a3b29c211ad52e1179085c470c664d2573e35
Prepared candidate/diff information remains local; do not deploy before source integrity and separate approval. Recover a Git bundle containing a8fd494 from its originating checkout, or independently review the exact exported candidate as a new revision. No reinstall/container recreation or dashboard modification.
Windows startup is owner-reported PASS; reboot persistence remains unverified. Grafana health/auth protection PASS; prior browser check unauthenticated, zero visible pulses. Exporter down; live acceptance BLOCKED. Ordinary reconnect is not a license to clear the M2 latch.
