"""Generate dashboard executor bookkeeping variants from the EXACT live overlay (hash-pinned).
V1: per-cycle ExitStack -> inline __enter__ + one LIFO exit block (same entities, order, exception semantics).
V2: post-wait waitable membership list scan (O(W^2)) -> per-cycle identity set (no cross-cycle state).
V3: V1 + V2."""
import hashlib, sys
from pathlib import Path
LIVE_SHA = '543e41125a6095ba5a69f114deaa2dc4cf54c4df2029f78fdb80c99ecf81b5c1'

HELPER = '''

class _EnteredHandles:
    """ATLAS: lightweight replacement for the per-cycle ExitStack used only by
    _wait_for_ready_callbacks. Each entity handle is entered inline (handle.__enter__())
    and appended to a list; on leaving the block every entered handle is exited in
    LIFO order with ExitStack's exception semantics (all exits run, an exception
    raised by an exit replaces the active one, a true return suppresses). Nothing
    is kept between wait cycles."""

    __slots__ = ('_entered',)

    def __init__(self, entered):
        self._entered = entered

    def __enter__(self):
        return self._entered

    def __exit__(self, *exc_details):
        received_exc = exc_details[0] is not None
        suppressed_exc = False
        pending_raise = False
        entered = self._entered
        while entered:
            handle = entered.pop()
            try:
                if handle.__exit__(*exc_details):
                    suppressed_exc = True
                    pending_raise = False
                    exc_details = (None, None, None)
            except BaseException:
                exc_details = sys.exc_info()
                pending_raise = True
        if pending_raise:
            raise exc_details[1]
        return received_exc and suppressed_exc
'''

def sub(s, old, new, count=1):
    n = s.count(old)
    if n != count:
        raise SystemExit('pattern count %d != %d: %r' % (n, count, old[:60]))
    return s.replace(old, new)

def v1(s):
    s = sub(s, 'import time\n', 'import sys\nimport time\n')
    s = sub(s, "WaitableEntityType = TypeVar('WaitableEntityType')\n", "WaitableEntityType = TypeVar('WaitableEntityType')\n" + HELPER)
    s = sub(s, '            with ExitStack() as context_stack:\n',
               '            entered_handles = []\n            with _EnteredHandles(entered_handles):\n')
    for expr in ('sub.handle', 'cli.handle', 'srv.handle', 'tmr.handle', 'gc.handle', 'waitable', 'self._context.handle'):
        s = sub(s, 'context_stack.enter_context(%s)' % expr,
                   '_h = %s; _h.__enter__(); entered_handles.append(_h)' % expr)
    assert 'context_stack' not in s
    return s

def v2(s):
    s = sub(s, '                waitables = valid_waitables\n',
               '                waitables = valid_waitables\n                waitable_ids = {id(w) for w in waitables}\n')
    s = sub(s, '                        if wt in waitables and wt.is_ready(wait_set):\n',
               '                        if id(wt) in waitable_ids and wt.is_ready(wait_set):\n')
    return s

if __name__ == '__main__':
    src, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    s = src.read_text()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == LIVE_SHA, 'live overlay hash mismatch'
    for name, text in (('v0', s), ('v1', v1(s)), ('v2', v2(s)), ('v3', v2(v1(s)))):
        p = out / ('executor_%s.py' % name); p.write_text(text)
        compile(text, str(p), 'exec')
        print(name, hashlib.sha256(text.encode()).hexdigest())
