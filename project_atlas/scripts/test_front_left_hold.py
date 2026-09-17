#!/usr/bin/env python3
"""Supervised incremental front-left clearance test; no calibration changes."""
import ast
from pathlib import Path
import signal
import sys
import time
directory=Path('/home/jetson/project_atlas/scripts')
values={}
for statement in ast.parse((directory/'yahboom_base.py').read_text()).body:
    if isinstance(statement,ast.Assign):
        for target in statement.targets:
            if isinstance(target,ast.Name) and target.id in ('FRONT_STEER_SERVO_ID','FRONT_STEER_CENTER','FRONT_STEER_LEFT'):
                values[target.id]=ast.literal_eval(statement.value)
channel=values['FRONT_STEER_SERVO_ID']
center=values['FRONT_STEER_CENTER']
limit=values['FRONT_STEER_LEFT']
assert channel==2 and center==81 and limit==121, 'Saved configuration changed; recheck before test'
test_limit=limit+10
sys.path.insert(0,str(directory))
from Rosmaster_Lib import Rosmaster
def interrupted(*_):
    raise KeyboardInterrupt()
signal.signal(signal.SIGTERM,interrupted)
bot=Rosmaster(car_type=5,com='/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0')
try:
    bot.set_motor(0,0,0,0)
    for angle in range(center,test_limit,2):
        bot.set_pwm_servo(channel,angle)
        time.sleep(.1)
    bot.set_pwm_servo(channel,test_limit)
    print(f'TEST: front channel {channel} at {test_limit} for 2 seconds; old limit remains {limit}',flush=True)
    time.sleep(2)
finally:
    bot.set_motor(0,0,0,0)
    bot.set_pwm_servo(channel,center)
    print(f'END: traction zero; front return commanded to {center}',flush=True)
