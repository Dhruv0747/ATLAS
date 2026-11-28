# Astra calibration guide: unlocking RGB-D 3D Mapping

**Time:** about 30 minutes. **Rover:** parked, E-STOP latched, the whole time. Nothing moves; only the camera runs.

RGB-D Mapping stays locked until the Astra has a calibration that is checked against real tape-measured distances.
Claude runs the tool; your job is the physical part (Steps 1, 3 and 5).

---

## Step 1: Print and prepare the board (you)

1. Print `atlas_checkerboard_A4_25mm_9x6.pdf` on A4 at **100 % / Actual size**. Do **not** use "Fit to page".
2. Check the printout with a ruler:
   - the line under the board must be **exactly 100 mm**;
   - one square must be **25.0 mm**. If it isn't, tell Claude the real size (for example 24.6 mm).
3. Glue or tape it **completely flat** onto stiff card, foam board or a clipboard. A bent board ruins the result.
4. Matte paper is best. Avoid glossy or laminated sheets, because reflections confuse the infrared camera.

## Step 2: Prepare the room

- **Light:** the depth camera sees **infrared**. Daylight from a window, or an ordinary filament/halogen bulb, helps a
  lot. LED lights give almost no infrared.
- **Optional:** if the board isn't being detected, cover the Astra's **laser projector** with a finger or a bit of tape
  during capture. That's the small window that is **not** the colour camera, normally the left-most one. Remove it
  afterwards.
- Clear about 1.5 m of space in front of the rover.

## Step 3: Show the board (you, about 5 minutes)

Claude runs `capture`. While it runs:

1. Hold the board **0.5 m to 1.0 m** from the Astra, with all of it visible.
2. **Hold still for about 1 second**, then move to a new pose. Claude sees "accepted view 7/22" and so on.
3. Cover the whole picture: put the board in the **four corners**, the **edges** and the **centre** of the camera's view,
   not just the middle. (The test run was rejected because it only covered 47 % of the image; at least 60 % is needed.)
4. **Tilt it:** left/right, up/down, and rotate it a little in some poses. Mix near and far.
5. About 22 good views are needed. If the camera session ends (each one lasts 60 s), Claude restarts it; just keep going.

**Pass mark** (set in your repo): training error < 0.5 px, held-out error < 0.8 px, coverage ≥ 60 %.

## Step 4: Claude computes the calibration

- If it passes, Claude converts it to the depth camera's 160 × 120 resolution and saves it as a **candidate**. It is
  **not active yet**.
- If it fails, Claude tells you why (usually "coverage" or "error"), and you repeat Step 3 with more varied poses.

## Step 5: Physical distance check (you, about 10 minutes)

This proves the 3D numbers are real.

1. Use a **flat, matte, light-coloured** surface at least about 40 × 30 cm, such as a large piece of cardboard or a wall.
2. Put it **straight in front of** the Astra (facing it squarely, not tilted). Using a **tape measure**, measure the
   distance from the **front glass of the Astra** to the surface.
3. Tell Claude the distance, for example "1.000 m". Claude runs `measure`.
4. Repeat at **at least 2 different distances**. Recommended: **0.80 m**, **1.20 m** and **1.60 m**.

**Pass mark per distance:** the depth must be within **10 mm or 1 % (whichever is larger)** of your tape measure, with
fewer than 10 % missing pixels, and the surface must look flat (≤ 5 mm RMS at 1 m).

## Step 6: Finalize, then install (your approval)

- Claude runs `finalize`. Only if **every** check passes does it produce a validated document.
- **Installing** that document makes it the rover's live calibration and unlocks RGB-D Mapping. Claude asks you
  before doing this. The old file, if any, is kept as a backup.

---

**Safety:** the camera only starts through the existing stationary guard (E-STOP latched, zero commands, CPU < 75 %).
No images are saved: only corner coordinates and distance statistics are kept. During the session the camera bridge
(`atlas-foxglove`) runs, and the voice companion and localization monitor are paused. Claude restores both afterwards.
