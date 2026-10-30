# Persistent monitoring preparation evidence — 2026-10-30

Verdict: **PASS for repository/offline preparation; PENDING for Jetson activation and reboot reliability.** No live installation or activation performed. PR remains unmerged.

## New executed evidence

Environment: Windows 11 + Ubuntu-22.04 WSL2, Python 3.10, systemd 249, nftables 1.0.2, native legacy iptables. Tests executed on PC, not Jetson.

| Check | Actual result |
|---|---|
| `python3 -m pytest -q project_atlas/tests/test_monitoring_persistent.py` | **34 passed in 0.30s** |
| `unshare --net python3 monitoring/atlas/persistent/test_packet_paths.py` | **8/8 true**, disposable namespaces only |
| `python3 monitoring/atlas/persistent/test_lifecycle.py` | **9/9 true**, uniquely named fake services removed afterward |
| `systemd-analyze verify` on three rendered units | exit 0; unrelated existing snapd unit warns about unknown RestartMode on systemd 249 |
| Exact exporter SHA256 | unchanged: caa6ebe571e4ae57aa2be5be9bc80bea00252c6fb9c2897387edc762caf8b0f9 |
| Windows task preparation | XML exported to local TEMP; three one-minute-spaced retries; no task registered/started |

Packet results: permitted Windows IPv4 source; denied other IPv4 source; denied IPv6; unrelated port preserved; denied loopback 9118; rollback restored original other-source behavior; unrelated nft table preserved; legacy rules preserved. These are real kernel packet tests, not only string checks. Source 192.168.1.6 means the Windows host and its NAT clients; it is not individual-client authentication.

Native fake-unit results: ordered readiness; watchdog crash stops exporter; preflight rejection prevents listener; watchdog stall stops exporter; restart burst limit; hardened fake process can read /proc but cannot write /etc; configured CPU/memory properties; clean shutdown; firewall retained on stop. No production service is referenced by this test. Test timers are accelerated, while candidate unit values are separately asserted.

During test development two harness assumptions were corrected: Type=simple start completion does not imply the Python worker has written its marker, and systemd 249 retains Result=exit-code when restart limiting fires. The final test waits for actual readiness, checks the rate-limit journal event, failed state and stable restart count. No production policy was changed to make tests pass.

Unit coverage includes exact 75/80 acceptance and over-limit rejection, temperature 70 rejection, malformed/negative/nonfinite/missing ages, E-STOP/manual/commission predicates, zero commands, encoder movement, thermal CV unavailability, API timeout/absolute deadline, exact firewall expressions/order, durable fault latch, evidence write failure, leftover observer crash marker, exporter hash mismatch, each-loop safety rejection, rollback listener retention, nonblocking stop to avoid dependency deadlock, immutable packaging and overwrite rejection.

Packaging also tests LF-checkout reconstruction of the exact CRLF trial artifact and rejects modified content. No exporter logic changed. Candidate helper files use explicit LF attributes for portable source checksums.

## Reused evidence, not rerun

Existing exporter/config tests: 24 passing. Existing Promtool configuration/rules validation: 14 rules and two alert scenarios passing. Existing Ubuntu Docker/Compose deployment and localhost Grafana dashboard verified in WSL_INSTALLATION_RESULT.md.

Owner-provided final five-minute trial output reports PASS / cleanup VERIFIED with all seven evidence checksums OK. Earlier retained trial measurements: approximately 0.963 exporter CPU-seconds over 300 seconds (~0.32% of one core), ~11 MiB exporter RAM, sampled whole-Jetson CPU average 61.71%, peak 62.52%, temperature 63.343 C and RAM 62.21%. These are historical exporter trial observations, **not measurements of the new watchdog or causal before/after CPU savings**. Root-only trial raw evidence has not been recopied in this preparation.

## Remaining risks / explicit pending checks

- New watchdog overhead and hardened exporter access to the actual jetson user bus/API are PENDING live validation. The PC fake hardening test proves the sandbox runs, not compatibility with all target services.
- Jetson nft JSON compatibility, real permitted/denied LAN traffic, systemd boot ordering, fresh post-reboot state and monitoring recovery are PENDING. Boot with unavailable safety data intentionally fails closed and requires review; there is no automatic fault clearing.
- Windows login/reboot recovery and persisted Grafana/Prometheus data after restart are PENDING. Docker restart policies and volumes already exist; prepared task is not active and requires user login.
- Root firewall removal is detected with finite delay. No software polling mechanism guarantees zero exposure under privileged external rule tampering. The exporter remains read-only and LAN-bound.
- The stationary policy will stop monitoring on encoder movement, E-STOP release, commissioning enablement or safety loss. Continuous monitoring during driving needs a separately reviewed policy, not a threshold bypass.
- Rollback with a lingering listener, unknown table or timed-out service stop retains firewall protection and reports failure. No broad ruleset restore or automatic retry.

## Next approval

Ready for review of the hashed package and **one controlled monitoring-only installation/activation**, subject to fresh target safety, identities, hashes and rollback checks in RUNBOOK.md. No critical rover restart is required. Windows task activation is a distinct opt-in. Controlled rover reboot and Windows logon tests require separate approval before claiming persistent reliability.

Implementation commit is the commit containing this report; `git rev-parse HEAD` and PR #13 identify it without a self-referential embedded hash. Source-file SHA256SUMS and generated-package manifest provide byte-level identity.
