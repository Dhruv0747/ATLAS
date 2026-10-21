"""Duty pacing for one explicitly owned NEW test process group, not production.

Useful when user cgroups lack the CPU controller. Duty fraction is wall-time
permission to execute, NOT an asserted CPU percentage (multithreaded work differs).
Actual aggregate CPU admission remains independently enforced by the supervisor.
"""
import os
import signal
import threading


class OwnedPacer:
    def __init__(self,proc,run_s=.02,hold_s=.08):
        if not 0<run_s<=.05 or not .01<=hold_s<=.2:raise ValueError('invalid bounded duty period')
        if proc.pid==os.getpid() or os.getpgid(proc.pid)!=proc.pid or os.getpgrp()==proc.pid:
            raise ValueError('only a newly session-owned child group may be paced')
        self.proc,self.run_s,self.hold_s=proc,run_s,hold_s
        self.event=threading.Event();self.error=None
        self.thread=threading.Thread(target=self._loop,name='owned-test-pacer',daemon=True)

    def _signal(self,sig):
        try:os.killpg(self.proc.pid,sig)
        except ProcessLookupError:pass

    def _loop(self):
        try:
            while not self.event.is_set() and self.proc.poll() is None:
                self._signal(signal.SIGSTOP)
                if self.event.wait(self.hold_s):break
                self._signal(signal.SIGCONT)
                self.event.wait(self.run_s)
        except Exception as e:self.error=str(e)
        finally:self._signal(signal.SIGCONT)

    def start(self):self.thread.start();return self

    def close(self):
        self.event.set();self.thread.join(timeout=1);self._signal(signal.SIGCONT)
        if self.thread.is_alive():raise RuntimeError('test pacer did not stop')
