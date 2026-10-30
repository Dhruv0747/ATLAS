#!/usr/bin/env python3
"""Stage 29: additive FlySky SwD E-STOP reset for the Stage 29 FlySky mux (applied AFTER insert_flysky_mux.py;
anchor-exact; refuses on any mismatch).

Adds ONLY a second way to release the existing latched E-STOP, and only when every check in
atlas_flysky_reset.MuxResetGate passes (reset gate ATLAS_FLYSKY_RESET_ENABLED=1, FlySky gate on, FlySky selected,
latched >= 2 s, Xbox connected and untouched, rover commanded zero and encoders still, fresh one-time request).
Unchanged: every stop (Xbox B, Xbox absence, FlySky SwB/SwA/failsafe, dashboard/voice), the Xbox LB reset, selection,
limits and every other channel. A release flushes every channel exactly like the LB reset.
Usage: insert_flysky_reset_mux.py <input Stage-29 atlas_cmd_vel_mux.py> <output>
"""
import sys

MARK = '# ATLAS Stage 29 FlySky reset'
REQUIRES = '# ATLAS Stage 29 FlySky'
EDITS = [
    ("from atlas_remote_stop import RemoteStop\n",
     "from atlas_remote_stop import RemoteStop\n"
     "from atlas_flysky_reset import GATE_ENV as FLYSKY_RESET_ENV, MuxResetGate   # ATLAS Stage 29 FlySky reset\n"),
    ("        self.create_subscription(Empty, '/atlas/flysky/stop', self.on_flysky_stop, 10)\n",
     "        self.create_subscription(Empty, '/atlas/flysky/stop', self.on_flysky_stop, 10)\n"
     "        # ATLAS Stage 29 FlySky reset: second release path, off unless its own gate is set.\n"
     "        self.flysky_reset_gate = MuxResetGate(os.environ.get(FLYSKY_RESET_ENV, '0') == '1')\n"
     "        self.create_subscription(String, '/atlas/flysky/reset_request', self.on_flysky_reset_request, 10)\n"),
    ("    def on_voice_stop(self, _msg):\n",
     "        self.flysky_reset_observe()   # ATLAS Stage 29 FlySky reset: end of on_encoder_health\n\n"
     "    def on_voice_stop(self, _msg):\n"),
    ("        self._remote_stop_hold_latched = latched\n        self._remote_stop_hold_reason = reason\n",
     "        self._remote_stop_hold_latched = latched\n        self._remote_stop_hold_reason = reason\n"
     "        self.flysky_reset_observe()   # ATLAS Stage 29 FlySky reset: see every latch transition\n"),
    ("    def on_flysky_stop(self, _msg):\n",
     "    # ---- ATLAS Stage 29 FlySky reset (additive)\n"
     "    def flysky_reset_observe(self):\n"
     "        gate = getattr(self, 'flysky_reset_gate', None)\n"
     "        if gate is not None:\n"
     "            gate.observe(time.monotonic(), bool(self.remote_stop.latched), self.moving(self.last_sent),\n"
     "                         self.encoder_health, self.encoder_health_rx)\n"
     "\n"
     "    def on_flysky_reset_request(self, msg):\n"
     "        now = time.monotonic()\n"
     "        self.remote_stop.check(now)              # an Xbox gap latches first, exactly as in the watchdog\n"
     "        ok, why = self.flysky_reset_gate.decide(\n"
     "            now, msg.data, drive_enabled=self.flysky_drive_enabled, controller=self.manual_controller,\n"
     "            latched=bool(self.remote_stop.latched), commanding=self.moving(self.last_sent),\n"
     "            xbox_rx=self.remote_stop.last_rx, xbox_neutral_since=self.remote_stop.neutral_since,\n"
     "            enc=self.encoder_health, enc_rx=self.encoder_health_rx)\n"
     "        if not ok:\n"
     "            self.get_logger().warn('FlySky reset refused: %s' % why)\n"
     "            self.publish_mode()\n"
     "            return\n"
     "        self.hold_remote_stop()                  # flush first: no pre-stop command can replay\n"
     "        rs = self.remote_stop\n"
     "        rs.latched, rs.reason = False, why\n"
     "        rs.reset_armed, rs.reset_since, rs.reset_ready = False, None, False\n"
     "        self.hold_remote_stop()                  # publish the release transition immediately\n"
     "        self.get_logger().warn(why)\n"
     "\n"
     "    def on_flysky_stop(self, _msg):\n"),
    ("            'flysky_drive_enabled': getattr(self, 'flysky_drive_enabled', False),\n",
     "            'flysky_drive_enabled': getattr(self, 'flysky_drive_enabled', False),\n"
     "            'flysky_reset': (self.flysky_reset_gate.status(time.monotonic())\n"
     "                             if getattr(self, 'flysky_reset_gate', None) is not None else None),   # ATLAS Stage 29 FlySky reset\n"),
]


def apply(text: str) -> str:
    if MARK in text:
        raise SystemExit('refused: already patched')
    if REQUIRES not in text:
        raise SystemExit('refused: input is not the Stage 29 FlySky mux')
    for old, new in EDITS:
        n = text.count(old)
        if n != 1:
            raise SystemExit('refused: anchor found %d times: %r' % (n, old[:70]))
        if old not in new:
            raise SystemExit('refused: edit is not additive around its anchor')
        text = text.replace(old, new, 1)
    return text


if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    out = apply(open(src, encoding='utf-8').read())
    compile(out, dst, 'exec')
    open(dst, 'w', encoding='utf-8').write(out)
    print('wrote', dst)
