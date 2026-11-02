# Monitoring reconnect review — 2026-11-02

Repository correction PASS; live recovery BLOCKED. No latch, firewall, service,
controller or dashboard was modified during this review.

## Actual outage, approximately 09:54 IST

Jetson firewall failed exit78; watchdog/exporter inactive, all PID0/restarts0;
no TCP9118 listener. Prometheus target is down with connection refused and still
scrapes every15s (timeout3s). Windows Grafana/Prometheus containers are up two days,
bound to localhost. Actual authenticated browser: Health Monitor DOWN, last update
and CPU UNAVAILABLE; Pulse View reports Missing/stale source evidence. No live
pulses or live metrics acceptance. Datasource requests reach Prometheus; missing
Jetson input is the blocker, not proof of a rendering failure.

Latest owner-authenticated retained evidence (09:43) has FAULT SHA256
fc5479c96fd42ee003a565b0ccb7e63caaf9d29c43a383eff5291a3c938302fd.
It records watchdog encoder movement, M2 -126 to -127, zero commands/speed and
latched E-STOP. Physical movement versus jitter remains UNKNOWN. Later firewall
startup events say fault latched; owner review required. Root-only latch contents
were not re-read through unprivileged SSH. No password was requested/stored.

The guard checks loopback dashboard safety data, local resources and firewall.
There is no remote Windows/Prometheus/internet availability check. Local safety
API loss does latch deliberately because independent safety evidence is missing;
this must not be reclassified as harmless WAN loss. No evidence identifies an
ordinary connectivity outage as the cause of the retained rejection.

## Minimal confirmed startup correction

A separate failure path exists when starting the exporter before its fixed LAN
address is assigned. Existing bind raises EADDRNOTAVAIL; bounded systemd attempts
can then exhaust. Reproduced offline on Linux using absent TEST-NET address
192.0.2.200: ordinary bind errno99; per-socket IP_FREEBIND binds only that address.
New optional --freebind retains the configured explicit private IPv4; no wildcard,
route, sysctl, firewall or allowed-source change. Default behavior remains unchanged.
No units or guard hash pins updated yet; this candidate cannot silently replace
the reviewed installed exporter. Bind failure closes the socket before collection.

20 focused tests PASS: exporter suite plus absent-address binding and client
disconnection/stale503-to-fresh200 recovery on the same process. Independent review
PASS. Actual Wi-Fi removal/restoration and ARM64 behavior remain PENDING; no outage
was induced. This fix does not clear a safety fault or claim to fix the M2 event.

## Automatic recovery scope

- Prometheus keeps polling after target failure; it needs no recovery transaction
  when the same approved endpoint becomes reachable again.
- Existing Wi-Fi and ATLAS-Cellular-RNDIS profiles have autoconnect=yes. Interface
  wlan wlP1p1s0 is192.168.1.16, cellular usb0 is192.168.225.219. No live failover test.
- Current firewall policy allows only iif wlP1p1s0 / source192.168.1.6 /
  destination192.168.1.16 TCP9118. Cellular/Tailscale scraping is deliberately NOT
  permitted. SIM-only monitoring requires separately reviewed authenticated VPN
  routing and least-privilege firewall policy; never public port forwarding.
- Windows task ATLAS-Monitoring-WSL is Ready, Interactive/Limited, wsl.exe
  -d Ubuntu-22.04 -- sleep infinity; three retries one minute apart, no execution
  time limit. Docker is enabled in WSL; containers restart unless-stopped.
  Startup is at user logon, not before login. Reboot and prolonged WSL failure
  recovery remain PENDING; restart exhaustion is not magically self-healing.
- A safety latch intentionally requires owner review. It is never auto-cleared.

## Required approval / rollback

Current-incident recovery binding remains required: old recover_once.py still pins
an earlier latch/attempt. Bounded fault-events list support was corrected separately
in3c50052. Do not run the old recovery command. No new recovery archive issued here.
Shortest operational route: bind existing transaction to current reviewed evidence,
archive/verify first, fresh safety admission, then request explicit approval for
one monitoring-only rearm and300s validation. Preserve CPU<75/RAM<80/temp<70, all
rover controls and first-fault evidence. Success requires fresh Prometheus metrics,
Grafana and real positive-rate Pulse View evidence. Failure uses existing cleanup.

The optional freebind candidate is a separate deployment: exact exporter/guard
hash update and ExecStart flag require reviewed installation approval. Back up
exact bytes; stop only monitoring under existing cleanup before changing these
files. Roll back exact exporter, guard and unit bytes on failure. No such actions
are authorized or performed by this report. Do not change firewall source policy
as part of this correction.

Windows remains optional monitoring only. No mapping/navigation dependency added.
