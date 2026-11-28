"""BMS freshness contract without ROS, Bluetooth or actuator access."""
import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest


SCRIPTS = Path(__file__).parents[1] / "scripts"


def isolated_methods(filename, class_name, names, globals_):
    path = SCRIPTS / filename
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    cls.bases = []
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), globals_)
    return globals_[class_name]


class Message:
    def __init__(self, data=None):
        self.data = data


class Publisher:
    def __init__(self):
        self.messages = []

    def publish(self, msg):
        self.messages.append(msg.data)


class DalyFreshnessTests(unittest.TestCase):
    def setUp(self):
        daly = isolated_methods(
            "daly_bms_node.py", "DalyBmsNode", ("publish_float", "publish_data"),
            {"json": json, "String": Message, "Float32": Message},
        )
        self.node = daly()
        for name in ("status_pub", "json_pub", "voltage_pub", "current_pub",
                     "percent_pub", "power_pub", "min_cell_pub", "max_cell_pub"):
            setattr(self.node, name, Publisher())
        self.node.cell_pubs = [Publisher() for _ in range(4)]

    def test_failed_read_reports_invalid_but_never_republishes_old_scalars(self):
        healthy = {"ok": True, "voltage_v": 13.2, "soc_percent": 90.0,
                   "cells_v": [3.3] * 4}
        self.node.publish_data(healthy)
        self.node.publish_data({**healthy, "ok": False, "error": "connect timeout"})
        self.assertEqual(len(self.node.json_pub.messages), 2)
        self.assertFalse(json.loads(self.node.json_pub.messages[-1])["ok"])
        self.assertEqual(self.node.percent_pub.messages, [90.0])
        self.assertEqual(self.node.voltage_pub.messages, [13.2])
        self.assertEqual([len(p.messages) for p in self.node.cell_pubs], [1] * 4)

    def test_agent_immediately_revokes_failed_or_malformed_snapshot(self):
        agent = isolated_methods(
            "atlas_agent_supervisor.py", "AtlasAgentSupervisor",
            ("on_traction_battery_status",),
            {"json": json, "math": math, "String": Message,
             "time": SimpleNamespace(monotonic=lambda: 100.0)},
        )()
        agent.traction_battery_percent = None
        agent.traction_battery_at = 0.0
        agent.on_traction_battery_status(Message(json.dumps({"ok": True, "soc_percent": 90})))
        self.assertEqual((agent.traction_battery_percent, agent.traction_battery_at), (90.0, 100.0))
        for bad in ({"ok": False, "soc_percent": 90}, {"ok": True, "soc_percent": "NaN"},
                    {"ok": True}, [], "broken"):
            agent.on_traction_battery_status(Message(
                bad if isinstance(bad, str) else json.dumps(bad)
            ))
            self.assertIsNone(agent.traction_battery_percent)
            self.assertEqual(agent.traction_battery_at, 0.0)


if __name__ == "__main__":
    unittest.main()
