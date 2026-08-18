#!/usr/bin/env python3
"""Dependency-free alert state machine for ATLAS mobile notifications."""

from dataclasses import dataclass


@dataclass
class BatteryAlertState:
    low_threshold: float = 20.0
    low_reset_threshold: float = 25.0
    full_threshold: float = 99.0
    full_reset_threshold: float = 95.0
    full_samples_required: int = 3
    low_alerted: bool = False
    full_alerted: bool = False
    full_samples: int = 0

    def update(self, percent: float) -> list[str]:
        """Return newly-triggered alert names for a valid BMS percentage."""
        value = float(percent)
        if not 0.0 <= value <= 100.0:
            return []

        alerts: list[str] = []
        if value >= self.low_reset_threshold:
            self.low_alerted = False
        if value <= self.full_reset_threshold:
            self.full_alerted = False

        if value <= self.low_threshold and not self.low_alerted:
            self.low_alerted = True
            alerts.append("battery_low")

        if value >= self.full_threshold:
            self.full_samples += 1
        else:
            self.full_samples = 0
        if (
            self.full_samples >= self.full_samples_required
            and not self.full_alerted
        ):
            self.full_alerted = True
            alerts.append("battery_full")
        return alerts
