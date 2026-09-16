#!/usr/bin/env python3
"""No network changes: policy, route ownership and client-preservation tests."""
import unittest
from unittest.mock import patch, Mock
import atlas_network_fallback as network


class PolicyTests(unittest.TestCase):
    def test_wifi_priority(self):
        p = network.Policy()
        for _ in range(10):
            self.assertEqual(p.update(True, True, False), ('WIFI', False))

    def test_single_loss_ignored(self):
        p = network.Policy()
        self.assertEqual(p.update(False, True, False), ('WIFI', False))
        self.assertEqual(p.update(True, True, False), ('WIFI', False))

    def test_cellular_after_three_failures(self):
        p = network.Policy()
        for _ in range(3):
            result = p.update(False, True, False)
        self.assertEqual(result, ('CELLULAR', False))

    def test_wifi_recovery_requires_three(self):
        p = network.Policy()
        for _ in range(3):
            p.update(False, True, False)
        for _ in range(2):
            self.assertEqual(p.update(True, True, False), ('CELLULAR', False))
        self.assertEqual(p.update(True, True, False), ('WIFI', False))

    def test_hotspot_after_six_both_failed(self):
        p = network.Policy()
        for _ in range(5):
            self.assertFalse(p.update(False, False, False)[1])
        self.assertEqual(p.update(False, False, False), ('OFFLINE', True))

    def test_no_hotspot_if_cellular_works(self):
        p = network.Policy()
        for _ in range(30):
            self.assertFalse(p.update(False, True, False)[1])

    def test_ap_does_not_cycle_on_cellular_recovery(self):
        p = network.Policy()
        self.assertEqual(p.update(False, True, True), ('CELLULAR', False))

    @patch.object(network, 'run')
    @patch.object(network, 'ip_json')
    def test_only_owned_default_deleted(self, ip, run):
        ip.return_value = [{'dst': 'default', 'metric': 9, 'dev': 'usb0'},
                           {'dst': 'default', 'metric': 50}, {'dst': '10.0.0.0/24', 'metric': 9}]
        network.clear_own_routes()
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            self.assertIn('199', call.args[0])
            self.assertNotIn('flush', call.args[0])

    def test_clients_keep_ap(self):
        config = {'wifi_interface': 'wlan0', 'cellular_interface': 'usb0'}
        m = network.Manager(config)
        m.last_retry = -1000
        m.clients = Mock(return_value=1)
        with patch.object(network, 'run') as run:
            m.retry_wifi()
            run.assert_not_called()
        m.pool.shutdown()

    @patch.object(network, 'gateway', return_value=None)
    def test_no_guessing_cellular_gateway(self, gateway):
        m = network.Manager({'wifi_interface': 'wlan0', 'cellular_interface': 'usb0'})
        with self.assertRaises(RuntimeError):
            m.route('CELLULAR')
        m.pool.shutdown()

    @patch.object(network.Path, 'exists', return_value=True)
    @patch.object(network, 'run')
    def test_tls_probe_rejects_captive_portal(self, run, exists):
        run.return_value = 'Please login\nATLAS_HTTP=200'
        # The first provider requires a trace payload. A valid TLS reply from
        # Google's exact numeric IP still demonstrates an external connection.
        run.side_effect = ['Please login\nATLAS_HTTP=200', RuntimeError('TLS failure')]
        self.assertFalse(network.probe('usb0')['ok'])

    @patch.object(network.Path, 'exists', return_value=True)
    @patch.object(network, 'run')
    def test_secondary_provider_can_pass(self, run, exists):
        run.side_effect = [RuntimeError('primary unavailable'), 'redirect\nATLAS_HTTP=302']
        self.assertTrue(network.probe('usb0')['ok'])


if __name__ == '__main__':
    unittest.main()
