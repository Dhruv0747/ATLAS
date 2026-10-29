#!/usr/bin/env python3
"""Stage 29: additive FlySky controller selection for atlas_cmd_vel_mux.py (anchor-exact; refuses on any mismatch).

What it adds (XBOX stays the boot default, so behaviour is unchanged until the owner selects FlySky):
  * channel FLYSKY on /cmd_vel_flysky, accepted ONLY when ATLAS_FLYSKY_DRIVE_ENABLED=1 and FlySky is selected;
    REMOTE (/cmd_vel_joy) is accepted only while XBOX is selected: exactly one manual controller can drive;
  * services /atlas/manual_controller/select_xbox and /select_flysky: handover only while the E-STOP is latched and
    the rover is stopped, and it flushes every channel (zero motion by construction); the normal reset is still needed;
  * stop-only input /atlas/flysky/stop -> the existing latched E-STOP ('REMOTE STOP: FlySky stop');
  * independent FLYSKY clamps (params flysky_max_linear/angular, hard ceilings 0.25 m/s, 0.8 rad/s);
  * control_policy gains 'manual_controller' and 'flysky_drive_enabled'.
Unchanged: the Xbox /joy stop and LB reset (the Xbox stays the stop device and must be connected), every other
channel, guard, timeout and limit.
Usage: insert_flysky_mux.py <input atlas_cmd_vel_mux.py> <output>
"""
import sys

MARK = '# ATLAS Stage 29 FlySky'
EDITS = [
    ("REMOTE_STOP_STATUS_KEEPALIVE_S = 1.0\n",
     "REMOTE_STOP_STATUS_KEEPALIVE_S = 1.0\n"
     "# ATLAS Stage 29 FlySky: hard ceilings equal to the Xbox teleop non-turbo scales (config/joy_config.yaml).\n"
     "FLYSKY_HARD_MAX_LINEAR = 0.25\n"
     "FLYSKY_HARD_MAX_ANGULAR = 0.80\n"),
    ("        self.manual_only = os.environ.get('ATLAS_MANUAL_ONLY', '0') == '1'\n",
     "        self.manual_only = os.environ.get('ATLAS_MANUAL_ONLY', '0') == '1'\n"
     "        # ATLAS Stage 29 FlySky: exactly one manual controller may drive; XBOX is the boot default.\n"
     "        self.manual_controller = 'XBOX'\n"
     "        self.flysky_drive_enabled = os.environ.get('ATLAS_FLYSKY_DRIVE_ENABLED', '0') == '1'\n"
     "        self.create_service(Trigger, '/atlas/manual_controller/select_xbox',\n"
     "                            lambda request, response: self.select_controller_service('XBOX', response))\n"
     "        self.create_service(Trigger, '/atlas/manual_controller/select_flysky',\n"
     "                            lambda request, response: self.select_controller_service('FLYSKY', response))\n"
     "        self.create_subscription(Empty, '/atlas/flysky/stop', self.on_flysky_stop, 10)\n"),
    ('        self.declare_parameter("foxglove_steering_expo", 2.0)\n',
     '        self.declare_parameter("foxglove_steering_expo", 2.0)\n'
     '        # ATLAS Stage 29 FlySky: independent clamps, never above the hard ceilings.\n'
     '        self.declare_parameter("flysky_max_linear", 0.15)\n'
     '        self.declare_parameter("flysky_max_angular", 0.60)\n'
     '        self.flysky_max_linear = max(0.0, min(FLYSKY_HARD_MAX_LINEAR, float(self.get_parameter("flysky_max_linear").value)))\n'
     '        self.flysky_max_angular = max(0.0, min(FLYSKY_HARD_MAX_ANGULAR, float(self.get_parameter("flysky_max_angular").value)))\n'),
    ('            "REMOTE": Channel("REMOTE", "/cmd_vel_joy", 1, manual_timeout),\n',
     '            "REMOTE": Channel("REMOTE", "/cmd_vel_joy", 1, manual_timeout),\n'
     '            # ATLAS Stage 29 FlySky: same rank as REMOTE; controller_accepts() admits only the selected one.\n'
     '            "FLYSKY": Channel("FLYSKY", "/cmd_vel_flysky", 1, manual_timeout),\n'),
    ("        if self.manual_only and name not in ('REMOTE', 'COMMISSION', 'RECOVERY'):\n",
     "        if not self.controller_accepts(name):   # ATLAS Stage 29 FlySky: only the selected manual controller\n"
     "            return\n"
     "        if self.manual_only and name not in ('REMOTE', 'COMMISSION', 'RECOVERY', 'FLYSKY'):\n",
     'MODIFIES: adds FLYSKY to the manual-only allow-list (the live mux runs ATLAS_MANUAL_ONLY=1)'),
    ('        elif name == "FOXGLOVE":\n',
     '        elif name == "FLYSKY":   # ATLAS Stage 29 FlySky: clamp independently of the teleop node\n'
     '            command.linear.x = max(-self.flysky_max_linear, min(self.flysky_max_linear, command.linear.x))\n'
     '            command.angular.z = max(-self.flysky_max_angular, min(self.flysky_max_angular, command.angular.z))\n'
     '            command.linear.y = 0.0\n'
     '            command.linear.z = 0.0\n'
     '            command.angular.x = 0.0\n'
     '            command.angular.y = 0.0\n'
     '        elif name == "FOXGLOVE":\n'),
    ('    def on_ultrasonic(self, sensor: str, msg: Float32) -> None:\n',
     '    # ---- ATLAS Stage 29 FlySky: manual controller selection (additive)\n'
     '    def controller_accepts(self, name: str) -> bool:\n'
     "        if name == 'REMOTE':\n"
     "            return self.manual_controller == 'XBOX'\n"
     "        if name == 'FLYSKY':\n"
     "            return self.flysky_drive_enabled and self.manual_controller == 'FLYSKY'\n"
     '        return True\n'
     '\n'
     '    def select_controller(self, target: str):\n'
     '        """Handover only while the E-STOP is latched and the rover is stopped: zero motion by construction."""\n'
     "        if target not in ('XBOX', 'FLYSKY'):\n"
     "            return False, 'unknown controller'\n"
     "        if target == 'FLYSKY' and not self.flysky_drive_enabled:\n"
     "            return False, 'FlySky driving is disabled on this rover (ATLAS_FLYSKY_DRIVE_ENABLED)'\n"
     '        if not self.remote_stop.latched:\n'
     "            return False, 'Latch the E-STOP before changing controller'\n"
     '        if self.moving(self.last_sent):\n'
     "            return False, 'Rover must be stopped before changing controller'\n"
     '        previous, self.manual_controller = self.manual_controller, target\n'
     '        self.hold_remote_stop()          # flush every channel and publish zero\n'
     '        self.publish_mode()\n'
     "        self.get_logger().warn('Manual controller %s -> %s' % (previous, target))\n"
     "        return True, 'Manual controller is %s. The E-STOP stays latched until the normal reset.' % target\n"
     '\n'
     '    def select_controller_service(self, target, response):\n'
     '        response.success, response.message = self.select_controller(target)\n'
     '        return response\n'
     '\n'
     '    def on_flysky_stop(self, _msg):\n'
     "        self.remote_stop.latch('REMOTE STOP: FlySky stop')\n"
     '        self.hold_remote_stop()\n'
     '\n'
     '    def on_ultrasonic(self, sensor: str, msg: Float32) -> None:\n'),
    ("            'source': mode,\n",
     "            'source': mode,\n"
     "            'manual_controller': getattr(self, 'manual_controller', 'XBOX'),   # ATLAS Stage 29 FlySky\n"
     "            'flysky_drive_enabled': getattr(self, 'flysky_drive_enabled', False),\n"),
]


def apply(text: str) -> str:
    if MARK in text:
        raise SystemExit('refused: already patched')
    for edit in EDITS:
        old, new = edit[0], edit[1]
        n = text.count(old)
        if n != 1:
            raise SystemExit('refused: anchor found %d times: %r' % (n, old[:70]))
        if old.strip() not in new and not (len(edit) > 2 and edit[2].startswith('MODIFIES:')):
            raise SystemExit('refused: edit is not additive around its anchor')
        text = text.replace(old, new, 1)
    return text


if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    out = apply(open(src, encoding='utf-8').read())
    compile(out, dst, 'exec')
    open(dst, 'w', encoding='utf-8').write(out)
    print('wrote', dst)
