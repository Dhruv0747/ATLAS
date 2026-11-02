# Post-boot binding update � supersedes package references below

2026-11-02 owner-provided administrator evidence confirms the original FAULT.json and seven of eight state hashes unchanged. fault-events.json appended one refusal for boot c485cc95-d91c-4d4c-8fac-18a691a6b68c; new SHA256 de3ca6e690eadd9819751459ae1d457920923cb03c674c0c1f417c4f52500320. This is the same retained M2 incident, not a new watchdog rejection.

Only that expected hash changed in recover_once.py. Archive/rollback/runtime/firewall/guard code unchanged. Three focused checks PASS (binding, eight-file archive/reset/restore, corrupt archive rejection); prior suites reused. Seven internal Linux SHA checks PASS. Original archive and live evidence preserved.

Use NEW PC archive monitoring-recovery-m2-postboot-20261102.tar.gz SHA256 1b4e62460bb8657dc213712bcd9ed904402d9f7d9c92f1971ff3bec9fbda9b2d. The earlier archive below is superseded; do not execute its old hash command. Existing unused transaction identity is unchanged; never reuse any consumed attempt directory. Separate execution approval and fresh in-transaction safety/firewall/configuration/state checks remain required. No staging, latch reset or restart performed.

# M2 recovery preparation — 2026-11-02

Preparation PASS; execution requires separate owner approval. No live mutations.

Existing transaction rebound to the eight owner-verified current hashes, including
FAULT.json fc5479c96fd42ee003a565b0ccb7e63caaf9d29c43a383eff5291a3c938302fd
and fault-events.json fd8448d20e6642e0d8fa7dacd0e0770d945be926fa9755b8d9d333a4c2aa6709.
New exclusive attempt identity: atlas-monitoring-recovery-m2-20261102.
The earlier October 30 fault and attempt archives are a different incident and are
left untouched. M2 -126 to -127 is confirmed; physical cause remains UNKNOWN.

31 focused archive, tamper, rollback and transaction checks passed; three continuous
boundary checks and one eight-file archive/reset/restore integration check passed. One unique-attempt identity check also passed (36 focused cases total).
Independent review PASS. No full suite or live recovery was repeated.
Strict CPU<75 and RAM<80 now apply to every transaction sample, not only admission;
the frozen installed guard, temperature<70, fault behavior and firewall are unchanged.

Read-only preflight: CPU65.95–68.60%, RAM63.99–64.05%, max63.593C. Existing guard
validated latched/manual-only, commissioning disabled, zero commands, fresh telemetry
and stationary counts [21,643,-66,-5]. These observations expire: repeat admission
inside the approved transaction. Live guard, all three units and firewall configuration
match package bytes. Exporter hash0248d329dd659f3557b68ae8731cb1a85db763bb7855850e1c5cec0ccd0f3e3d.
Source restriction remains wlP1p1s0,192.168.1.6 ->192.168.1.16 TCP9118, other sources dropped.
Last administrator firewall evidence is the owner's unchanged legacy Tailscale-only /
empty nft ruleset. Worker must revalidate it before mutation; no current privileged
firewall inspection or fault clear was performed by this preparation.

## Package and future execution ONLY AFTER APPROVAL

PC archive: C:/Users/Dhruv/Documents/Codex/2026-07-24/h/tmp/monitoring-recovery-m2-20261102.tar.gz
SHA256: fb6f27539e9fbdc2fa89005650d5ad47648603b719fa8b327ca374ee9987dd67
Seven internal hashes verified with Linux sha256sum. Archive not yet transferred.

After execution approval, copy this exact archive to
/home/jetson/project-atlas-migration/monitoring-recovery-m2-20261102.tar.gz.
Then enter administrator authentication only in the local Jetson terminal:

```sh
sudo /bin/sh -c 'set -eu; umask 077; cd /home/jetson/project-atlas-migration; echo "fb6f27539e9fbdc2fa89005650d5ad47648603b719fa8b327ca374ee9987dd67  monitoring-recovery-m2-20261102.tar.gz" | sha256sum -c -; mkdir /opt/atlas-monitoring-recovery-m2-20261102; tar --no-same-owner -xzf monitoring-recovery-m2-20261102.tar.gz -C /opt/atlas-monitoring-recovery-m2-20261102; cd /opt/atlas-monitoring-recovery-m2-20261102; sha256sum -c RECOVERY_SHA256SUMS; exec /usr/bin/python3 -I -B recover_once.py start'
```

One start only,300s monitoring,330s worker limit and existing410s fallback cleanup.
Archive and verify all eight originals before any reset. Existing temporary monitoring-only
Restart=no policy; no rover service changes. Fail closed on drift or safety failure.

Separate client acknowledgement is REQUIRED while the attempt runs, only after real
Prometheus/Grafana checks pass. Target start+120s; latest start+240s. Never confirm blindly:

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-m2-20261102/recover_once.py confirm-client
```

Missing confirmation fails closed. Pulse View5075e03 asset update remains a separate
PC-only deployment; real animation is not certified by this package.

## Rollback

Existing automatic cleanup stops exporter/watchdog before removing owned monitoring
firewall protection, verifies no9118 listener, preserves new fault evidence and restores
old latch bytes if no new latch exists. All original evidence remains in original-state.
Restores original monitoring restart/enable policies and checks unchanged rover identities,
configuration hashes and legacy rules. Any cleanup failure remains an OPEN incident.
Existing fallback/manual cleanup action (not a retry):

```sh
sudo /usr/bin/python3 -I -B /opt/atlas-monitoring-recovery-m2-20261102/recover_once.py cleanup
```

GO for requesting one controlled recovery approval. No live acceptance, reboot recovery,
ordinary network interruption recovery or fix of encoder physical cause is claimed.

## Overnight preparation follow-up (2026-11-02; no execution)
Archive SHA256 rechecked unchanged. Reuse the36 passing focused checks; no changed transaction code or repeat suite. Owner later reported manually touching/moving the wheel as the physical explanation. This is an owner statement, not replacement of original M2 evidence or independently proven cause. Original latch remains retained.
Recovery is now STOPPED after the separate snapshot CPU abort; prior PID2089 observations above are historical. Restore original Recovery first under separate approval. Monitoring recovery still needs its own approval and fresh configuration/evidence/safety checks. No monitoring services restarted or latch cleared. Ordinary reconnect remains live-PENDING; exporter DOWN must not animate pulses.
