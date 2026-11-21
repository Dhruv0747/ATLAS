#!/usr/bin/env python3
"""Static regression checks for the consolidated dashboard reports."""

import ast
from pathlib import Path
import unittest


SOURCE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "atlas_status_web.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
DIAGNOSTICS_SOURCE = (SOURCE_PATH.parent / "atlas_diagnostics_ui.js").read_text(encoding="utf-8")
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

    def test_bms_health_and_power_card_require_valid_fresh_snapshot(self):
        self.assertIn("function bmsSnapshot(r)", self.page)
        self.assertIn("function bmsLive(r)", self.page)
        self.assertIn("!recent(r,'bms_status',10)", self.page)
        self.assertIn("b.cells_complete!==true", self.page)
        self.assertIn("[b.soc_percent,b.voltage_v,b.current_a,b.power_w,...b.cells_v].every(valid)", self.page)
        self.assertIn("['DALY BMS',bmsLive(r)?'ok':'fail'", self.page)
        self.assertIn("let bms=bmsSnapshot(r)", self.page)
        self.assertIn("bms?`${n(bms.soc_percent,0)}% • ${bmsState}`:'UNAVAILABLE'", self.page)
        self.assertIn("PACK CURRENT", self.page)
        self.assertIn("PACK POWER", self.page)
        self.assertIn("last-known values hidden", self.page)
        self.assertIn("const b=bmsSnapshot(r);", DIAGNOSTICS_SOURCE)
        self.assertIn("openDetail('bms_status')", DIAGNOSTICS_SOURCE)
        self.assertIn("class=\"batteryMetrics\"", DIAGNOSTICS_SOURCE)
        self.assertIn("${b.currentA.toFixed(2)} A · ${b.powerW.toFixed(1)} W", DIAGNOSTICS_SOURCE)
        self.assertIn(".batteryMetrics{display:block", self.page)

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

    def test_live_mapping_page_is_linked_and_source_backed(self):
        self.assertIn('href="/mapping"', self.page)
        self.assertIn("LIVE MAP / ROVER POSITION", self.page)
        source = SOURCE
        self.assertIn('n.create_subscription(OccupancyGrid, "/map"', source)
        self.assertIn("DurabilityPolicy.TRANSIENT_LOCAL", source)
        self.assertIn('n.create_subscription(NavPath, "/plan"', source)
        self.assertIn('lookup_transform("map", "base_link"', source)
        self.assertIn('if self.path.startswith("/api/map")', source)
        self.assertIn('if self.path.startswith("/map.png")', source)

    def test_map_markers_follow_the_active_map(self):
        marker_function = next(
            node
            for node in TREE.body
            if isinstance(node, ast.FunctionDef) and node.name == "map_markers"
        )
        rendered = ast.unparse(marker_function)
        self.assertIn("candidate_is_active", rendered)
        self.assertIn("map_size_cells", rendered)
        self.assertIn("active mapping candidate", rendered)
        self.assertIn("accepted named places", rendered)


if __name__ == "__main__":
    unittest.main()
