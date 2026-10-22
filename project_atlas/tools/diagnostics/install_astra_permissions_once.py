#!/usr/bin/env python3
"""Reviewed owner-run permission installation only. Never starts cameras/services.

Installs the existing two-interface rule, a dedicated group and temporary ACLs
for already-running processes. No blanket trigger, hotplug, reboot or profiling.
End-to-end reboot and numbered-node guardian validation remain separate gates.
"""
import grp
import hashlib
import importlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import time
import urllib.request

STAGE = Path(__file__).resolve().parent
TARGET = Path('/etc/udev/rules.d/99-atlas-astra-access.rules')
RULE = '99-atlas-astra-access.rules.candidate'
RULE_SHA = '54a8bc029e21364d1d259f11ebf3cefcf10ad263c45ae98aabda880393c2e7c4'
HELPER_SHA = '7129baf4708d259ff08f482477a72a67f7d5b7da0b20f61907edd114d7fd5d95'


def run(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=12)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_bundle():
    for name, expected in [(RULE, RULE_SHA), ('astra_access_cpu_once.py', HELPER_SHA)]:
        if digest(STAGE/name) != expected:
            raise RuntimeError('Package hash mismatch: '+name)
    sys.path.insert(0, str(STAGE))
    return importlib.import_module('astra_access_cpu_once')


def group_state():
    try:
        value = grp.getgrnam('atlas-astra')
    except KeyError:
        return None
    primary = [p.pw_name for p in pwd.getpwall() if p.pw_gid == value.gr_gid]
    if set(primary + value.gr_mem) - {'jetson'}:
        raise RuntimeError('Existing atlas-astra group grants access to other users')
    return {'gid': value.gr_gid, 'members': value.gr_mem, 'primary': primary}


def check_only():
    if os.geteuid() != pwd.getpwnam('jetson').pw_uid:
        raise RuntimeError('Checks must run with actual jetson credentials')
    helper = validate_bundle()
    for rel, expected in helper.HASHES.items():
        helper.verified_hash(helper.LIVE/rel, expected)
    sys.path.insert(0, str(helper.LIVE/'tools/vision3d'))
    G = importlib.import_module('stationary_gate')
    P = importlib.import_module('stationary_ros_probe')
    rows = []
    for _ in range(3):
        a = G.ticks();time.sleep(1)
        cpu = G.cpu_delta(a, G.ticks())
        G.require_cpu(cpu)
        data = P.safety_snapshot()
        row = G.check(cpu, data)
        helper.require_sensors(data['ros'])
        status = json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/vision3d/summary', timeout=2))
        helper.require_camera_off(status, subprocess.run(['pgrep','-x','astra_camera_no'],
                                  stdout=subprocess.DEVNULL, timeout=2).returncode)
        rows.append(row)
    services = G.services()
    for name in ('rover-status-web.service','atlas-voice-companion.service'):
        raw = run(['systemctl','--user','show',name,'-p','MainPID','-p','NRestarts','-p','ActiveState'])
        services[name] = dict(line.split('=',1) for line in raw.strip().splitlines())
    if any(v['ActiveState'] != 'active' or v['MainPID'] == '0' for v in services.values()):
        raise RuntimeError('Protected service not active')
    identities = helper.usb_identity()
    access = {node: os.access(node, os.R_OK|os.W_OK) for node in identities}
    print(json.dumps({'samples': rows, 'services': services, 'identities': identities, 'access': access}))


def user_check():
    user = pwd.getpwnam('jetson')
    return json.loads(run(['/usr/sbin/runuser','-u','jetson','--','/usr/bin/env',
        'HOME='+user.pw_dir, 'XDG_RUNTIME_DIR=/run/user/'+str(user.pw_uid),
        'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/'+str(user.pw_uid)+'/bus',
        '/usr/bin/python3','-I',str(Path(__file__).resolve()),'--check-only']))


def install_transaction(ops):
    """Pure sequencing seam for fault-injection tests; backend owns rollback."""
    try:
        ops.preflight()
        ops.install_group()
        ops.install_rule()
        ops.restore_current_access()
        ops.postflight()
    except BaseException:
        ops.rollback()
        raise


class Installer:
    def __init__(self):
        self.backup = None
        self.before = None
        self.group_added = self.member_added = self.rule_added = self.acl_touched = False
        self.report = {'status':'NOT_STARTED','camera_started':False,'services_restarted':False}

    def preflight(self):
        self.helper = validate_bundle()
        if run(['/usr/bin/udevadm','--version']).strip() != '249':
            raise RuntimeError('udev version differs from isolated validation')
        if TARGET.exists() or TARGET.is_symlink():
            raise RuntimeError('Rule already exists; inspect instead of overwriting/retrying')
        self.original_group = group_state()
        self.before = user_check()  # No mutation before all guards pass.
        self.backup = Path(tempfile.mkdtemp(prefix='atlas-astra-usb-',dir='/var/backups'))
        os.chmod(self.backup,0o700)
        (self.backup/'before.json').write_text(json.dumps(self.before,indent=2))
        (self.backup/'group-before.json').write_text(json.dumps(self.original_group))
        self.nodes = sorted(self.before['identities'])
        (self.backup/'before.acl').write_text(run(['/usr/bin/getfacl','-p',*self.nodes]))
        self.report.update(backup=str(self.backup),preflight=self.before,original_rule='absent')

    def install_group(self):
        if self.original_group is None:
            run(['/usr/sbin/groupadd','--system','atlas-astra']);self.group_added=True
        current = group_state()
        if 'jetson' not in current['members'] and 'jetson' not in current['primary']:
            run(['/usr/sbin/usermod','-a','-G','atlas-astra','jetson']);self.member_added=True

    def install_rule(self):
        # Complete file before exposing it to udev; refuse replacing any target.
        content = (STAGE/RULE).read_bytes()
        if hashlib.sha256(content).hexdigest() != RULE_SHA:
            raise RuntimeError('Rule changed after preflight')
        fd, temp = tempfile.mkstemp(prefix='.atlas-astra-',dir=TARGET.parent)
        try:
            with os.fdopen(fd,'wb') as out:
                out.write(content);out.flush();os.fsync(out.fileno())
            os.chmod(temp,0o644)
            os.link(temp,TARGET);self.rule_added=True
        finally:
            Path(temp).unlink()
        run(['/usr/bin/udevadm','control','--reload-rules'])  # NEVER trigger.

    def restore_current_access(self):
        if self.helper.usb_identity() != self.before['identities']:
            raise RuntimeError('Astra changed before ACL grant')
        self.acl_touched=True
        run(['/usr/bin/setfacl','-m','u:jetson:rw',*self.nodes])

    def postflight(self):
        after = user_check()
        self.report['postflight']=after
        if after['identities'] != self.before['identities'] or not all(after['access'].values()):
            raise RuntimeError('USB identity/access verification failed')
        if after['services'] != self.before['services']:
            raise RuntimeError('Protected service identities changed')
        if digest(TARGET) != RULE_SHA:
            raise RuntimeError('Installed rule hash mismatch')
        group = group_state()
        if 'jetson' not in group['members'] and 'jetson' not in group['primary']:
            raise RuntimeError('Group membership missing')
        self.report.update(status='INSTALLED_NOT_REBOOT_VALIDATED',rule_sha256=RULE_SHA,
                           group=group,session_renewal_required=True,
                           numbered_guardian_renumbering_validation='still pending')

    def rollback(self):
        errors=[]
        def attempt(action):
            try:action()
            except Exception as exc:errors.append(repr(exc))
        if self.rule_added:
            def rule_undo():
                if digest(TARGET) != RULE_SHA:raise RuntimeError('Refuse removing changed rule')
                TARGET.unlink()  # Only this newly installed, hash-verified file.
                run(['/usr/bin/udevadm','control','--reload-rules'])
            attempt(rule_undo)
        if self.acl_touched:
            def acl_undo():
                if self.helper.usb_identity() != self.before['identities']:
                    raise RuntimeError('Refuse restoring ACL on changed device')
                run(['/usr/bin/setfacl','--restore='+str(self.backup/'before.acl')])
            attempt(acl_undo)
        if self.member_added:
            attempt(lambda:run(['/usr/bin/gpasswd','-d','jetson','atlas-astra']))
        if self.group_added:
            def group_undo():
                group=group_state()
                if group and (group['members'] or group['primary']):
                    raise RuntimeError('Refuse deleting used group')
                run(['/usr/sbin/groupdel','atlas-astra'])
            attempt(group_undo)
        self.report['rollback_errors']=errors


def main():
    if sys.argv[1:] == ['--check-only']:
        check_only();return 0
    if sys.argv[1:] or os.geteuid()!=0 or os.environ.get('SUDO_USER')!='jetson':
        raise RuntimeError('Use the reviewed sudo command from the jetson account')
    os.umask(0o077)
    ops=Installer()
    try:
        install_transaction(ops)
    except BaseException as exc:
        ops.report.update(status='ABORTED',error=repr(exc))
    if ops.backup:
        (ops.backup/'result.json').write_text(json.dumps(ops.report,indent=2))
    print(json.dumps(ops.report,indent=2),flush=True)
    return 0 if ops.report['status']=='INSTALLED_NOT_REBOOT_VALIDATED' else 1


if __name__=='__main__':sys.exit(main())
