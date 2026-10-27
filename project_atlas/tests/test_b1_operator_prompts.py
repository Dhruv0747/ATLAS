"""PTY interaction with stub Python only: no systemctl, serial or physical operations."""
import os
from pathlib import Path
import pty
import select
import subprocess
import time


def test_prompts_wait_for_each_confirmation(tmp_path):
    script=Path(__file__).parents[1]/'tools/diagnostics/stm32_readback/b1_supervised_read.sh'
    stub=tmp_path/'python3'
    stub.write_text('#!/bin/bash\nprintf "%s\n" "$*" >> "$CALL_LOG"\nexit 0\n')
    stub.chmod(0o755)
    log=tmp_path/'calls'
    env=dict(os.environ,PATH=str(tmp_path)+':'+os.environ['PATH'],CALL_LOG=str(log),OWNER_APPROVED='yes',ATLAS_B1_SESSION='fake',ATLAS_B1_OUT=str(tmp_path/'out'),ATLAS_B1_PORT='/dev/fake')
    master,slave=pty.openpty()
    p=subprocess.Popen(['bash',str(script)],stdin=slave,stdout=slave,stderr=slave,env=env)
    os.close(slave)
    output=b''
    def until(token):
        nonlocal output
        deadline=time.monotonic()+3
        while token.encode() not in output:
            assert time.monotonic()<deadline, output
            if select.select([master],[],[],.1)[0]: output+=os.read(master,8192)
    try:
        until('Confirm physical STM32F103RCT6')
        assert not log.exists()
        os.write(master,b'DONE\n');until('Press and HOLD BOOT0 now.')
        assert 'atlas_stm32_readback.py' not in log.read_text()
        os.write(master,b'DONE\n');until('While holding BOOT0, press and release RESET.')
        assert 'atlas_stm32_readback.py' not in log.read_text()
        os.write(master,b'DONE\n');until('Now release BOOT0. Do not press any button again.')
        assert 'atlas_stm32_readback.py' not in log.read_text()
        os.write(master,b'DONE\n')
        assert p.wait(timeout=3)==0
        calls=log.read_text()
        assert calls.count('atlas_stm32_readback.py')==1
        assert calls.count('check-read')==3
        assert 'abort --session fake' in calls
    finally:
        if p.poll() is None:p.kill();p.wait()
        os.close(master)
