#!/usr/bin/env python3
"""Local network-only failover. No ROS, motion, modem AT writes or public access.

Own routes are tagged protocol 199; never delete NetworkManager/DHCP routes.
Internet probes bind their sockets to each interface, bypassing the default route.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

LOG = logging.getLogger('atlas-network')
PROTO = '199'
METRIC = '9'
STATUS = Path('/run/atlas-network/status.json')


def run(args, timeout=8, check=True):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f'{args[0]} failed: {p.stderr.strip()[:250]}')
    return p.stdout.strip()


def ip_json(*args):
    return json.loads(run(['ip', '-j', *args]) or '[]')


class Policy:
    """Hysteresis prevents one missed request from changing the operator link."""
    def __init__(self):
        self.good_wifi = 0
        self.bad_wifi = 0
        self.bad_both = 0
        self.uplink = 'WIFI'

    def update(self, wifi, cellular, ap):
        self.good_wifi = self.good_wifi + 1 if wifi else 0
        self.bad_wifi = 0 if wifi else self.bad_wifi + 1
        self.bad_both = 0 if wifi or cellular else self.bad_both + 1
        if ap:
            self.uplink = 'CELLULAR' if cellular else 'OFFLINE'
            return self.uplink, False
        if wifi and (self.uplink == 'WIFI' or self.good_wifi >= 3):
            self.uplink = 'WIFI'
        elif self.bad_wifi >= 3 and cellular:
            self.uplink = 'CELLULAR'
        elif self.bad_both >= 6:
            self.uplink = 'OFFLINE'
        return self.uplink, self.bad_both >= 6


def probe(iface):
    """No DNS dependency or redirects. TLS certificate validation stays enabled."""
    start = time.monotonic()
    if not Path('/sys/class/net', iface).exists():
        return {'ok': False, 'reason': 'interface absent'}
    # Two different providers; neither needs the currently selected DNS server.
    for url in ('https://1.1.1.1/cdn-cgi/trace', 'https://8.8.8.8/'):
        try:
            value = run(['curl', '-4', '--noproxy', '*', '--interface', iface,
                         '--connect-timeout', '2', '--max-time', '3', '--max-filesize', '4096',
                         '-fsS', '-w', '\nATLAS_HTTP=%{http_code}', url], timeout=4)
            code = value.rsplit('ATLAS_HTTP=', 1)[-1].strip()
            valid = (code == '200' and '\nip=' in '\n'+value) if 'cdn-cgi' in url else code in ('200', '301', '302')
            if valid:
                return {'ok': True, 'elapsed_ms': round((time.monotonic()-start)*1000),
                        'reason': 'authenticated HTTPS endpoint reached'}
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            pass
    return {'ok': False, 'reason': 'both HTTPS probes failed'}


def gateway(iface):
    for route in ip_json('-4', 'route', 'show', 'default'):
        if route.get('dev') == iface and route.get('gateway') and str(route.get('protocol')) != PROTO:
            return route['gateway']
    return None


def clear_own_routes():
    for family in ('-4', '-6'):
        for route in ip_json(family, 'route', 'show', 'proto', PROTO):
            if route.get('dst') != 'default' or str(route.get('metric')) != METRIC:
                continue
            args = ['ip', family, 'route', 'del']
            if route.get('type') == 'unreachable':
                args += ['unreachable']
            args += ['default', 'proto', PROTO, 'metric', METRIC]
            if route.get('dev'):
                args += ['dev', route['dev']]
            run(args, check=False)


def domains(iface):
    out = run(['resolvectl', 'domain', iface], check=False)
    return out.split(':', 1)[1].split() if ':' in out else []


class Manager:
    def __init__(self, config, monitor=False):
        self.config = config
        self.wifi = config['wifi_interface']
        self.cell = config['cellular_interface']
        self.policy = Policy()
        self.monitor = monitor
        self.last_retry = time.monotonic()
        self.last_action = 'Starting; no network change yet'
        self.last_mode = None
        self.cell_probe_at = 0.0
        self.cell_probe_result = None
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.network_lock = threading.RLock()
        self.wifi_setup = None

    def ap_active(self):
        return run(['nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', self.wifi],
                   check=False) == self.config['hotspot_uuid']

    def set_dns(self, cell):
        current = domains(self.cell)
        # Only our catch-all routing domain is added/removed; keep DHCP domains.
        wanted = [x for x in current if x != '~.'] + (['~.'] if cell else [])
        if wanted != current:
            run(['resolvectl', 'domain', self.cell, *(wanted or [''])], check=False)

    def route(self, selected):
        if selected == 'CELLULAR':
            gw = gateway(self.cell)
            if not gw:
                raise RuntimeError('Cellular probe passed but no cellular DHCP gateway exists')
            run(['ip', '-4', 'route', 'replace', 'default', 'via', gw, 'dev', self.cell,
                 'proto', PROTO, 'metric', METRIC])
            # Do not leave a broken Wi-Fi IPv6 default preferred by applications.
            run(['ip', '-6', 'route', 'replace', 'unreachable', 'default',
                 'proto', PROTO, 'metric', METRIC])
            self.set_dns(True)
        elif selected in ('WIFI', 'OFFLINE'):
            clear_own_routes()
            self.set_dns(False)

    def hotspot(self):
        run(['nmcli', '--wait', '20', 'connection', 'up', 'uuid', self.config['hotspot_uuid']], timeout=25)
        run(['systemctl', 'start', 'atlas-hotspot-dhcp.service'])
        self.last_retry = time.monotonic()
        self.last_action = 'Local rescue hotspot active; Internet is not provided by this hotspot'
        LOG.warning(self.last_action)

    def clients(self):
        return run(['iw', 'dev', self.wifi, 'station', 'dump']).count('Station ')

    def retry_wifi(self):
        """A single radio cannot probe home Wi-Fi while keeping the AP up.

        Never disconnect an associated rescue operator. With no clients, try once
        every three minutes, and restore the AP if Internet remains unavailable.
        """
        if time.monotonic() - self.last_retry < 180 or self.clients() > 0:
            return
        self.last_retry = time.monotonic()
        LOG.info('No rescue clients; checking saved Wi-Fi (AP briefly unavailable)')
        run(['systemctl', 'stop', 'atlas-hotspot-dhcp.service'])
        try:
            candidate = self.wifi_setup.candidate() if self.wifi_setup else self.config['wifi_uuid']
            if not candidate:
                self.hotspot()
                return
            run(['nmcli', '--wait', '15', 'connection', 'up', 'uuid', candidate], timeout=20)
            if probe(self.wifi)['ok']:
                self.policy.good_wifi = 3
                self.policy.uplink = 'WIFI'
                self.policy.bad_wifi = self.policy.bad_both = 0
                self.route('WIFI')
                self.last_action = 'Saved Wi-Fi Internet recovered'
                LOG.info(self.last_action)
                return
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
        self.hotspot()

    def sample(self):
        ap = self.ap_active()
        # Keep standby SIM probing modest (~30 seconds); probe every cycle on
        # Wi-Fi failure or when cellular is the selected uplink.
        probe_cell = self.cell_probe_result is None or time.monotonic()-self.cell_probe_at >= 30 or ap or self.policy.bad_wifi > 0 or self.policy.uplink == 'CELLULAR'
        futures = {name: self.pool.submit(probe, iface) for name, iface in
                   [('wifi', self.wifi), ('cellular', self.cell)]
                   if not (ap and name == 'wifi') and not (name == 'cellular' and not probe_cell)}
        checks = {name: task.result() for name, task in futures.items()}
        if probe_cell:
            self.cell_probe_at = time.monotonic()
            self.cell_probe_result = checks['cellular']
        checks['cellular'] = {**self.cell_probe_result, 'age_s': round(time.monotonic()-self.cell_probe_at, 1)}
        checks.setdefault('wifi', {'ok': False, 'reason': 'radio in hotspot mode'})
        selected, start_ap = self.policy.update(checks['wifi']['ok'], checks['cellular']['ok'], ap)
        if not self.monitor:
            self.route(selected)
            if start_ap and not ap:
                self.hotspot()
            elif ap:
                run(['systemctl', 'start', 'atlas-hotspot-dhcp.service'])
                self.retry_wifi()
            else:
                run(['systemctl', 'stop', 'atlas-hotspot-dhcp.service'])
        ap = self.ap_active()
        selected = self.policy.uplink
        actual = ip_json('-4', 'route', 'get', '1.1.1.1')
        state = {'time': time.time(), 'mode': 'MONITOR_ONLY' if self.monitor else selected,
                 'selected_interface': actual[0].get('dev') if actual else None,
                 'checks': checks, 'hotspot_active': ap, 'hotspot_ssid': self.config['hotspot_ssid'],
                 'hotspot_dashboard': 'http://10.42.0.1:8088/',
                 'last_action': self.last_action, 'wifi_failures': self.policy.bad_wifi,
                 'both_failures': self.policy.bad_both,
                 'note': 'Hotspot is local-only. Existing motion watchdogs remain unchanged. Probe failure is not proof of a defective SIM.'}
        if self.last_mode != (selected, ap):
            if not ap:
                self.last_action = {'WIFI': 'Wi-Fi Internet preferred; cellular checked on standby',
                                    'CELLULAR': 'Wi-Fi failed; Internet routed through SIM',
                                    'OFFLINE': 'Both Internet checks failed'}[selected]
                state['last_action'] = self.last_action
            LOG.info('Uplink=%s hotspot=%s Wi-Fi=%s cellular=%s', selected, ap,
                     checks['wifi']['ok'], checks['cellular']['ok'])
            self.last_mode = (selected, ap)
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATUS.with_suffix('.tmp')
        tmp.write_text(json.dumps(state))
        tmp.chmod(0o644)
        tmp.replace(STATUS)
        return state

    def cleanup(self):
        if not self.monitor:
            clear_own_routes()
            self.set_dns(False)
        self.pool.shutdown(wait=False, cancel_futures=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/atlas-network.json')
    parser.add_argument('--monitor', action='store_true')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--cleanup', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    config = json.loads(Path(args.config).read_text())
    manager = Manager(config, args.monitor)
    if args.cleanup:
        manager.cleanup()
        return
    server = None
    if not args.monitor and not args.once:
        from atlas_wifi_manager import start
        manager.wifi_setup, server = start(manager)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopping:
            try:
                with manager.network_lock:
                    result = manager.sample()
                if args.once:
                    print(json.dumps(result, indent=2))
                    break
            except Exception as exc:
                LOG.exception('Network check failed; existing network profiles retained')
                if STATUS.exists():
                    try:
                        prior = json.loads(STATUS.read_text())
                        prior.update(time=time.time(), mode='ERROR', error=str(exc))
                        STATUS.write_text(json.dumps(prior))
                    except (OSError, ValueError):
                        pass
            # Responsive termination; this process never runs in the ROS loop.
            for _ in range(10):
                if stopping or args.once:
                    break
                time.sleep(0.5)
    finally:
        if server:
            server.shutdown()
            server.server_close()
        manager.cleanup()


if __name__ == '__main__':
    main()
