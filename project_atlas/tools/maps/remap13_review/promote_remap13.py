"""Promote the reviewed remap-13 candidate (owner approved 2026-11-14 'Yes, accept'). --dry-run prints only."""
import glob, json, sys, time
sys.path.insert(0, '/home/jetson/project_atlas/scripts')
from pathlib import Path
import atlas_map_acceptance_core as A
DRY = '--dry-run' in sys.argv
C = Path('/home/jetson/.config/project_atlas'); M = Path('/home/jetson/project_atlas/maps')
pref = glob.glob(str(M / '.atlas_candidate_21ed0671*.yaml'))[0][:-5]
Y, I = Path(pref + '.yaml'), Path(pref + '.pgm')
session = json.load(open(C / 'rejected_session_21ed0671/mapping_session.json')); sid = session['id']
review = json.load(open('/tmp/review_remap13_eval.json'))
assert review['failures_session_time'] == [], review['failures_session_time']
assert all('map->odom' in f and 'stale' in f for f in review['failures_review_time']), review['failures_review_time']
cid = A.map_pair_id(Y, I); assert cid == review['evidence']['candidate_map_id'], 'candidate bytes changed since review'
old_id = A.map_pair_id(M / 'atlas_latest.yaml', M / 'atlas_latest.pgm')
home = json.load(open(C / 'home_pose.rejected-session-21ed0671.json'))
seed = json.load(open(C / 'localization_seed_pose.rejected-session-21ed0671.json'))
accepted_places = json.load(open(C / 'named_places.json'))
session_places = {'dhruv room': dict(review['places_dhruv_room'], mapping_session_id=sid,
                                     note='selected on the candidate map (>=0.45 m clear), owner confirmed from picture 2026-11-14'),
                  'hall': accepted_places['hall']}
assert session_places['hall'].get('mapping_session_id') == sid
merged = A.merge_session_places(accepted_places, session_places, sid)
ph, pse, pp = A.prepare_map_bound_metadata_values(home=home, seed=seed, places=merged, session_id=sid, new_map_id=cid, old_map_id=old_id)
print('old map', old_id, '-> new map', cid)
print('home', {k: ph[k] for k in ('x', 'y', 'map_id')}); print('seed', {k: pse[k] for k in ('x', 'y', 'map_id')})
for k, v in pp.items():
    if isinstance(v, dict): print('place', k, round(v['x'], 2), round(v['y'], 2), v.get('map_id'))
if DRY:
    print('DRY RUN - nothing written'); sys.exit(0)
updates = {C / 'home_pose.json': json.dumps(ph, indent=2).encode(), C / 'localization_seed_pose.json': json.dumps(pse, indent=2).encode(),
           C / 'named_places.json': json.dumps(pp, indent=2).encode()}
tag = time.strftime('%Y%m%d-%H%M%S') + '-' + sid[:8] + '-review'
new = A.transactionally_promote_map_pair(candidate_yaml=Y, candidate_image=I, accepted_yaml=M / 'atlas_latest.yaml',
        accepted_image=M / 'atlas_latest.pgm', backup_dir=M / 'accepted_backups', expected_map_id=cid, backup_tag=tag,
        metadata_updates=updates)
report = dict(review, decision='accepted_after_owner_review', promoted_unix=time.time(), promoted_map_id=new, old_map_id=old_id, backup_tag=tag,
              deviation='session evidence evaluated at 17:37:42; connectivity/plans/footprint evaluated parked at 18:08:21; '
                        'each set passes at its own time; single-moment freshness cannot hold offline. final_map_consistency recomputed '
                        'from the recording (latest-TF method). dhruv room place selected on the map, owner confirmed.')
(M / 'accepted_backups' / f'remap13_review_{tag}.json').write_text(json.dumps(report, indent=1, default=str))
print('PROMOTED', new, 'backup tag', tag)
