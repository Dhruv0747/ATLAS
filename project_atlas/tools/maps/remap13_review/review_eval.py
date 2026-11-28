"""Evaluate every map-acceptance gate for the remap-13 candidate with the official core (no writes)."""
import glob, json, math, sys, time
sys.path.insert(0, '/home/jetson/project_atlas/scripts')
from pathlib import Path
import atlas_map_acceptance_core as A
C = Path('/home/jetson/.config/project_atlas')
pref = glob.glob('/home/jetson/project_atlas/maps/.atlas_candidate_21ed0671*.yaml')[0][:-5]
Y, I = Path(pref + '.yaml'), Path(pref + '.pgm')
stored = json.load(open(pref + '.acceptance.json'))
session = json.load(open(C / 'rejected_session_21ed0671/mapping_session.json'))
review = json.load(open('/tmp/review_remap13.json'))
fmc = json.load(open('/tmp/fmc_remap13.json'))
places = json.load(open(C / 'named_places.json'))
dr = dict(places['dhruv room'], x=0.08, y=0.54, selected_offline=True); hall = places['hall']
cid = A.map_pair_id(Y, I)
print('candidate id', cid, '| stored evidence id', stored['candidate_map_id'], '| same bytes:', cid == stored['candidate_map_id'])
conn = {'session_id': session['id'], 'candidate_map_id': cid, 'connected': False, 'unknown_is_blocked': True, 'inflation_radius_m': 0.18}
conn.update(A.exact_candidate_connectivity(Y, I, dr, hall, inflation_radius_m=0.18))
print('exact connectivity', {k: conn[k] for k in ('connected', 'reachable_cells') if k in conn})
fp = dict(review['footprint']); fp['connected'] = bool(review['forward']['passed'] and review['reverse']['passed'])
ev = {'schema_version': A.EVIDENCE_SCHEMA_VERSION, 'session_id': session['id'], 'candidate_map_id': cid,
      'tf_jump': stored['tf_jump'], 'round_trip_closure': stored['round_trip_closure'],
      'exact_candidate_connectivity': conn, 'full_footprint_connectivity': fp,
      'bidirectional_plans': {'forward': review['forward'], 'reverse': review['reverse']},
      'motion_dispatched': False, 'session_mode': session.get('mode'), 'startup_stillness': session.get('startup_stillness'),
      'final_map_consistency': fmc}
pol = A.MapAcceptancePolicy(final_map_replaces_tf_jump=True)
kw = dict(expected_session_id=session['id'], expected_candidate_map_id=cid,
          session_started_unix=float(session.get('ready_unix', session['started_unix'])), policy=pol,
          source_floor_unix=float(session['started_unix']))
session_t = stored['evaluated_unix']; review_t = review['footprint']['observed_unix'] + 1.0
a = A.evaluate_acceptance_evidence(ev, evaluated_unix=session_t, **kw)
b = A.evaluate_acceptance_evidence(ev, evaluated_unix=review_t, **kw)
print('\nA) evaluated at the session evaluation time', time.strftime('%H:%M:%S', time.localtime(session_t)), '->', a or 'NO FAILURES')
print('B) evaluated at the parked review time     ', time.strftime('%H:%M:%S', time.localtime(review_t)), '->', b or 'NO FAILURES')
print('guard trips:', session.get('guard_trips') or 'none')
json.dump({'evidence': ev, 'failures_session_time': a, 'failures_review_time': b, 'places_dhruv_room': dr}, open('/tmp/review_remap13_eval.json', 'w'), indent=1, default=str)
