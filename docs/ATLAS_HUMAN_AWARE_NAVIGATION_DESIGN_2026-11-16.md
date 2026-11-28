# ATLAS Human-Aware Navigation — Design (2026-11-16)

Status: **DESIGN ONLY — nothing implemented or deployed.** Owner request, 2026-11-16:

> "When an obstacle comes, find a new way. If it is a human, know that it is a human, how far away it is and
> which way it is going. If it is standing still, find a new way. When it sees a human it should say politely
> 'please move aside'. Then the human moves, and through the RD-03D radar it will know that the human moved."

Master-plan position (`docs/AI_ROBOTICS_ADAPTATION_PHASE0_2026-09-30.md`):

- Steps 7 (benchmark the TensorRT YOLO path) and 8 (advisory semantic perception).
- Work starts only after **Stage 3** (supervised Dhruv Room → Hall → Dhruv Room round trip with safe-stop and
  return-home evidence) passes.

---

## सारांश (हिंदी)

- ATLAS रास्ते में **इंसान** को चीज़ से अलग पहचानेगा।
  - **RD-03D radar** बताएगा कि कोई चल रहा है, कितनी दूर है, किस दिशा में और कितनी तेज़।
  - **RGB camera पर YOLO** पक्का करेगा कि वह इंसान है।
  - **Astra depth** सटीक दूरी और आकार देगा।
- व्यवहार:
  - इंसान **खड़ा** है → उसे बड़ी जगह छोड़कर नया रास्ता।
  - रास्ता **पार कर रहा** है → रुककर इंतज़ार।
  - **सामने से आ रहा** है → धीमा होकर किनारे।
  - रास्ता रोककर **खड़ा** है → विनम्रता से "कृपया थोड़ा साइड हो जाइए", और radar से देखेगा कि वह हटा या नहीं।
  - नहीं हटा → नया रास्ता, या इंतज़ार करके dashboard पर बताएगा।
- यह सब **सिर्फ़ ज़्यादा समझदारी जोड़ता है**। Safety (LiDAR guard, costmap, ultrasonic, E-STOP) कभी इस पर निर्भर नहीं होगी, क्योंकि camera या radar इंसान को miss कर सकते हैं।

---

## 1. Goals and non-goals

**Goals**

1. Classify a near-path obstacle as **PERSON** or **OBJECT** with distance, bearing and velocity.
2. Person-specific behaviour: give way to crossing people, slow near people, larger clearance around people, and
   a polite spoken request when a stationary person blocks the only path.
3. Confirm with the radar (and camera) that the person moved, then continue. Never insist, never approach.
4. Explain every decision by voice and on the dashboard (owner request from 2026-11-15: "always tell the real reason").

**Non-goals**

- No person identification or face recognition. Track IDs are short-lived and anonymous (as in `atlas_radar_core.py`).
- No following or herding of people (separate `atlas_follow_person.py` work, not part of this).
- Never used to *grant* motion. Every person-layer output can only slow, stop, wait or add costmap cost.

## 2. What already exists (verified 2026-11-16)

| Piece | File / service | State |
|---|---|---|
| RD-03D decoder, odom-frame tracker, advisory risk model, `guard_scale` | `scripts/atlas_radar_core.py`, `atlas_radar_tracking.py`, service `rover-radar` | Running. Publishes `/radar/targets`, `/radar/nearest_*`, `/radar/zone`, `/radar/target_count` |
| Mux radar speed gate | `atlas_cmd_vel_mux.py` (`/radar/speed_guard`, `ATLAS_RADAR_GATE_ENABLED`) | Code present, **disabled** (env 0). No `/radar/speed_guard` publisher live. Fail-closed when enabled |
| Radar ↔ camera person association helpers | `scripts/atlas_person_fusion_core.py`, `atlas_person_sensor_fusion.py` | Exists, not part of navigation |
| TensorRT YOLOv8 detector | `scripts/trt_yolo_detector.py` | Exists, not running as a service; not benchmarked under full load |
| Astra depth obstacle scan + coverage | `atlas_astra_obstacle_*`, domain 77 → bridge | Live (coverage since 2026-11-16) |
| Voice narrator (Hindi) | `atlas_autonomy_voice(_core).py`, `/atlas/voice/test_speak` | Live |
| Replan-if-blocked BT | `config/atlas_ackermann_replan_if_blocked.xml` | Live (per goal) |

## 3. Sensors and what each is trusted for

| Sensor | Strength | Weakness | Trusted for |
|---|---|---|---|
| RD-03D radar (24 GHz, ≤ 3 targets, ~8 m) | Detects **moving** people early with radial speed. Works in the dark and through glass/black surfaces | Static people fade. Coarse angle. Indoor multipath ghosts. Max 3 targets | "Something is moving there, at this speed and direction"; confirming a person moved away |
| RGB camera + YOLOv8 (TensorRT) | "Is it a person?" | Misses in dark, backlight or occlusion. CPU/GPU load | Class label PERSON only, never distance |
| Astra depth (160×120) | Accurate range and size in front (~±29°) | BLINDED on glass/black, narrow FOV | Distance, footprint of the person for the costmap |
| LiDAR | 360° geometry | No class. No echo on some surfaces (A/B/C spots) | Unchanged safety guard + costmap |

**Fusion rule:**

- **PERSON** = YOLO person box whose bearing matches an Astra depth cluster (± 6°) **or** a radar track (± 12°, range ± 0.4 m).
- **Radar-only moving target** = `MOVER` (unknown class). Behaviour as a person for slowing; no spoken request.
- **Camera-only person without depth/radar** = `PERSON_UNCONFIRMED`. Slow only.

## 4. Architecture

```
 RD-03D ─► rover-radar (tracks, odom frame) ─┐
 RGB ─► yolo_person (TensorRT, ≤ 5 Hz) ──────┼─► atlas_person_tracker ─► /atlas/people (JSON, base_link + map)
 Astra depth ─► obstacle clusters ───────────┘        │
                                                      ├─► person costmap layer (larger inflation) ─► Nav2
                                                      ├─► /radar/speed_guard (scale 0..1) ─► mux gate (exists)
                                                      └─► atlas_people_behaviour ─► mission control (pause/resume)
                                                                               └─► voice ("कृपया साइड हो जाइए")
```

- **`atlas_person_tracker`** (new, pure core + thin node): associates detections and smooths with a constant-velocity filter. Per person it outputs `{id, class, x, y, vx, vy, speed, heading, confidence, sources, age}`.
- **Person costmap layer:** publishes people as an obstacle `PointCloud2`/`LaserScan` with **0.6 m** personal-space inflation (objects keep the normal inflation). Nav2 then replans around a standing person automatically.
- **Speed guard:** reuses the existing mux radar gate (`guard_scale`, fail-closed). The tracker publishes `/radar/speed_guard` `{scale, qualified, reason}`:
  - scale 1.0 when no person is within 2.0 m of the path;
  - linear down to 0.4 at 1.0 m;
  - 0 when a person is within 0.6 m of the swept path.
- **`atlas_people_behaviour`:** a small state machine (section 5) that can only **pause** the current Nav2 goal (cancel and re-send the same goal) and talk.

## 5. Behaviour state machine

| State | Enter when | Action | Leave when |
|---|---|---|---|
| `CLEAR` | no person within 2 m of the planned path | normal | person near path |
| `SLOW` | person within 2 m of path, not blocking | speed scale per §4, extra clearance | person > 2.5 m or → other state |
| `YIELD_CROSSING` | person's predicted track crosses the path within 3 s | pause goal, say "आप पहले जाइए" | track out of path for 1.5 s → resume |
| `ONCOMING` | person ahead moving toward the rover (closing speed > 0.2 m/s) | slow to 0.08 m/s, prefer the side with more free space (costmap), stop if < 1.0 m | track passes or stops |
| `BLOCKED_ASK` | person stationary ≥ 3 s inside the swept path within 1.5 m **and** Nav2 has no alternative path (replan fails or path ≥ 2× longer) | stop, say once: "माफ़ कीजिए, क्या आप थोड़ा साइड हो सकते हैं? मुझे आगे जाना है।" | person leaves the swept path (radar track or depth cluster moves ≥ 0.4 m sideways) → say "धन्यवाद!" and resume |
| `BLOCKED_WAIT` | `BLOCKED_ASK` and no move after 8 s | ask a second (last) time; after 8 s more: wait, say "मैं इंतज़ार कर रहा हूँ", dashboard notice | person moves, or owner cancels |

Rules:

- At most **2 requests per person track**.
- Never move toward a person.
- Never reverse toward a person.
- No speech when the class is only `MOVER` (could be a radar ghost or a pet), or at night quiet hours (configurable).

## 6. Safety principles (unchanged and non-negotiable)

1. The person layer can only reduce speed, pause a goal, add costmap cost or speak. It never removes a veto and never grants motion.
2. LiDAR availability guard (with map-known gaps + Astra coverage), costmap, ultrasonic advisory, mux watchdogs and E-STOP stay exactly as they are.
3. Missing, stale or invalid person data means "no extra knowledge", never "path clear". The mux radar gate is already fail-closed when enabled.
4. Radar ghost suppression: a radar track must persist ≥ 0.5 s and must not sit on a mapped wall cell (± 0.2 m), or it is ignored for behaviour (it may still slow).

## 7. Compute budget (Jetson Orin Nano)

- Current load average during drives is **11–25**. YOLO must not starve localization (lesson from 2026-11-14/15: stale localization when extra ROS processes start during a drive).
- Plan:
  - YOLOv8n at 320×320, ≤ 5 Hz, only while a Nav2 goal is active, `nice` 10;
  - benchmark first (master-plan step 7): GPU %, CPU %, AMCL and controller loop rates with and without YOLO on a recorded drive;
  - abort criterion: controller or AMCL rate drops > 10 %.
- Radar and the tracker are cheap (< 3 % CPU).

## 8. Implementation phases (each: offline replay → tests → owner OK → deploy → supervised test)

| Phase | Content | Exit evidence |
|---|---|---|
| H0 | Record 3 supervised drives with people crossing, standing and approaching. Topics: `/radar/targets`, Astra coverage/scan, RGB at 5 Hz, `/scan`, `/amcl_pose`, `/cmd_vel_nav` | Labelled bag set |
| H1 | Radar-only `MOVER` slow-down via the existing mux gate (`/radar/speed_guard`). Replay ghost rate on recordings | Ghost-triggered slowdowns < 5 % of driving time; real people slow every time in the recordings |
| H2 | YOLO benchmark + `atlas_person_tracker` (radar + camera + depth fusion), shadow mode (publish only) | Person classification ≥ 90 % in recordings; load criteria (§7) met |
| H3 | Person costmap layer (0.6 m personal space) + `YIELD_CROSSING` / `ONCOMING` | Supervised: 5 crossings, 5 oncoming, 0 contacts, all yields logged and spoken |
| H4 | `BLOCKED_ASK` / `BLOCKED_WAIT` with voice + radar confirmation | Supervised: 5 ask-and-move, 2 refuse-to-move (rover waits/replans), max 2 requests each |
| H5 | Dashboard: people on the map (anonymous dots with arrows), current state and reason | Owner review |

## 9. Tests

- **Pure unit tests:** association (radar/camera/depth bearings), constant-velocity prediction, crossing-time computation, every state transition, request counter, ghost filter, fail-closed on stale inputs.
- **Replay tests** on H0 bags: decisions per frame vs labels.
- **Mux:** existing radar-gate tests stay; new tests that the person path can never raise speed above the Nav2 command.

## 10. Open questions for the owner

1. Quiet hours for speech? (default: none)
2. Personal-space radius: 0.6 m default — OK?
3. Should the rover also say "रास्ता दीजिए" to pets or unknown `MOVER`s? (default: no)
4. When it waits for a person who does not move: how long before it gives up the goal? (default: 60 s, then ABORT + dashboard)
