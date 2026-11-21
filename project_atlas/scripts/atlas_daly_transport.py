"""Bounded, response-driven gatttool polling; no ROS or actuator access."""
import os
import select
import subprocess
import time


def collect_until(read_chunk, predicate, deadline, clock=time.monotonic, stage='response'):
    text = ''
    while clock() < deadline:
        chunk = read_chunk(min(0.1, max(0.0, deadline - clock())))
        if chunk is None:
            raise RuntimeError(f'Daly Bluetooth process closed during {stage}')
        text += chunk
        if predicate(text):
            return text
    raise TimeoutError(f'Daly Bluetooth response deadline exceeded during {stage}')


class PersistentDalyClient:
    """One GATT connection, no pairing commands; fresh transactions or failure.

    Backoff is handled by the node, separately from healthy five-second polling.
    Any protocol/transport failure closes the connection before another attempt.
    """
    def __init__(self, mac, address_type, cccd, handle):
        self.mac, self.address_type = mac, address_type
        self.cccd, self.handle = cccd, handle
        self.proc = None
        self.connections = 0

    def _read(self, timeout):
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            return ''
        data = os.read(self.proc.stdout.fileno(), 4096)
        return data.decode('utf-8', errors='replace') if data else None

    def _exchange(self, command, predicate, stage, deadline):
        self.proc.stdin.write((command + '\n').encode())
        self.proc.stdin.flush()
        return collect_until(self._read, predicate, deadline, stage=stage)

    def read_snapshot(self, commands, decode):
        deadline = time.monotonic() + 8.0
        try:
            if self.proc is None:
                self.connections += 1
                self.proc = subprocess.Popen(
                    ['gatttool', '-b', self.mac, '-t', self.address_type, '-I'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self._exchange('connect', lambda s: 'Connection successful' in s, 'connect', deadline)
                self._exchange('mtu 64', lambda s: 'MTU was exchanged successfully:' in s, 'mtu', deadline)
                self._exchange(f'char-write-req {self.cccd} 0100',
                               lambda s: 'Characteristic value was written successfully' in s,
                               'notifications', deadline)
            # Never reuse bytes waiting from a previous transaction. Bounded
            # drain refuses an unsolicited continuous stream instead of hanging.
            for _ in range(64):
                stale = self._read(0)
                if stale is None:
                    raise RuntimeError('Daly Bluetooth process closed before transaction')
                if not stale:
                    break
            else:
                raise RuntimeError('Daly unsolicited input exceeded drain limit')
            checks = {
                'pack': lambda d: all(k in d for k in ('voltage_v', 'current_a', 'soc_percent')),
                'cells': lambda d: d.get('cells_complete') is True,
                'cell_extreme': lambda d: 'min_cell_voltage_v' in d and 'max_cell_voltage_v' in d,
            }
            output = []
            for name, command in commands.items():
                output.append(self._exchange(f'char-write-req {self.handle} {command}',
                              lambda text, check=checks[name]: check(decode(text)), name, deadline))
            return '\n'.join(output)
        except Exception:
            self.close()
            raise

    def close(self):
        proc, self.proc = self.proc, None
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=0.5)


class ReconnectBackoff:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.failures = 0
        self.next_at = 0.0

    def remaining(self):
        return max(0.0, self.next_at-self.clock())

    def failed(self):
        self.failures += 1
        delay = (10, 20, 40, 80, 120)[min(self.failures-1, 4)]
        self.next_at = self.clock()+delay

    def succeeded(self):
        self.failures, self.next_at = 0, 0.0


def read_snapshot(mac, address_type, cccd, handle, commands, decode):
    """Compatibility one-shot caller; production node owns a persistent client."""
    client = PersistentDalyClient(mac, address_type, cccd, handle)
    try:
        return client.read_snapshot(commands, decode)
    finally:
        client.close()
