#!/usr/bin/env python3
"""Operator-supervised lifted steering check; no traction commands except zero."""
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
            if isinstance(target,ast.Name) and target.id in ('FRONT_STEER_SERVO_ID','FRONT_STEER_CENTER'):
                values[target.id]=ast.literal_eval(statement.value)
channel=values['FRONT_STEER_SERVO_ID']
center=values['FRONT_STEER_CENTER']
assert channel in (1,2) and 10<=center<=170
sys.path.insert(0,str(directory))
from Rosmaster_Lib import Rosmaster
def interrupted(*_):
    raise KeyboardInterrupt()
signal.signal(signal.SIGTERM,interrupted)
bot=Rosmaster(car_type=5,com='/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0')
try:
    bot.set_motor(0,0,0,0)
    bot.set_pwm_servo(channel,center)
    time.sleep(.5)
    print(f'FRONT channel={channel}: center={center}, test={center+10}',flush=True)
    bot.set_pwm_servo(channel,center+10)
    time.sleep(2.0)
finally:
    bot.set_motor(0,0,0,0)
    bot.set_pwm_servo(channel,center)
    print(f'STOP: traction zero; front commanded back to {center}',flush=True)
