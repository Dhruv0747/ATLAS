import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from atlas_amcl_replay_fidelity import map_overlap


class ReplayFidelityTest(unittest.TestCase):
    def test_saved_map_matches_ros_bottom_up_trinary_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "map.pgm"
            Image.fromarray(np.array([[0, 255], [205, 0]], dtype=np.uint8)).save(image)
            config = Path(directory) / "map.yaml"
            config.write_text("image: map.pgm\nresolution: 0.05\n"
                              "origin: [0, 0, 0]\nnegate: 0\n"
                              "occupied_thresh: 0.65\nfree_thresh: 0.25\n")
            origin = SimpleNamespace(position=SimpleNamespace(x=0., y=0.),
                                     orientation=SimpleNamespace(x=0., y=0., z=0., w=1.))
            msg = SimpleNamespace(info=SimpleNamespace(height=2, width=2, origin=origin),
                                  data=[0, 100, 100, 0])
            result = map_overlap(msg, config)
            self.assertEqual(result["different_cells"], 0)


if __name__ == "__main__":
    unittest.main()
