#!/usr/bin/env python3
"""Static regression checks for the consolidated dashboard reports."""

import ast
from pathlib import Path
import unittest


SOURCE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "atlas_status_web.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def returned_page(function_name):
    function = next(
        node
        for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    returned = next(node for node in function.body if isinstance(node, ast.Return))
    return ast.literal_eval(returned.value)


class SmartDashboardPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = returned_page("render_control_page")

    def test_encoder_health_is_consolidated(self):
        self.assertEqual(self.page.count("DRIVE FEEDBACK • ALL 4 WHEELS"), 1)
        self.assertNotIn("ENCODER M1 • BACK LEFT", self.page)
        self.assertNotIn("ENCODER M4 • FRONT RIGHT',(encoderHealth", self.page)

    def test_four_wheel_report_is_one_click_target(self):
        self.assertIn("SMART DRIVE REPORT — ALL 4 WHEELS", self.page)
        self.assertIn("openDetail('encoders')", self.page)
        self.assertIn("ONE PANEL IS AUTHORITATIVE FOR ALL FOUR WHEELS", self.page)

    def test_jetson_live_report_is_present(self):
        self.assertIn("JETSON LIVE REPORT — TOUCH FOR DETAILS", self.page)
        self.assertIn("openDetail('jetson')", self.page)
        self.assertIn("JETSON ORIN — SMART LIVE REPORT", self.page)
        self.assertIn("NVIDIA software throttling begins at 99°C", self.page)

    def test_backend_exposes_gpu_fields(self):
        status_function = next(
            node
            for node in TREE.body
            if isinstance(node, ast.FunctionDef) and node.name == "system_status"
        )
        rendered = ast.unparse(status_function)
        self.assertIn("gpu_status()", rendered)
        gpu_function = next(
            node
            for node in TREE.body
            if isinstance(node, ast.FunctionDef) and node.name == "gpu_status"
        )
        gpu_source = ast.unparse(gpu_function)
        self.assertIn("load_value / 10.0", gpu_source)
        self.assertIn("gpu_frequency_mhz", gpu_source)


if __name__ == "__main__":
    unittest.main()
