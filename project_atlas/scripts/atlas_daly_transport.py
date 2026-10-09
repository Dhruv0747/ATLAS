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


def read_snapshot(mac, address_type, cccd, handle, commands, decode):
    # Healthy transactions usually finish well before this deadline. Failure
    # produces unhealthy telemetry, never old data stamped as a fresh success.
    deadline = time.monotonic() + 8.0
    proc = subprocess.Popen(
        ['gatttool', '-b', mac, '-t', address_type, '-I'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    output = []

    def read_chunk(timeout):
        ready, _, _ = select.select([proc.stdout], [], [], timeout)
        if not ready:
            return ''
        data = os.read(proc.stdout.fileno(), 4096)
        return data.decode('utf-8', errors='replace') if data else None

    def exchange(command, predicate, stage):
        proc.stdin.write((command + '\n').encode())
        proc.stdin.flush()
        result = collect_until(read_chunk, predicate, deadline, stage=stage)
        output.append(result)

    try:
        exchange('connect', lambda s: 'Connection successful' in s, 'connect')
        exchange('mtu 64', lambda s: 'MTU was exchanged successfully:' in s, 'mtu')
        exchange(f'char-write-req {cccd} 0100',
                 lambda s: 'Characteristic value was written successfully' in s, 'notifications')
        checks = {
            'pack': lambda d: all(k in d for k in ('voltage_v', 'current_a', 'soc_percent')),
            'cells': lambda d: d.get('cells_complete') is True,
            'cell_extreme': lambda d: 'min_cell_voltage_v' in d and 'max_cell_voltage_v' in d,
        }
        for name, command in commands.items():
            exchange(f'char-write-req {handle} {command}',
                     lambda text, check=checks[name]: check(decode(text)), name)
        return '\n'.join(output)
    finally:
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=0.5)
