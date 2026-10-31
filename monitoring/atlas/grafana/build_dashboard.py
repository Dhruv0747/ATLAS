#!/usr/bin/env python3
"""Generates dashboards/atlas-health.json (ATLAS HEALTH MONITOR). Deterministic; run after editing panels."""
import json
from pathlib import Path

DS = {'type': 'prometheus', 'uid': 'atlas-prom'}
UNAVAILABLE = 'UNAVAILABLE'
pid = [0]


def panel(kind, title, exprs, x, y, w=8, h=7, unit=None, mappings=None, thresholds=None, desc='', legend=None):
    pid[0] += 1
    # Readable series names: a single-query panel is named by its title; multi-query panels must name each query.
    # Grafana's '__auto' printed raw 'metric{instance=...,job=...}' labels (fixed 2026-10-31).
    if legend is None:
        if len(exprs) != 1:
            raise ValueError('multi-query panel needs explicit legend names: ' + title)
        legend = [title]
    p = {'id': pid[0], 'type': kind, 'title': title, 'description': desc, 'datasource': DS,
         'gridPos': {'x': x, 'y': y, 'w': w, 'h': h},
         'targets': [{'refId': chr(65 + i), 'expr': e, 'legendFormat': legend[i], 'datasource': DS}
                     for i, e in enumerate(exprs)],
         'fieldConfig': {'defaults': {'noValue': UNAVAILABLE, 'mappings': mappings or [], 'custom': {}}, 'overrides': []},
         'options': {}}
    if kind in ('table', 'stat'):
        for target in p['targets']:
            target.update(instant=True, range=False)
    if kind == 'table':
        for target in p['targets']:
            target['format'] = 'table'
    if unit:
        p['fieldConfig']['defaults']['unit'] = unit
    if thresholds:
        p['fieldConfig']['defaults']['thresholds'] = {'mode': 'absolute', 'steps': thresholds}
        if kind == 'timeseries':
            p['fieldConfig']['defaults']['custom']['thresholdsStyle'] = {'mode': 'line'}
    if kind == 'timeseries':
        p['fieldConfig']['defaults']['custom'].update({'spanNulls': False, 'showPoints': 'never'})   # gaps stay visible
    return p


def vmap(pairs):
    return [{'type': 'value', 'options': {str(k): {'text': t, 'color': c} for k, (t, c) in pairs.items()}}]


OKBAD = vmap({1: ('OK', 'green'), 0: (UNAVAILABLE, 'red')})
STALE = vmap({0: ('FRESH', 'green'), 1: ('STALE', 'orange')})
GREEN, AMBER, RED = 'green', 'orange', 'red'


def row(title, y):
    pid[0] += 1
    return {'id': pid[0], 'type': 'row', 'title': title, 'collapsed': False, 'gridPos': {'x': 0, 'y': y, 'w': 24, 'h': 1}, 'panels': []}


def build():
    pid[0] = 0
    P = []
    P.append(row('Overall', 0))
    P += [panel('stat', 'Exporter reachable', ['up{job="atlas-jetson"}'], 0, 1, 4, 4, mappings=vmap({1: ('UP', GREEN), 0: ('DOWN', RED)})),
          panel('stat', 'Last successful update', ['time() - atlas_exporter_observed_timestamp_seconds'], 4, 1, 4, 4, unit='s',
                thresholds=[{'color': GREEN, 'value': None}, {'color': AMBER, 'value': 30}, {'color': RED, 'value': 45}],
                desc='Seconds since the exporter last collected. Over 45 s = STALE.'),
          panel('stat', 'E-STOP', ['atlas_estop_latched'], 8, 1, 4, 4, mappings=vmap({1: ('LATCHED', GREEN), 0: ('RELEASED', AMBER)}),
                desc='From the mux control policy via the dashboard. Display only; this system cannot change it.'),
          panel('stat', 'Selected controller', ['sum((atlas_control_selected{controller="XBOX"} == 1) or ((atlas_control_selected{controller="FLYSKY"} == 1) * 2)) or vector(-1)'], 12, 1, 4, 4, mappings=vmap({1: ('XBOX', GREEN), 2: ('FLYSKY', GREEN), -1: (UNAVAILABLE, AMBER), 3: ('UNKNOWN', AMBER)}),
                desc='Display-only mapping from verified controller labels: XBOX=1, FLYSKY=2. Missing=UNAVAILABLE; conflicting selection=UNKNOWN.'),
          panel('table', 'Data sources', ['atlas_source_available'], 16, 1, 8, 4, mappings=OKBAD, legend=['{{source}}'],
                desc='UNAVAILABLE = that source is missing; its metrics are not shown (never as zero).')]
    P.append(row('Jetson (aligned time axis: compare faults with CPU spikes)', 5))
    lim = lambda v: [{'color': GREEN, 'value': None}, {'color': RED, 'value': v}]
    P += [panel('timeseries', 'CPU %', ['atlas_cpu_utilization_percent'], 0, 6, 8, 7, unit='percent', thresholds=lim(75), legend=['CPU']),
          panel('timeseries', 'Temperature (max zone)', ['atlas_thermal_max_celsius'], 8, 6, 8, 7, unit='celsius', thresholds=lim(70), legend=['max']),
          panel('timeseries', 'RAM / swap used %', ['100 * (1 - atlas_memory_available_bytes / atlas_memory_total_bytes)',
                                                  '100 * (1 - atlas_swap_free_bytes / clamp_min(atlas_swap_total_bytes, 1))'],
                16, 6, 8, 7, unit='percent', thresholds=lim(80), legend=['RAM', 'swap']),
          panel('timeseries', 'GPU load % / frequency', ['atlas_gpu_load_percent', 'atlas_gpu_frequency_hz / 1e6'], 0, 13, 8, 7,
                legend=['GPU %', 'GPU MHz'], desc='Frequency scaling alone does not establish thermal throttling; throttle flags are unavailable.'),
          panel('timeseries', 'Disk free %', ['100 * atlas_disk_free_bytes / atlas_disk_total_bytes'], 8, 13, 8, 7, unit='percent', legend=['/']),
          panel('timeseries', 'Load average (1 min)', ['atlas_load1'], 16, 13, 8, 7, legend=['load1'])]
    P.append(row('Cameras', 20))
    P += [panel('timeseries', 'Pi camera: metadata age', ['atlas_topic_age_seconds{topic="camera_info"}'], 0, 21, 12, 7, unit='s',
                thresholds=lim(5), legend=['age'], desc='Pi camera FPS is UNAVAILABLE without a new camera subscriber (not allowed). CameraInfo age is metadata freshness, not proof of image frames.'),
          panel('stat', 'Astra Pro RGB/depth', ['atlas_source_available{source="astra"}'], 12, 21, 6, 7, mappings=vmap({1: ('PRESENT', GREEN), 0: (UNAVAILABLE, RED)})),
          panel('state-timeline', 'atlas-camera service', ['atlas_service_active{service="atlas-camera"}'], 18, 21, 6, 7,
                mappings=vmap({1: ('active', GREEN), 0: ('not active', RED)}))]
    P.append(row('Sensors and base MCU freshness', 28))
    P += [panel('timeseries', 'Topic age (s)', ['atlas_topic_age_seconds'], 0, 29, 12, 8, unit='s', legend=['{{topic}}']),
          panel('table', 'Freshness now', ['atlas_topic_stale'], 12, 29, 6, 8,
                mappings=STALE, legend=['{{topic}}'],
                desc='STALE = older than its limit (atlas_topic_freshness_limit_seconds). missing topics appear in the availability table.'),
          panel('table', 'Topic availability', ['atlas_topic_available'], 18, 29, 6, 8, mappings=OKBAD, legend=['{{topic}}'])]
    P.append(row('Remote controls', 37))
    P += [panel('state-timeline', 'Active control source', ['atlas_control_selected'], 0, 38, 12, 6, legend=['{{controller}}'],
                mappings=vmap({1: ('selected', GREEN), 0: ('-', 'transparent')})),
          panel('timeseries', 'Xbox /joy rate (Hz) / FlySky frame age (s)', ['atlas_topic_rate_hz{topic="joy"}', 'atlas_flysky_frame_age_seconds'],
                12, 38, 12, 6, legend=['Xbox Hz', 'FlySky frame age'], desc='FlySky frame age exists only while the FlySky teleop runs.'),
          panel('stat', 'FlySky failsafe / frame lost', ['atlas_flysky_failsafe or vector(-1)', 'atlas_flysky_frame_lost or vector(-1)'], 0, 44, 12, 5,
                legend=['failsafe', 'frame lost'], mappings=vmap({-1: (UNAVAILABLE, AMBER), 0: ('clear', GREEN), 1: ('SET', RED)})),
          panel('timeseries', 'Seconds since last drive command', ['atlas_command_age_seconds'], 12, 44, 12, 5, unit='s',
                desc='The mux publishes /cmd_vel only while something drives: a large age when idle is normal.')]
    P.append(row('ROS services', 49))
    P += [panel('state-timeline', 'Service active', ['atlas_service_active'], 0, 50, 16, 9, legend=['{{service}}'],
                mappings=vmap({1: ('active', GREEN), 0: ('not active', RED)})),
          panel('timeseries', 'Restarts in 10 min', ['increase(atlas_service_restarts_total[10m])'], 16, 50, 8, 9, legend=['{{service}}'])]
    P.append(row('Battery and encoders', 59))
    P += [panel('timeseries', 'Battery voltage', ['atlas_battery_voltage_volts'], 0, 60, 8, 7, unit='volt', legend=['{{source}}']),
          panel('timeseries', 'Battery % (BMS) / current (A)', ['atlas_battery_percent', 'atlas_battery_current_amps'], 8, 60, 8, 7, legend=['%', 'A']),
          panel('timeseries', 'Encoder faults and link errors (10 min)', ['atlas_encoder_faults', 'increase(atlas_encoder_serial_checksum_errors_total[10m])',
                                                                           'increase(atlas_encoder_link_stale_events_total[10m])'],
                16, 60, 8, 7, legend=['faults', 'checksum errors', 'link stale events'])]
    P.append(row('Additional cached telemetry (no new ROS subscribers)', 67))
    P += [panel('timeseries', 'Battery power (signed BMS value)', ['atlas_battery_power_watts'], 0, 68, unit='watt'),
          panel('timeseries', 'Jetson power', ['atlas_jetson_power_watts'], 8, 68, unit='watt'),
          panel('timeseries', 'Raw encoder counts', ['atlas_encoder_count'], 16, 68, legend=['{{wheel}}']),
          panel('stat', 'Encoder READY', ['atlas_encoder_ready'], 0, 75, mappings=vmap({1: ('READY', GREEN), 0: ('NOT READY', RED)})),
          panel('stat', 'FlySky drive enabled (display only)', ['atlas_flysky_drive_enabled'], 8, 75),
          panel('timeseries', 'Serial writes and link recoveries (10 min)',
                ['increase(atlas_encoder_serial_write_errors_total[10m])', 'increase(atlas_encoder_link_recoveries_total[10m])'],
                16, 75, legend=['write errors', 'recoveries'])]
    return {'uid': 'atlas-health-monitor', 'title': 'ATLAS HEALTH MONITOR', 'tags': ['atlas', 'read-only'], 'timezone': 'browser',
            'schemaVersion': 39, 'version': 1, 'editable': False, 'refresh': '30s', 'time': {'from': 'now-6h', 'to': 'now'},
            'graphTooltip': 1, 'panels': P,
            'description': 'Read-only. UNAVAILABLE = source missing; STALE = older than its limit. Shared crosshair aligns all panels in time.'}


if __name__ == '__main__':
    out = Path(__file__).resolve().parent / 'dashboards/atlas-health.json'
    out.write_text(json.dumps(build(), indent=1) + '\n')
    print('wrote', out)

