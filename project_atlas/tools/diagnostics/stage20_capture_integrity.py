"""Read-only incomplete/crashed-capture detection. Never repair/delete a bag."""
import hashlib
import json
from pathlib import Path

def inspect(directory):
    root=Path(directory)
    evidence=root/'stage20_evidence.json';closed=root/'atlas_capture_manifest.json'
    if not evidence.is_file() or not closed.is_file():
        return {'complete':False,'reason':'interrupted_or_not_finalized','delete_permitted':False}
    try:
        e=json.loads(evidence.read_text());c=json.loads(closed.read_text())
        for name,expected in e['files'].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():raise ValueError('unsafe/missing file')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('checksum mismatch')
        if e.get('drops') or e['writer'].get('error') or c['reason']=='worker_error':
            return {'complete':False,'reason':'recording_loss_or_writer_failure','delete_permitted':False}
        if e.get('capture_profile')=='stationary_30_v1' and not e.get('public_topic_window_complete'):
            return {'complete':False,'reason':'incomplete_stationary_window',
                    'finalization_integrity_verified':True,'replay_fidelity_verified':False,'delete_permitted':False}
        return {'complete':True,'reason':'finalization_integrity_only',
                'replay_fidelity_verified':False,'delete_permitted':False}
    except (OSError,ValueError,KeyError,TypeError):
        return {'complete':False,'reason':'corrupt_or_incomplete_manifest','delete_permitted':False}
