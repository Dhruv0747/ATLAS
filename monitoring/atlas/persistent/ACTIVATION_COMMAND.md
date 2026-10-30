# Approved activation command preparation — 2026-10-30

The owner approved one persistent activation of runtime commit 852feb9. Runtime package SHA256SUMS remains `9161805480525237f4a75f4a9763b997b3c893a57a1641caf4e5f4d0d0937318`; all seven members verified again on Jetson. No activation has run at this checkpoint.

The local-sudo orchestrator `activate_once.py` was staged in `/home/jetson/project-atlas-migration/monitoring-persistent-852feb9/`. Its SHA256 is `248dc495530d331f38753c7a53995b8666c38f906b216075c120aaefb134b0ff`. It does not alter the reviewed runtime guard/exporter/units. Four simulated transaction tests passed: success, baseline safety rejection, active safety rejection and protected-service-change rollback. Repeated invocation refuses because the root evidence directory is exclusive.

Workflow: verify exact package/UID and absent installed destinations; preserve both firewall baselines and protected service identities; sample stationary safety/resources for 60 seconds; install only reviewed files; verify units/hashes; arm an independent 480-second rollback timer; install/verify firewall; start monitoring only; observe five minutes; enable exporter and cancel expiry only on acceptance. Resource thresholds and missing-data rejection remain unchanged. On failure stop/remove only new monitoring deployment, retain evidence; ambiguous rollback retains protection and reports failure. No critical restart or rover command exists in the wrapper.

Actual CPU/RAM/temperature overhead and Grafana live data are PENDING execution. Root evidence will be `/var/lib/atlas-monitoring-activation-20261030/`, with samples, service/firewall snapshots, result and checksums. The wrapper reports Grafana verification pending for separate PC observation; it never treats local process startup as proof of scraping or dashboard freshness. Reboot persistence is unverified.

Administrator authentication is required in the local Jetson terminal only. Owner must not rerun after failure. A persistent PASS leaves exporter enabled/active; monitoring automatically stops on its stationary safety gate. Windows startup tasks are not activated by this command.
