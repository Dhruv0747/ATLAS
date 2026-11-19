# One timestamp-fixed retry — prepared, NOT executed

2026-10-30 IST. Runtime source b1946bd204584b106c950ce9f9f4c06315b7fc1d. Existing failed activation and its root evidence are preserved.

**GO for package preparation; NO-GO for execution until privileged rollback inspection and separate owner execution approval.** Remote sudo requires local-terminal authentication. No privilege bypass or automatic activation attempted.

## Actual checks

- Fresh three-sample read-only preflight: CPU 63.5368/62.7869/62.1578%; RAM 62.5019/62.5668/62.5207%; max temperatures 63.593/63.531/63.562 C. All safety predicates passed; manual-only, stop latched, commissioning false, zero commands, LIVE/fresh telemetry. Encoder counts unchanged at [3624,-2013,-38446,-1944].
- Current Jetson Unix timestamp 1793372962.2762566 round-tripped with zero error. Same-clock telemetry timestamp age 0.053–0.118s. No sensor-time rewriting; observed timestamp remains Unix seconds, cache expiry monotonic. Saved 2301.702-second rounding defect already covered by passing offline tests.
- Old monitoring units and rollback timer: LoadState not-found, inactive, PID0; TCP9118 has no listener. Exporter/guard files removed, monitoring configuration directories empty. Source route still wlP1p1s0, Jetson192.168.1.16 → Windows192.168.1.6.
- Root-only /var/lib/atlas-monitoring remains. Contents and live root firewall tables cannot yet be independently inspected remotely. Previous wrapper reported rollback VERIFIED; this does not substitute for the requested fresh privileged check.
- Prometheus ready; Grafana database healthy. No exporter started for these checks.
- New package rebuilt and all seven manifest entries verified on Jetson. Native systemd-analyze verify exit0; only preexisting snapd RestartMode and NVIDIA syslog warnings. Actual staged files nonexecutable/read-only-to-others; installed files will be root0644.
- **12 isolated simulated activation transaction tests passed (0.84s)**, including previous-state archive, fault-state rejection, baseline/active safety failure, service changes, successful acceptance and second-invocation refusal. Initial expanded mock incorrectly answered a multi-property systemctl query with PID-only output; corrected the mock and all cases passed. No candidate safety relaxation.
- Reused 86 passing timestamp/exporter/package tests and native Promtool freshness boundaries; unrelated tests not repeated.

## Hashes and staging

Stage: `/home/jetson/project-atlas-migration/monitoring-timestamp-retry-b1946bd/`.

- Package manifest SHA256: `155bb0074f653a7a3846bac120f5284f1be458952eb2831ebc8f32a39e882c27`
- Exporter SHA256: `0248d329dd659f3557b68ae8731cb1a85db763bb7855850e1c5cec0ccd0f3e3d`
- New wrapper SHA256: `a25ff2d8c6a516357d61f4a1d70fadf98b36178b9e547d25d1643b937bdd8969`

New wrapper keeps the existing 60-second baseline, five-minute supervision, 480-second independent rollback expiry, CPU75/RAM80/temp70 limits and firewall restrictions. Uses distinct single-use root evidence `/var/lib/atlas-monitoring-timestamp-retry-20261030` and distinct rollback timer. Prior clean inactive monitoring state may be archived intact under that new evidence directory only after fresh safety, no-listener/no-table and PID0 checks. Existing FAULT.json, observer-active.json, unknown files or untrusted ownership cause refusal; never silently clear a fault. The old attempt claim is never deleted. Existing root safety guards/firewall predicates are unchanged.

## Prepared execution command — DO NOT RUN before separate approval

```sh
cd /home/jetson/project-atlas-migration/monitoring-timestamp-retry-b1946bd &&
printf '%s\n' 'a25ff2d8c6a516357d61f4a1d70fadf98b36178b9e547d25d1643b937bdd8969  activate_timestamp_retry_once.py' |
sha256sum -c - &&
sudo timeout --signal=TERM --kill-after=20s 450s python3 -I -B activate_timestamp_retry_once.py
```

The wrapper additionally verifies the exact package-manifest digest before installation. Do not run the old command. Stop/rollback if any live gate fails; no automatic retry. Old runtime files are not reused.

## Required read-only gate now

In the local Jetson terminal, administrator authentication only:

```sh
sudo bash -c 'set -e; nft -j list ruleset; iptables-save; ip6tables-save; ls -la /var/lib/atlas-monitoring; cat /var/lib/atlas-monitoring-activation-20261030/result.json'
```

Review that monitoring rules are absent, original Tailscale rules remain, and preserved state contains no uncleared fault/active observer. Then obtain separate execution approval. Real Grafana update age and stale-alert clearing must be verified during the new run; cross-host clock synchronization and reboot persistence must not be claimed from offline tests. No reboot authorized. No installation, activation, critical-service restart, firmware/motor/controller change or PR merge occurred in this preparation.
