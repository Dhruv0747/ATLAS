"""Re-run the established native QoS/shutdown scenarios (test_executor_qos_shutdown_native.exercise) against the
LIVE Dashboard overlay and the ExitStack-removal candidate, instead of the stock-generated variants.
Opt-in: isolated PC ROS domain 213, ROS_LOCALHOST_ONLY=1, ATLAS_LIVE_OVERLAY and ATLAS_CANDIDATE_OVERLAY paths."""
import hashlib, importlib.util, os, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qos_native', ROOT / 'tests/test_executor_qos_shutdown_native.py')
Q = importlib.util.module_from_spec(spec); spec.loader.exec_module(Q)
LIVE_SHA = '543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1'


class LiveVsCandidateQosShutdown(Q.QosShutdownTests):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '213':
            raise unittest.SkipTest('isolated PC ROS domain213 required')
        live, cand = os.environ.get('ATLAS_LIVE_OVERLAY'), os.environ.get('ATLAS_CANDIDATE_OVERLAY')
        if not (live and cand):
            raise unittest.SkipTest('overlay paths required')
        cls.live, cls.cand = Path(live).read_text(), Path(cand).read_text()
        assert hashlib.sha256(cls.live.encode()).hexdigest() == LIVE_SHA, 'live overlay hash mismatch'

    def sources(self):
        return [('live_543e4112', self.live), ('candidate_exitstack_removed', self.cand)]



if __name__ == '__main__':
    unittest.main(verbosity=2)
