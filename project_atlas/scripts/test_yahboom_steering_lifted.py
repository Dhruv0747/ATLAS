#!/usr/bin/env python3
"""Small front/rear steering test. Keep hands clear of the linkage."""
import time
from Rosmaster_Lib import Rosmaster

CENTER = 90
LEFT_TEST = 82
RIGHT_TEST = 98

bot = Rosmaster(car_type=5, com="/dev/yahboom")
bot.create_receive_threading()
bot.set_car_type(5)
bot.set_auto_report_state(True, False)
time.sleep(1.5)

try:
    bot.set_motor(0, 0, 0, 0)
    bot.set_pwm_servo(1, CENTER)
    bot.set_pwm_servo(2, CENTER)
    time.sleep(1.0)

    print("FRONT steering: centre -> left -> right -> centre", flush=True)
    bot.set_pwm_servo(1, LEFT_TEST)
    time.sleep(1.0)
    bot.set_pwm_servo(1, RIGHT_TEST)
    time.sleep(1.0)
    bot.set_pwm_servo(1, CENTER)
    time.sleep(0.8)

    print("REAR steering: centre -> left -> right -> centre", flush=True)
    bot.set_pwm_servo(2, LEFT_TEST)
    time.sleep(1.0)
    bot.set_pwm_servo(2, RIGHT_TEST)
    time.sleep(1.0)
    bot.set_pwm_servo(2, CENTER)
    time.sleep(0.8)
finally:
    bot.set_motor(0, 0, 0, 0)
    bot.set_pwm_servo(1, CENTER)
    bot.set_pwm_servo(2, CENTER)
    print("SAFE END: drive zero, front/rear steering centred", flush=True)
