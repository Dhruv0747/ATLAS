"""Monitoring stack config (monitoring/atlas): alerts and dashboard only use metrics the exporter really emits; the
dashboard marks missing data UNAVAILABLE; Prometheus keeps 15 s / 7 d / 1 GB and LAN/loopback-only ports.
(promtool is run on the VM: see monitoring/atlas/README.md.)"""
import json
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MON = ROOT.parent / 'monitoring/atlas'
sys.path.insert(0, str(ROOT / 'tests'))
import test_atlas_health_exporter as T   # noqa: E402
import atlas_health_exporter as E        # noqa: E402

PROMQL_FUNCS = {'time', 'increase', 'avg_over_time', 'max', 'clamp_min', 'by', 'or', 'and', 'up'}


def exporter_metric_names():
    E.STATE['cpu'] = None
    r = T.sysroot()
    (r.path / 'proc/stat').write_text(r.cpu[0] + '\n'); E.collect(sysroot=str(r.path), get=T.api(), run=T.run_ok)
    (r.path / 'proc/stat').write_text(r.cpu[1] + '\n')
    text = E.collect(sysroot=str(r.path), get=T.api(), run=T.run_ok)
    return {l.split('{')[0].split(' ')[0] for l in text.splitlines()} | {'up'}


def metrics_in(expr):
    expr = re.sub(r'\{[^}]*\}', '', expr)
    expr = re.sub(r'\[[^\]]*\]', '', expr)
    expr = re.sub(r'\$\w+', '', expr)
    return {t for t in re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', expr) if t.startswith('atlas_') or t == 'up'}


class Config(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = exporter_metric_names()
        cls.alerts = yaml.safe_load((MON / 'alerts.yml').read_text())
        cls.dash = json.loads((MON / 'grafana/dashboards/atlas-health.json').read_text())

    def test_every_alert_uses_real_metrics_and_has_for_and_summary(self):
        rules = [r for g in self.alerts['groups'] for r in g['rules']]
        self.assertGreaterEqual(len(rules), 12)
        names = [r['alert'] for r in rules]
        self.assertEqual(len(names), len(set(names)))
        for r in rules:
            self.assertTrue(metrics_in(r['expr']) <= self.names, (r['alert'], metrics_in(r['expr']) - self.names))
            self.assertIn('for', r); self.assertIn('summary', r['annotations']); self.assertIn(r['labels']['severity'], ('warning', 'critical'))
            self.assertEqual(r['expr'].count('('), r['expr'].count(')'), r['alert'])

    def test_alert_thresholds_match_atlas_limits(self):
        exprs = {r['alert']: r['expr'] for g in self.alerts['groups'] for r in g['rules']}
        self.assertIn('>= 70', exprs['AtlasTemperatureHigh']); self.assertIn('> 75', exprs['AtlasCpuSustainedHigh'])

    def test_dashboard_title_panels_metrics_and_unavailable(self):
        self.assertEqual(self.dash['title'], 'ATLAS HEALTH MONITOR')
        self.assertEqual(self.dash['graphTooltip'], 1)                         # shared crosshair: aligned timestamps
        panels = [p for p in self.dash['panels'] if p['type'] != 'row']
        self.assertGreaterEqual(len(panels), 20)
        for p in panels:
            self.assertEqual(p['fieldConfig']['defaults']['noValue'], 'UNAVAILABLE', p['title'])
            self.assertEqual(p['datasource']['uid'], 'atlas-prom')
            for t in p['targets']:
                self.assertTrue(metrics_in(t['expr']) <= self.names, (p['title'], metrics_in(t['expr']) - self.names))
            if p['type'] == 'timeseries':
                self.assertFalse(p['fieldConfig']['defaults']['custom']['spanNulls'], p['title'])   # gaps stay visible
        text = json.dumps(self.dash)
        for word in ('STALE', 'UNAVAILABLE', 'LATCHED'):
            self.assertIn(word, text)

    def test_dashboard_is_generated_and_provisioned(self):
        sys.path.insert(0, str(MON / 'grafana'))
        import build_dashboard
        self.assertEqual(build_dashboard.build(), self.dash)
        self.assertEqual(build_dashboard.build(), self.dash)                   # committed JSON == generator output
        ds = yaml.safe_load((MON / 'grafana/provisioning/datasources/atlas.yml').read_text())
        self.assertEqual(ds['datasources'][0]['uid'], 'atlas-prom')

    def test_availability_mapping_and_target_format(self):
        panels = {p['title']: p for p in self.dash['panels']}
        self.assertEqual(panels['Topic availability']['fieldConfig']['defaults']['mappings'][0]['options']['1']['text'], 'OK')
        self.assertEqual(len(panels['Freshness now']['targets']), 1)
        self.assertTrue(panels['Topic availability']['targets'][0]['instant'])
        targets = json.loads((MON / 'targets.json').read_text())
        self.assertIsInstance(targets[0]['targets'], list)

    def test_prometheus_scrape_retention_and_ports(self):
        prom = yaml.safe_load((MON / 'prometheus.yml').read_text())
        self.assertEqual(prom['global']['scrape_interval'], '15s')
        dc = yaml.safe_load((MON / 'docker-compose.yml').read_text())
        cmd = ' '.join(dc['services']['prometheus']['command'])
        self.assertIn('retention.time=7d', cmd); self.assertIn('retention.size=1GB', cmd)
        for svc in dc['services'].values():
            for port in svc.get('ports', []):
                self.assertTrue(port.startswith('127.0.0.1:'), port)          # never published on the LAN or Internet
        self.assertEqual(dc['services']['grafana']['environment']['GF_AUTH_ANONYMOUS_ENABLED'], 'false')


if __name__ == '__main__':
    unittest.main()
