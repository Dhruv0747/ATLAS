#!/usr/bin/env python3
"""One-axle small steering check; all wheels must be lifted, hands clear."""
import ast
import os
import sys
import time
from pathlib import Path
from Rosmaster_Lib import Rosmaster

axle = sys.argv[1].upper() if len(sys.argv) == 2 else ''
if axle not in ('FRONT', 'REAR'):
    raise SystemExit('Specify front or rear')
settings = {}
for node in ast.parse(Path(__file__).with_name('yahboom_base.py').read_text()).body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith(axle + '_STEER_'):
                settings[target.id] = ast.literal_eval(node.value)
channel = settings[axle + '_STEER_SERVO_ID']
center = settings[axle + '_STEER_CENTER']
low = settings[axle + '_STEER_RIGHT']
high = settings[axle + '_STEER_LEFT']
assert 0 <= low <= center - 8 < center + 8 <= high <= 180
port = os.environ['ATLAS_YAHBOOM_PORT']
if not Path(port).exists():
    raise SystemExit('Explicit motor board port missing')
bot = Rosmaster(car_type=5, com=port)
try:
    bot.set_motor(0, 0, 0, 0)
    for angle in (center, center + 8, center - 8, center):
        print(f'{axle} servo={channel} commanded={angle}; drive zero', flush=True)
        bot.set_pwm_servo(channel, angle)
        time.sleep(2.0)
finally:
    bot.set_motor(0, 0, 0, 0)
    bot.set_pwm_servo(channel, center)
    print(f'SAFE END: drive zero; {axle} saved centre commanded, not measured', flush=True)
