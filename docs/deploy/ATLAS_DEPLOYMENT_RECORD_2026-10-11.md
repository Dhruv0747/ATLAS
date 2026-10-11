# ATLAS deployment record and consolidated status, 2026-10-11 (13:10 IST)

## Deployed on the Jetson (all live files equal branch HEAD `105a8b4`, byte for byte)

| Stage | Installed | Restarted | Backup and `ROLLBACK.sh` (`~/project_atlas/data/backups/…`) | Approval |
|---|---|---|---|---|
| 1 safety: E-STOP latch, drive refused while latched, stops during shutdown, reboot action removed, classic E-STOP on pointerdown | 12:51:55 | rover-status-web 12:52:02 | `2026-10-11-125155-119852623-stage1-safety` | 12:46 / 12:47 |
| 1b web E-STOP reset (server-side checks, event log) | 12:59:27 | rover-status-web 12:59:32 | `2026-10-11-125927-471586548-stage1b-estop-reset` | 12:58 ("deploy remaining") |
| 2 Glass UI V2 at `/v2/` (V1 stays the default at `/`) | 13:00:00 | rover-status-web 13:00:06 | `2026-10-11-130000-680458815-stage2-glass-ui-v2` | 12:58 |
| 3 hot/cold executor split | 13:01:50 | rover-status-web 13:01:55 | `2026-10-11-130150-855115200-stage3-executor-split` | 12:58 |
| 4 Visual Cloud: local, viewer- and activity-activated, bounded history | 13:04:20 | visual-cloud server + agent 13:04:25 | `2026-10-11-130420-327556352-stage4-visual-cloud` | 12:58 |

Each install followed the same sequence:
1. Checksum check.
2. Precondition check: latched, odometry zero, mission READY.
3. Patch rehearsal on a scratch copy.
4. Backup.
5. Apply.
6. Scope check: only the stage's own files changed.
7. Precondition re-check, then restart of only that stage's service(s).
8. GET-only verification.

The stages were installed one at a time, each verified before the next. The cmd_vel mux was never
restarted (same PID 1872 throughout).

**Live hashes after deployment:**

| File | sha256 (prefix) |
|---|---|
| `atlas_status_web.py` | `fb620ec5` |
| `atlas_estop_reset.py` | `fb415830` |
| `atlas_web_v2.py` | `76a1d709` |
| Visual Cloud agent | `76d94338` |
| Visual Cloud core | `1e35456a` |
| Visual Cloud server | `db094637` |
| `config/atlas_visual_cloud.json` | `767cdd54` |

The live classic page and the V2 `command.js` are byte-identical to the files used in every
browser test.

**Production results (read-only measurements).**

| Check | Result |
|---|---|
| rover-status-web CPU (stage 3) | **55.9% → 39.4% of one core** (60 s each). Status keys and delivered rates unchanged: 104 keys, 246 → 245.5 Hz. `/atlas_web_control` and `/atlas_web_status` both present. No `web_error` |
| V2 static route | All V2 pages and assets 200. Traversal attempts sent with `--path-as-is` all 404. (A `verify.sh` FAIL line came from curl normalising `/v2/../logo.png` to `/logo.png` client-side. `verify.sh` is fixed on the branch) |
| Visual Cloud (stage 4) | Upload mode `local`. 0 failed uploads since restart. The 25 GB `history.sqlite3` is unchanged (same size and mtime, Oct 4 15:09). Bounded history rows are about 2.3 KB. Live view has data |
| Visual Cloud idle CPU | **Not yet confirmed.** The agent stayed at about 11%, which is the expected cost *with a viewer*. The server reports a viewer every second (`viewer_age_s` 0.1–1.5), coming in through the Tailscale proxy, so a Visual Cloud page is open in some browser on the tailnet. Once that tab is closed it should fall to about 1.4% (measured live earlier). Re-measuring is read-only |
| Web reset (stage 1b) | `/api/estop/state`: latched; reset **blocked only by "no operator PIN configured"**, so the remote is connected, the rover still and no drive is active. The event log `data/safety/estop_events.jsonl` is being written |
| Safety state now | **Latched** ("voice stop requested" = web E-STOP), stationary, mission READY, autonomy unchanged (disabled), re-localisation mode `suggest` |

## Controller mapping (verified read-only, 12:48–12:51)

The Jetson identifies the controller as "Microsoft X-Box 360 pad", USB `045e:028e`.
- **B** = button index 1: the mux latched with reason "REMOTE STOP: B pressed" (12:50:57).
- **LB** = button index 4: neutral sticks plus LB held ≥ 2 s, then let go, released the latch
  (12:48:16–12:48:19).

## Motion events today (recorded, not commanded by Claude)

Every motor command below came from the **physical Xbox remote** (REMOTE channel). The web channel
carried only zero speeds throughout.

| Time | What happened | Result |
|---|---|---|
| ~12:48:16–12:48:21 | During the controller check, an LB hold of 2.1 s with sticks neutral released the latch. LB was then held again with the left stick forward and back | Odometry +5.2 cm (x −0.001 → 0.052 m). Re-latched with B at 12:50:57 |
| 12:58:18–12:58:58 | Operator remote release (LB), then a short remote drive forward/back, then B | Odometry +4.9 cm (0.052 → 0.100 m) |

My instruction to tap LB contributed to the first event. No LB press will be requested again
outside an approved release test.

## Operator observations recorded but not counted as passed

A read-only recorder ran 12:52–13:07. It saw:
- 4 web E-STOP latch requests (12:57:33–12:57:35 and 12:59:05), each latching the mux;
- 159 web drive messages, **all zero**: web drive was refused while latched.

Per your instruction, **C1–C5 are not marked passed** until you run them in the planned session.
The recorder cannot tell which phone gestures were used.

## Built and tested but not deployed

- **None of the planned code stages.** All five are installed.
- **Proposals only, not built:**
  - security items 3 (same-origin on all control POSTs) and 5 (escaping telemetry, intercom
    auth);
  - Visual Cloud legacy-history archive or extract;
  - switching the default dashboard to V2.

## Needs your approval or action (no session required)

1. **Set the operator PIN** (your action; it enables the web reset):
   `python3 ~/project_atlas/scripts/atlas_estop_reset.py set-pin`
2. **Close the Visual Cloud tab** if you don't need it. I will then re-measure the agent's idle
   CPU (read-only).
3. **Decisions, whenever convenient:**
   - rotate the Jetson password that appears in git history and 2 scripts;
   - security items 3 and 5;
   - what to do with the 25 GB legacy DB (kept);
   - when to make V2 the default;
   - the earlier pending items: LiDAR restart limit (on hold) and the corridor re-map.

## Requires physical testing: one short supervised session, about 20 minutes

Prerequisites: rover parked, remote in hand, phone, PIN already set, wheels-lifted stand ready for
part D.

| Order | Block | Steps | Motion? | Needs approval |
|---|---|---|---|---|
| A | Stage 1 stationary (latched) | C1 tap E-STOP · C2 two-finger E-STOP while holding FORWARD · C3 hold FORWARD (nothing moves) · C4 phone Wi-Fi off/on · C5 close and reopen the tab. Run on the **classic page**, then repeat C1–C3 on **V2** (pad and dock E-STOP) | none | approved |
| B | Stage 1b reset (latched → reset → re-latch; wheels may stay down) | E1 panel shows RESET AVAILABLE · E2 hold FORWARD → RESET BLOCKED · E3 remote off → BLOCKED · E4 one wrong PIN · E5 correct PIN → released, **no motion** · E7 re-latch with B · E8 Claude checks the event log | none | **yes** |
| C | Remote release (formal C6) | neutral plus LB 2 s, let go → released, no motion, then B | none | **yes** |
| D | Wheels lifted | F2 short hold → wheels turn · F3 E-STOP with a second finger while holding → wheels stop and stay stopped · F4 press again → no motion · F6 after a web reset, only a fresh press turns the wheels · repeat F3 on V2 | **yes, wheels only** | **yes** |
| E | V2 with your PC off (can be folded into A) | open `/v2/` on the phone over the LAN IP, then Tailscale; camera, chips and dock visible | none | already approved (stage 2) |

Blocks A and E can run together with no new approval. B and C need about 5 minutes and your
approval. D needs the stand and its own approval.

## Rollback

Undo the stages in reverse order: 4, 3, 2, 1b, 1. Run each with
`bash <backup>/ROLLBACK.sh`, then restart that stage's service(s). Every rollback is pinned to the
live tree and restores the exact previous files.
