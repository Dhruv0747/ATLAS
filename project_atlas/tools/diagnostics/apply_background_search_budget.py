"""Parked, exact-hash deployment of the suggest-only diagnostic search pacer."""
import argparse
import json
from pathlib import Path
import py_compile
import shutil
import subprocess
import time
import uuid
import urllib.error
from apply_parked_cpu_manual_fix import ROOT, PROTECTED, UNITS, digest, parked, unit_state

OLD = 'fff2ab007e45d2ac44bd001b65d1327c297a19ba362feb5eb3a1f866cec40b2a'
CORE = 'abe5c2a3b66984264596c0fea974d5aa24014c3613689701b1f6d034d5ddcb64'
PACED_MONITOR = 'cddbbc8d44a07b57c62a6ec4160cbbe9c0b02e4fe82d91ab126bafd66f68839b'
PACER20 = '3f8331d781b9776214221b97f9bb78376f161734680f73f24bc0c3d436c7ec16'
UNIT = 'atlas-localization-monitor.service'


def observe_ready(check, *, clock=time.monotonic, pause=time.sleep, seconds=20):
    """Read-only startup observation; never retries installation/restart.

    A timeout or stale telemetry can settle. Unsafe policy/resource values are
    never swallowed, and the original fresh-data thresholds remain unchanged.
    """
    started = clock()
    while True:
        try:
            return check()
        except (TimeoutError, urllib.error.URLError):
            if clock()-started >= seconds: raise
        except ValueError as exc:
            if str(exc) != 'stale stop/command' or clock()-started >= seconds: raise
        pause(.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--monitor-sha', required=True)
    parser.add_argument('--budget-sha', required=True)
    args = parser.parse_args()
    stage = Path(__file__).parent
    target = ROOT / 'scripts/atlas_localization_monitor.py'
    helper = ROOT / 'scripts/atlas_background_search_budget.py'
    result = {'changed': False, 'result': 'PREFLIGHT'}
    backup = None
    try:
        result['before'] = parked(True)
        units = UNITS + ('atlas-cmd-vel-mux.service', UNIT)
        before = unit_state(units)
        result['units_before'] = before
        if before['atlas-stage20-public-capture.service']['ActiveState'] != 'inactive':
            raise ValueError('recorder not OFF')
        if Path('/home/jetson/.config/project_atlas/relocalize_mode').read_text().strip() != 'suggest':
            raise ValueError('requires suggest-only mode')
        original_monitor_hash = digest(target)
        if original_monitor_hash not in (OLD, PACED_MONITOR) or digest(ROOT / 'scripts/atlas_localization_verify_core.py') != CORE:
            raise ValueError('unreviewed monitor/core')
        if helper.exists() and digest(helper) not in (args.budget_sha, PACER20):
            raise ValueError('unreviewed existing helper')
        candidates = [(stage/'monitor.py', target, args.monitor_sha),
                      (stage/'budget.py', helper, args.budget_sha)]
        for source, _, expected in candidates:
            if digest(source) != expected: raise ValueError('candidate hash mismatch')
            py_compile.compile(str(source), doraise=True)
        hashes = {p: digest(ROOT/p) for p in PROTECTED}
        result['protected_before'] = hashes
        backup = ROOT/'data/backups'/('20261015_search_pacer_'+uuid.uuid4().hex[:8])
        backup.mkdir(parents=True, exist_ok=False)
        shutil.copy2(target, backup/'monitor.original')
        if helper.exists(): shutil.copy2(helper, backup/'helper.original')
        result['backup'] = str(backup)
        result['helper_preexisted'] = helper.exists()
        result['rollback'] = 'restore monitor.original and helper.original if present; restart only '+UNIT
        (backup/'transaction.json').write_text(json.dumps(result, indent=2))
        result['changed'] = True
        # Install helper first; old monitor does not import it.
        for source, destination, _ in reversed(candidates):
            temporary = destination.with_name(destination.name+'.'+uuid.uuid4().hex)
            shutil.copy2(source, temporary)
            if destination.exists(): shutil.copymode(destination, temporary)
            temporary.replace(destination)
        subprocess.run(['systemctl','--user','restart',UNIT],check=True,timeout=15)
        time.sleep(5)
        result['after'] = observe_ready(lambda: parked(True))
        result['units_after'] = unit_state(units)
        for unit in units:
            if unit != UNIT and before[unit] != result['units_after'][unit]:
                raise ValueError('protected production service changed: '+unit)
        result['protected_after'] = {p: digest(ROOT/p) for p in PROTECTED}
        if result['protected_after'] != hashes: raise ValueError('protected source changed')
        for _, destination, expected in candidates:
            if digest(destination) != expected: raise ValueError('installed hash mismatch')
        if result['units_after'][UNIT]['ActiveState'] != 'active': raise ValueError('monitor failed')
        result['installed_hashes'] = {str(dst): digest(dst) for _,dst,_ in candidates}
        result['result'] = 'VERIFIED'
    except Exception as exc:
        result['result'] = 'FAILED'
        result['error'] = type(exc).__name__+': '+str(exc)
        if result['changed'] and backup:
            shutil.copy2(backup/'monitor.original', target)
            if (backup/'helper.original').exists(): shutil.copy2(backup/'helper.original', helper)
            subprocess.run(['systemctl','--user','restart',UNIT],check=True,timeout=15)
            result['rolled_back'] = digest(target) == original_monitor_hash
    finally:
        if backup: (backup/'transaction.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2),flush=True)
    return 0 if result['result'] == 'VERIFIED' else 2


if __name__ == '__main__': raise SystemExit(main())
