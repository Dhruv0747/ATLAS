"""Linux-only isolated child tests; no ROS or hardware."""
import os
import subprocess
import sys
import time
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
if sys.platform=='linux':from bounded_process import OwnedPacer


@unittest.skipUnless(sys.platform=='linux','POSIX process-group pacing')
class PacerTests(unittest.TestCase):
    def test_rejects_own_process(self):
        class P:pid=os.getpid()
        with self.assertRaises(ValueError):OwnedPacer(P())
    def test_child_is_resumed_after_close(self):
        p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.2);print("ok")'],start_new_session=True,stdout=subprocess.PIPE)
        try:
            q=OwnedPacer(p).start();time.sleep(.15);q.close();out=p.communicate(timeout=2)[0];self.assertIn(b'ok',out)
        finally:
            if p.poll() is None:p.kill();p.wait()
    def test_busy_child_is_paced(self):
        code='import time,json;w=time.monotonic();c=time.process_time();\nwhile time.monotonic()-w<1: pass\nprint(json.dumps({"cpu":time.process_time()-c,"wall":time.monotonic()-w}))'
        p=subprocess.Popen([sys.executable,'-c',code],start_new_session=True,stdout=subprocess.PIPE)
        q=OwnedPacer(p).start()
        try:
            import json
            out=p.communicate(timeout=4)[0];q.close();row=json.loads(out);self.assertLess(row['cpu']/row['wall'],.55)
        finally:
            q.close()
            if p.poll() is None:p.kill();p.wait()
