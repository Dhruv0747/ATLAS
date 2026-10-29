# ATLAS Stage 29: morning lifted-wheel FlySky test (2026-10-30)

Owner at the rover the whole time. Wheels off the ground. Limits are 0.05 m/s and 0.20 rad/s (reviewed config 875feb35); do not raise them.
The software E-STOP is **not** a motor-power disconnect: there is no independent power kill. If anything moves unexpectedly, press Xbox **B**, then switch the base off at its own power switch.

Helper, on the Jetson (read-only: it never selects, resets, releases or commands anything):

```
cd ~/project-atlas-migration/stage29A_pkg_bc79e75/project_atlas/tools/deploy/stage29_flysky_drive
python3 stage29_morning.py precheck
```

## A. Before touching anything
1. Rover lifted, all four wheels free, nobody's hands near them.
2. Xbox controller on and in reach. FlySky on with SwA UP, SwB UP, SwC MIDDLE, sticks centred.
3. If the Jetson rebooted overnight, stop here: the gate is OFF and gate-on needs a fresh approval.
4. Run `precheck`. Continue only on **PRECHECK GO**. Check the temperature line: it read 65.5 °C last night (limit 70 °C).

## B. Hand over and arm
5. Start the recorder: `python3 stage29_morning.py record 900`.
6. On the dashboard FlySky Driving page, press **SELECT FLYSKY** yourself (it is never automatic).
7. Release the E-STOP with Xbox **LB held 2 s** with the sticks centred and nothing else pressed, then let go.
   Nothing may move yet: SwA is still UP.
8. SwA DOWN = armed. Still nothing moves with the sticks centred.

## C. Direction checks (SwC MIDDLE, then DOWN)
9. Right stick a little up: wheels forward. A little down: reverse. Release: stop.
10. Right stick right: turn right. Left: turn left. Release: stop.
11. Repeat 9–10 with SwC DOWN (full 0.05 m/s). SwC UP gives 0.0165 m/s, inside the base dead band: no motion there is expected, not a fault.
    If a direction is wrong, press B and note it. Do not change the config at the rover.

## D. Stop tests (drive gently forward before each; the recorder times them)
12. SwB DOWN → stop and latch. SwB UP, Xbox LB reset, SwA UP then DOWN before driving again.
13. SwB MIDDLE → stop and latch. Reset as in 12.
14. Xbox **B** → stop and latch. Reset as in 12.
15. SwA UP → stop (disarm).
16. Let go of the stick → stop.
17. Turn the FlySky transmitter OFF → stop within 1.3 s. Turn it on; SwA must go UP then DOWN again.
18. Dashboard E-STOP → stop and latch.
    Optional, last: turn the Xbox off → stop and latch within 1.5 s.

## E. Restore
19. Latch with Xbox B. Press **SELECT XBOX** on the dashboard. FlySky SwA UP.
20. `systemctl --user stop atlas-s29-stop-recorder` (if still running), then `python3 stage29_morning.py analyze`.
21. Ask Claude to run **gate-off** (separate approval). Send the analyze output.

`analyze` reports OVERALL FAIL when the recording holds no stop events; that means nothing was tested, not a stop failure.

PASS only if every direction was correct by eye and `analyze` prints OVERALL PASS. Simulation results are not physical PASS results.
