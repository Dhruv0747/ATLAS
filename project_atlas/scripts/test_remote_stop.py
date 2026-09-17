import unittest
from atlas_remote_stop import RemoteStop


class StopTests(unittest.TestCase):
    def neutral(self, gate, start=0):
        for i in range(25):
            gate.update([0]*8, [0]*11, start+i*.05)

    def test_startup_and_reset(self):
        gate = RemoteStop()
        self.assertTrue(gate.check(0))
        self.neutral(gate)
        self.assertTrue(gate.reset(1.2))

    def test_b_latched(self):
        gate = RemoteStop()
        self.neutral(gate)
        gate.reset(1.2)
        gate.update([0]*8, [0, 1]+[0]*9, 1.25)
        self.assertTrue(gate.check(1.25))
        self.neutral(gate, 1.3)
        self.assertTrue(gate.latched)

    def test_no_reset_with_stick_or_button(self):
        for axes, buttons in (([0, 1, 0, 0, 0], [0]*11),
                              ([0]*8, [0]*4+[1]+[0]*6)):
            gate = RemoteStop()
            self.neutral(gate)
            gate.update(axes, buttons, 1.25)
            self.assertFalse(gate.reset(1.25))

    def test_disconnect_latches_on_reconnect(self):
        gate = RemoteStop()
        self.neutral(gate)
        gate.reset(1.2)
        gate.update([0]*8, [0]*11, 3)
        self.assertTrue(gate.latched)
        self.assertFalse(gate.reset(3))

    def test_invalid(self):
        gate = RemoteStop()
        self.neutral(gate)
        gate.reset(1.2)
        gate.update([float('nan')]*8, [0]*11, 1.25)
        self.assertTrue(gate.latched)

    def hold_reset(self, gate, start=1.25, duration=2.1, axes=None, extra=None):
        buttons = [0]*11
        buttons[gate.reset_button] = 1
        if extra is not None:
            buttons[extra] = 1
        for i in range(round(duration/.05)+1):
            gate.update(axes or [0]*8, buttons, start+i*.05)

    def test_hold_requires_release(self):
        gate = RemoteStop()
        self.neutral(gate)
        self.hold_reset(gate)
        self.assertTrue(gate.latched)
        self.assertTrue(gate.reset_ready)
        gate.update([0]*8, [0]*11, 3.4)
        self.assertFalse(gate.latched)

    def test_short_hold_does_not_reset(self):
        gate = RemoteStop()
        self.neutral(gate)
        self.hold_reset(gate, duration=1)
        gate.update([0]*8, [0]*11, 2.3)
        self.assertTrue(gate.latched)

    def test_unsafe_hold_does_not_reset(self):
        for extra in (1, 7, 5, 0):
            gate = RemoteStop()
            self.neutral(gate)
            self.hold_reset(gate, extra=extra)
            gate.update([0]*8, [0]*11, 3.4)
            self.assertTrue(gate.latched)
        gate = RemoteStop()
        self.neutral(gate)
        self.hold_reset(gate, axes=[0, .5, 0, 0, 0, 0, 0, 0])
        gate.update([0]*8, [0]*11, 3.4)
        self.assertTrue(gate.latched)

    def test_lb_held_at_boot_or_reconnect_does_not_reset(self):
        gate = RemoteStop()
        self.hold_reset(gate)
        gate.update([0]*8, [0]*11, 3.4)
        self.assertTrue(gate.latched)
        self.hold_reset(gate, start=5)
        gate.update([0]*8, [0]*11, 7.15)
        self.assertTrue(gate.latched)

    def test_b_cancels_ready_reset(self):
        gate = RemoteStop()
        self.neutral(gate)
        self.hold_reset(gate)
        gate.update([0]*8, [0, 1]+[0]*9, 3.4)
        gate.update([0]*8, [0]*11, 3.45)
        self.assertTrue(gate.latched)


if __name__ == '__main__':
    unittest.main()
