# Stationary calibration measurement sheet

Fill actual measurements; blanks remain UNKNOWN. Do not move the rover or alter
wiring. This sheet authorizes no camera activation. Existing recordings may be
replayed without a new checkerboard session when their metadata is sufficient.

| Item | Actual measured value / uncertainty |
|---|---|
| Camera serial, date, operator | |
| RGB/depth/IR exact resolution and encoding | |
| Checkerboard inner corners (columns x rows) | |
| Measured width across N squares / N | |
| Measured height across N squares / N | |
| Target flatness, board dimensions, print scaling | |
| Distance reference: optical origin or named housing surface | |
| Matte target near distance and uncertainty | |
| Matte target middle distance and uncertainty | |
| Matte target far distance and uncertainty | |
| Target plane orientation/ROI | |
| Documented base_link physical origin | |
| Camera reference x forward, y left, z up (metres) | |
| Mount roll, pitch, yaw; units and axis convention | |
| Camera reference to optical-origin offset/uncertainty | |
| Photograph/sketch reference (optional; privacy-reviewed) | |

Example target only:9x6 inner corners,10x7 squares,nominal30mm squares on rigid
matte A3 backing. Use measured square dimensions, not nominal values. Suggested
depth positions0.8/1.0/1.5m only if supported and physically measurable; do not
populate measurements from these suggestions. Existing calibration solver needs
>=12 diverse views and held-out validation. One60s session may be insufficient.

Capture proposal:60s total from admission, early10s no-stream abort,128MiB SQLite
database page cap plus up to another database-sized rollback journal allocation.
Reserve>=1GiB free before start. These capture storage settings are separate from
the future2GiB map-session target. No continuous recording or automatic retry.
