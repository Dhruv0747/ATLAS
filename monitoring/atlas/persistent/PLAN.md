# Persistent monitoring design — 2026-10-30

**Implementation update:** see [RUNBOOK.md](RUNBOOK.md) and [VALIDATION.md](VALIDATION.md) for the implemented guard, tested units, exact commands and pending live gates. The original design below is retained as history. The implementation uses one `atlas-monitoring-guard.py` helper, `ExecCondition` rather than `ExecStartPre`, and a three-second exporter stop timeout. No production activation has occurred.

GO for the design and isolated firewall candidate; NO-GO for production activation until the integration gates below pass. No installation/reboot/service restart authorized or performed by this preparation.

## Immutable exporter

Reuse project_atlas/scripts/atlas_health_exporter.py byte-for-byte:
SHA256 caa6ebe571e4ae57aa2be5be9bc80bea00252c6fb9c2897387edc762caf8b0f9.
Arguments: --bind 192.168.1.16 --port 9118. Keep 15-second cache collection, 45-second stale HTTP 503, read-only routes and existing topic freshness rules. Never add ROS participants. Trial CPU cost 0.963 CPU-seconds/300 seconds; about 11 MiB RAM. Whole-Jetson samples are not proof of a causal CPU delta.

## Exact proposed installed files

- /opt/atlas-monitoring-exporter/atlas_health_exporter.py (root-owned 0644, exact hash)
- /etc/atlas-monitoring/atlas-monitor.nft (root-owned 0644, candidate alongside this plan)
- /usr/local/libexec/atlas-monitoring-preflight (root-owned safety/hash/firewall verifier; integration implementation still pending)
- /usr/local/libexec/atlas-monitoring-watchdog (root-owned observer of safety/freshness/resources/firewall; implementation still pending)
- /etc/systemd/system/atlas-monitoring-firewall.service
- /etc/systemd/system/atlas-monitoring-exporter.service
- /etc/systemd/system/atlas-monitoring-watchdog.service
- /var/lib/atlas-monitoring/ (root-owned rollback manifests, sanitized evidence and durable fault latch)

The new preflight/watchdog must reuse existing Orin-aware thermal handling, not missing-zone zero substitution. CPU >75%, RAM >80%, temperature >=70 C, malformed/stale safety or changed firewall must refuse startup/stop only monitoring. Preserve failed observations before cleanup. Failures latch; no repeated startup attempts after a safety rejection. Policy changes during legitimate future driving must stop monitoring under the current stationary authorization; monitoring during movement requires a separately reviewed policy.

## Firewall persistence and ordering

Use ONLY the dedicated inet atlas_monitor nft table, not /etc/nftables.conf (that file contains flush ruleset). Do not enable nftables.service or install a blanket iptables-save restore service. Preserve legacy iptables/Tailscale unchanged.

The prepared chain hooks INPUT at priority -10, before legacy filter priority 0. Only Wi-Fi IPv4 traffic from 192.168.1.6 to 192.168.1.16 TCP 9118 returns to the remaining firewall evaluation; every other TCP 9118 packet, including IPv6, is dropped. All other traffic continues unchanged. An earlier/later ACCEPT cannot override the DROP in this chain. The allow path does not bypass existing legacy restrictions. Source IP grants access to the Windows host, not solely one WSL distro. Reserve/recheck Windows IP; a changed IP means monitoring unavailable, never broaden the rule automatically.

firewall.service: Type=oneshot, RemainAfterExit=yes, Before=atlas-monitoring-exporter.service, ExecStart preflight table ownership/absence then nft -c -f and nft -f the dedicated file. Never flush a foreign or ambiguous table. No ExecStop that deletes rules. A failed/abnormal monitoring shutdown keeps protection installed. Reboot rebuilds this table before any listener. Root-level external removal of firewall rules cannot be made impossible by a monitoring service; watchdog detection has a finite delay and must be reported honestly.

exporter.service: Requires/After=atlas-monitoring-firewall.service, BindsTo/After=atlas-monitoring-watchdog.service, After=network-online.target; User=jetson, Group=jetson; ExecStartPre=+the reviewed preflight; ExecStart=/usr/bin/python3 -I -B /opt/atlas-monitoring-exporter/atlas_health_exporter.py --bind 192.168.1.16 --port 9118. Resolve and verify the real jetson UID before rendering XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS; do not assume UID 1000. Those variables are needed for existing user-systemd status reads.

Resource/shutdown proposal: CPUQuota=10%, MemoryMax=64M, TasksMax=32, Nice=10, KillMode=control-group, TimeoutStopSec=5, NoNewPrivileges=yes, ProtectSystem=strict, ProtectHome=read-only, PrivateTmp=yes, RestrictAddressFamilies=AF_INET AF_UNIX AF_NETLINK. No PrivateNetwork (would break host cached API). These hardening settings must be tested with real cached API/systemd reads in isolation before approval.

Restart policy: Restart=on-failure, RestartSec=30, StartLimitIntervalSec=600, StartLimitBurst=3; safety verifier exit 78 and RestartPreventExitStatus=78 plus durable latch. A watchdog safety failure explicitly stops exporter (systemd explicit stop does not auto-restart). Watchdog itself has no automatic restart after failure; BindsTo stops exporter if it dies. Automatic startup only when all safety checks pass; boot timing or missing dashboard fails closed and may require owner rearm. This deliberately favors safety over automatic recovery.

## External outages

Windows/WSL/Prometheus loss never triggers a rover recovery or restart. Exporter continues its bounded cache polling if local safety remains valid; no growing buffer, no commands, no network repair. Dashboard/source loss yields unavailable metrics/503 and the watchdog stops on safety-data loss. Wi-Fi IP/interface loss stops/binds fail; no automatic Tailscale/mobile/hotspot listener substitution. The existing Wi-Fi/mobile/hotspot priority is untouched.

## Proposed commands, NOT executable deployment approval

After final scripts/units are implemented, reviewed, hashed, backed up and installed using install -o root -g root with the modes above:

    sudo systemd-analyze verify /etc/systemd/system/atlas-monitoring-{firewall,watchdog,exporter}.service
    sudo systemctl daemon-reload
    sudo systemctl enable atlas-monitoring-exporter.service
    sudo systemctl start atlas-monitoring-exporter.service

Only monitoring dependencies may start. Never restart production services. Before enable/start, verify fresh resource/stop/command/encoder gates and both firewall backends against backup. Verify the actual nft JSON expressions and ordering, not only text existence, before opening the listener.

Rollback order (after verifying these names refer to this deployment):

    sudo systemctl disable --now atlas-monitoring-exporter.service
    sudo systemctl stop atlas-monitoring-watchdog.service
    sudo systemctl show atlas-monitoring-exporter.service -p MainPID -p ActiveState
    sudo ss -H -ltn 'sport = :9118'

Only if PID is zero and no listener exists:

    sudo systemctl stop atlas-monitoring-firewall.service
    sudo nft delete table inet atlas_monitor

If shutdown cannot be proved, KEEP firewall protection and report failure. Restore only backed-up monitoring files; daemon-reload; compare normalized legacy/nft rules and protected service identities. Never flush the global ruleset or restore a stale complete Tailscale snapshot. Retain evidence/data. Failed installation before listener starts removes only a newly owned table, never preexisting unknown state.

## Windows/WSL persistence

Verified Docker/containerd enabled; both containers unless-stopped; two named data volumes preserve Prometheus/Grafana state. Configuration and password live under /opt/atlas-monitoring. Localhost ports and 512 MiB/container caps preserved. Actual Windows reboot recovery NOT tested. A hidden wsl sleep process currently keeps Ubuntu running but is not login/reboot persistent.

Proposed Windows logon task ATLAS-Monitoring-WSL, current user's interactive token, no stored password, action `wsl.exe -d Ubuntu-22.04 -- sleep infinity`, unlimited task execution duration, three task restart attempts spaced one minute. Docker systemd then restores the containers. Login-dependent, not a pre-login service; sleep interrupts monitoring. Do not change Windows power/sleep settings or unrelated WSL distributions. Proposed rollback: disable/unregister only that task and stop its verified keep-alive PID, preserving Docker volumes. No task created yet. Do not use wsl --shutdown (affects other distributions).

## Focused validation and measured limits

Completed: exact exporter hash check; isolated PC network-namespace native nft syntax/load/delete test PASS, with unrelated table preserved. Test did not touch PC host or Jetson firewall. This validates rule installation/rollback syntax, not Jetson packet flow or reboot persistence.

Remaining before final deployment request: implement and simulate verifier/watchdog/latch; fake-unit startup dependency, watchdog crash, restart saturation and stop-order tests; isolated allowed/denied IPv4/IPv6 TCP tests alongside legacy Tailscale-shaped ACCEPT rules; hardening compatibility; service unit static validation. Then approved stationary live trial comparing 60-second baseline, 5-minute operation, 60-second post-stop with one-second resource/safety samples, exporter CPU/RSS, telemetry ages, all protected PIDs/restart counts, authenticated Grafana query and firewall rollback. Do not average away threshold failures. A separately approved controlled reboot and Windows login test is needed to claim persistence. No physical movement tests needed.

Approval sequence: reviewed complete package -> optional monitoring-only installation/activation -> separately approved reboot/reconnect recovery validation. This document is a concrete design, not a claim that the unimplemented supervisor or full persistent deployment is tested.
