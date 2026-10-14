"""CDR and timing checks for the read-only encoder bag audit."""
import importlib.util
import json
import struct
import unittest
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "tools/diagnostics/encoder_packet_timing.py"
SPEC = importlib.util.spec_from_file_location("encoder_packet_timing", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EncoderPacketTimingTests(unittest.TestCase):
    def test_headerless_int32_count_jump_after_receipt_gap(self):
        rows = [(0, b"\0\1\0\0" + struct.pack("<i", 10)),
                (100_000_000, b"\0\1\0\0" + struct.pack("<i", 10)),
                (600_000_000, b"\0\1\0\0" + struct.pack("<i", 16))]
        result = MODULE.audit_series(rows)
        self.assertEqual(result["messages"], 3)
        self.assertEqual(result["gaps_over_350ms"], 1)
        self.assertEqual(result["count_jumps_after_gap"], [6])
        self.assertEqual(result["repeated_count_intervals"], 1)

    def test_encoder_update_separates_sequence_loss_from_stale_sample(self):
        def row(stamp, sequence, age, fresh):
            body = json.dumps({"sequence": sequence, "stamp_ns": stamp,
                               "packet_age_s": age, "integration_dt_s": 0.1,
                               "packet_fresh": fresh, "source": "wheel_encoder_delta_4ws"}).encode()
            return stamp + 5_000_000, b"\0\1\0\0" + struct.pack("<I", len(body) + 1) + body + b"\0"
        result = MODULE.audit_updates([row(0, 10, 0.02, True),
                                       row(100_000_000, 12, 0.41, False)])
        self.assertEqual(result["sequence_gaps"], 1)
        self.assertEqual(result["packet_stale_samples"], 1)
        self.assertEqual(result["bag_receipt_minus_publish_p95_s"], 0.005)


if __name__ == "__main__":
    unittest.main()
