# ATLAS voice-speaker protocol v2

Protocol v2 is backward compatible with the deployed protocol v1 and adds:

- `0x85`: streaming PCM S16LE, mono, 16 kHz playback
- `STATE CALL`: red privacy LED and unmuted streaming output

The ESP32 continues publishing microphone packets while stream packets play.
Only `atlas_intercom.py` may send `0x85`; the mode owner first stops the normal
AI voice service so two processes can never open the same USB serial device.
