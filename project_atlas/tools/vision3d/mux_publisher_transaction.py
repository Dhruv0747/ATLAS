"""Offline Mux transaction binding. The installed system has no maintenance authority.

Fixed paths and user-service scope. No caller-supplied approval token or safety
override. Linux worker and cleanup are serialized in a private single-use journal.
"""
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from existing_safety_snapshot import SourceConsumer
from mux_publisher_files import MuxFiles, read
from mux_restart_policy import MuxPolicy, UNIT, FRAGMENT
from restart_policy import save
from restart_safety_observer import Safety
from snapshot_benchmark_once import resources, THERMAL
from stationary_gate import ticks, cpu_delta

HOME_DIR = Path('/home/jetson')
MIGRATION = HOME_DIR / 'project-atlas-migration'
STAGE = MIGRATION / 'inactive-publishers-f95c9d2-20261102' / 'mux'
ROOT = MIGRATION / 'mux-transaction-f95c9d2'
SNAPSHOT = Path('/run/user/1000/atlas-restart-safety/state.json')
UNIT_ROOT = Path('/run/user/1000/systemd/user')
SCRIPTS = HOME_DIR / 'project_atlas/scripts'
DROPINS = {
    '40-manual-commissioning.conf': '792fc4065199ab713c19e9e72a91114ffdf58b50447a5c70b8b423fced4d846c',
    'priority.conf': '91ba36a24dde057faa9a07831c688a71ab59239b8242d94d9057bdf61adc3bd8',
}
HARDWARE_ENV_SHA = '2d4b2795654f661a3f71e6d6f712a56b55e2b1fd302f38cd93b4cd6f52cf6664'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(read(path)).hexdigest()


class ServiceBinding:
    def __init__(self, policy):
        self.policy = policy

    def dependencies(self):
        p = self.policy
        expected = {Path(FRAGMENT + '.d') / name: sha for name, sha in DROPINS.items()}
        if p.path.exists():
            expected[p.path] = hashlib.sha256(b'[Service]\nRestart=no\n').hexdigest()
        require(set(p.prop('DropInPaths').split()) == {str(path) for path in expected},
                'effective Mux drop-in set changed')
        for path, sha in expected.items():
            require(digest(path) == sha, 'Mux drop-in drift')
        for key, values in [('Requires', {'basic.target', 'app.slice'}), ('Wants', set()),
                            ('After', {'basic.target', 'app.slice', 'network.target'})]:
            require(set(p.prop(key).split()) == values, 'Mux unit dependency drift: ' + key)
        require(digest(HOME_DIR / '.config/project-atlas/hardware.env') == HARDWARE_ENV_SHA,
                'Mux environment file drift')

    def check(self, binding, replacement=None):
        p = self.policy
        p.checkpoint()
        require(binding['boot_id'] == p.boot(), 'reviewed boot identity changed')
        self.dependencies()
        keys = ['Id','MainPID','ActiveState','NRestarts','FragmentPath','Restart']
        args = ['/usr/bin/systemctl','--user','show',*binding['services']]
        for key in keys:
            args.extend(['-p',key])
        rows = subprocess.check_output(args, text=True, timeout=min(2,p.deadline-p.now()))
        observed = {}
        for block in rows.strip().split('\n\n'):
            row = dict(line.split('=',1) for line in block.splitlines())
            require(row['Id'] not in observed, 'duplicate service identity')
            observed[row['Id']] = row
        require(set(observed) == set(binding['services']), 'protected service evidence missing')
        for unit, reviewed in binding['services'].items():
            row = observed[unit]
            pid = int(row['MainPID'])
            identity = [int(reviewed['MainPID']),reviewed['start_ticks']]
            if unit == UNIT and replacement is not None:
                identity = replacement
            require(row['ActiveState'] == reviewed['ActiveState'] == 'active'
                    and row['NRestarts'] == reviewed['NRestarts']
                    and row['FragmentPath'] == reviewed['FragmentPath']
                    and digest(Path(row['FragmentPath'])) == reviewed['unit_sha256'],
                    'protected service drift: ' + unit)
            expected_restart = 'no' if unit == UNIT and p.path.exists() else reviewed['Restart']
            require(row['Restart'] == expected_restart, 'restart-policy drift: ' + unit)
            stat = Path('/proc',str(pid),'stat').read_text()
            require([pid,int(stat[stat.rfind(')')+2:].split()[19])] == identity,
                    'process identity drift: ' + unit)
        p.checkpoint()

    def before(self, binding):
        self.check(binding)

    def after(self, binding, identity):
        self.check(binding, identity)


def check_envelope(consumer, data, now, previous):
    observations = data['observations']
    output = data['published_mono']
    require(data['boot_id'] == consumer.boot_id and SourceConsumer.finite(output)
            and 0 <= now-output <= .75, 'observer boot/freshness failure')
    state = Safety()
    for key in ('policy','command','encoders'):
        value, receipt = observations[key]
        require(SourceConsumer.finite(receipt) and receipt <= output,'invalid callback time')
        state.receive(key,value,receipt)
    require(state.evaluate(now)['safe'], 'unsafe replacement evidence')
    payload, policy_receipt = observations['policy']
    command, command_receipt = observations['command']
    source = payload['source_provenance']['observed_mono']
    mirror = payload['published_command']
    published = mirror['published_mono']
    # Snapshot callbacks can follow the source by several milliseconds. Verify
    # source clocks independently even when the observer republishes identical data.
    require(SourceConsumer.finite(source) and SourceConsumer.finite(published)
            and 0 <= now-published <= 1 and published <= source <= policy_receipt
            and published <= command_receipt and command == mirror['values'],
            'command/source stale or inconsistent')
    encoder, enc_receipt = observations['encoders']
    if 'encoder_packet_monotonic' in encoder:
        packet = encoder['encoder_packet_monotonic']
        require(SourceConsumer.finite(packet) and packet <= enc_receipt
                and 0 <= now-packet <= 1, 'encoder source expired')
    if payload != previous:
        consumer.receive('policy',payload,now)
    return payload


def verify_replacement(policy, identity):
    boot = policy.boot()
    consumer = SourceConsumer(boot, {'policy':(boot,*identity)})
    end = policy.now()+20
    previous = None
    advances = 0
    while policy.now() < end:
        policy.checkpoint()
        data = json.loads(read(SNAPSHOT))
        payload = check_envelope(consumer,data,time.monotonic(),previous)
        if previous != payload:
            advances += 1
        previous = payload
        policy.checkpoint()
        time.sleep(.05)
    require(advances >= 2, 'no advancing replacement evidence')

def worker_body(policy, files, identity, acceptance):
    check = policy.checkpoint
    files.verify_original(check)
    identity.before(files.binding)
    policy.prepare()
    files.install(check)
    new = policy.restart('activation')
    files.verify_installed(check)
    identity.after(files.binding,new)
    acceptance(policy,new)
    policy.accept_new_process(str(new[0]))
    policy.restore_healthy()
    identity.after(files.binding,new)
    files.verify_installed(check)
    check()
    return new


def cleanup_body(policy, files):
    policy.quiesce_for_rollback()
    files.rollback(policy.checkpoint)
    policy.cleanup()


class ResourceSamples:
    """Independent parent-side sampling, including the worker's startup interval."""
    def __init__(self):
        self.stamp = MuxPolicy.now()
        self.counters = ticks()
        self.count = 0

    def check(self):
        now = MuxPolicy.now()
        interval = now-self.stamp
        if interval < 1:
            return
        require(interval <= 1.1, 'missing or delayed CPU interval')
        current = ticks()
        cpu = cpu_delta(self.counters,current)
        ram, temperatures = resources()
        require(set(temperatures)==THERMAL and all(math.isfinite(v) and v>0 for v in temperatures.values()),
                'required temperature missing/invalid')
        MuxPolicy.resources(cpu,ram,max(temperatures.values()))
        self.stamp, self.counters = now, current
        self.count += 1


@contextlib.contextmanager
def absolute_alarm(end):
    """Last-resort kernel timer for blocking reads, fsync or a blocked supervisor."""
    require(signal.getitimer(signal.ITIMER_REAL)==(0,0), 'outer timer already owned')
    remaining = end-MuxPolicy.now()
    if remaining<=0:
        raise TimeoutError('transaction deadline exhausted')
    old = signal.signal(signal.SIGALRM,signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL,remaining)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,old)


def guarded_child(operation, check, end):
    """Parent keeps checking safety while a worker blocks. systemd owns its cgroup."""
    pid = os.fork()
    if pid == 0:
        try:
            # A forked worker does not inherit the parent's interval timer.
            with absolute_alarm(end):
                operation()
        except BaseException as exc:
            print('Mux transaction failed:',repr(exc),file=sys.stderr,flush=True)
            os._exit(1)
        os._exit(0)
    try:
        while True:
            check()
            if MuxPolicy.now()>=end:
                raise TimeoutError('Mux phase deadline')
            waited,status = os.waitpid(pid,os.WNOHANG)
            if waited:
                pid = None
                require(os.waitstatus_to_exitcode(status)==0,'Mux worker failed')
                return
            time.sleep(.02)
    finally:
        if pid is not None:
            try:
                os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            # No subsequent mutation in this process. systemd KillMode=control-group
            # quiesces remaining children before its independent ExecStopPost.


def _run_phase(cleaning, start, entered):
    p = MuxPolicy(ROOT,UNIT_ROOT)
    files = MuxFiles(STAGE,ROOT,SCRIPTS)
    if cleaning and not ROOT.exists():
        return
    # Preconditions are hard requirements of the service manager wrapper.
    require(os.getuid()==1000 and os.environ.get('INVOCATION_ID'), 'user systemd invocation required')
    require('/atlas-mux-provenance-once.service' in Path('/proc/self/cgroup').read_text().splitlines()[0]
            and Path('/proc/self/cgroup').read_text().strip().endswith('/atlas-mux-provenance-once.service'),
            'wrong transaction unit')
    if not cleaning:
        p.independent_check()  # unavailable today: reject even before journal creation
        ROOT.mkdir(mode=0o700)
    require(not ROOT.is_symlink() and ROOT.resolve()==ROOT and ROOT.stat().st_uid==os.getuid()
            and ROOT.stat().st_mode & 0o077==0,'untrusted transaction directory')
    with (ROOT/'lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if cleaning:
            if not p.budget_file.exists():
                require(not p.state.exists() and not files.intent.exists(),'missing budget with owned mutations')
                return
            require(p.limits() == (start+p.WORKER_SECONDS,start+p.WORKER_SECONDS+p.CLEANUP_SECONDS),
                    'transaction origin mismatch')
            p.resume_budget(cleanup=True, cleanup_started=entered)
            if (ROOT/'accepted.json').exists():
                # A final durable decision is written only after acceptance and policy restoration.
                require(p.load()['restored'] and json.loads(read(ROOT/'accepted.json'))['unit']==UNIT,
                        'corrupt acceptance state')
                return
            signal.setitimer(signal.ITIMER_REAL, remaining(p.deadline))
            cleanup_body(p,files)
            return
        p.begin_budget(start)
        end = p.deadline
        def apply():
            new = worker_body(p,files,ServiceBinding(p),verify_replacement)
            # Worker makes no final decision. Parent checks safety at commit.
            save(ROOT/'validated.json',{'unit':UNIT,'identity':new})
        monitor = ResourceSamples()
        def safety():
            p.checkpoint()
            monitor.check()
        while monitor.count<3:
            safety()
            time.sleep(.02)
        guarded_child(apply,safety,end)
        safety()
        proof = json.loads(read(ROOT/'validated.json'))
        require(p.load()['restored'] and proof['unit']==UNIT,'incomplete Mux result')
        require(p._pid_identity(p.prop('MainPID'))==proof['identity'],'Mux exited before acceptance')
        safety()
        save(ROOT/'accepted.json',proof)



def remaining(end):
    left=end-MuxPolicy.now()
    if left<=0:
        raise TimeoutError('Mux transaction deadline expired')
    return left


def run_phase(cleaning):
    # Both systemd processes inherit the *same* launch-time CLOCK_BOOTTIME stamp.
    # Arm the kernel timer before filesystem access, including opening rollback state.
    start=float(os.environ['ATLAS_MUX_ORIGIN_BOOTTIME'])
    require(math.isfinite(start) and 0<=start<=MuxPolicy.now(),'invalid launch origin')
    end=start+MuxPolicy.WORKER_SECONDS+(MuxPolicy.CLEANUP_SECONDS if cleaning else 0)
    entered=MuxPolicy.now()
    if cleaning:
        end=min(end,entered+MuxPolicy.CLEANUP_SECONDS)
    with absolute_alarm(end):
        _run_phase(cleaning,start,entered)


def transient_command():
    """Build the one-unit specification for review. This function never launches it."""
    script=str(Path(__file__).resolve())
    require(not any(c.isspace() or c in '%$' for c in script),'unsupported controller path')
    return [
        '/usr/bin/systemd-run','--user','--unit=atlas-mux-provenance-once','--wait','--collect',
        '--setenv=ATLAS_MUX_ORIGIN_BOOTTIME='+repr(MuxPolicy.now()),
        '--property=Type=exec','--property=Restart=no','--property=KillMode=control-group',
        '--property=RuntimeMaxSec=60','--property=TimeoutStopSec=30','--property=UMask=0077',
        '--property=NoNewPrivileges=yes','--property=LimitCORE=0',
        '--property=ExecStopPost=/usr/bin/python3 -E -s -B '+script+' cleanup',
        '/usr/bin/python3','-E','-s','-B',script,'worker',
    ]

if __name__=='__main__':
    if sys.argv[1:] not in (['worker'],['cleanup']):
        raise SystemExit('expected worker or cleanup')
    run_phase(sys.argv[1]=='cleanup')
