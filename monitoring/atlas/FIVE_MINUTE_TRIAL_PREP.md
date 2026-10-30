# ATLAS 5-minute exporter trial — PREPARED, NOT STARTED

Status: awaiting a **separate explicit START GO**. No live firewall or exporter changes are authorized by this runbook.

## Preconditions, checked immediately before START

- E-STOP remains latched, commissioning disarmed, manual-only. No movement test.
- Fresh 5-sample evidence: commanded linear/angular speed=0, motor speeds=0, all 4 encoders stationary; MCU telemetry live; CPU <75%, RAM <80%, measured max temperature <70°C.
- Never classify CV0-CV2 unreadable thermal sensors as 0°C.
- Verify exporter file hash, Python syntax, metrics content/labels and no write/control paths. Confirm port 9118 unused.
- Identify **actual** Jetson LAN IPv4, Ubuntu VM source IPv4, network interface, firewall backend, existing INPUT policy and rules; preserve a verified rollback snapshot.
- Verify the dashboard endpoints and the safety sampling source are independent of the exporter being tested. Use one monitoring observer that continues even when exporter fails.
- Confirm no conflicting ATLAS watchdog/service-management workflow could relaunch the exporter or reclaim port 9118.
- Authentication is entered ONLY in the interactive local Jetson terminal; never in GitHub, scripts or chat.

## Trial ordering (only after separate START GO)

1. Start an independent local 300-second deadline/watchdog first. Its timeout and fault handlers must execute cleanup even if the trial shell exits. Include an operator manual-stop path.
2. Install a **temporary source-restricted firewall rule** for VM IPv4 → Jetson LAN IPv4 TCP/9118. Verify exact rules/order without modifying Tailscale, SSH, dashboard, forwarding or NAT. If effective restriction cannot be proven, **ABORT before starting exporter**. A permissive ACCEPT rule alone is not an access restriction.
3. Launch a one-off exporter as an isolated foreground or tracked child process (no enable/restart of rover services).
4. Check `/metrics` from VM, verify timestamp progression and missing-data handling, plus confirm unauthorized LAN peer cannot reach 9118 when safely testable.
5. Continue independent safety checks at <=1-second sampling cadence. Stop at FIRST: E-STOP released, command nonzero, wheel encoder movement, stale/lost MCU telemetry, CPU >=75%, RAM >=80%, measured thermal max >=70°C, safety observer stalled, critical process lost, exporter exits unexpectedly, or expiration.
6. Stop exporter process first; verify PID/port 9118 is gone (including children), then remove **only the exact trial firewall rule(s)**. Verify original firewall state is restored and Tailscale/SSH/dashboard are unchanged. No automatic re-run.
7. Record start/end wall-clock and monotonic timestamps, failure reason, CPU/RAM/temp distributions, safety samples, camera/ROS response evidence, and 15-second scrape gaps. Never claim overhead without comparable pre/post baseline.

## Offline checks and artifacts

Before any START GO, run: `python3 -m py_compile project_atlas/scripts/atlas_health_exporter.py`; static checks of exporter; inspect current firewall; and validate rollback procedures. The firewall operation must be constructed from verified local addresses/rules, not copied from a guessed template.

Record for the decision: Jetson IPv4, VM IPv4, firewall backend, a read-only current firewall rule snapshot, exporter path and sha256, independent observer command/source, and local administrator access availability.

## Abort and rollback

If the timer or observer fails, treat trial as invalid. Independently stop only the exporter PID/process group, verify TCP/9118 closed, then remove only the tagged temporary rule(s); verify prior firewall state and rover operations. Preserve logs locally; never upload private telemetry. If cleanup cannot be verified, leave START blocked until an operator inspects the system.

**This is a preparation document. It neither executes the trial nor authorizes any live changes.**
