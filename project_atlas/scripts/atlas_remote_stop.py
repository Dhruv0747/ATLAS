"""Pure state for the operator's latched software stop (not a hardware E-stop)."""
import math


class RemoteStop:
    def __init__(self, reset_button=4, reset_hold_s=2.0):
        self.latched = True
        self.last_rx = None
        self.neutral_since = None
        self.reason = 'REMOTE STOP: startup; neutral reset required'
        self.reset_button = reset_button
        self.reset_hold_s = reset_hold_s
        self.reset_armed = False
        self.reset_since = None
        self.reset_ready = False

    def update(self, axes, buttons, now):
        valid = (len(axes) >= 5 and len(buttons) > max(5, self.reset_button)
                 and all(math.isfinite(x) for x in axes))
        if not valid:
            self.latch('REMOTE STOP: invalid joystick')
            self.neutral_since = None
            return
        # A gap cannot be hidden by the first returning joystick packet.
        self.check(now)
        self.last_rx = now
        neutral = (all(abs(axes[i]) < 0.1 for i in (0, 1, 3, 4))
                   and not any(buttons))
        self.neutral_since = (self.neutral_since if self.neutral_since is not None
                              else now) if neutral else None
        if buttons[1]:  # Xbox B, verified on this controller on 2026-09-17.
            self.latch('REMOTE STOP: B pressed')
            return
        if not self.latched:
            return
        sticks_centred = all(abs(axes[i]) < 0.1 for i in (0, 1, 3, 4))
        other_buttons = any(v for i, v in enumerate(buttons)
                            if i != self.reset_button)
        if not sticks_centred or other_buttons:
            self.reset_armed = False
            self.reset_since = None
            self.reset_ready = False
        elif buttons[self.reset_button]:
            if self.reset_armed:
                if self.reset_since is None:
                    self.reset_since = now
                if now - self.reset_since >= self.reset_hold_s:
                    self.reset_ready = True
                    self.reason = 'REMOTE STOP: release LB to reset'
        else:
            # Clear only on release after a qualified hold. Never resume with
            # the reset/drive-enable button still pressed.
            if self.reset_ready:
                self.latched = False
                self.reason = 'REMOTE STOP: released by neutral LB hold'
            self.reset_armed = True
            self.reset_since = None
            self.reset_ready = False

    def latch(self, reason):
        self.latched = True
        self.reason = reason
        self.reset_armed = False
        self.reset_since = None
        self.reset_ready = False

    def check(self, now):
        if self.last_rx is None or now - self.last_rx > 0.5:
            self.latch('REMOTE STOP: joystick unavailable')
            self.neutral_since = None
        return self.latched

    def reset(self, now):
        self.check(now)
        if (self.neutral_since is None or now - self.neutral_since < 1.0):
            return False
        self.latched = False
        self.reason = 'REMOTE STOP: released by operator'
        return True
