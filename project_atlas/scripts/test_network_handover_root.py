#!/usr/bin/env python3
"""Explicit supervised stationary network test; never run on boot.

Momentarily activates cellular routing and the AP; independent systemd rollback
restores saved Wi-Fi. No ROS/control commands. Requires both Internet probes good.
"""
import json
import os
from pathlib import Path
import subprocess
import socket
import struct
import sys
import time
sys.path.insert(0, '/usr/local/lib/atlas-network')
import atlas_network_fallback as net

CONFIG = json.loads(Path('/etc/atlas-network.json').read_text())


def restore():
    try:
        net.run(['nmcli', '--wait', '20', 'connection', 'up', 'uuid', CONFIG['wifi_uuid']], timeout=25)
        net.run(['systemctl', 'stop', 'atlas-hotspot-dhcp.service'])
    finally:
        m = net.Manager(CONFIG)
        m.cleanup()
        net.run(['systemctl', 'start', 'atlas-network-fallback.service'])


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo')
    if '--restore' in sys.argv:
        restore()
        return
    assert net.probe(CONFIG['wifi_interface'])['ok'], 'Wi-Fi must be healthy before test'
    assert net.probe(CONFIG['cellular_interface'])['ok'], 'Cellular must be healthy before test'
    guard = 'atlas-network-test-restore-'+str(int(time.time()))
    net.run(['systemd-run', '--unit', guard, '--on-active=90s', '/usr/bin/python3',
             str(Path(__file__).resolve()), '--restore'])
    net.run(['systemctl', 'stop', 'atlas-network-fallback.service'])
    m = net.Manager(CONFIG)
    try:
        m.route('CELLULAR')
        actual = net.ip_json('-4', 'route', 'get', '1.1.1.1')
        assert actual[0]['dev'] == CONFIG['cellular_interface'], actual
        response = net.run(['curl', '-4', '--noproxy', '*', '--connect-timeout', '4', '--max-time', '8',
                            '-fsS', 'https://www.cloudflare.com/cdn-cgi/trace'], timeout=10)
        assert 'ip=' in response, 'Default-route cellular HTTPS failed'
        print('PASS: default route and DNS use cellular; unbound HTTPS succeeded', flush=True)
        m.hotspot()
        assert m.ap_active(), 'AP profile not active'
        radio = net.run(['iw', 'dev', CONFIG['wifi_interface'], 'info'])
        assert 'type AP' in radio and 'ssid ATLAS-Rescue' in radio, radio
        addr = net.run(['ip', '-4', 'addr', 'show', 'dev', CONFIG['wifi_interface']])
        assert '10.42.0.1/24' in addr, addr
        assert net.run(['systemctl', 'is-active', 'atlas-hotspot-dhcp.service']) == 'active'
        sockets = net.run(['ss', '-ulnp'])
        assert ':67 ' in sockets, 'DHCP socket not open'
        web = net.run(['curl', '--noproxy', '*', '--max-time', '4', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                       'http://10.42.0.1:8088/'])
        assert web == '200', 'Dashboard inaccessible on AP address'
        # Test captive DNS without changing the Jetson's resolver.
        label = 'connectivitycheck.gstatic.com'
        query = struct.pack('!HHHHHH', 0xA71A, 0x0100, 1, 0, 0, 0)
        query += b''.join(bytes([len(x)])+x.encode() for x in label.split('.'))+b'\x00\x00\x01\x00\x01'
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as dns:
            dns.settimeout(3)
            dns.sendto(query, ('10.42.0.1', 53))
            answer, _ = dns.recvfrom(1024)
        assert answer[-4:] == socket.inet_aton('10.42.0.1'), 'Captive DNS did not resolve to the AP'
        print('PASS: captive DNS resolves phone connectivity checks to ATLAS', flush=True)
        # Standard phone/desktop HTTP connectivity checks must redirect, not
        # pretend to provide working Internet. HTTPS is never intercepted.
        for endpoint in ('generate_204', 'hotspot-detect.html', 'connecttest.txt'):
            result = net.run(['curl', '--noproxy', '*', '--max-time', '3', '--retry', '3', '--retry-connrefused', '--retry-delay', '1', '-sS', '-o', '/dev/null',
                              '-w', '%{http_code} %{redirect_url}', 'http://10.42.0.1/'+endpoint])
            assert result == '302 http://10.42.0.1:8088/', result
        print('PASS: Android/Apple/Windows HTTP checks redirect to dashboard', flush=True)
        print('PASS: AP broadcasting, local IP set, DHCP listening, dashboard HTTP 200', flush=True)
        print('Phone association / DHCP lease still needs an operator test; not inferred from sockets', flush=True)
    finally:
        restore()
        if net.probe(CONFIG['wifi_interface'])['ok']:
            net.run(['systemctl', 'stop', guard+'.timer'], check=False)
            print('PASS: saved Wi-Fi restored and automatic service running', flush=True)
        else:
            print('Wi-Fi not verified; independent restore timer retained', flush=True)


if __name__ == '__main__':
    main()
