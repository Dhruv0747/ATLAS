#!/usr/bin/env python3
"""Stage 28 (proposal): add the read-only RC report hook to yahboom_base.py. Additive, anchor-exact.

Adds, and nothing else:
  * a guarded import of the Stage 27 FrameForwarder and the new RC report decoder;
  * ONE publisher (/atlas/rc/frames, std_msgs/String JSON, the existing Test Lab schema);
  * ONE 10 Hz timer that reads the latest report Rosmaster_Lib stored and forwards new, fresh frames.
No subscription, no command, no change to motor keepalive, mixer, E-STOP, arbitration or odometry.
Usage: insert_rc_hooks.py <yahboom_base.py>   (refuses if any anchor is missing or already patched)
"""
import sys

MARK = '# ATLAS Stage 28 RC report'

IMPORT_ANCHOR = 'from atlas_usb_identity import open_verified\n'
IMPORT_ADD = '''try:  # ATLAS Stage 28 RC report: optional, read-only; the base driver runs without it.
    from atlas_rc_readonly_bridge import FrameForwarder as _RcFrameForwarder
    from atlas_yahboom_rc_report import RcReportForwarder as _RcReportForwarder
except Exception:  # pragma: no cover - missing module must never stop the motor driver
    _RcFrameForwarder = _RcReportForwarder = None
'''

TIMER_ANCHOR = '        self.create_timer(1.0, self._systemd_watchdog)\n'
TIMER_ADD = '''        # ATLAS Stage 28 RC report: publish-only telemetry for the FlySky Test Lab.
        self._rc_forwarder = None
        self._rc_last_stamp = None
        if (_RcReportForwarder is not None and os.environ.get('ATLAS_RC_REPORT', '1') != '0'
                and hasattr(self.bot, 'get_rc_sbus_report')):
            self._rc_forwarder = _RcReportForwarder(_RcFrameForwarder('sbus'))
            self._pub_rc_frames = self.create_publisher(String, '/atlas/rc/frames', 10)
            self.create_timer(0.1, self._forward_rc_report)
'''

METHOD_ANCHOR = '    def _systemd_watchdog(self):\n'
METHOD_ADD = '''    def _forward_rc_report(self):
        """ATLAS Stage 28 RC report: read-only. Never raises into the executor."""
        try:
            report = self.bot.get_rc_sbus_report()
            if report is None or report[1] == self._rc_last_stamp:
                return
            self._rc_last_stamp = report[1]
            was_bad = self._rc_forwarder.drive_enabled_seen
            self._rc_forwarder.handle(report[0], report[1], time.time(), self._publish_rc_frame)
            if self._rc_forwarder.drive_enabled_seen and not was_bad:
                self.get_logger().error(
                    'RC report says the board firmware can DRIVE from SBUS; frames ignored. '
                    'Disconnect the SBUS lead and restore the approved firmware.')
        except Exception as exc:  # pragma: no cover - defensive
            self.get_logger().warning(f'RC report forward skipped: {exc}', throttle_duration_sec=30.0)

    def _publish_rc_frame(self, msg):
        out = String()
        out.data = json.dumps(dict(msg, src='yahboom'), separators=(',', ':'))
        self._pub_rc_frames.publish(out)

'''


def patch(text: str) -> str:
    if MARK in text:
        raise SystemExit('already patched')
    for anchor in (IMPORT_ANCHOR, TIMER_ANCHOR, METHOD_ANCHOR):
        if text.count(anchor) != 1:
            raise SystemExit('anchor not unique/missing: %r' % anchor)
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_ADD)
    text = text.replace(TIMER_ANCHOR, TIMER_ANCHOR + TIMER_ADD)
    text = text.replace(METHOD_ANCHOR, METHOD_ADD + METHOD_ANCHOR)
    return text


if __name__ == '__main__':
    path = sys.argv[1]
    src = open(path, encoding='utf-8').read()
    out = patch(src)
    compile(out, path, 'exec')
    open(path, 'w', encoding='utf-8').write(out)
    print('patched', path)
