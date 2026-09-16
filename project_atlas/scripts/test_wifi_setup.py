import unittest
from unittest.mock import Mock, patch
import tempfile
from pathlib import Path
import atlas_wifi_manager as wifi
import atlas_wifi_web as web

class WifiTests(unittest.TestCase):
    def test_rollback_preserves_saved_profile(self):
        manager=Mock()
        manager.config={'hotspot_uuid':'hotspot'}
        manager.wifi='wlan0'
        obj=wifi.WifiManager.__new__(wifi.WifiManager)
        obj.manager=manager
        with patch.object(wifi.net,'run',return_value='') as run, patch.object(wifi.net,'probe',return_value={'ok':True}):
            obj.rollback({'previous':'00000000-0000-0000-0000-000000000001'})
            self.assertFalse(any('delete' in c.args[0] for c in run.call_args_list))
            manager.hotspot.assert_not_called()

    def test_failed_previous_restores_hotspot(self):
        manager=Mock()
        manager.config={'hotspot_uuid':'hotspot'}
        manager.wifi='wlan0'
        obj=wifi.WifiManager.__new__(wifi.WifiManager)
        obj.manager=manager
        with tempfile.TemporaryDirectory() as directory, patch.object(wifi,'PROFILES',Path(directory)), patch.object(wifi.net,'run',return_value=''), patch.object(wifi.net,'probe',return_value={'ok':False}):
            obj.rollback({'previous':'00000000-0000-0000-0000-000000000001','new_uuid':'00000000-0000-0000-0000-000000000002'})
            manager.hotspot.assert_called_once()

    def test_validation(self):
        for data in ({'ssid':''}, {'ssid':'ATLAS-Rescue'}, {'ssid':'x','password':'short'}, {'ssid':'x\n','open':True}):
            with self.assertRaises(ValueError): wifi.validate(data)
        self.assertTrue(wifi.validate({'ssid':'Guest','open':True})['open'])
        self.assertEqual(wifi.validate({'ssid':'Home','password':'12345678'})['ssid'],'Home')

    def test_escaped_fields(self):
        self.assertEqual(wifi.split_nm(r'Guest\:WiFi:95:WPA2'), ['Guest:WiFi','95','WPA2'])

    def test_keyfile(self):
        text=wifi.keyfile({'ssid':'A;B','password':' abcdefg ','open':False}, '00000000-0000-0000-0000-000000000001','wlan0')
        self.assertIn('ssid=65;59;66;',text)
        self.assertIn('psk=\\sabcdefg\\s',text)
        self.assertIn('autoconnect=false',text)

    def test_origin(self):
        for host in ('192.168.1.14:8088','100.87.208.71:8088','jetsan-desktop.local:8088'):
            self.assertTrue(web.same_origin({'Host':host,'Origin':'http://'+host,'X-Atlas-Wifi':'1'}))
        self.assertFalse(web.same_origin({'Host':'192.168.1.14:8088','Origin':'http://evil.example','X-Atlas-Wifi':'1'}))
        self.assertFalse(web.same_origin({'Host':'evil.example','Origin':'http://evil.example','X-Atlas-Wifi':'1'}))
        self.assertFalse(web.same_origin({'Host':'192.168.1.14:8088','Origin':'http://192.168.1.14:8088'}))

if __name__=='__main__': unittest.main()
