#!/usr/bin/env python3
"""SIMULATION ONLY. Generic sensor/protected service; optional heartbeat file (e.g. fake LiDAR /scan)."""
import json, os, time
from pathlib import Path
hb = os.environ.get('SIM_HB')
if hb and Path(hb + '.stop').exists():
    Path(hb + '.stop').unlink()          # a restart clears the simulated fault
print(f"{os.environ.get('INVOCATION_ID', '-')} {time.time():.3f} sleeper {os.environ.get('SIM_NAME', '')} started", flush=True)
while True:
    if hb and not Path(hb + '.stop').exists():
        Path(hb + '.tmp').write_text(json.dumps({'wall': time.time(), 'pid': os.getpid()}))
        os.replace(hb + '.tmp', hb)
    time.sleep(0.1)
