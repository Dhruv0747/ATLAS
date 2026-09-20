# USB role discovery — 2026-09-19

GPS, IM10A and Yahboom use CH340 adapters without distinct serial numbers.
Their shared by-id name and ttyUSB numbers cannot identify their roles.
The new atlas_usb_identity helper passively validates checksummed protocols,
skips occupied ports, serializes discovery, rejects ambiguous matches and hands
the already-verified serial handle to the driver. No discovery query is sent.

## Deployment

- GPS and IM10A auto_usb service overrides installed on Jetson and restarted.
- GPS verified on ttyUSB2: 75 valid NMEA, 0 invalid, 0 reconnects at initial
  post-fix snapshot. NMEA_LIVE_NO_FIX is communication, not satellite lock.
- IM10A live on dashboard; navigation fusion remains uncommissioned.
- Yahboom optional verified-handle support and service override are source-only
  / staged. NOT activated on Jetson: existing motor process was left unchanged.
  A stationary motor-power-off commissioning session is still required.
- Existing unique USB identities for UNO, speaker, LiDAR and modem unchanged.
- No motor, steering, navigation or goal commands issued.

GPS initially interpreted empty nonblocking PySerial reads as EOF; corrected to
use PySerial read semantics. Actual disconnect exceptions and existing freshness
checks remain enabled.

## Tests and limits

16 identity/transport tests passed on Jetson (4 Linux-only tests skipped on
Windows). Existing motor mapping 4, encoder selection 14, serial lines 6 passed.
Physical USB swaps and a full cold boot have NOT yet been verified.
Yahboom discovery requires existing passive telemetry; a silent controller is
not blindly queried or enabled. Identical duplicate devices are rejected.
This does not repair power loss, bad cables or USB hub faults, nor automatically
authorize motion after reconnection. Do not swap motor USB while driving.
