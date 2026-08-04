#!/usr/bin/env python3
"""Short individual Yahboom motor test. Use only with every wheel lifted."""
import time
import sys
from Rosmaster_Lib import Rosmaster

PWM = int(sys.argv[1]) if len(sys.argv) > 1 else 50
if not -70 <= PWM <= 70 or PWM == 0:
    raise SystemExit('PWM must be between -70 and 70, excluding zero')
RUN_SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 0.50
REST_SECONDS = float(sys.argv[3]) if len(sys.argv) > 3 else 0.50
if not 0.2 <= RUN_SECONDS <= 2.0 or not 0.2 <= REST_SECONDS <= 5.0:
    raise SystemExit('run/rest seconds outside safe test range')
MOTOR = int(sys.argv[4]) if len(sys.argv) > 4 else 0
if MOTOR not in (0, 1, 2, 3, 4):
    raise SystemExit('motor must be 0 for all or 1-4 for one motor')

bot = Rosmaster(car_type=5, com="/dev/yahboom")
bot.create_receive_threading()
bot.set_car_type(5)
bot.set_auto_report_state(True, False)
time.sleep(1.5)

print(f"firmware={bot.get_version()} battery={bot.get_battery_voltage():.1f}V")
try:
    bot.set_motor(0, 0, 0, 0)
    time.sleep(0.5)
    indices = range(4) if MOTOR == 0 else [MOTOR - 1]
    for index in indices:
        before = bot.get_motor_encoder()
        pwm = [0, 0, 0, 0]
        pwm[index] = PWM
        print(f"M{index+1} START pwm={PWM} before={before}", flush=True)
        bot.set_motor(*pwm)
        time.sleep(RUN_SECONDS)
        bot.set_motor(0, 0, 0, 0)
        time.sleep(REST_SECONDS)
        after = bot.get_motor_encoder()
        delta = tuple(after[channel] - before[channel] for channel in range(4))
        print(f"M{index+1} STOP after={after} delta={delta}", flush=True)
finally:
    bot.set_motor(0, 0, 0, 0)
    print("SAFETY STOP: ALL MOTOR OUTPUTS ZERO", flush=True)
