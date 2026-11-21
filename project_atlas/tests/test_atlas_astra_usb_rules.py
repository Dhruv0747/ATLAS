"""Static candidate matching only, NOT a native udev execution/persistence test.

Exact attributes are from read-only Jetson inventory 2026-10-21. No live device
opens, rules installation, triggers, subprocesses or permissions changes.
"""
import fnmatch
from pathlib import Path
import re
import unittest

RULE=Path(__file__).resolve().parents[1]/'config/udev/99-atlas-astra-access.rules.candidate'


def parsed():
    rows=[]
    for line in RULE.read_text().splitlines():
        if not line or line.startswith('#'):continue
        fields=[]
        for token in line.split(', '):
            m=re.fullmatch(r'([\w{}]+)(==|:=|\+=)"([^"\n]*)"',token)
            if not m:raise ValueError(token)
            fields.append(m.groups())
        rows.append(fields)
    return rows


def matches(row,device):
    return all(any(fnmatch.fnmatchcase(device.get(k,''),x) for x in v.split('|'))
               for k,op,v in row if op=='==')


def device(product='0403',path='2.3.1.2',**extra):
    d={'ACTION':'add','SUBSYSTEM':'usb','ENV{DEVTYPE}':'usb_device',
       'ENV{ID_PATH}':'platform-3610000.usb-usb-0:'+path,
       'ATTR{idVendor}':'2bc5','ATTR{idProduct}':product}
    d.update(extra);return d


class Rules(unittest.TestCase):
    def test_exact_interfaces(self):
        for d in (device(),device('0501','2.3.1.1')):
            self.assertEqual(sum(matches(r,d) for r in parsed()),1)

    def test_reenumeration_does_not_affect_matching(self):
        for n in ('011','014','031','099'):
            self.assertTrue(matches(parsed()[0],device(DEVNUM=n,BUSNUM='007')))

    def test_other_port_or_missing_path_denied(self):
        for p in ('2.4.1','2.3.1.1',''):
            self.assertFalse(any(matches(r,device(path=p)) for r in parsed()))

    def test_other_connected_vendors_denied(self):
        for vid,pid in [('1a86','7523'),('10c4','ea60'),('2341','006d'),('303a','1001'),
                        ('1e0e','907b'),('045e','028e'),('0bda','c822'),('2109','2817'),
                        ('214b','7260'),('05e3','0608'),('1d6b','0002')]:
            self.assertFalse(any(matches(r,device(**{'ATTR{idVendor}':vid,'ATTR{idProduct}':pid})) for r in parsed()))

    def test_interface_and_video_events_not_matched(self):
        for updates in ({'ENV{DEVTYPE}':'usb_interface'},{'SUBSYSTEM':'video4linux'},
                        {'SUBSYSTEM':'tty'},{'ACTION':'remove'}):
            self.assertFalse(any(matches(r,device(**updates)) for r in parsed()))

    def test_add_change_only(self):
        self.assertTrue(matches(parsed()[0],device(ACTION='change')))
        self.assertFalse(matches(parsed()[0],device(ACTION='bind')))

    def test_least_privilege_and_no_execution(self):
        for row in parsed():
            assignments={k:(op,v) for k,op,v in row if op!='=='}
            self.assertEqual(assignments['MODE'],(':=','0660'))
            self.assertEqual(assignments['GROUP'],(':=','atlas-astra'))
            self.assertEqual(assignments['OWNER'],(':=','root'))
            self.assertEqual(set(assignments),{'MODE','GROUP','OWNER','SYMLINK'})

    def test_aliases_unique_and_not_kernel_names(self):
        names=[v for r in parsed() for k,op,v in r if k=='SYMLINK']
        self.assertEqual(len(set(names)),2)
        self.assertTrue(all(n.startswith('atlas-astra-') for n in names))


if __name__=='__main__':unittest.main()
