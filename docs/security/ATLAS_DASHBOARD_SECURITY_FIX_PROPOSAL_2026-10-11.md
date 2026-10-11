# ATLAS dashboard: prioritised security and safety fix proposal (2026-10-11)

Status: **proposal only.** None of these changes are implemented, committed to production
code or deployed. Glass UI V2 does not change any of these behaviours. Each item needs its own
approval, its own commit and its own supervised on-device check.

Scope: `project_atlas/scripts/atlas_status_web.py` (port 8088) and the related pages. Line
numbers are from the branch `claude/localization-motion-investigation` at the time of writing.

How the evidence was gathered:
- code reading;
- the offline Playwright harness (`tools/ui_v2/test_ui_v2.py`), which runs both UIs against
  recorded responses and captures every POST without sending it.

No request was sent to ATLAS.

## Priority order

| # | Issue | Risk | Effort | Proposed fix |
|---|---|---|---|---|
| 1 | E-STOP can be overridden by a drive button still held | **Motion after E-STOP** | small (UI + server) | E-STOP cancels local drive repeat and latches the mux |
| 2 | Hard-coded sudo password in the reboot action | credential exposure; unauthenticated reboot | small | remove the action (no UI uses it); rotate the password |
| 3 | Control POSTs authorised by source IP only (no same-origin / CSRF check) | drive / service / mapping commands from any page a LAN or tailnet user visits | medium | require the existing `same_origin()` + `X-Atlas-Wifi` on every state-changing POST |
| 4 | Shutdown rejects `stop` / `e_stop` with 409 | a stop is refused during the shutdown window | small | always accept stop and e_stop; verify zero before poweroff |
| 5 | Unescaped telemetry in `innerHTML`; intercom (:8091) has no HTTP auth | script injection from ROS strings; voice/audio access from the LAN | medium | escape at render; bind intercom to localhost behind Tailscale serve |

---

## 1. E-STOP vs a drive button that is still held (highest priority)

**What happens today (V1 and V2 identical).**
- E-STOP (`#stop`) sends `action=e_stop`.
- The server calls `stop_rover()` (`:1611`), which publishes one zero Twist. Nothing is
  latched (`:1951`).
- The hold-to-drive loop in the browser keeps sending `action=drive` every 120 ms until that
  button gets pointerup, pointercancel, lostpointercapture, window blur or page hidden.
- On a touch screen, an operator can press E-STOP with a second finger while the first is still
  on Forward. The next drive pulse, ≤120 ms later, moves the rover again.

The harness reproduces this in both UIs. See `estop_while_holding` in the test report. It counts
`action=drive` requests sent after `action=e_stop` while the drive button stays pressed.

**Proposed fix (two layers; both are needed).**
1. **Client.** E-STOP first calls the existing `stopDrive()`, clears the repeat timer and
   disables the drive pad until all pointers lift. Then it sends `e_stop`.
2. **Server.** `e_stop` also publishes `/atlas/voice/stop` (`Empty`). This is the same latch the
   commissioning page's LATCH DRIVE STOP already uses (`:385`, `:1859`). The `cmd_vel` mux then
   holds every source at zero until the existing remote release (sticks neutral, hold LB).
   `drive` while latched returns `409 Stop latched` instead of publishing.

Notes:
- Latching changes operator workflow, because release then needs the physical remote. That
  needs an explicit decision.
- If you do not want the latch, the client fix alone removes the reproduced hazard, but not a
  second-browser hazard.

**Tests.**
- Harness: after `e_stop`, zero `action=drive` requests while the button is held.
- Unit test: the server `e_stop` publishes on the latch topic, and `drive` is refused while
  latched.
- On the device, wheels lifted:
  - hold Forward, press E-STOP, confirm the wheels stop and stay stopped;
  - confirm release needs the remote.

**Rollback.** Revert the commit and restart `rover-status-web` (coordinated, rover parked).

## 2. Hard-coded sudo password in `reboot`

`:2004-2006`:

```
elif action == "reboot":
    subprocess.Popen(["bash", "-lc", "sleep 1; echo password | sudo -S reboot"], ...)
```

Problems:
- A literal password string is in the source and in git history.
- The action needs only an allowed source IP: no confirmation, no same-origin check, no stop
  first.
- No page calls it. It was confirmed absent from all V1 and V2 controls by the contract test's
  control inventory.

**Proposed fix.**
1. Delete the `reboot` branch, so requests get `400 unknown action`.
2. If remote reboot is wanted later, model it on `shutdown`:
   - confirmation token;
   - `same_origin()`;
   - a `sudo -n` rule limited to `/sbin/reboot`;
   - stop the rover first.
3. **Rotate the Jetson user's password** if that string is (or was) real. Removing it from the
   source does not remove it from git history. Rewriting history is a separate decision, because
   it affects every clone.

**Tests.** A unit test that `action=reboot` returns 400, and a grep test that no `sudo -S` remains.
**Rollback.** Revert the commit. The password rotation is independent.

## 3. Control POSTs authorised only by source IP

`client_allowed()` (`:1646`) accepts loopback, RFC1918 and 100.64/10 addresses.
`same_origin()` (`atlas_wifi_web.py:8`) is enforced only for commissioning, voice, Wi-Fi and
shutdown.

The form POSTs to `/` have no origin check: drive, camera, AI mode, mapping/Nav2 topics, service
start/stop/restart and reboot. Any web page opened by someone on the same LAN or tailnet could
submit a form to `http://<atlas>:8088/`. The browser sends it because a simple form POST needs
no CORS preflight.

**Proposed fix.**
1. Require `same_origin(self.headers)` for every `POST /`, with one exception: allow `stop` and
   `e_stop` without it (a stop must never be refused).
2. Both UIs must send `X-Atlas-Wifi: 1`:
   - V2 can add it in one place: the `post()` helper and `estop.js`.
   - V1's `post()` needs the same one-line change. This is the only V1 edit in this proposal.
3. Optional, later: a per-session token in a cookie with `SameSite=Strict`.

**Risk of the fix.** Access by raw IP (for example `http://100.87.x.x:8088`) fails the
hostname allowlist in `same_origin()` (`atlas_wifi_web.py:15`). Users who browse by IP would
lose drive control. Either:
- add the known IPs to the allowlist, or
- compare `Origin` to `Host` only and drop the name allowlist.

This must be settled before the change.

**Tests.**
- Unit tests: cross-origin POSTs return 403 for each action; `stop` / `e_stop` still return 200.
- Harness: the V1/V2 contract test still passes with the header added.
- On the device: from a phone, by local name, Tailscale name and Tailscale IP.

**Rollback.** Revert. This is server-only, plus the one-line header change.

## 4. Shutdown blocks stop and e_stop

Once `SHUTDOWN_PENDING` is set (`:2015`), every POST to `/` returns 409 (`:1946`), including
`stop` and `e_stop`. The server does call `stop_rover()` once before the 2 s poweroff delay. A
drive command already queued elsewhere (remote, voice) can still arrive during that window, and
a user pressing E-STOP gets "controls disabled".

**Proposed fix.**
1. Move the `stop` / `e_stop` branches above the `SHUTDOWN_PENDING` check.
2. In `power_off()`:
   - publish zero again;
   - latch (`/atlas/voice/stop`, see #1);
   - check that `/odom` speed is ~0;
   - only then call `shutdown -h now`.
3. If the rover is not stopped within 3 s, abort the shutdown, clear the flag and report it.

**Tests.** Unit tests: `e_stop` returns 200 while shutdown is pending; `power_off` aborts on
non-zero odometry (mocked). No live poweroff test without your separate approval.
**Rollback.** Revert.

## 5. Unescaped telemetry in `innerHTML`; intercom without auth

- **Command center.** It builds many tiles with template strings into `innerHTML` (for example
  `:2478`, the network panel). Values come from ROS topics and system commands, such as Wi-Fi
  SSIDs, the operator name and service messages. An SSID like `<img src=x onerror=…>` within
  radio range would run script in the dashboard.
  - Fix: wrap every interpolated telemetry value in the existing `esc()` helper.
  - V2 generates `command.js` from V1, so the fix belongs in V1's source and flows to V2 on the
    next build.
- **Intercom (`atlas_intercom.py`, :8091).** The installer says to "publish port 8091 only
  through authenticated Tailscale HTTPS".
  - Proposed: bind it to 127.0.0.1 and expose it only through `tailscale serve`.
  - Verify the current binding first. The fix needs a networking change, so it needs separate
    approval under the standing networking rule.

**Tests.** A harness test with a hostile SSID in `wifi.json` and `status.json`: no script
executes. A port scan from a LAN device shows :8091 closed.

## Not changed by Glass UI V2

Glass UI V2 sends the same requests as V1 (see the feature-preservation report). The only new
request path is the dock E-STOP on the Live map and Wi-Fi pages. It is byte-identical to the
command-center E-STOP (`action=e_stop`, form-encoded, POST `/`). None of the five issues above
is fixed or made worse by V2.
