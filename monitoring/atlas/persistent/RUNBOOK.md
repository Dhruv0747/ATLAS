# Persistent monitoring candidate — preparation only

**Superseded candidate notice:** the 852feb9 activation was rolled back after a timestamp precision defect. See [../TIMESTAMP_FIX.md](../TIMESTAMP_FIX.md) for the new offline-only exporter hash/package and test results. Do not execute the historical activation command or old hash below; a newly approved single-use activation command is required. Firewall/safety design below is unchanged.

No Jetson installation, activation, firewall change or service restart was performed for this implementation. No Windows startup task was registered. This runbook supersedes the implementation-pending sections of PLAN.md; that document retains the design rationale.

## Reviewed payload and ordering

The exporter is unchanged from the successful five-minute trial: SHA256 `caa6ebe571e4ae57aa2be5be9bc80bea00252c6fb9c2897387edc762caf8b0f9`.

The trial file used CRLF while Git stores its canonical source as LF. The package builder reconstructs the exact CRLF trial bytes when necessary and rejects any result not matching the trial SHA. Persistent helper files are pinned to LF with .gitattributes so source manifests remain reproducible across checkouts.

New files are guard.py, atlas-monitor.nft, three systemd units, prepare_package.py and prepare-windows-task.ps1. The exporter unit is rendered with the actual jetson UID, never an assumed production UID. SHA256SUMS in this directory identifies source files. The generated package has its own manifest; record its SHA256 after rendering and compare independently before installation.

Firewall oneshot -> watchdog Type=notify readiness after two fresh samples -> exporter privileged ExecCondition repeats integrity and safety -> unprivileged listener. Exact nft JSON expressions, table, priority, family and rule order are checked, not merely a chain name. Startup rejects an existing listener or an unowned table. Only inet atlas_monitor is managed; generic nftables.service and global ruleset restores are forbidden.

The watchdog polls every one second. Each observation has a two-second absolute deadline, with bounded nft subprocesses and HTTP requests. It requires latched stop, manual-only, commissioning disabled, zero commands/speed, unchanged four encoder counts, LIVE MCU and fresh sensor data. Missing or malformed fields reject. CPU >75%, RAM >80% and any trustworthy temperature >=70 C reject. Unavailable known CV thermal zones are skipped; absence of trustworthy measurements rejects.

Faults persist in root-only /var/lib/atlas-monitoring/FAULT.json; unclean observer exits retain observer-active.json. No automatic safety rearm. Exporter process failures have RestartSec=30 and at most three starts per 600 seconds; watchdog has no restart. Fault cleanup stops only the exporter and RETAINS firewall protection. Watchdog death is coupled through BindsTo; a hung watchdog is killed by systemd after five seconds. Exporter stop deadline is three seconds. Thus detection/shutdown is bounded in normal scheduling (up to approximately six seconds for observation timeout, eight for watchdog stall), not a hard real-time guarantee. External root deletion of the firewall can create a finite exposure interval before detection; no claim of atomic firewall-removal/listener-shutdown is made.

Exporter limits: CPUQuota=10% (one core), MemoryMax=64M, TasksMax=32, Nice=10, read-only system/home, no new privileges. Root watchdog/firewall helpers have only CAP_NET_ADMIN in their capability bounding sets, strict filesystem protection and 64M/16-task limits. Watchdog is not CPU-throttled because that would delay safety detection. Its actual Jetson overhead is PENDING. Services contain no ROS participants, serial access, motor commands or rover restart operations.

## Exact preparation commands (PC only)

From the repository root in Ubuntu:

```sh
python3 -m pytest -q project_atlas/tests/test_monitoring_persistent.py
sudo unshare --net python3 monitoring/atlas/persistent/test_packet_paths.py
sudo python3 monitoring/atlas/persistent/test_lifecycle.py
# UID 1000 below is an isolated rendering example, NOT a target identity assertion.
python3 monitoring/atlas/persistent/prepare_package.py --uid 1000 --output /tmp/atlas-monitoring-review
systemd-analyze verify /tmp/atlas-monitoring-review/*.service
```

The packet test creates disposable network namespaces, never modifies host firewall rules, and tests legacy Tailscale-shaped ACCEPT rules alongside the nft restriction. The lifecycle test creates uniquely named atlas-prep-* fake units under /run on the PC, then removes only those units. It uses accelerated test timers; production timers are checked separately. Do not run these tests on Jetson during deployment.

Windows preparation, without activation:

```powershell
.\monitoring\atlas\persistent\prepare-windows-task.ps1 -OutputPath "$env:TEMP\ATLAS-Monitoring-WSL.xml"
```

## Activation approval gate — NOT authorized yet

Request approval for installing this exact hashed package, system-level daemon-reload, and enabling/starting ONLY atlas-monitoring-exporter and its two monitoring dependencies. Administrator authentication stays in the local Jetson terminal. A separate Windows approval covers registration of the prepared logon task. Reboot testing needs separate approval.

Before approval execution: recheck package SHA, actual `id -u jetson`, stable addresses/interface, source observed by Jetson, no 9118 listener, no conflicting atlas_monitor table, exact baseline firewall state, and protected service PIDs/restart counts. Use fresh read-only dashboard/resource evidence for E-STOP/manual/commission/zero commands, stationary encoder counts, LIVE telemetry, CPU <=75%, RAM <=80%, temperature <70 C. Missing data is NO-GO. Confirm user-systemd bus exists at the rendered UID. Confirm native nft version/JSON compatibility and all monitoring file destinations absent; if preexisting files differ, stop for review rather than overwrite.

Render on PC with the freshly verified UID and copy the package to a new staging directory. Record source commit, package-manifest SHA and all file hashes. The following commands are for future approved execution ONLY, from that verified staging directory:

```sh
sha256sum -c SHA256SUMS
test "$(id -u jetson)" = "$(cat TARGET_UID)"
# Save root-only baseline and verify backup checksums before installing.
sudo test ! -e /var/lib/atlas-monitoring-backup
sudo install -d -m 0700 /var/lib/atlas-monitoring-backup
sudo sh -c 'umask 077; iptables-save > /var/lib/atlas-monitoring-backup/iptables.before; ip6tables-save > /var/lib/atlas-monitoring-backup/ip6tables.before; nft -j list ruleset > /var/lib/atlas-monitoring-backup/nft.before'
sudo sh -c 'cd /var/lib/atlas-monitoring-backup && sha256sum *.before > SHA256SUMS && sha256sum -c SHA256SUMS'
sudo install -d -o root -g root -m 0755 /opt/atlas-monitoring-exporter /etc/atlas-monitoring /usr/local/libexec
sudo install -o root -g root -m 0644 atlas_health_exporter.py /opt/atlas-monitoring-exporter/atlas_health_exporter.py
sudo install -o root -g root -m 0644 guard.py /usr/local/libexec/atlas-monitoring-guard.py
sudo install -o root -g root -m 0644 atlas-monitor.nft /etc/atlas-monitoring/atlas-monitor.nft
sudo install -o root -g root -m 0644 atlas-monitoring-*.service /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/atlas-monitoring-{firewall,watchdog,exporter}.service
# Compare every installed file to its staged counterpart (cmp); stop on any mismatch.
cmp atlas_health_exporter.py /opt/atlas-monitoring-exporter/atlas_health_exporter.py
cmp guard.py /usr/local/libexec/atlas-monitoring-guard.py
cmp atlas-monitor.nft /etc/atlas-monitoring/atlas-monitor.nft
for f in atlas-monitoring-*.service; do cmp "$f" "/etc/systemd/system/$f" || exit 1; done
sudo systemctl daemon-reload
sudo systemctl enable atlas-monitoring-exporter.service
sudo systemctl start atlas-monitoring-exporter.service
```

Execute as supervised steps with stop-on-error, not blind paste of the whole runbook. No `enable --now` or retry after failure. Firewall and watchdog dependencies must pass before any listen. Confirm `nft -j list table inet atlas_monitor`, unit states, port binding, Prometheus target, actual metrics and Grafana freshness. Compare 60-second parked baseline, five-minute operation and post-stop measurements using existing bounded diagnostics: per-process CPU/RSS plus whole-system CPU/RAM/temperature, API ages, encoders, protected PIDs/restarts. Do not average away a failing sample. Do not start additional camera/ROS tools to validate monitoring.

## Rollback and fault handling

After approved activation, the bounded helper provides ordered rollback:

```sh
sudo python3 -I -B /usr/local/libexec/atlas-monitoring-guard.py rollback
sudo systemctl show atlas-monitoring-exporter.service -p MainPID -p ActiveState
sudo ss -H -ltn 'sport = :9118'
sudo nft list tables
```

It disables/stops only exporter, stops watchdog, verifies PID zero/no listener, then removes only the exactly matching owned table. If stop times out or a listener/table is ambiguous, protection stays and rollback FAILS for operator review. Do not rerun automatically or flush rules. Independent fallback: `sudo systemctl disable --now atlas-monitoring-exporter.service`, then `sudo systemctl stop atlas-monitoring-watchdog.service`; prove PID zero/no listener; stop atlas-monitoring-firewall; inspect exact owned table before `sudo nft delete table inet atlas_monitor`. Never delete protection before listener shutdown is verified.

Retain fault/state/journal evidence. Remove only newly installed monitoring files after verifying their hashes match this package, then daemon-reload. Compare original rules semantically, excluding counters, and protected PIDs/restarts. Do not restore a stale complete Tailscale ruleset. No preexisting monitoring files may be overwritten under this first-install procedure. Clearing FAULT.json/observer-active.json requires a reviewed root cause and separate manual rearm; do not clear at boot.

## Windows/WSL availability

Existing Docker/containerd enabled state, container unless-stopped policy, localhost bindings, named volumes and 512MiB limits are retained. Future separately approved logon activation:

```powershell
Register-ScheduledTask -TaskName ATLAS-Monitoring-WSL -Xml (Get-Content "$env:TEMP\ATLAS-Monitoring-WSL.xml" -Raw)
# Do not start now; future approved logon or explicit start is separate.
# Rollback registration only:
Disable-ScheduledTask -TaskName ATLAS-Monitoring-WSL
Unregister-ScheduledTask -TaskName ATLAS-Monitoring-WSL -Confirm:$false
```

The task uses current user's interactive token (no stored password), starts only Ubuntu-22.04 keepalive, and allows three one-minute-spaced retries. Login is required; it is not pre-login availability. If already running at rollback, identify and terminate ONLY that task's keepalive process, never `wsl --shutdown`; preserve containers/volumes. Windows sleep/network/Prometheus outages produce monitoring gaps, never robot recovery or control changes. Jetson remains bounded/read-only while local safety is valid; missing local safety data stops it. Source-IP changes deny access; no automatic widening or fallback listener.

## Pending live acceptance

Jetson native hardened startup, actual watchdog CPU overhead, allowed/denied real LAN clients, protected service identity comparison, and post-reboot ordering remain PENDING. Windows reboot/logon and volume/data recovery remain PENDING. Controlled activation may be approved after reviewing this package; persistent reliability must not be declared until those tests pass. No PR merge is part of this procedure.
