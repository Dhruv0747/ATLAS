# ATLAS permanent USB access and reboot recovery

Date: 21 October 2026. Branch: `agent/sync-developer-20261011`.
Status: **Phase A/B and static Phase C complete; NOT DEPLOYED.**
Baseline commit: e44cdafbc2f2e65632fc2fcfd02b334b9f7d0210.
Result commit: use `git log -1 --format=%H -- ATLAS_PERMANENT_USB_ACCESS_AND_REBOOT_RECOVERY.md` (also supplied in the delivery message).

## 1. Findings and scope

Only Astra has a confirmed missing persistent access grant. Its two temporary
jetson RW ACLs now work, including direct open. Serial devices already have
persistent group-based access; do not apply a blanket USB permission fix.

**Important naming defect:** three serial-number-less CH340 adapters all advertise
the same `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`. That link is ambiguous,
not a trustworthy role identifier. Current open descriptors distinguish motor,
IMU and GPS. Motor service explicitly uses passive protocol discovery; preserve it.

**Radar is NOT a separate USB-UART in this setup.** Running PID1962 has
`ATLAS_RADAR_SOURCE=topic` and no serial descriptor. The UNO hub owns ttyACM0.
Do not invent a fourth CH340 radar adapter or assign radar permissions to one.

Current Astra guardian still hard-codes bus001/dev014 and011. Persistent udev
permissions alone cannot make that guardian tolerate renumbering. A separate
reviewed resolver update must consume and verify the proposed stable aliases
(VID/PID, topology, character-device identity; ambiguity fails closed) before
end-to-end re-enumeration reliability can be claimed. No resolver deployed here.

## 2. Inventory: application devices

Read-only sources: sysfs, udev database, getfacl, `/proc/*/fd`, process environments,
service files and group membership. No serial probes or device resets performed.
All USB bus nodes were root:root0664; Astra additionally has named jetson RW ACLs.
Raw USB permission is not the access path used by ordinary tty services.

| Device / verified consumer (user jetson) | VID:PID / USB serial | Topology; current bus node | Application node / driver / access |
|---|---|---|---|
| Astra depth/IR; Vision Lab web PID1992 launches worker | 2bc5:0403; no USB serial | 1-2.3.1.2; 001/014 | raw usbfs; vendor depth interface unbound, audio interfaces snd-usb-audio; temporary jetson RW |
| Astra RGB; same worker | 2bc5:0501; no USB serial | 1-2.3.1.1; 001/011 | raw usbfs temporary RW; video1/video2 uvcvideo root:video0660, jetson RW |
| RPLIDAR A1; rplidar PID2345 | 10c4:ea60; 0001 | 1-2.2.1; 001/009 | ttyUSB3; cp210x; root:dialout0666, jetson RW |
| STM32/Yahboom motor board; yahboom_base PID3293 | 1a86:7523; none | 1-2.2.3; 001/012 | ttyUSB0; ch341; root:dialout0660, jetson RW |
| Hiwonder GPS; gnss_node PID2630 | 1a86:7523; none | 1-2.4.2; 001/013 | ttyUSB1; ch341; root:dialout0660, jetson RW |
| IM10A; observer PID1841 | 1a86:7523; none | 1-2.4.3; 001/016 | ttyUSB2; ch341; root:dialout0660, jetson RW |
| UNO R4 sensor/radar hub; bridge PID1897 | 2341:006d; 3718211158323232840133334B573038 | 1-2.1; 001/004 | ttyACM0; cdc_acm; root:dialout0660, jetson RW |
| Voice companion PID2045 | 303a:1001; 28:84:85:57:02:24 | 1-2.2.4; 001/015 | ttyACM1; cdc_acm; root:dialout0660, jetson RW |
| Cellular modem; OS modem/network owners, cellular telemetry jetson | 1e0e:907b; 0123456789ABCDEF | 1-2.4.1; 001/010 | ttyUSB4/5/6 interfaces02/03/04 option; root:dialout0660; rndis_host networking |
| Remote controller; joy_node jetson | 045e:028e; 3E5296D0 | 1-2.4.4; 001/018 | xpad/input; existing targeted dialout0660 rule; no proposed change |
| Bluetooth radio; OS BlueZ/BMS client | 0bda:c822; 00e04c000001 | 1-3; 001/003 | btusb; managed through Bluetooth stack, not raw USB by BMS |
| Pi Camera3 (NOT USB) | no USB identity | platform-tegra-capture-vi | video0 root:video0660; jetson RW; unchanged |

Serial device ACLs contain only owner/group/other entries; no temporary per-user
ACL needed. Web process actual supplementary groups include dialout20 and video44.
Account groups: jetson,adm,dialout,sudo,audio,video,render,i2c,gdm,gpio,weston-launch.
No atlas-astra membership was created. SDK Astra serial17122120830 is not an
exposed USB attribute and must NOT be placed in an ATTR{serial} rule.

### Infrastructure USB nodes (no access changes)

| VID:PID | Topology / bus node | Driver / serial |
|---|---|---|
| 1d6b:0002 | usb1 /001/001 | root hub; 3610000.usb |
| 1d6b:0003 | usb2 /002/001 | root hub; 3610000.usb |
| 0bda:5489 | 1-2 /001/002 | hub; none |
| 0bda:0489 | 2-1 /002/002 | hub; none |
| 2109:0817 | 2-1.2 /002/003 | hub; none |
| 2109:2817 | 1-2.2 /001/005 | hub; none |
| 214b:7260 | 1-2.3 /001/006, 1-2.4 /001/007 | hubs; none |
| 05e3:0608 | 1-2.3.1 /001/008 | hub; none |
| 2109:8817 | 1-2.2.5 /001/017 | billboard, no bound interface driver; 0000000000000001 |

These raw nodes are root:root0664. No ATLAS user-space raw access requirement
identified. Do not expand permissions merely because these devices are connected.

## 3. Existing rules and persistence

- `50-udev-default.rules` assigns tty devices to dialout; current serial0660 plus
  jetson membership is already persistent policy. A future reboot was NOT tested.
- `70-project-atlas-uno-r4.rules` uses exact UNO VID/PID/serial, dialout0660,
  ModemManager exclusions and `/dev/atlas-sensor-hub`; present and correct.
- `99-project-atlas-xbox.rules` preserves remote input access; unchanged.
- `99-atlas-ch340-ports.rules` matches OLD ID_PATH `...0:2.2:1.0`, which does not
  match current motor path `...0:2.2.3:1.0`; `/dev/atlas-yahboom` is absent.
  No observed outage: current motor owner uses `ATLAS_YAHBOOM_AUTO_USB=1`.
  Do not silently replace protocol discovery with that stale link.
- Vendor `60-ros-humble-rplidar-ros.rules` grants all10c4:ea60 tty devices
  MODE:="0666" and /dev/rplidar. This is existing world-write exposure, NOT introduced
  here. A later MODE assignment cannot override final `:=`. Separate hardening
  review should replace/mask that vendor rule with an exact serial/topology0660
  policy and test LiDAR; not bundled into Astra repair.
- `85-brltty.rules` matches1a86:7523; potential conflict worth noting, but all three
  adapters are currently bound ch341 and open by the expected processes. No evidence
  that brltty caused this Astra ACL loss; no disabling done.
- Existing modem rules and NVIDIA/CUPS rules preserved. No Astra access rule found
  in /etc,/run,/usr/lib udev rule directories. User-added temporary ACLs remain.

## 4. Exact candidate (not installed)

File: `project_atlas/config/udev/99-atlas-astra-access.rules.candidate`.
Install name, ONLY after approval: `/etc/udev/rules.d/99-atlas-astra-access.rules`.

```udev
ACTION=="add|change", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ENV{ID_PATH}=="platform-3610000.usb-usb-0:2.3.1.2", ATTR{idVendor}=="2bc5", ATTR{idProduct}=="0403", OWNER:="root", GROUP:="atlas-astra", MODE:="0660", SYMLINK+="atlas-astra-depth-usb"
ACTION=="add|change", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ENV{ID_PATH}=="platform-3610000.usb-usb-0:2.3.1.1", ATTR{idVendor}=="2bc5", ATTR{idProduct}=="0501", OWNER:="root", GROUP:="atlas-astra", MODE:="0660", SYMLINK+="atlas-astra-rgb-usb"
```

Dedicated group `atlas-astra`: only jetson member, root owner retained. No RUN,
PROGRAM, global chmod, all-USB matches or login-session uaccess dependency. Exact
ID_PATH values observed in udev database. VID/PID + physical port disambiguates
serial-less Astra. Devnum changes do not affect matching. Moving to a different
hub port intentionally fails closed and requires inventory/review; topology is
not a cryptographic device identity. USB serial spoofing is not solved by udev.

udev249 is installed; final assignment is supported. Matching/assignment semantics:
[systemd udev reference](https://www.freedesktop.org/software/systemd/man/250/udev.html).
Keep the rule after persistent-path property generation. No tty or video node
permissions are changed by these usb_device-only rules.

## 5. Stable naming and service accounts

- Preserve LiDAR's existing serial0001 by-id path; verify uniqueness if another
  CP2102 is added. Preserve UNO/voice unique by-id and UNO atlas-sensor-hub alias.
- Keep current protocol discovery for motor/IMU/GPS. Their by-path links are unique
  for fixed wiring; new role aliases are unnecessary until a consumer needs them.
- Do not create an atlas-radar serial link: radar is topic-fed via UNO.
- New raw Astra aliases avoid ephemeral devnums, but consumers must verify identity
  on each admission. Existing guardian resolver update is a distinct needed change.
- Running services do not inherit a group added later. These are systemd USER
  services: changing account membership alone will not update the existing user
  manager. Do not promise that restarting only a child service fixes membership.
  Use a separately approved controlled reboot/session renewal, then inspect actual
  /proc/PID/status Groups. Do not restart the entire user manager during deployment.

## 6. Validation performed and limits

Eight offline unittest cases PASS: exact two interfaces; devnum/busnum renumbering;
wrong/missing topology; unrelated connected VID/PIDs; interface/video/tty/remove
events rejected; add/change handling; least-privilege assignment/no execution;
unique aliases. Tests parse the actual candidate rule text and use captured match
attributes. This is STATIC rule matching, not a native udev simulator or live pass.

No `udevadm trigger`, `udevadm test` on production, service restart or hotplug was
performed. Native isolated udev validation (including full rule ordering and group
resolution) remains a deployment prerequisite; do not claim it passed from these
static tests. Live udev test may touch database/nodes/builtins, so is not used as
a supposedly read-only substitute. Syntax is limited to documented249 keys.

Previous conditional preview request stopped at first CPU sample75.2902% (>75%).
No Start, no installation, no retry. USB identity/access and fresh sensors passed.
Postflight stop latched, manual-only, commands zero, recorder inactive, Astra process
absent; protected PIDs/restarts unchanged. Probe/runtime original hashes remain.
Latest instruction supersedes camera testing with this audit. Temporary ACLs added
by owner remain unchanged; no privileged restoration can be performed by current
SSH account without administrator authentication. No image/rosbag captured.

## 7. Deployment, verification and rollback plan

1. Obtain approval for EXACT rule file, dedicated group + jetson membership and
   any separately reviewed guardian stable-path update. Verify fresh safety and
   CPU<=75%,RAM<=80%,temperature<=70C. Require working local recovery terminal.
2. Capture hashes, current rules, ACLs (including owner-added grants), memberships,
   udev properties, service PIDs/restarts and safety state in timestamped backup.
   If rule/group already exists, inspect rather than overwrite. Back up atomic
   installation targets. Prepare exact restore commands before writes.
3. Validate native matching in an isolated environment using the same udev version
   and properties. Confirm rule order and exactly two targets. Resolve new group
   before installing. Do not apply to all USB devices.
4. Install reviewed rule and reload udev rules (no blanket trigger). This alone
   does not fix existing node permissions or running process groups. Retain existing
   temporary access until controlled transition; no service restarts inferred.
5. Separate owner-approved reboot/reconnect test: motors/camera power safe, E-STOP,
   recording OFF, autonomy disabled. Confirm all services recover, serial role
   discovery correct, fresh LiDAR/IMU/encoders/radar, remote stop, camera3 health.
   Verify Astra raw nodes now root:atlas-astra0660 without temporary user ACL;
   service process actually has group, aliases resolve to verified identities.
6. Test one controlled Astra reconnect with possible devnum change only under
   separate approval; never reset the shared hub. Compare descriptors/topology and
   stable alias resolution. Camera streaming needs its own guarded approval.
7. Rollback on failed matching/access/service/safety: keep stopped; restore original
   rule bytes or remove only the newly installed file; reload rules without blanket
   trigger; restore saved ACLs on identity-verified current nodes. Remove membership
   added by this change only, and group only if newly created and unused. Existing
   processes may retain groups until an approved restart/session renewal. Revalidate
   protected services. Never delete recordings/maps or reset USB to force recovery.

No live deployment backups created in this offline phase; no persistent changes
exist to roll back. Existing recovery evidence is preserved.

## 8. Files and exact approvals

New report, candidate rule and eight-case static test; README/CHANGELOG/blocker
registry updated. No production service, configuration or calibration edits.

Needed separately:
1. Approval after native isolated validation for installing the two-interface rule,
   creating atlas-astra and adding jetson; any guardian resolver patch separately.
2. Approval for controlled reboot/session renewal and hardware recovery checks.
3. Approval for targeted Astra reconnect and later one guarded preview test.
4. Optional independent LiDAR permission hardening and stale CH340 alias cleanup.

Do not claim full reboot reliability before2/3 pass; no Windows dependency in the
proposed on-Jetson rules, group or service discovery.
