"""Publisher metadata only. No ROS entities or control decisions."""
import os
import time
from pathlib import Path

class Provenance:
    def __init__(self):
        self.identity = None
        self.sequence = 0
        self.command = None
        try:
            raw = Path('/proc/self/stat').read_text()
            self.identity = dict(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                                 pid=os.getpid(), start_ticks=int(raw.rsplit(')', 1)[1].split()[19]))
        except (OSError, ValueError, IndexError):
            pass  # Missing metadata must reject consumers, never interrupt control.

    def stamp(self, observed_mono):
        self.sequence += 1
        return dict(self.identity, sequence=self.sequence, observed_mono=observed_mono) if self.identity else None

    def sent(self, msg, stamp):
        try:
            values = [msg.linear.x,msg.linear.y,msg.linear.z,msg.angular.x,msg.angular.y,msg.angular.z]
            sequence = self.command['sequence']+1 if self.command else 1
            self.command = dict(values=values, published_mono=stamp, sequence=sequence)
        except Exception:
            self.command = None
