import importlib.util
import sqlite3
import tempfile
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "atlas_visual_cloud_server.py"


class VisualCloudServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("atlas_visual_cloud_server_test", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_adaptive_interval(self):
        m = self.module
        self.assertEqual(m.persistence_interval({"system": {"load": [0, 0, 0]}}), m.NORMAL_PERSIST_S)
        self.assertEqual(m.persistence_interval({"system": {"load": [m.HEAVY_LOAD, 0, 0]}}), m.HEAVY_PERSIST_S)
        mapping = {"traffic": {"/atlas/mission_status": {"value": "MAPPING ACTIVE"}}}
        self.assertEqual(m.persistence_interval(mapping), m.HEAVY_PERSIST_S)

    def test_live_latest_updates_when_history_is_throttled(self):
        m = self.module
        with tempfile.TemporaryDirectory() as directory:
            m.DB = Path(directory) / "history.sqlite3"
            m.LATEST.clear()
            m.LAST_PERSIST = 0.0
            m.NORMAL_PERSIST_S = 60.0
            m.HEAVY_PERSIST_S = 60.0
            m.store({"robot_id": "atlas", "observed_at": 1, "system": {"load": [0, 0, 0]}})
            m.store({"robot_id": "atlas", "observed_at": 2, "system": {"load": [0, 0, 0]}})
            self.assertEqual(m.LATEST["atlas"]["observed_at"], 2)
            db = sqlite3.connect(m.DB)
            count = db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            db.close()
            self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
