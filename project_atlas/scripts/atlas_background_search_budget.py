"""Cooperative pacing for a non-control diagnostic search, not a safety gate.

Preserves search work/results and its original wall deadline. Only the calling
worker sleeps; ROS callbacks, sensors and control owners are not throttled.
"""
import time


class BackgroundSearchBudget:
    def __init__(self, check_deadline, *, fraction=0.10, wall=time.monotonic,
                 cpu=time.thread_time, pause=time.sleep):
        if not 0 < fraction <= 1:
            raise ValueError('CPU fraction must be in (0, 1]')
        self.check_deadline = check_deadline
        self.fraction, self.wall, self.cpu, self.pause = fraction, wall, cpu, pause
        self.wall_start, self.cpu_start = wall(), cpu()

    def __call__(self):
        self.check_deadline()
        while True:
            delay = ((self.cpu() - self.cpu_start) / self.fraction
                     - (self.wall() - self.wall_start))
            if delay <= 0.001:
                break
            self.pause(min(delay, 0.05))
            self.check_deadline()
        self.check_deadline()
