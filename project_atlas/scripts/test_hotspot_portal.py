#!/usr/bin/env python3
import http.client
from http.server import ThreadingHTTPServer
import threading
import unittest
from atlas_hotspot_portal import PortalHandler, DASHBOARD


class PortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), PortalHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)
        c.request(method, path)
        r = c.getresponse()
        result = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return result

    def test_android_apple_windows_probes_redirect(self):
        for path in ('/generate_204', '/hotspot-detect.html', '/connecttest.txt', '/'):
            status, headers, body = self.request('GET', path)
            self.assertEqual(status, 302)
            self.assertEqual(headers['Location'], DASHBOARD)
            self.assertIn(b'Internet is unavailable', body)

    def test_no_open_redirect(self):
        self.assertEqual(self.request('GET', '/?next=https://example.com')[1]['Location'], DASHBOARD)

    def test_no_control_api(self):
        self.assertEqual(self.request('POST', '/api/drive')[0], 405)

    def test_head_no_body(self):
        self.assertEqual(self.request('HEAD', '/')[2], b'')


if __name__ == '__main__':
    unittest.main()
