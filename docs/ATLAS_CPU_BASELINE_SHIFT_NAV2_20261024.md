# Why the parked Jetson moved from ~65% to ~71% CPU (21 → 24 October) — offline comparison

**Method:** existing evidence only (no new profiling, no restart, no camera, no motion). Read-only copies of saved
1-s recorder traces and the ranked capture's per-process tick totals; read-only `journalctl` and unit/config
file metadata on the Jetson.

## Answer

It is **not a code regression**. On 21 October the low baseline (and the IR camera session that passed) happened
while the **Nav2 navigation servers were never activated**: in that boot the navigation bring-up stopped at
`planner_server` "Checking transform" (AMCL had no initial pose yet), so `planner_server`, `behavior_server`,
`bt_navigator` and `waypoint_follower` sat configured-but-inactive at ~0.1% each. In every boot since (21 Oct
20:18 and 23 Oct 20:04), the navigation lifecycle completed ("Managed nodes are active") and those servers now
run at 4–6% of a core each. Unit file (19 Aug), Nav2 params (11 Oct) and launch file (10 Aug) are unchanged.

## Evidence

Whole-Jetson CPU, camera off (existing recorder traces):

| Time | Mean | Note |
|---|---:|---|
| 21 Oct 19:16 (boot −3) | 65.5% | navigation servers inactive |
| 21 Oct 22:00 (boot −2) | 69.3% | navigation active |
| 23 Oct 23:32 – 24 Oct 00:27 (boot 0) | 70.6–71.4% | navigation active |
| 24 Oct 06:56 | 73.7% | localization-install attempt window |
| 24 Oct ~11:10 (light observer) | 72.9% | |

Journal, per boot: navigation "Managed nodes are active" / planner bonded — boot −3: **0 / 0**; boot −2: 1 / 1;
boot 0: 1 / 1. Localization (map_server + AMCL) was active in all three.

Per-process, % of ONE core (21 Oct: 115 s steady window, recorder covers 90% of busy; 24 Oct: 8 s
baseline+postflight of the ranked capture, its own observer excluded):

| Process (atlas-localization) | 21 Oct | 24 Oct |
|---|---:|---:|
| bt_navigator | 0.2 | 5.6 |
| behavior_server | 0.1 | 5.1 |
| planner_server | 0.1 | 4.7 |
| waypoint_follower | 0.0 | 3.9 |
| controller_server | 3.6 | 5.1 |
| lifecycle managers (2) | 4.8 | 11.6 |
| amcl | 4.3 | 6.1 |
| map_server | 2.2 | 4.0 |
| **Listed Nav2 total** | **15.3** | **46.1** (+30.8 ≈ +5.1 pts of whole-Jetson) |

Everything else is roughly flat (Dashboard 43.9→41.1, telemetry 27.0→26.7, voice 26.0→22.1, mux 16.1→15.0,
sensor recovery 16.9→15.5, safety status 13.3→12.2, localization monitor 10.1→11.2, mission control 9.5→10.9,
camera node ~31→30). The GNOME desktop session is ~0.1% of the machine. The ranked capture's observer was
41.6% of one core (~6.9 pts) and is not ATLAS load.

## What it means

- The only camera session that passed the unchanged 75% guard did so with Nav2 navigation half-down.
- Normal, fully-active Nav2 costs ~5 points of whole-Jetson CPU on a parked robot — more than ten times the
  Dashboard ExitStack candidate (~0.4 points by extrapolation).
- Why idle *active* servers cost 4–6% each is not established from CPU totals alone (candidates: costmap update
  loops, bond heartbeats, TF/parameter-event delivery over the UDPv4-only transport this unit forces). Previous
  reports warn against bond/timer tuning on thin evidence; none is proposed here.

## Options (owner decision; nothing changed)

1. **Parked diagnostic profile:** for a stationary camera session only, pause Nav2 *navigation* (lifecycle
   PAUSE of controller/planner/behavior/bt/waypoint; keep map_server + AMCL localization), run the session, then
   RESUME and verify "Managed nodes are active". This reproduces the measured 21 Oct state. Needs design and
   validation first: what mission control, localization monitor, readiness and the Dashboard report while
   navigation is paused, and a guaranteed resume. Not navigation-settings changes, but a runtime state change —
   owner approval required.
2. Investigate why active-but-idle Nav2 servers cost 4–6% each, offline first, then a targeted fix.
3. Leave Nav2 as is and accept that the 3D preview cannot reliably start while full navigation is active.

Raw copies are kept privately (`Downloads/atlas_deploy/cpu_timeline_20261024a/`), not committed.
