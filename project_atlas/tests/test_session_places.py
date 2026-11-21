"""2026-11-14: places saved during a mapping session must not overwrite the accepted map's places (remaps 9-13 did)."""
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import atlas_map_acceptance_core as A  # noqa: E402
try:
    import atlas_mission_control as M
except Exception:  # pragma: no cover - ROS not available
    M = None

OLD = {"map_id": "old", "dhruv room": {"frame_id": "map", "x": 0.3, "y": -1.5, "map_id": "old"},
       "kitchen": {"frame_id": "map", "x": 2.0, "y": 1.0, "map_id": "old"}}


class Merge(unittest.TestCase):
    def test_session_places_override_only_for_this_session(self):
        session = {"dhruv room": {"frame_id": "map", "x": -0.8, "y": 0.2, "mapping_session_id": "s1"},
                   "hall": {"frame_id": "map", "x": 1.5, "y": -5.9, "mapping_session_id": "s0"}}
        merged = A.merge_session_places(OLD, session, "s1")
        self.assertEqual(merged["dhruv room"]["x"], -0.8)
        self.assertNotIn("hall", merged)                      # other session ignored
        self.assertEqual(merged["kitchen"], OLD["kitchen"])
        self.assertEqual(OLD["dhruv room"]["x"], 0.3)        # input not mutated

    def test_promotion_binds_session_places_and_keeps_old_bound(self):
        session = {"dhruv room": {"frame_id": "map", "x": -0.8, "y": 0.2, "mapping_session_id": "s1"}}
        merged = A.merge_session_places(OLD, session, "s1")
        home = {"x": 0, "y": 0, "mapping_session_id": "s1"}
        _, _, places = A.prepare_map_bound_metadata_values(
            home=home, seed=dict(home), places=merged, session_id="s1", new_map_id="new", old_map_id="old")
        self.assertEqual(places["dhruv room"]["map_id"], "new")
        self.assertNotIn("mapping_session_id", places["dhruv room"])
        self.assertEqual(places["kitchen"]["map_id"], "old")   # fails closed on the new map, as before

    def test_malformed_inputs(self):
        self.assertEqual(A.merge_session_places(None, None, "s"), {})
        self.assertEqual(A.merge_session_places(OLD, "x", "s"), OLD)


@unittest.skipIf(M is None, "atlas_mission_control needs ROS 2")
class SaveRouting(unittest.TestCase):
    def node(self, tmp, session):
        n = object.__new__(M.AtlasMissionControl)
        n.places_file = Path(tmp) / "named_places.json"
        n.session_places_file = Path(tmp) / "mapping_session_places.json"
        n.places_file.write_text(json.dumps(OLD))
        n.current_pose = lambda: {"frame_id": "map", "x": -0.8, "y": 0.2, "qz": 0.0, "qw": 1.0}
        n.active_mapping_session = lambda: session
        n.current_map_id = lambda: "old"
        n.status = lambda _t: None
        return n

    def test_in_session_save_leaves_accepted_places_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            n = self.node(tmp, {"id": "s1", "state": "active"})
            n.session_places_file.write_text(json.dumps({"hall": {"x": 9, "mapping_session_id": "stale"}}))
            n.save_named_place("dhruv room")
            self.assertEqual(json.loads(n.places_file.read_text()), OLD)
            sp = json.loads(n.session_places_file.read_text())
            self.assertEqual(sp["dhruv room"]["mapping_session_id"], "s1")
            self.assertNotIn("hall", sp)                     # stale session entry dropped

    def test_save_without_session_still_writes_accepted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            n = self.node(tmp, None)
            n.save_named_place("garage")
            self.assertEqual(json.loads(n.places_file.read_text())["garage"]["map_id"], "old")
            self.assertFalse(n.session_places_file.exists())


if __name__ == "__main__":
    unittest.main()
