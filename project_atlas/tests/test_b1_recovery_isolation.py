"""Exercise only the isolation gate in bash; never execute the B1 script."""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/diagnostics/stm32_readback/b1_run.sh'


@pytest.mark.parametrize('state,rc,allowed', [
    ('inactive', 0, True), ('active', 0, False), ('activating', 0, False),
    ('deactivating', 0, False), ('failed', 0, False), ('', 0, False),
    ('inactive', 1, False), ('inactive\nactive', 0, False),
])
def test_recovery_gate(tmp_path, state, rc, allowed):
    source = SCRIPT.read_text()
    gate = source.split('require_recovery_isolated() {', 1)[1].split('\n}', 1)[0]
    stub = tmp_path / 'systemctl'
    stub.write_text('#!/bin/bash\nprintf "%s\\n" "$TEST_STATE"\nexit "$TEST_RC"\n')
    stub.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path) + ':' + os.environ['PATH'],
               TEST_STATE=state, TEST_RC=str(rc))
    result = subprocess.run(['bash', '-c', 'require_recovery_isolated() {' + gate +
                             '\n}\nrequire_recovery_isolated'], env=env,
                            capture_output=True, text=True)
    assert (result.returncode == 0) == allowed


def test_gate_precedes_stop_and_does_not_stop_recovery():
    source = SCRIPT.read_text()
    assert source.count('require_recovery_isolated || exit 2') == 2
    assert 'require_recovery_isolated || exit 2\nsystemctl --user stop rover-base-telemetry.service' in source
    assert 'stop atlas-sensor-recovery' not in source
