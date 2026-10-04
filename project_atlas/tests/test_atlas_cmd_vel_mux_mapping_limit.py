import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
MUX_PATH = ROOT / "scripts" / "atlas_cmd_vel_mux.py"


def twist(linear_x=0.0, angular_z=0.0):
    return NS(
        linear=NS(x=linear_x, y=0.0, z=0.0),
        angular=NS(x=0.0, y=0.0, z=angular_z),
    )


def extracted_mux(clock):
    """Compile the command conditioner without importing ROS dependencies."""

    tree = ast.parse(MUX_PATH.read_text(encoding="utf-8"))
    mux = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AtlasCmdVelMux"
    )
    mux.bases = []
    mux.decorator_list = []
    mux.body = [
        node
        for node in mux.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"copy_twist", "moving", "on_command"}
    ]
    scope = {
        "time": NS(monotonic=clock),
        "Twist": lambda: twist(),
    }
    exec(compile(ast.Module(body=[mux], type_ignores=[]), str(MUX_PATH), "exec"), scope)
    return scope["AtlasCmdVelMux"]


class MappingRemoteLimitTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        mux_class = extracted_mux(lambda: self.now)
        self.mux = mux_class()
        self.mux.remote_stop = NS(check=lambda _now: False)
        self.mux.hold_remote_stop = Mock()
        self.mux.manual_only = False
        self.mux.commission_until = 0.0
        self.mux.channels = {
            "REMOTE": NS(last_rx=0.0, command=twist(), engaged=False),
        }
        self.mux.remote_linear_deadband = 0.06
        self.mux.remote_angular_deadband = 0.12
        self.mux.remote_steer_hold_s = 0.35
        self.mux.mapping_remote_max_linear = 0.30
        self.mux.mapping_remote_max_angular = 1.20
        self.mux._remote_held_yaw = 0.0
        self.mux._remote_last_steer_rx = 0.0
        self.mux._remote_raw_steer = 0.0
        self.mux._remote_raw_steer_rx = 0.0
        self.mux.active_name = None
        self.mux.publish_stop = Mock()

    def test_mapping_caps_speed_but_keeps_commissioned_steering(self):
        self.mux.operating_mode = "MAPPING"
        self.mux.on_command("REMOTE", twist(0.52, 1.20))

        command = self.mux.channels["REMOTE"].command
        self.assertAlmostEqual(command.linear.x, 0.30)
        self.assertAlmostEqual(command.angular.z, 1.20)
        self.assertTrue(self.mux.channels["REMOTE"].engaged)

        self.mux.operating_mode = "LOCALIZATION"
        self.mux.on_command("REMOTE", twist(0.52, 1.20))
        command = self.mux.channels["REMOTE"].command
        self.assertAlmostEqual(command.linear.x, 0.52)
        self.assertAlmostEqual(command.angular.z, 1.20)

    def test_mapping_limits_are_symmetric_in_reverse_and_turn_direction(self):
        self.mux.operating_mode = "MAPPING"
        self.mux.on_command("REMOTE", twist(-0.52, -1.20))

        command = self.mux.channels["REMOTE"].command
        self.assertAlmostEqual(command.linear.x, -0.30)
        self.assertAlmostEqual(command.angular.z, -1.20)

    def test_mapping_limit_preserves_small_deliberate_commands(self):
        self.mux.operating_mode = "MAPPING"
        self.mux.on_command("REMOTE", twist(0.18, 0.30))

        command = self.mux.channels["REMOTE"].command
        self.assertAlmostEqual(command.linear.x, 0.18)
        self.assertAlmostEqual(command.angular.z, 0.30)


if __name__ == "__main__":
    unittest.main()
