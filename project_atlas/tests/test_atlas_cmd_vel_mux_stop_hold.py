import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
MUX_PATH = ROOT / "scripts" / "atlas_cmd_vel_mux.py"


class String:
    def __init__(self, data=""):
        self.data = data


def twist(linear_x=0.0, angular_z=0.0):
    return NS(
        linear=NS(x=linear_x, y=0.0, z=0.0),
        angular=NS(x=0.0, y=0.0, z=angular_z),
    )


def extracted_mux(clock):
    """Compile only stop-hold methods without importing ROS or hardware code."""
    tree = ast.parse(MUX_PATH.read_text(encoding="utf-8"))
    constants = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id.startswith("REMOTE_STOP_")
            ):
                constants[target.id] = ast.literal_eval(node.value)
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
        and node.name in {"moving", "hold_remote_stop", "reset_remote_stop"}
    ]
    scope = dict(
        time=NS(monotonic=clock),
        Twist=twist,
        String=String,
        **constants,
    )
    exec(compile(ast.Module(body=[mux], type_ignores=[]), str(MUX_PATH), "exec"), scope)
    return scope["AtlasCmdVelMux"], constants


class RemoteStopHoldTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        mux_class, self.constants = extracted_mux(lambda: self.now)
        self.mux = mux_class()
        self.mux.remote_stop = NS(
            latched=True,
            reason="REMOTE STOP: joystick unavailable",
        )
        self.mux.channels = {
            "REMOTE": NS(engaged=True, command=twist(0.2)),
            "NAV2": NS(engaged=True, command=twist(0.1)),
        }
        self.mux.commission_until = 30.0
        self.mux._remote_held_yaw = 0.4
        self.mux.active_name = "NAV2"
        self.mux.last_sent = twist(0.1)
        self.mux.output = Mock()
        self.mux.safety_output = Mock()
        self.mux.publish_mode = Mock()
        self.mux._remote_stop_hold_latched = None
        self.mux._remote_stop_hold_reason = None
        self.mux._remote_stop_last_zero = float("-inf")
        self.mux._remote_stop_last_status = float("-inf")

    def test_first_latch_stops_immediately_and_flushes_all_sources(self):
        self.mux.hold_remote_stop()

        self.mux.output.publish.assert_called_once()
        self.assertFalse(self.mux.moving(self.mux.last_sent))
        self.assertEqual(self.mux.active_name, None)
        self.assertEqual(self.mux.commission_until, 0.0)
        self.assertEqual(self.mux._remote_held_yaw, 0.0)
        self.assertTrue(all(not channel.engaged for channel in self.mux.channels.values()))
        self.assertTrue(
            all(
                not self.mux.moving(channel.command)
                for channel in self.mux.channels.values()
            )
        )
        self.assertEqual(
            self.mux.safety_output.publish.call_args.args[0].data,
            "REMOTE STOP: joystick unavailable",
        )
        self.mux.publish_mode.assert_called_once_with()

    def test_unchanged_latch_rate_limits_zero_status_and_mode(self):
        self.mux.hold_remote_stop()
        self.mux.hold_remote_stop()
        self.now += 0.05
        self.mux.hold_remote_stop()

        self.assertEqual(self.mux.output.publish.call_count, 1)
        self.assertEqual(self.mux.safety_output.publish.call_count, 1)
        self.assertEqual(self.mux.publish_mode.call_count, 1)

        self.now = 10.201
        self.mux.hold_remote_stop()
        self.assertEqual(self.mux.output.publish.call_count, 2)
        self.assertEqual(self.mux.safety_output.publish.call_count, 1)
        self.assertEqual(self.mux.publish_mode.call_count, 1)

        self.now = 11.001
        self.mux.hold_remote_stop()
        self.assertEqual(self.mux.output.publish.call_count, 3)
        self.assertEqual(self.mux.safety_output.publish.call_count, 2)
        self.assertEqual(self.mux.publish_mode.call_count, 1)
        self.assertLess(
            self.constants["REMOTE_STOP_ZERO_KEEPALIVE_S"],
            0.45,
            "zero keepalive must remain inside the base command deadman",
        )

    def test_40_hz_callback_churn_is_capped(self):
        for tick in range(41):
            self.now = 10.0 + tick * 0.025
            self.mux.hold_remote_stop()

        self.assertLessEqual(self.mux.output.publish.call_count, 6)
        self.assertEqual(self.mux.safety_output.publish.call_count, 2)
        self.assertEqual(self.mux.publish_mode.call_count, 1)

    def test_motion_reappearing_during_latch_gets_immediate_zero(self):
        self.mux.hold_remote_stop()
        self.now += 0.01
        self.mux.last_sent = twist(0.1)

        self.mux.hold_remote_stop()

        self.assertEqual(self.mux.output.publish.call_count, 2)
        self.assertEqual(self.mux.safety_output.publish.call_count, 1)
        self.assertEqual(self.mux.publish_mode.call_count, 1)

    def test_reason_and_release_changes_publish_immediately(self):
        self.mux.hold_remote_stop()
        self.now += 0.01
        self.mux.remote_stop.reason = "REMOTE STOP: B pressed"
        self.mux.hold_remote_stop()

        self.assertEqual(self.mux.output.publish.call_count, 1)
        self.assertEqual(self.mux.safety_output.publish.call_count, 2)
        self.assertEqual(self.mux.publish_mode.call_count, 2)

        self.now += 0.01
        self.mux.remote_stop.latched = False
        self.mux.remote_stop.reason = "REMOTE STOP: released by operator"
        self.mux.hold_remote_stop()
        self.assertEqual(self.mux.output.publish.call_count, 2)
        self.assertEqual(self.mux.safety_output.publish.call_count, 3)
        self.assertEqual(self.mux.publish_mode.call_count, 3)

    def test_service_reset_records_release_before_returning(self):
        class Stop:
            latched = True
            reason = "REMOTE STOP: B pressed"

            def reset(stop, now):
                del now
                stop.latched = False
                stop.reason = "REMOTE STOP: released by operator"
                return True

        self.mux.remote_stop = Stop()
        response = NS()

        returned = self.mux.reset_remote_stop(object(), response)

        self.assertIs(returned, response)
        self.assertTrue(response.success)
        self.assertEqual(response.message, "REMOTE STOP: released by operator")
        self.assertFalse(self.mux._remote_stop_hold_latched)
        self.assertEqual(self.mux.output.publish.call_count, 2)
        self.assertEqual(self.mux.publish_mode.call_count, 2)


if __name__ == "__main__":
    unittest.main()
