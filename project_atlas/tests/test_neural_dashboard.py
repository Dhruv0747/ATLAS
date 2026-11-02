import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'monitoring/atlas/grafana'))
from build_neural_dashboard import build
from neural_queries import TOPOLOGY,edge_query,labels

def test_graph_and_links():
 d=build();g=next(p for p in d['panels'] if p['type']=='nodeGraph')
 assert {q['refId'] for q in g['targets']}=={'nodes','edges'}
 assert d['refresh']=='30s'
 assert all('/d/' in x['url'] for x in g['fieldConfig']['overrides'][0]['properties'][0]['value'])
 assert len({p['id'] for p in d['panels']})==len(d['panels'])
def test_topology_integrity_and_scope():
 ids={n['id'] for n in TOPOLOGY['nodes']}
 for e in TOPOLOGY['edges']:
  assert e['source'] in ids and e['target'] in ids
  if e['verified']:assert e['target']=='cache' and e['topic'] and e['limit']>0
  else:assert 'UNVERIFIED' in edge_query(e)
def test_no_fake_rates_or_automatic_commands():
 for e in TOPOLOGY['edges']:
  q=edge_query(e);assert 'vector(0/0)' in q;assert 'or vector(0)' not in q
  if e['verified']:assert 'time() -' in q and 'up{' in q
 assert all(p['type'] in ('text','timeseries','nodeGraph') for p in build()['panels'])
def test_generated_matches():
 assert json.loads((ROOT/'monitoring/atlas/grafana/dashboards/atlas-neural.json').read_text())==build()
