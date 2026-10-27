#!/usr/bin/env python3
"""Stage 28 (proposal): additive, anchor-exact base-maintenance coordination for atlas_sensor_recovery.py.

Applies ONLY to the exact live baseline (SHA256 c6b5ac79...daaf5); refuses on any other input or on a second run.
Removes no source line. Adds, and nothing else:
  * a guarded import of atlas_base_maintenance (if it is missing, an existing lease FAILS CLOSED for the base);
  * base-only hold in maintenance_hold() while a lease is ACTIVE or INVALID (camera hold unchanged);
  * the final lease check for a base restart INSIDE the dispatch lock, held until `systemctl restart` returns;
  * a per-check() acknowledgement (session, in-flight base recovery) for the deployer, plus INVALID notices;
  * "base_maintenance" in /atlas/recovery_state.
Unrelated monitors never enter the new code; E-STOP / zero-command restart guards and fault reporting are untouched.
Usage: insert_recovery_base_hold.py <atlas_sensor_recovery.py>
"""
import hashlib
import sys

BASELINE_SHA256 = 'c6b5ac7979b6aff24c2f1a13a365d039b833da4c37997d3a8a07b21a928daaf5'
MARK = '# ATLAS Stage 28 base maintenance'

EDITS = [
    # (anchor, insertion, where)
    ('from std_msgs.msg import Float32, Int32, String\n',
     '''import contextlib as _atlas_contextlib  # ATLAS Stage 28 base maintenance
try:  # ATLAS Stage 28 base maintenance: if missing, an existing lease fails closed for the base only
    import atlas_base_maintenance as _atlas_bm
except Exception:  # pragma: no cover - exercised by test_recovery_without_module
    _atlas_bm = None
_ATLAS_BASE = "rover-base-telemetry.service"  # ATLAS Stage 28 base maintenance
''', 'after'),
    ('        self.recovering = set()\n',
     '        self._atlas_base_init()  # ATLAS Stage 28 base maintenance\n', 'after'),
    ('    def maintenance_hold(self, item):\n'
     '        """True while an intentional, bounded restart of this service is owned by another ATLAS component."""\n',
     '''        if item.service == _ATLAS_BASE and self._atlas_base_verdict()[0] != "NONE":  # ATLAS Stage 28
            return True
''', 'after'),
    ('    def maintenance_hold(self, item):\n',
     '''    # ATLAS Stage 28 base maintenance: additive and base-only. Other monitors never enter this code.
    def _atlas_base_init(self):
        self._atlas_base_hold_state = "NONE"
        self._atlas_base_stacks = {}
        self._atlas_base_notice = 0.0
        self._atlas_base_session = None
        self._atlas_bm_m = None
        try:
            if _atlas_bm is not None:
                self._atlas_bm_m = _atlas_bm.Maintenance()
        except Exception as exc:  # pragma: no cover
            self.get_logger().error(f"ATLAS base maintenance init failed: {exc!r}")
        self.get_logger().info(
            "ATLAS base maintenance coordination: " + (
                "loaded" if self._atlas_bm_m is not None
                else "UNAVAILABLE (an existing lease withholds base restarts)"))

    def _atlas_base_verdict(self):
        if self._atlas_bm_m is None:
            path = f"/run/user/{os.getuid()}/atlas-base-maintenance/lease.json"
            if os.path.lexists(path):
                return "INVALID", "maintenance module unavailable while a lease exists", None
            return "NONE", "no lease", None
        try:
            verdict = self._atlas_bm_m.evaluate()
            return verdict.state, verdict.reason, verdict.lease
        except Exception as exc:
            return "INVALID", f"lease evaluation error {type(exc).__name__}", None

    def _atlas_base_busy(self):
        with self.lock:
            return any(i.name in self.recovering for i in MONITORS if i.service == _ATLAS_BASE)

    def _atlas_base_maint_tick(self):
        """Every check(): publish INVALID notices and acknowledge an ACTIVE lease. Never raises."""
        try:
            state, reason, lease = self._atlas_base_verdict()
            self._atlas_base_hold_state = state
            now = time.monotonic()
            if state == "INVALID" and now - self._atlas_base_notice >= COOLDOWN:
                self._atlas_base_notice = now
                self.publish_status(
                    f"BASE MAINTENANCE HOLD INVALID: {reason}; base restarts withheld; "
                    "fault reporting and other recovery active; operator release required")
            if state != "ACTIVE" or self._atlas_bm_m is None:
                self._atlas_base_session = None
                return
            if lease["session"] != self._atlas_base_session:
                self._atlas_base_session = lease["session"]
                self.publish_status(
                    f"BASE MAINTENANCE HOLD ACTIVE: session {lease['session'][:8]}; base restarts withheld; "
                    "fault reporting and other recovery active")
            try:
                with self._atlas_bm_m.lock("dispatch", timeout=0):
                    self._atlas_bm_m.write_ack(lease["session"], self._atlas_base_busy(), os.getpid())
            except _atlas_bm.Refused:
                self._atlas_bm_m.write_ack(lease["session"], True, os.getpid(), "dispatch busy")
        except Exception as exc:
            if time.monotonic() - self._atlas_base_notice >= COOLDOWN:
                self._atlas_base_notice = time.monotonic()
                self.publish_status(f"BASE MAINTENANCE ACK FAILED: {type(exc).__name__}: {exc}")

    def _atlas_base_dispatch_enter(self, item):
        """Final lease check for a base restart, under the dispatch lock kept until restart returns."""
        if item.service != _ATLAS_BASE:
            return True
        if self._atlas_bm_m is None:
            state, reason, _ = self._atlas_base_verdict()
            if state != "NONE":
                self.publish_status(f"RECOVERY CANCELED: {item.name}; base maintenance {state}: {reason}")
                return False
            return True
        stack = _atlas_contextlib.ExitStack()
        try:
            verdict = stack.enter_context(self._atlas_bm_m.recovery_dispatch())
        except Exception as exc:
            stack.close()
            self.publish_status(f"RECOVERY CANCELED: {item.name}; base maintenance dispatch unavailable ({exc})")
            return False
        if verdict.hold:
            stack.close()
            self.publish_status(
                f"RECOVERY CANCELED: {item.name}; base maintenance {verdict.state}: {verdict.reason}")
            return False
        self._atlas_base_stacks[item.name] = stack
        return True

    def _atlas_base_dispatch_exit(self, item):
        stack = self._atlas_base_stacks.pop(item.name, None)
        if stack is not None:
            stack.close()

''', 'before'),
    ('    def check(self):\n        now = time.monotonic()\n',
     '        self._atlas_base_maint_tick()  # ATLAS Stage 28 base maintenance\n', 'after'),
    ('            subprocess.run(\n                ["systemctl", "--user", "restart", item.service],\n',
     '''            if not self._atlas_base_dispatch_enter(item):  # ATLAS Stage 28: last check, under lock
                return
''', 'before'),
    ('        finally:\n            with self.lock:\n                self.recovering.discard(item.name)\n',
     '            self._atlas_base_dispatch_exit(item)  # ATLAS Stage 28 base maintenance\n', 'after_first_line'),
    ('            "recovering": sorted(self.recovering),\n',
     '            "base_maintenance": getattr(self, "_atlas_base_hold_state", "UNKNOWN"),  # ATLAS Stage 28\n',
     'after'),
]


def patch(src):
    if hashlib.sha256(src.encode('utf-8')).hexdigest() != BASELINE_SHA256:
        raise SystemExit('refused: input is not the reviewed live baseline c6b5ac79')
    if MARK in src:
        raise SystemExit('refused: already patched')
    for anchor, add, where in EDITS:
        if src.count(anchor) != 1:
            raise SystemExit(f'refused: anchor not unique/missing: {anchor[:60]!r}')
        i = src.index(anchor)
        if where == 'after':
            src = src[:i + len(anchor)] + add + src[i + len(anchor):]
        elif where == 'before':
            src = src[:i] + add + src[i:]
        else:  # after_first_line: insert right after the anchor's first line ("finally:")
            j = i + anchor.index('\n') + 1
            src = src[:j] + add + src[j:]
    return src


def main():
    path = sys.argv[1]
    out = patch(open(path, encoding='utf-8').read())
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(out)
    print('patched', path)


if __name__ == '__main__':
    main()
