# ATLAS automatic network fallback — 2026-09-15

## Operator use

1. Normal home Wi-Fi: use the existing LAN/Tailscale dashboard.
2. Wi-Fi Internet fails (including a router with no upstream Internet): after
   three failed cycles, select verified SIM8230G Internet. No modem reset occurs.
3. Both Internet links fail for six cycles: the radio becomes **ATLAS-Rescue**.
   Join it with the separately supplied password and open **http://10.42.0.1:8088/**.
   A captive portal directs supported phones' network-login view to that dashboard.
   Other phones show **Sign in to network**, which must be tapped. If no prompt
   appears, open **http://10.42.0.1/** or the direct dashboard address manually.
   This AP provides **local access only**, not Internet, upstream DNS forwarding or NAT.
   A phone's “no Internet” warning is expected; stay connected for local access.

The WPA2 password is in the root-protected NetworkManager profile, not Git.
The current user-selected password is simple; change it before sharing access
with untrusted users. A software dashboard stop still depends on a working link;
the rover's existing local watchdogs and emergency-stop mechanisms are unchanged.

## Switching and recovery

- Probe Wi-Fi about every five seconds; probe standby cellular about every
  thirty seconds, and every cycle once Wi-Fi fails or cellular is active.
- Real HTTPS requests are socket-bound to each interface and use numeric
  addresses with certificate validation (Cloudflare, then Google fallback).
  No default DNS dependency, captive-portal redirects, speed test or bulk download.
- Failover normally takes about 15–35 seconds; both-link fallback roughly
  30–65 seconds depending on network timeouts. These are not motion watchdog times.
- Three successful Wi-Fi cycles restore its preference. Probe state is not a
  guarantee that every Internet service is reachable.
- Own temporary routes use protocol 199 / metric 9. DHCP/NetworkManager defaults
  are retained. Cellular selection also handles DNS routing and suppresses the
  unusable Wi-Fi IPv6 default with a reversible owned unreachable route.
- The installed RTL8822CE reports AP support but no concurrent interface
  combinations. While the AP has clients, preserve it. With no clients, retry
  saved Wi-Fi every three minutes (up to roughly 25 seconds of AP interruption).
  If Wi-Fi still lacks Internet, restore the local AP.
- If cellular returns while a rescue client is connected, the Jetson can use it
  without dropping that local client. The rescue AP remains local-only.

## Deployment

- Root-owned agent: `/usr/local/lib/atlas-network/atlas_network_fallback.py`.
- Boot-enabled unit: `atlas-network-fallback.service`.
- On-demand AP DHCP unit: `atlas-hotspot-dhcp.service` (not independently boot enabled).
- On-demand captive portal: `atlas-hotspot-portal.service`, bound only to
  10.42.0.1:80 and stopped with the DHCP service. Captive DNS answers locally;
  Android/Apple/Windows HTTP probes receive a 302 to the existing port-8088 page.
  No HTTPS interception or certificate bypass; no new motor/control API.
- Non-secret configuration: `/etc/atlas-network.json` (root-only).
- Read-only public status: `/run/atlas-network/status.json`; the dashboard marks
  it stale after 45 seconds. It has no passwords, commands or control endpoints.
- Sources and supervised test scripts are staged on the Jetson under
  `/home/jetson/project-atlas-migration/network-20260915/`.
- Installation backups: `/var/backups/atlas-network/`.

### SIM8230 DHCP ownership correction

Boot logs showed NetworkManager obtaining a RNDIS lease, followed by
ModemManager claiming `usb0` and NetworkManager removing it/cancelling DHCP.
The address happened to remain usable, but renewal was no longer managed.
`99-atlas-sim8230-rndis-net.rules` excludes **only** the SIMCOM RNDIS network port
from ModemManager's candidate inventory; serial AT and GNSS ports are unchanged. A saved
`ATLAS-Cellular-RNDIS` Ethernet profile owns DHCP with lower priority than Wi-Fi.
One supervised NetworkManager inventory restart was needed on this installed
1.36 version; a timed independent Wi-Fi recovery was in place. The cellular
profile activated and bound HTTPS passed. No USB power cycle or modem firmware
command was used. The optional setup script is
`configure_sim8230_rndis_root.sh`; it is an installation operation, not a boot task.

Install from the provided scripts/services/config directory layout with
`sudo bash scripts/install_network_fallback_root.sh`. Enter the hotspot password
at its local prompt. Use `--existing-profile` only when ATLAS-Rescue is already
configured. Never run the supervised handover test automatically at boot.

## Test evidence

- 12 mocked Python checks: preference/hysteresis, both-links-failed AP decision,
  preservation of associated AP clients, owned-route-only cleanup, no guessed
  gateway, probe payload validation and secondary provider success.
- Python compilation and dashboard JS checks passed.
- Four portal tests passed: common probe URLs, fixed redirect target, HEAD, and
  rejection of POST/control requests. Real phone UI behavior is OS-dependent.
- Supervised live test on September 15: unbound HTTPS used the cellular default
  route and DNS successfully; AP reported `type AP`, SSID ATLAS-Rescue and
  10.42.0.1/24; DHCP listened on UDP 67; dashboard returned HTTP 200 at the AP IP.
- Saved Wi-Fi restored afterward and the automatic service resumed.
- Final portal test at 11:56 IST passed captive DNS resolution and 302 redirects
  for Android, Apple and Windows-style probe paths. Wi-Fi restored at 11:56:38.
  ModemManager now lists only its serial ports; the RNDIS profile stayed active
  beyond modem rediscovery. Candidate exclusion must be ordered after
  `80-mm-candidate.rules`; a port-ignore tag alone was insufficient on this system.
- No motor, steering, mapping or navigation command was issued.
- Not yet verified: a phone obtaining a DHCP lease/using the AP, a full physical
  outage and reboot test, or long-duration roaming. Do not describe these as passed.

For driving, prefer the full browser and keep the physical emergency stop ready.
Some captive-login mini-browsers close or suspend on their own. Auto-opening the
page must never automatically start motion, mapping or unlock an emergency stop.

## Rollback

From local access or working Wi-Fi, stop/disable `atlas-network-fallback.service`.
Its stop hook removes only its tagged routes and DNS catch-all override. Bring
up the saved home Wi-Fi profile and stop `atlas-hotspot-dhcp.service`. Keep the
AP profile as an optional manual recovery connection, or remove only that named
profile if explicitly retiring it. Original Wi-Fi settings are backed up.

## References

- [NetworkManager profile settings](https://networkmanager.dev/docs/api/1.46.0/nm-settings-nmcli.html)
- [ModemManager port ownership and ignore rules](https://modemmanager.org/docs/modemmanager/port-and-device-detection/)
- [Android captive portal behavior](https://developer.android.com/about/versions/11/features/captive-portal)
- [Apple captive Wi-Fi login behavior](https://support.apple.com/en-lamr/102554)
# Saved Wi-Fi provisioning — September 15 update

Dashboard NETWORK → WI-FI SETUP / SAVED NETWORKS opens `/wifi`.
The page scans nearby SSIDs, accepts WPA/WPA2 Personal credentials or explicitly
selected open networks, and reconnects saved profiles. Credentials are stored in
root-only NetworkManager keyfiles, never returned by the API or placed in Git.
Saved visible networks are considered during empty-hotspot recovery retries.
The most recently verified profile becomes preferred. Existing profiles remain.

Network changes require the operator to stop ATLAS first. A bounded connection
attempt verifies Internet before committing the preferred profile; failure restores
the previous working connection or ATLAS-Rescue. A persisted pending record enables
recovery after service restart. No navigation or motor parameters are changed.

The root helper exposes only status/scan/connect on a local UID-restricted Unix
socket. Browser mutations require a matching allowed Origin and custom header.
The page displays current IP, local hostname and Tailscale dashboard links.
External Wi-Fi does not guarantee automatic browser popups or `.local` resolution;
rescue-AP captive detection remains the automatic dashboard-opening mechanism.
Enterprise authentication and third-party captive-login completion are not supported.

Validation: unit tests, live saved-profile listing, live scan, API/page availability,
and enabled root/user services verified. Connecting a *new* router still needs an
operator-supplied SSID/password and an end-to-end test there. No movement was issued.
