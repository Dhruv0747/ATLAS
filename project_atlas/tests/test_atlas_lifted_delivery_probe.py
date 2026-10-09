"""Pure safety contract for the rejected-only delivery probe."""

import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "atlas_lifted_delivery_probe.py"
SPEC = importlib.util.spec_from_file_location("atlas_lifted_delivery_probe", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DeliveryProbeTests(unittest.TestCase):
    def test_only_unrecognized_probe_operation_is_generated(self):
        self.assertEqual(MODULE.probe_request(1), '{"op":"probe","seq":1}')
        for sequence in (0, 11, True, "1"):
            with self.assertRaises(ValueError):
                MODULE.probe_request(sequence)

    def test_requires_stop_raw_disabled_and_all_outputs_zero(self):
        safe = {
            "state": "IDLE", "stop_latched": True,
            "raw_interface_enabled": False, "final_zero": True,
            "applied_motor_outputs": [0, 0, 0, 0],
        }
        self.assertTrue(MODULE.safe_idle(safe))
        for key, value in (
            ("state", "ARMED"), ("stop_latched", False),
            ("raw_interface_enabled", True), ("final_zero", False),
            ("applied_motor_outputs", [1, 0, 0, 0]),
        ):
            unsafe = dict(safe, **{key: value})
            self.assertFalse(MODULE.safe_idle(unsafe))


if __name__ == "__main__":
    unittest.main()
