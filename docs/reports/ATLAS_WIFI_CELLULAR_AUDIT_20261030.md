# Wi-Fi / SIM / optional cloud — read-only findings

Observed 30 October 2026 around 22:05 IST. No route/firewall/network-service change,
modem AT command, SIM reset, manual probe or induced outage was performed.

## Actual state

* SIMCOM SIM8230G, power on, registered at home on Airtel LTE, packet service
  attached. ModemManager recent signal quality 58%; no unlock required reported.
  SIM identifiers were deliberately not collected. Subscription/data-plan balance
  and APN credentials were not read or verified.
* Actual data path is USB RNDIS `usb0`, address 192.168.225.231, gateway
  192.168.225.1, connected NM profile `ATLAS-Cellular-RNDIS`, IPv4 metric 600,
  metered=yes, IPv6 disabled. GSM ttyUSB6 showing disconnected is NOT sufficient
  to declare the RNDIS data path down.
* Wi-Fi `wlP1p1s0`, 192.168.1.16, gateway 192.168.1.1, IPv4 metric 50;
  IPv6 Wi-Fi default also present. Wi-Fi autoconnect priority 100, RNDIS 90.
* Existing service `atlas-network-fallback` active PID 1041, NRestarts=0.
  NetworkManager, ModemManager and tailscaled active.
* Existing local status reported WIFI selected, no failures, rescue AP inactive.
  Its authenticated HTTPS Wi-Fi probe passed (~144 ms); cached cellular probe
  passed (~554 ms, 26.4 seconds old at observation). This is existing service
  evidence of Internet reachability, not a newly performed failover test.
* `/cellular/connected` was false while registration was home and RNDIS Internet
  probe passed. Treat this as differing modem-bearer vs actual IP-path semantics;
  do not present that single Boolean as authoritative Internet availability.

## Existing functionality; do not rebuild it

Live `/usr/local/lib/atlas-network/atlas_network_fallback.py` matches repository
source after line-ending normalization. It already implements Wi-Fi first, mobile
data second, local rescue hotspot last. Interface-bound HTTPS probes avoid DNS
dependency, check TLS and use two endpoints. Main loop sleeps five seconds after
work; timings are therefore approximate, not a strict five-second sample period.

Three failed Wi-Fi samples plus passing cellular evidence select mobile data;
three good Wi-Fi samples restore Wi-Fi. Six both-failed samples request rescue AP.
Cellular standby probe approximately every 30 seconds; active/failing paths more
frequent. Owned IPv4 default uses protocol 199/metric 9. Cellular selection adds an
owned IPv6 unreachable default to avoid a broken Wi-Fi IPv6 path and assigns its
DNS routing domain. Cleanup removes only owned defaults/catch-all DNS routing.

Single-radio rescue AP can replace the Wi-Fi association. Wi-Fi retry waits 180
seconds and avoids disconnecting an associated rescue operator. Hotspot is local
access, not a third Internet provider. Do not change these live policies casually.

Pure offline Policy assertions PASS: short loss does not switch; third failure
selects cellular; third recovery selects Wi-Fi; sixth dual failure requests AP;
AP plus working cellular retains cellular. No Manager/network mutation methods
were invoked. DNS, IPv6 routing and real outage recovery remain untested here.

## Proposed architecture and controls

Reuse this manager and NM profiles. Keep ROS, sensor fusion, mapping databases,
navigation and safety local. No cloud dependency may gate E-STOP, controllers,
localization or the mapping supervisor. Current standalone mapping is still an
unverified candidate; network-independent physical mapping is not proven here.

Use Tailscale private access with explicit user/device ACLs; no router port
forwarding, public dashboard/ROS/camera listeners or Funnel activation. Current
public exposure/firewall state was not independently root-audited in this task.
Keep Grafana monitoring optional; home-Windows scrape availability may disappear
on cellular without affecting local guards. Do not broaden its firewall allowlist.

Notifications and remote AI: opt-in, bounded local queue, small redacted health
summaries only by default. Disable image/video/map uploads on cellular by default.
Encrypted backups: local encryption before upload, owner-held keys, Wi-Fi-only
default, explicit retention/deletion and no biometric gallery upload. Cloud loss
should suspend upload/retry with backoff, not stop local robot services.

Proposed data controls (NOT installed): operator-selected monthly/daily budgets,
persistent per-interface byte accounting across reboot/reset, warnings at 80/95%,
pause optional cloud transfers at budget exhaustion. Metered=yes is advisory,
not an enforced quota. Include Tailscale and existing HTTPS probes in accounting;
do not estimate billed usage from HTTP body size. Budget must not disable local
safety or abruptly revoke an operator's emergency access.

## GO / NO-GO

GO for further isolated policy/route/DNS tests. NO-GO for a live induced failover
now: only policy logic was exercised, no native namespace route/DNS/IPv6 acceptance,
operator recovery path or interruption recovery test was completed. Existing
automatic failover is already active; no installation needed to turn it on.

Next controlled test proposal, requiring separate owner approval: first prepare
fake Wi-Fi/cellular gateways in a dedicated network namespace (no real NICs),
validate exact route/DNS mutations and cleanup. Then one supervised stationary
outage/failback window with local owner/terminal access, fresh stopped safety
checks, preserved profile/route/DNS snapshots, strictly scoped fault injection,
bounded deadline and independent restoration. No service/robot restart, controller
change or camera activation. Abort on telemetry/safety loss; no automatic retry.
