"""Offline only: no USB access, stream starts or permission changes."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import stationary_ros_probe as P


class UsbAccessTests(unittest.TestCase):
    def check(self, outputs, access=True):
        with patch.object(P.subprocess,'check_output',side_effect=outputs), \
             patch.object(P.os,'access',return_value=access):
            return P.verify_astra_usb_access()

    def test_both_interfaces_pass(self):
        rows=self.check(['Bus 001 Device 014: ID 2bc5:0403 Astra','2bc5:0501'])
        self.assertEqual(len(rows),2)

    def test_lost_acl_identifies_depth_node(self):
        with self.assertRaisesRegex(RuntimeError,'access denied.*014'):
            self.check(['2bc5:0403'],False)

    def test_rgb_denied_still_blocks(self):
        with patch.object(P.subprocess,'check_output',side_effect=['2bc5:0403','2bc5:0501']), \
             patch.object(P.os,'access',side_effect=[True,False]):
            with self.assertRaisesRegex(RuntimeError,'access denied.*011'):
                P.verify_astra_usb_access()

    def test_missing_renumbered_or_wrong_device_blocks(self):
        for output in ('','2bc5:0501','2bc5:04030'):
            with self.subTest(output=output), self.assertRaisesRegex(RuntimeError,'identity missing/mismatch'):
                self.check([output])

    def test_query_failure_and_timeout_fail_closed(self):
        for error in (FileNotFoundError(),subprocess.CalledProcessError(1,'lsusb'),
                      subprocess.TimeoutExpired('lsusb',2)):
            with self.subTest(error=error), self.assertRaisesRegex(RuntimeError,'identity query failed'):
                self.check(error)

    def test_query_is_bounded_and_read_only(self):
        with patch.object(P.subprocess,'check_output',side_effect=['2bc5:0403','2bc5:0501']) as query, \
             patch.object(P.os,'access',return_value=True):
            P.verify_astra_usb_access()
        self.assertEqual(query.call_count,2)
        for call in query.call_args_list:
            self.assertEqual(call.args[0][0],'lsusb')
            self.assertEqual(call.kwargs['timeout'],2)
