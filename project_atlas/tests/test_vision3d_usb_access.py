"""Offline only: no USB access, stream starts or permission changes."""
from pathlib import Path
import os
import stat
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/vision3d'))
import stationary_ros_probe as P


class UsbAccessTests(unittest.TestCase):
    def check(self, access=True, vendor='2bc5', controller='3610000.usb',
              missing=False, duplicate=False, alias=False, char=True, major=189,
              changed=False, number=42):
        reads=[0]
        def glob(path,pattern):
            rows=[] if missing else [Path('/sys/bus/usb/devices/3-'+pattern[2:])]
            return rows*2 if duplicate else rows
        def resolve(path,strict=False):
            return (Path('/sys/devices/platform')/controller/path.name if str(path).startswith('/sys/')
                    else Path('/dev/bus/usb/003/099'))
        def read(path):
            reads[0]+=1
            depth=path.parent.name.endswith('.2')
            num=number if depth else number+1
            values=dict(idVendor=vendor,idProduct='0403' if depth else '0501',
                        devpath='2.3.1.2' if depth else '2.3.1.1',busnum='3',
                        devnum=str(num),dev=f'189:{256+num-1}')
            if changed and reads[0]>6 and path.name=='devnum':return '44'
            return values[path.name]
        def node_stat(path):
            return SimpleNamespace(st_mode=stat.S_IFCHR if char else stat.S_IFREG,
                                   st_rdev=os.makedev(major,256+int(path.name)-1))
        with patch.object(Path,'glob',glob),patch.object(Path,'resolve',resolve), \
             patch.object(Path,'read_text',read),patch.object(Path,'stat',node_stat), \
             patch.object(P.os.path,'lexists',return_value=alias), \
             patch.object(P.os,'access',return_value=access):
            return P.verify_astra_usb_access()

    def test_both_interfaces_pass(self):
        rows=self.check()
        self.assertEqual([r['path'] for r in rows],['/dev/bus/usb/003/042','/dev/bus/usb/003/043'])

    def test_lost_acl_identifies_depth_node(self):
        with self.assertRaisesRegex(RuntimeError,'access denied.*042'):
            self.check(access=False)

    def test_node_type_and_identity(self):
        for kwargs in ({'char':False},{'major':1}):
            with self.subTest(kwargs=kwargs),self.assertRaisesRegex(RuntimeError,'device-node identity mismatch'):
                self.check(**kwargs)

    def test_missing_renumbered_or_wrong_device_blocks(self):
        for kwargs in ({'vendor':'ffff'},{'controller':'other.usb'},{'missing':True},{'duplicate':True}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(RuntimeError,'identity missing'):
                self.check(**kwargs)

    def test_query_failure_fail_closed(self):
        with patch.object(Path,'glob',side_effect=OSError('unplugged')):
            with self.assertRaisesRegex(RuntimeError,'query failed'):P.verify_astra_usb_access()

    def test_query_is_bounded_and_read_only(self):
        with patch.object(P.subprocess,'check_output',side_effect=AssertionError('process launch')):
            self.assertEqual(len(self.check()),2)

    def test_stale_alias_blocks(self):
        with self.assertRaisesRegex(RuntimeError,'alias mismatch'):self.check(alias=True)

    def test_renumber_during_check_blocks(self):
        with self.assertRaisesRegex(RuntimeError,'changed during check'):self.check(changed=True)

    def test_invalid_number_blocks(self):
        with self.assertRaisesRegex(RuntimeError,'invalid bus/device'):self.check(number=999)
