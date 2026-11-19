# WSL deployment preparation — 2026-10-30

PREPARED ONLY. No monitoring installation or rover changes.

Verified Ubuntu-22.04 is WSL2, Ubuntu 22.04.5, with systemd and default user root. Inspection started the previously stopped Ubuntu distribution. Internal IP: 172.31.250.86; gateway: 172.31.240.1. Windows Wi-Fi: 192.168.1.6. Ubuntu successfully fetched ATLAS 192.168.1.16:8088 (HTTP 200).

Docker and Podman executables are absent; monitoring services are not active. Ports 3000/9090 are free inside Ubuntu. About 945 GiB is available inside the dynamic WSL filesystem (not guaranteed Windows capacity). Shared VM RAM: 15,879 MiB total, 685 MiB used. TimeMachine-MY_MAC_BACKUP is unrelated and must remain untouched.

## Prepared sequence, not executed

1. Recheck addresses, Windows free disk, existing package dependencies and port availability. Back up existing Ubuntu configuration.
2. With installation approval, install Docker Engine and Compose from Docker's signed Ubuntu apt repository. Review apt changes before executing. This starts a PC-side daemon and adds container networking; no Jetson or Windows restart is planned. Do not remove unrelated packages or expose the Docker API.
3. Stage the reviewed PR #13 monitoring directory under /opt/atlas-monitoring on the native Linux filesystem. Record SHA256 hashes. Configure targets.json as `[{"targets":["192.168.1.16:9118"],"labels":{"robot":"atlas"}}]` after address verification. Generate a local Grafana secret, mode 0600, never committed; verify container readability.
4. Validate Compose configuration, Prometheus config/rules and alerts.test.yml. Record image digests and review image security before launch. Preserve loopback-only ports 3000/9090, 512 MiB limits per container and 7-day/1-GB Prometheus retention.
5. Separately authorize the optional Jetson exporter/firewall trial. Require fresh E-STOP latched, zero commands, LIVE telemetry and unchanged CPU 75%, RAM 80%, temperature below 70 C checks. No critical service restart is needed.
6. Verify the source address actually seen by Jetson before allowing TCP 9118. WSL NAT is expected to use Windows 192.168.1.6, not internal 172.31.250.86; this is not yet measured. Preserve existing firewall policy and unrelated rules. A host IP restriction does not identify a single WSL distribution.
7. Start only the optional monitoring stack and bounded five-minute exporter trial. Validate target UP, fresh metrics, missing-source semantics, authenticated Grafana rendering, resource impact and unchanged rover service PIDs. Stop optional monitoring on a safety/resource failure. No firmware, cameras or movement.
8. Verify Windows access through localhost:3000. No LAN port forwarding or WSL network-mode change is planned. WSL/PC sleep interrupts monitoring; continuous/autostart operation needs separate review.

## Rollback and pending gates

Stop only the optional exporter and monitoring containers; preserve data volumes. Remove only the exact firewall rule introduced by this deployment and restore staged configuration backups. Leave unrelated Docker/WSL workloads untouched.

Pending: owner approval for PC Docker installation/stack launch and separate Jetson optional exporter/firewall trial; actual NAT source verification; Docker runtime and secret-file access; Grafana rendering/end-to-end scrape validation. No PR merge required. Candidate: aa76fbdaa373ecbcde78dcfb709292cc33722b88.

Official references: https://docs.docker.com/engine/install/ubuntu/ and https://learn.microsoft.com/en-us/windows/wsl/networking
