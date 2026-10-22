# Permanent Astra permission installer — owner execution pending

Scope: only the already reviewed two-interface udev policy, dedicated
`atlas-astra` group, jetson membership and current-node temporary ACLs. No Wi-Fi
changes, camera activation, profiling, service restart, reboot, hub reset or
udev trigger. All existing75% CPU/80% RAM/70C and freshness limits retained.

## Owner command

```sh
sudo /usr/bin/python3 -I /home/jetson/project-atlas-migration/admin-diag-20261023/install_astra_permissions_once.py
```

This is NOT the earlier profiling command. It does not profile or record.
Keep ATLAS stopped; paste its final result before taking any next step.

## Verified preparation

- Installer SHA256: `3cb2acd7ab48220a4fba1c99ba48c31c118a0a1147f9d7cf3b8881132d8c9a0b`.
- Rule SHA256: `54a8bc029e21364d1d259f11ebf3cefcf10ad263c45ae98aabda880393c2e7c4`.
- Shared read-only identity/sensor helper SHA256:
  `7129baf4708d259ff08f482477a72a67f7d5b7da0b20f61907edd114d7fd5d95`.
- Source rule remains `project_atlas/config/udev/99-atlas-astra-access.rules.candidate`.
- Recovered isolated native ARM64 udev249 evidence: add/change cases for both
  interfaces return0, set OWNER0/GROUP2999(test group)/MODE0660 and expected
  stable aliases. This is an isolated fixture result, NOT live hotplug proof.
  Live version is249 and both captured ID_PATH values still match.
-21 offline tests pass:6 installer transaction/group/rollback/hash checks,
  8 existing rules tests,7 helper safety/identity tests.
-Staged hash-verified installer executed in nonprivileged `--check-only` mode:
  three samples69.7674%,72.3618%,69.6970% CPU; maxRAM63.175%,max60.062C.
  Fresh required feeds, latched stop, manual-only, zero commands, recorder OFF
  and Astra stopped pass. Both device access checks now true; this shows current
  access, not persistence. No assertion about who restored the ACLs.
-Protected service snapshot includes existing nonzero restart counts:
  telemetry1, localization2, LiDAR5; these were observed, not caused by this work.
  Installer requires identical before/after PIDs and restart counts.

## Operation and fail-closed rollback

Root installer first validates package/live hashes and invokes read-only checks
as the real jetson user. It refuses an existing target rule rather than overwrite
unknown work. Existing group membership must not include other users.
Before mutation it saves identity, safety, group and ACL evidence into a private
`/var/backups/atlas-astra-usb-*` directory.

It creates the group only if absent, adds jetson only if absent, installs the
complete rule without replacing an existing file, reloads rule definitions
without triggering devices, and applies only named jetson RW ACLs to the two
identity-verified current Astra nodes. No world-writable USB permissions.

Postflight repeats three guarded samples, device/access checks, service identity
comparison, installed hash and group membership. Success is explicitly
`INSTALLED_NOT_REBOOT_VALIDATED`. On failure the installer removes only its own
hash-matching rule, reloads definitions, restores the saved ACLs only to unchanged
devices, and removes only membership/group it created. Rollback errors are
reported, not hidden. No automatic retry. Evidence and result remain in backup.
Privileged installation and actual-hardware rollback are still unexecuted.

## Important remaining distinction

Udev rules are persistent, but existing user services do not acquire new
supplementary groups automatically. Temporary ACLs preserve current access.
A separately controlled full session renewal/reboot is needed to verify the user
manager and service groups, next-event permissions and aliases. Do not reboot now.

The currently deployed stationary guardian still checks numbered USB paths.
This permission installer does NOT silently replace that production code.
Its separately reviewed stable-path correction and re-enumeration test remain
necessary before claiming complete plug/reboot reliability. No camera test is
authorized by this installation command.
