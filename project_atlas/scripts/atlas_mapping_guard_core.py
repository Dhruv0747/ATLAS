#!/usr/bin/env python3
"""Manual-mapping safeguard (pure logic, no ROS). 2026-11-13.

While a manual mapping session is drive-ready, mission control feeds this guard once per second. It trips when
the data SLAM depends on goes stale or the Jetson stays overloaded, because the eight rejected remaps of
2026-11-13 all had 1.1-1.7 m single-step map->odom jumps while the CPU was saturated (load 30-55, idle 2-4 %).

A trip is a STOP request only: mission control latches the existing mux remote stop (released by the operator
with the normal sticks-centred + LB 3 s gesture) and records the trip in the session, which the map acceptance
then rejects. The guard never commands motion and never releases a stop.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple


@dataclass
class GuardPolicy:
    max_scan_age_s: float = 1.5          # LiDAR /scan at ~7.5 Hz: 1.5 s = ~11 missed scans
    max_wheel_odom_age_s: float = 1.5    # /yahboom/odom at ~7-10 Hz
    max_slam_tf_gap_s: float = 4.0       # slam_toolbox republishes map->odom continuously (0.02 s period)
    overload_window_s: float = 20.0      # CPU must be saturated for this long (not a single spike)
    overload_min_idle_fraction: float = 0.04
    overload_min_load_per_core: float = 4.0
    startup_grace_s: float = 10.0        # after drive-ready, let subscriptions settle


@dataclass
class GuardSample:
    now: float                            # monotonic seconds
    scan_age_s: Optional[float]           # None = never received
    wheel_odom_age_s: Optional[float]
    slam_tf_age_s: Optional[float]
    cpu_idle_fraction: Optional[float]    # since the previous sample, from /proc/stat
    load1_per_core: Optional[float]


@dataclass
class MappingGuard:
    policy: GuardPolicy = field(default_factory=GuardPolicy)
    armed_at: Optional[float] = None
    tripped: Optional[str] = None         # reason while the trip condition persists
    trips: List[dict] = field(default_factory=list)
    _cpu: Deque[Tuple[float, float, float]] = field(default_factory=deque)

    def arm(self, now: float) -> None:
        self.armed_at, self.tripped = now, None
        self.trips.clear(); self._cpu.clear()

    def disarm(self) -> None:
        self.armed_at, self.tripped = None, None
        self._cpu.clear()

    def reasons(self, s: GuardSample) -> List[str]:
        p = self.policy
        out = []
        for label, age, limit in (("LiDAR scan", s.scan_age_s, p.max_scan_age_s),
                                  ("wheel odometry", s.wheel_odom_age_s, p.max_wheel_odom_age_s),
                                  ("SLAM map->odom", s.slam_tf_age_s, p.max_slam_tf_gap_s)):
            if age is None:
                out.append(f"{label} missing")
            elif age > limit:
                out.append(f"{label} stale {age:.1f}s>{limit:.1f}s")
        if s.cpu_idle_fraction is not None and s.load1_per_core is not None:
            self._cpu.append((s.now, s.cpu_idle_fraction, s.load1_per_core))
        while self._cpu and s.now - self._cpu[0][0] > p.overload_window_s:
            self._cpu.popleft()
        if self._cpu and s.now - self._cpu[0][0] >= p.overload_window_s - 1.5:
            idle = sum(c[1] for c in self._cpu) / len(self._cpu)
            load = min(c[2] for c in self._cpu)
            if idle < p.overload_min_idle_fraction and load > p.overload_min_load_per_core:
                out.append(f"CPU overload idle {idle*100:.0f}% load/core {load:.1f} for {p.overload_window_s:.0f}s")
        return out

    def update(self, s: GuardSample) -> Optional[str]:
        """Return a reason string exactly once when a new trip starts; otherwise None."""
        if self.armed_at is None:
            return None
        r = self.reasons(s)
        if s.now - self.armed_at < self.policy.startup_grace_s:
            return None
        if not r:
            self.tripped = None          # condition cleared; a later recurrence trips again
            return None
        if self.tripped is not None:
            return None
        self.tripped = "; ".join(r)
        self.trips.append({"monotonic": round(s.now, 3), "reason": self.tripped})
        return self.tripped


def cpu_idle_fraction(prev: Optional[List[int]], cur: List[int]) -> Optional[float]:
    """Idle fraction between two /proc/stat 'cpu' rows (user nice system idle iowait irq softirq steal ...)."""
    if prev is None:
        return None
    d = [b - a for a, b in zip(prev, cur)]
    total = sum(d[:8])
    return None if total <= 0 else (d[3] + d[4]) / total
