"""Offline temperature/admission regression; no Jetson, sockets or services."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import offboard_bridge_preflight as probe


class TemperatureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def zone(self, identifier='thermal_zone0', name=b'cpu-thermal\n', value=b'58000\n'):
        zone = self.root / identifier
        zone.mkdir()
        (zone / 'type').write_bytes(name)
        (zone / 'temp').write_bytes(value)
        return zone

    def test_reproduce_original_utf8_none_read_exception_offline(self):
        class Unavailable(io.RawIOBase):
            def readable(self): return True
            def readinto(self, target): return None
        with io.TextIOWrapper(io.BufferedReader(Unavailable()), encoding='utf-8') as reader:
            with self.assertRaisesRegex(TypeError, "can't concat NoneType to bytes"):
                reader.read()

    def test_valid_zones_with_duplicate_type_keep_both_measurements(self):
        self.zone(value=b'58000\n')
        self.zone('thermal_zone1',value=b'61000\n')
        result = probe.read_thermal(self.root)
        self.assertEqual(result['thermal_zones_c'], {'thermal_zone0':58.,'thermal_zone1':61.})
        self.assertEqual(result['thermal_read_errors'], [])
        self.assertTrue(all(x['type']=='cpu-thermal' for x in result['thermal_measurements']))

    def test_blank_malformed_nonfinite_and_impossible_temperature_block(self):
        zone = self.zone()
        for value in (b'',b' \n',b'nan',b'inf',b'58000C',b'58.0',b'-273151',b'\xff'):
            with self.subTest(value=value):
                (zone/'temp').write_bytes(value)
                result=probe.read_thermal(self.root)
                self.assertEqual(result['thermal_zones_c'],{})
                self.assertEqual(result['thermal_read_errors'][0]['path'],str(zone/'temp'))
                self.assertEqual(result['thermal_read_errors'][0]['stage'],'temp')
                self.assertIn('Traceback',result['thermal_read_errors'][0]['traceback'])

    def test_none_result_is_explicit_error_and_descriptor_closed(self):
        zone=self.zone()
        with patch.object(probe.os,'open',return_value=123), \
             patch.object(probe.os,'read',return_value=None) as read, \
             patch.object(probe.os,'close') as close:
            with self.assertRaisesRegex(OSError,'no bytes object'):
                probe.read_sysfs_text(zone/'temp')
            read.assert_called_once_with(123,257)
            close.assert_called_once_with(123)

    def test_unavailable_read_fails_once_without_retry(self):
        zone=self.zone()
        with patch.object(probe.os,'open',return_value=123), \
             patch.object(probe.os,'read',side_effect=BlockingIOError(11,'temporarily unavailable')) as read, \
             patch.object(probe.os,'close') as close:
            with self.assertRaises(BlockingIOError):probe.read_sysfs_text(zone/'temp')
            self.assertEqual(read.call_count,1)
            close.assert_called_once_with(123)

    def test_disappeared_temp_preserves_other_zone_and_exact_error_path(self):
        bad=self.zone();(bad/'temp').unlink()
        self.zone('thermal_zone1',value=b'62000\n')
        result=probe.read_thermal(self.root)
        self.assertEqual(result['thermal_zones_c'],{'thermal_zone1':62.})
        error=result['thermal_read_errors'][0]
        self.assertEqual((error['path'],error['exception_type']),(str(bad/'temp'),'FileNotFoundError'))

    def test_missing_type_still_records_temp_but_blocks(self):
        zone=self.zone();(zone/'type').unlink()
        result=probe.read_thermal(self.root)
        self.assertEqual(result['thermal_zones_c'],{'thermal_zone0':58.})
        self.assertEqual(result['thermal_read_errors'][0]['stage'],'type')

    def test_missing_or_empty_thermal_root_blocks(self):
        for root in (self.root,self.root/'missing'):
            with self.subTest(root=root):
                result=probe.read_thermal(root)
                self.assertTrue(result['thermal_read_errors'])
                self.assertEqual(result['thermal_read_errors'][0]['stage'],'enumerate')

    def test_attribute_size_is_bounded(self):
        zone=self.zone(name=b'x'*257)
        result=probe.read_thermal(self.root)
        self.assertIn('larger than 256',result['thermal_read_errors'][0]['error'])

    def run_admission(self, *, temperature=b'70000\n', cpu=75., ram=80., alter_status=None):
        self.zone(value=temperature)
        # Five exact 1s CPU intervals at the selected percentage.
        increments=[(int(1000*i),int((1000-10*cpu)*i)) for i in range(6)]
        status={'system':{'cpu_percent':cpu,'ram_percent':ram,'temp':'70 C'},
                'ros':{'control_policy':{'age':.1,'value':{'stop_latched':True,
                    'commission_armed':False,'manual_only':True,'source':'STOPPED'}},
                       'cmd_vel':{'age':.1,'value':{'lin':0.,'ang':0.}}}}
        if alter_status:alter_status(status)
        memory='MemTotal: 100000 kB\nMemAvailable: %s kB\n'%round(100000*(1-ram/100))
        units='Id=atlas-stage20-public-capture.service\nActiveState=inactive\nMainPID=0\nNRestarts=0\n'
        output=io.StringIO()
        with patch.object(probe,'THERMAL_ROOT',self.root), \
             patch.object(probe,'ticks',side_effect=increments), \
             patch.object(probe.time,'monotonic',side_effect=range(6)), \
             patch.object(probe.time,'sleep'), \
             patch.object(Path,'read_text',return_value=memory), \
             patch.object(probe.shutil,'disk_usage',return_value=SimpleNamespace(free=3*1024**3)), \
             patch.object(probe,'status',return_value=copy.deepcopy(status)) as fetch, \
             patch.object(probe.subprocess,'run',return_value=SimpleNamespace(stdout=units)) as services, \
             contextlib.redirect_stdout(output):
            code=probe.main()
        return code,json.loads(output.getvalue()),fetch.call_count,services.call_count

    def test_exact_resource_boundaries_pass_only_to_pending_sensor_gate(self):
        code,result,_,_=self.run_admission()
        self.assertEqual(code,0)
        self.assertEqual(result['thermal_zones_c'],{'thermal_zone0':70.})
        self.assertEqual(result['decision'],'RESOURCE_SAFETY_PASS_SENSOR_ADMISSION_PENDING')
        self.assertFalse(result['bridge_connected'])

    def test_failed_temperature_never_queries_dashboard_or_services(self):
        code,result,fetches,services=self.run_admission(temperature=b'nan')
        self.assertEqual((code,fetches,services),(2,0,0))
        self.assertEqual(result['decision'],'BLOCKED')
        self.assertEqual(result['measurement_error']['phase'],'temperature')
        self.assertIn('temp',result['thermal_read_errors'][0]['path'])
        self.assertIn('Traceback',result['measurement_error']['traceback'])

    def test_above_temperature_limit_still_blocks(self):
        code,result,_,_=self.run_admission(temperature=b'70001\n')
        self.assertEqual(code,2)
        self.assertTrue(any('exceeds70' in x for x in result['reasons']))

    def test_cpu_ram_and_safety_limits_unchanged(self):
        changes=(dict(cpu=75.1),dict(ram=80.1),
            dict(alter_status=lambda s:s['ros']['control_policy']['value'].update(stop_latched=False)),
            dict(alter_status=lambda s:s['ros']['control_policy']['value'].update(commission_armed=True)),
            dict(alter_status=lambda s:s['ros']['control_policy']['value'].update(manual_only=False)),
            dict(alter_status=lambda s:s['ros']['cmd_vel']['value'].update(lin=.1)))
        for change in changes:
            with self.subTest(change=change):
                # Each run uses the same synthetic zone, recreated for the fixture.
                if (self.root/'thermal_zone0').exists():
                    (self.root/'thermal_zone0'/'type').unlink()
                    (self.root/'thermal_zone0'/'temp').unlink()
                    (self.root/'thermal_zone0').rmdir()
                code,result,_,_=self.run_admission(**change)
                self.assertEqual(code,2)
                self.assertEqual(result['decision'],'BLOCKED')
                self.assertFalse(result['production_subscriptions_started'])


if __name__=='__main__':unittest.main()
