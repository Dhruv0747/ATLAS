# How ATLAS stays safe

ATLAS drives around people at home, so safety is designed in layers. Any single layer can stop the rover; no layer can
override the one above it.

## The layers, from strongest to weakest

| # | Layer | What it does |
|---|---|---|
| 1 | **Remote stop (B)** | Latched stop from the FlySky / Xbox remote. Overrides every other command, including autonomy. |
| 2 | **Dashboard E-STOP and Abort mission** | E-STOP sends a zero-speed command and latches. Abort switches to manual and cancels the Nav2 goal. |
| 3 | **Priority velocity mux** | The only path to the motors. Applies priorities, a stale-command watchdog and every safety check below. |
| 4 | **Manual-only default** | Autonomy is off after boot and after any stop; the operator must arm it. |
| 5 | **LiDAR blind-spot guard** | Blocks Nav2 motion toward any direction that is not observed live by the LiDAR, the Astra depth camera, the ultrasonic sensors, or a known map wall at a safe distance. |
| 6 | **Close-range stops** | Front ultrasonic stop at 0.30 m; LiDAR side-sector stops. |
| 7 | **Health gates** | Encoder consensus (three wheels must agree), localization confirmed by a LiDAR scan check, fresh depth-camera obstacles, battery and sensor freshness. |
| 8 | **Nav2 costmaps** | Inflated obstacles from the map, virtual obstacles, LiDAR and depth camera keep planned paths clear. |

AI features (voice, vision, language model, cloud telemetry) are **advisory only**: none of them can send a motion
command around the mux.

## Rules for working on ATLAS

These rules apply to people and to AI coding agents (see [AGENTS.md](../AGENTS.md)).

1. **Never bypass a safety gate**, not even "just for a test". If a gate is wrong, fix it with evidence and review.
2. **Movement is commanded by the operator only.** Software work never starts a drive on its own.
3. **Restart drive-related services only while parked with the stop latched.**
4. **Test on recordings first.** Every change is replayed on saved drives (rosbags) before it touches the robot.
5. **One change at a time, with a rollback.** Back up files before replacing them and record what was deployed.
6. **Speed evidence expires.** Any change to the speed loop or the base driver requires two new passing Speed checks.
7. **Keep the record honest.** Failures and rejected experiments stay in the
   [blockers log](audits/ATLAS_CURRENT_BLOCKERS.md). A unit test or one good run is not a physical PASS.
8. **No secrets in the repo:** no credentials, tokens, private network addresses or personal data.

## Known limits

- The RPLIDAR A1 gets no echo from some dark, shiny or glass surfaces. Such objects need tape, a virtual obstacle or
  another sensor.
- The Astra depth camera only sees about ±26° ahead and nothing closer than 0.35 m.
- HC-SR04 ultrasonic sensors have a wide cone and can miss soft or steeply angled surfaces.
- Unattended operation is **not approved**. Every autonomous drive needs an operator holding the remote.
