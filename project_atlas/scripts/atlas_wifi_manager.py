#!/usr/bin/env python3
"""Narrow local Wi-Fi provisioning API. Secrets never leave NetworkManager files.

Only the dashboard UID (1000) and root may use the Unix socket. No shell command
strings, ROS operations, arbitrary paths, profile deletion API or secret reads.
"""
import configparser
import io
import json
import os
from pathlib import Path
import socket
import socketserver
import struct
import threading
import time
import uuid
import atlas_network_fallback as net

SOCKET = '/run/atlas-network/wifi.sock'
STATE = Path('/var/lib/atlas-network')
PROFILES = Path('/etc/NetworkManager/system-connections')


def split_nm(line):
    fields, value, escaped = [], '', False
    for c in line:
        if escaped:
            value += c
            escaped = False
        elif c == '\\':
            escaped = True
        elif c == ':':
            fields.append(value)
            value = ''
        else:
            value += c
    fields.append(value + ('\\' if escaped else ''))
    return fields


def validate(data):
    if data.get('uuid'):
        return {'uuid': str(uuid.UUID(data['uuid']))}
    ssid, password = data.get('ssid', ''), data.get('password', '')
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32 or any(ord(c) < 32 for c in ssid):
        raise ValueError('Wi-Fi name must be 1–32 bytes with no control characters')
    if ssid == 'ATLAS-Rescue':
        raise ValueError('The rescue hotspot is not an upstream Wi-Fi network')
    if not isinstance(password, str) or any(ord(c) < 32 for c in password):
        raise ValueError('Invalid password')
    opened = data.get('open') is True
    if not opened and not (8 <= len(password.encode()) <= 63 or len(password) == 64 and all(c in '0123456789abcdefABCDEF' for c in password)):
        raise ValueError('Personal Wi-Fi password must contain 8–63 characters, or a 64-digit hex key')
    return {'ssid': ssid, 'password': '' if opened else password, 'open': opened}


def keyfile(data, profile_uuid, iface):
    c = configparser.ConfigParser(interpolation=None)
    # SSID stored as bytes avoids keyfile whitespace/semicolon/backslash parsing.
    c['connection'] = {'id': 'ATLAS WiFi '+profile_uuid[:8], 'uuid': profile_uuid,
                       'type': 'wifi', 'interface-name': iface, 'autoconnect': 'false'}
    c['wifi'] = {'mode': 'infrastructure', 'ssid': ';'.join(str(x) for x in data['ssid'].encode())+';'}
    if not data['open']:
        # GLib keyfile escaping, including meaningful leading/trailing spaces.
        psk = data['password'].replace('\\', '\\\\').replace(' ', '\\s')
        c['wifi-security'] = {'key-mgmt': 'wpa-psk', 'psk': psk, 'psk-flags': '0'}
    c['ipv4'] = {'method': 'auto', 'route-metric': '50'}
    c['ipv6'] = {'method': 'auto', 'route-metric': '50'}
    stream = io.StringIO()
    c.write(stream, space_around_delimiters=False)
    return stream.getvalue()


def atomic_json(path, data):
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f)
    tmp.replace(path)


class WifiManager:
    def __init__(self, manager):
        self.manager = manager
        self.job_lock = threading.Lock()
        self.job = {'state': 'idle', 'message': 'Ready'}
        self.retry_index = 0
        self.scanned = []
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            preferred = json.loads((STATE/'preferred.json').read_text())['uuid']
            if preferred in {x['uuid'] for x in self.saved()}:
                manager.config['wifi_uuid'] = preferred
        except (OSError, ValueError, KeyError):
            pass
        # A process crash during a connection attempt must not strand the AP.
        if (STATE/'pending.json').exists():
            pending = json.loads((STATE/'pending.json').read_text())
            self.rollback(pending)
            (STATE/'pending.json').unlink(missing_ok=True)

    def saved(self):
        rows = net.run(['nmcli', '-t', '-f', 'UUID,TYPE', 'connection', 'show']).splitlines()
        result = []
        for line in rows[:128]:
            parts = split_nm(line)
            if len(parts) != 2 or parts[1] != '802-11-wireless':
                continue
            ident = str(uuid.UUID(parts[0]))
            if ident == self.manager.config['hotspot_uuid']:
                continue
            fields = net.run(['nmcli', '-g', '802-11-wireless.mode,802-11-wireless.ssid',
                              'connection', 'show', 'uuid', ident]).splitlines()
            if fields and fields[0] == 'infrastructure':
                result.append({'uuid': ident, 'ssid': split_nm(fields[1])[0] if len(fields) > 1 else '',
                               'preferred': ident == self.manager.config['wifi_uuid']})
        return result

    def scan(self):
        if not self.manager.network_lock.acquire(blocking=False):
            return {'networks': self.scanned, 'note': 'Network operation in progress; showing cached scan'}
        try:
            note = ''
            try:
                text = net.run(['nmcli', '--wait', '8', '-t', '-f', 'SSID,SIGNAL,SECURITY',
                                'device', 'wifi', 'list', 'ifname', self.manager.wifi, '--rescan', 'yes'], timeout=12)
            except Exception:
                text = net.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi',
                                'list', 'ifname', self.manager.wifi, '--rescan', 'no'])
                note = 'Showing cached networks; manual SSID entry is available if AP-mode scanning is unavailable'
            networks = {}
            for line in text.splitlines():
                parts = split_nm(line)
                if len(parts) != 3 or not parts[0] or parts[0] == 'ATLAS-Rescue':
                    continue
                row = {'ssid': parts[0], 'signal': int(parts[1] or 0), 'security': parts[2] or 'OPEN'}
                if row['signal'] > networks.get(row['ssid'], {}).get('signal', -1):
                    networks[row['ssid']] = row
            self.scanned = sorted(networks.values(), key=lambda x: -x['signal'])[:64]
            return {'networks': self.scanned, 'note': note}
        finally:
            self.manager.network_lock.release()

    def candidate(self):
        saved = self.saved()
        if not saved:
            return None
        strength = {x['ssid']: x['signal'] for x in self.scan()['networks']}
        visible = [x for x in saved if x['ssid'] in strength]
        choices = sorted(visible, key=lambda x: (-int(x['preferred']), -strength[x['ssid']])) if visible else sorted(saved, key=lambda x: not x['preferred'])
        selected = choices[self.retry_index % len(choices)]['uuid']
        self.retry_index += 1
        return selected

    def status(self):
        addresses = net.ip_json('-4', 'addr', 'show', 'dev', self.manager.wifi)
        ips = [a['local'] for d in addresses for a in d.get('addr_info', []) if a.get('scope') == 'global']
        with self.job_lock:
            job = dict(self.job)
        return {'saved': self.saved(), 'job': job, 'hotspot': self.manager.ap_active(),
                'dashboard_urls': [f'http://{ip}:8088/' for ip in ips],
                'local_name_url': 'http://'+socket.gethostname().split('.')[0]+'.local:8088/',
                'tailscale_url': 'http://100.87.208.71:8088/'}

    def set_job(self, **values):
        with self.job_lock:
            self.job.update(values)

    def connect(self, request):
        data = validate(request)
        if 'uuid' in data and data['uuid'] not in {x['uuid'] for x in self.saved()}:
            raise ValueError('Choose a saved Wi-Fi profile, not another device or hotspot')
        with self.job_lock:
            if self.job['state'] == 'connecting':
                raise ValueError('A connection attempt is already running')
            self.job = {'state': 'connecting', 'message': 'Connecting shortly. Your browser may disconnect; join the new Wi-Fi and use the displayed local name or Tailscale link.'}
        threading.Thread(target=self._connect, args=(data,), daemon=True).start()
        return {'accepted': True, 'message': 'Connection queued. Credentials are not returned or logged.'}

    def rollback(self, pending):
        if pending.get('new_uuid'):
            # Only a newly created, unverified candidate may be removed.
            ident = str(uuid.UUID(pending['new_uuid']))
            net.run(['nmcli', 'connection', 'delete', 'uuid', ident], check=False)
            (PROFILES/f'atlas-wifi-{ident}.nmconnection').unlink(missing_ok=True)
        previous = pending.get('previous')
        if previous and previous != self.manager.config['hotspot_uuid']:
            try:
                net.run(['nmcli', '--wait', '15', 'connection', 'up', 'uuid', str(uuid.UUID(previous))], timeout=20)
                if net.probe(self.manager.wifi)['ok']:
                    return
            except Exception:
                pass
        self.manager.hotspot()

    def _connect(self, data):
        time.sleep(2)  # Return the HTTP acknowledgement before switching radios.
        with self.manager.network_lock:
            settled = False
            pending = {'previous': net.run(['nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', self.manager.wifi], check=False)}
            try:
                ident = data.get('uuid')
                if not ident:
                    ident = str(uuid.uuid4())
                    pending['new_uuid'] = ident
                atomic_json(STATE/'pending.json', pending)
                if pending.get('new_uuid'):
                    path = PROFILES/f'atlas-wifi-{ident}.nmconnection'
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, 'w') as stream:
                        stream.write(keyfile(data, ident, self.manager.wifi))
                    data.clear()
                    net.run(['nmcli', 'connection', 'load', str(path)])
                net.run(['systemctl', 'stop', 'atlas-hotspot-dhcp.service'])
                net.run(['nmcli', '--wait', '25', 'connection', 'up', 'uuid', ident], timeout=30)
                if not net.probe(self.manager.wifi)['ok']:
                    raise RuntimeError('No Internet')
                net.run(['nmcli', 'connection', 'modify', 'uuid', ident,
                         'connection.autoconnect', 'yes', 'connection.autoconnect-priority', '100'])
                atomic_json(STATE/'preferred.json', {'uuid': ident})
                self.manager.config['wifi_uuid'] = ident
                self.manager.policy = net.Policy()
                self.manager.route('WIFI')
                self.set_job(state='connected', message='Wi-Fi verified and saved. It will reconnect automatically when available.')
                settled = True
            except Exception:
                try:
                    self.rollback(pending)
                    settled = True
                    self.set_job(state='failed', message='New Wi-Fi did not pass connection/Internet checks. Previous working Wi-Fi or ATLAS-Rescue has been restored. Check password, signal or router Internet.')
                except Exception:
                    self.set_job(state='failed', message='Connection and recovery failed; pending recovery will retry when the network service restarts.')
            finally:
                data.clear()
                if settled:
                    (STATE/'pending.json').unlink(missing_ok=True)


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def start(manager):
    wifi = WifiManager(manager)

    class Request(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(20)
            _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in (0, 1000):
                return
            try:
                line = self.rfile.readline(4097)
                if len(line) > 4096:
                    raise ValueError('Request too large')
                req = json.loads(line)
                action = req.get('action')
                if action == 'status':
                    response = wifi.status()
                elif action == 'scan':
                    response = wifi.scan()
                elif action == 'connect':
                    response = wifi.connect(req)
                else:
                    raise ValueError('Unknown Wi-Fi operation')
            except ValueError as exc:
                response = {'error': str(exc)}
            except Exception:
                response = {'error': 'Wi-Fi service unavailable; existing profiles retained'}
            self.wfile.write(json.dumps(response).encode()+b'\n')

    Path(SOCKET).unlink(missing_ok=True)
    server = Server(SOCKET, Request)
    os.chown(SOCKET, 0, 1000)
    os.chmod(SOCKET, 0o660)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return wifi, server
