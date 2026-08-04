#!/usr/bin/env python3
"""Short individual Yahboom motor test. Use only with every wheel lifted."""
import time
from Rosmaster_Lib import Rosmaster

PWM = 90
RUN_SECONDS = 0.35

bot = Rosmaster(car_type=5, com="/dev/yahboom")
bot.create_receive_threading()
bot.set_car_type(5)
bot.set_auto_report_state(True, False)
time.sleep(1.5)

print(f"firmware={bot.get_version()} battery={bot.get_battery_voltage():.1f}V")
try:
    bot.set_motor(0, 0, 0, 0)
    time.sleep(0.5)
    for index in range(4):
        before = bot.get_motor_encoder()
        pwm = [0, 0, 0, 0]
        pwm[index] = PWM
        print(f"M{index+1} START pwm={PWM} before={before}", flush=True)
        bot.set_motor(*pwm)
        time.sleep(RUN_SECONDS)
        bot.set_motor(0, 0, 0, 0)
        time.sleep(0.5)
        after = bot.get_motor_encoder()
        delta = tuple(after[channel] - before[channel] for channel in range(4))
        print(f"M{index+1} STOP after={after} delta={delta}", flush=True)
finally:
    bot.set_motor(0, 0, 0, 0)
    print("SAFETY STOP: ALL MOTOR OUTPUTS ZERO", flush=True)
