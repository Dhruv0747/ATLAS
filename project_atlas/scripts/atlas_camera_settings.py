"""ATLAS camera settings (issue #11, 25 Oct 2026): truthful capabilities, validated settings, persistence.

Two independent cameras, never sharing settings:
  astra  - Orbbec Astra Pro (depth + IR via OpenNI, RGB via its UVC camera). Settings take effect at the next
           Vision Lab Start; the existing 60-s session, viewer lease, CPU/RAM/temperature guards and identity checks
           are unchanged.
  picam  - Raspberry Pi Camera Module 3 (IMX708) through Jetson Argus (nvarguscamerasrc). Applying restarts
           atlas-camera, only while ATLAS is parked (E-STOP latched, manual-only, mission READY) and the Vision Lab
           is idle; a failed start is reverted automatically.

Detected capabilities come from the hardware, never from the manufacturer catalogue:
  astra depth/IR : read-only OpenNI enumeration of this unit (stage32_device_info, 21 Oct 2026, streams_started=false)
  astra RGB      : the UVC descriptors Linux cached at plug-in (sysfs; the camera is not opened)
  picam          : the sensor modes Argus printed when atlas-camera last started (journal)
No camera is started by any function in this module.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = Path(os.environ.get('ATLAS_CAMERA_SETTINGS') or Path.home() / '.config/project_atlas/camera_settings.json')
LOG_PATH = Path(os.environ.get('ATLAS_CAMERA_SETTINGS_LOG') or Path.home() / '.local/state/project_atlas/camera_settings.log')
ASTRA_DETECTED = ROOT / 'config/astra_detected_capabilities.json'
ASTRA_DETECTED_STATE = Path.home() / '.local/state/project_atlas/astra_detected_capabilities.json'   # newest runtime re-detection
ASTRA_INFO_TOOL = ROOT / 'tools/vision3d/astra_device_info.py'
ASTRA_RUNTIME = Path('/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2')
PICAM_CACHE = Path.home() / '.local/state/project_atlas/picam_detected_modes.json'
SCHEMA = 1

# ---------------------------------------------------------------- defaults = the exact values running before #11
ASTRA_DEFAULTS = {'depth': '160x120@30', 'color': '320x240@15', 'ir': '640x480@30'}
PICAM_DEFAULTS = {'width': 1280, 'height': 720, 'framerate': 10, 'sensor_mode': -1, 'jpeg_quality': 75,
                  'rotate_180': True, 'edge_enhancement': 0.60, 'noise_reduction': 0.35,
                  'exposure_compensation': 0.25, 'saturation': 1.20, 'white_balance_mode': 1,
                  'ae_lock': False, 'awb_lock': False, 'ae_antibanding': 1}

MANUFACTURER = {
    'astra': {'source': 'https://www.orbbec.com/products/structured-light-camera/astra-series/',
              'note': 'Legacy Astra family; RGB varies by variant. Reference only, not proof a mode works on this Jetson.',
              'depth_max': '640x480 @ 30 fps', 'rgb': 'varies by variant (Astra Pro: up to 1280x720)'},
    'picam': {'source': 'https://www.raspberrypi.com/documentation/accessories/camera.html',
              'note': 'Raspberry Pi listed video modes. Reference only; the Jetson Argus driver exposes its own modes.',
              'modes': ['2304x1296 @ 56 fps', '2304x1296 HDR @ 30 fps', '1536x864 @ 120 fps', 'still 4608x2592']},
}

# Evidence for the recommendation and the "verified" badges (measured on this ATLAS, never inferred).
ASTRA_VERIFIED = {
    'depth': {'160x120@30': 'Verified 24 Oct 2026: full 60-s Dashboard session, ~14 fps observed, Jetson CPU 67% mean.'},
    'ir': {'640x480@30': 'Verified 21 Oct 2026: full 60-s session, 29.7 fps.'},
    'color': {'320x240@15': 'Worked in the isolated Stage 29 test; not yet run through the Dashboard.'},
}
ASTRA_NOT_SERVED = {'ir': {'320x240@30', '320x240@60'}}   # advertised but never delivered by this unit (fw 5.8.22)
PICAM_VERIFIED = {'1280x720@10': 'In daily use (AI annotator, camera obstacles); camera node measured 38-40% of one core.'}

PICAM_CONTROLS = {   # nvarguscamerasrc properties present on this Jetson (gst-inspect-1.0, 25 Oct 2026)
    'exposure_compensation': {'min': -2.0, 'max': 2.0, 'step': 0.05, 'label': 'Exposure compensation'},
    'saturation': {'min': 0.0, 'max': 2.0, 'step': 0.05, 'label': 'Saturation'},
    'edge_enhancement': {'min': -1.0, 'max': 1.0, 'step': 0.05, 'label': 'Edge enhancement'},
    'noise_reduction': {'min': -1.0, 'max': 1.0, 'step': 0.05, 'label': 'Noise reduction'},
    'white_balance_mode': {'enum': {0: 'Off', 1: 'Auto', 2: 'Incandescent', 3: 'Fluorescent', 4: 'Warm fluorescent',
                                    5: 'Daylight', 6: 'Cloudy daylight', 7: 'Twilight', 8: 'Shade', 9: 'Manual'},
                           'label': 'White balance'},
    'ae_antibanding': {'enum': {0: 'Off', 1: 'Auto', 2: '50 Hz', 3: '60 Hz'}, 'label': 'Flicker (anti-banding)'},
    'ae_lock': {'bool': True, 'label': 'Lock auto exposure'},
    'awb_lock': {'bool': True, 'label': 'Lock auto white balance'},
    'rotate_180': {'bool': True, 'label': 'Rotate 180 degrees (camera mounted upside down)'},
    'jpeg_quality': {'min': 30, 'max': 95, 'step': 1, 'int': True, 'label': 'Dashboard JPEG quality'},
}
# Pixel formats actually used by each path (shown, not selectable: each driver path is fixed to one format).
FORMATS = {'astra': {'depth': '16-bit depth in millimetres (OpenNI DEPTH_1_MM)', 'ir': '8-bit intensity (GRAY8)',
                     'color': 'MJPEG from the UVC camera (YUY2 also advertised; not used by the Vision Lab driver)'},
           'picam': 'Argus NV12 in GPU memory -> BGR -> JPEG for the dashboard (published as /camera/image_raw and /compressed)'}
# USB 2.0 practical payload budget for the Astra Pro (all three streams share one 480 Mbit/s hub).
USB2_BUDGET_MBPS = 32.0
BYTES_PER_PIXEL = {'depth': 2.0, 'ir': 1.0, 'color': 0.25}   # color: MJPEG estimate (~4:1 vs 8-bit), conservative


def stream_mbps(kind, mode):
    w, h, fps = parse_mode(mode)
    return w * h * fps * BYTES_PER_PIXEL[kind] / 1e6


def astra_bandwidth(settings, streams=None):
    """Estimated USB payload (MB/s) per stream and total for the enabled streams."""
    streams = streams or {'depth': True, 'color': True, 'ir': True}
    per = {k: round(stream_mbps(k, settings[k]), 1) for k in ('depth', 'color', 'ir')}
    total = round(sum(per[k] for k in per if streams.get(k if k != 'color' else 'rgb', streams.get(k))), 1)
    return {'per_stream_mbps': per, 'total_mbps': total, 'budget_mbps': USB2_BUDGET_MBPS}


PICAM_UNSUPPORTED = {'autofocus': 'Not exposed by the Jetson Argus pipeline for this sensor.',
                     'hdr': 'No HDR sensor mode is reported by Argus on this Jetson.'}
PICAM_SIZES = [(4608, 2592), (2304, 1296), (1920, 1080), (1536, 864), (1280, 720), (960, 540), (640, 360)]


class SettingsError(ValueError):
    pass


MAINTENANCE_PATH = Path(os.environ.get('ATLAS_SERVICE_MAINTENANCE_FILE') or
                        Path.home() / '.local/state/project_atlas/service_maintenance.json')
MAINTENANCE_HOLD_S = 40.0   # atlas_sensor_recovery honours at most 45 s, and only for atlas-camera.service


def set_maintenance(service, seconds=MAINTENANCE_HOLD_S, owner='camera_settings'):
    """Tell atlas_sensor_recovery that this restart is intentional (26 Oct 2026). Bounded; best-effort."""
    try:
        MAINTENANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:data = json.loads(MAINTENANCE_PATH.read_text())
        except (OSError, ValueError):data = {}
        data = data if isinstance(data, dict) else {}
        data[service] = {'until_unix': round(time.time() + min(float(seconds), MAINTENANCE_HOLD_S), 2), 'owner': owner}
        tmp = MAINTENANCE_PATH.with_suffix('.tmp'); tmp.write_text(json.dumps(data)); os.replace(tmp, MAINTENANCE_PATH)
        return True
    except OSError:
        return False


def log(event, **kw):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open('a') as f:
            f.write(json.dumps(dict(t=round(time.time(), 2), event=event, **kw), default=str) + '\n')
    except OSError:
        pass


def parse_mode(text):
    m = re.fullmatch(r'(\d{2,4})x(\d{2,4})@(\d{1,3})', str(text))
    if not m:
        raise SettingsError('mode must look like 640x480@30')
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


# ---------------------------------------------------------------- persistence
def load_all(path=None):
    p = Path(path or SETTINGS_PATH)
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, dict) and data.get('schema') == SCHEMA else {'schema': SCHEMA}
    except (OSError, ValueError):
        return {'schema': SCHEMA}


def save_camera(cam, settings, path=None):
    p = Path(path or SETTINGS_PATH)
    data = load_all(p)
    previous = data.get(cam)
    data[cam] = dict(settings, saved_unix=round(time.time(), 1))
    if previous:
        data.setdefault('previous', {})[cam] = previous
    data['schema'] = SCHEMA
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    os.replace(tmp, p)
    return data[cam]


def stored(cam, path=None):
    data = load_all(path)
    base = dict(ASTRA_DEFAULTS if cam == 'astra' else PICAM_DEFAULTS)
    saved = data.get(cam) or {}
    for k in base:
        if k in saved:
            base[k] = saved[k]
    return base, bool(saved)


# ---------------------------------------------------------------- Astra capabilities
def astra_detected(devinfo_path=None, usb_find=None, uvc_read=None):
    info = {}
    paths = [Path(devinfo_path)] if devinfo_path else [ASTRA_DETECTED_STATE, ASTRA_DETECTED]
    for candidate in paths:
        try:
            info = json.loads(candidate.read_text())
            if info.get('sensors'):
                break
        except (OSError, ValueError):
            info = {}
    sensors = info.get('sensors', {})

    def modes(kind, wanted):
        out = []
        for m in sensors.get(kind, {}).get('video_modes', []):
            size, fmt = m.split(' ', 1)
            if fmt == wanted and size not in out:
                out.append(size)
        return out
    depth = modes('depth', 'DEPTH_1_MM')
    ir = [m for m in modes('ir', 'GRAY8') if m not in ASTRA_NOT_SERVED['ir']]
    color, color_src = [], 'not available'
    try:
        if usb_find is None:
            import atlas_astra_usb
            usb_find = atlas_astra_usb.find_astra
        if uvc_read is None:
            import uvc_descriptors
            uvc_read = uvc_descriptors.read
        found = usb_find()
        for f in uvc_read(found['rgb']):
            if f['format'] == 'MJPEG':          # the Vision Lab driver requests MJPEG from the UVC camera
                for s in f['sizes']:
                    for fps in s['fps']:
                        mode = '%dx%d@%d' % (s['w'], s['h'], round(fps))
                        if mode not in color:
                            color.append(mode)
        color_src = 'UVC descriptors cached by Linux at plug-in (camera not opened)'
    except Exception as exc:
        color_src = 'RGB modes unavailable: %s' % str(exc)[:80]
    props = info.get('device_properties', {})
    controls = {
        'ir_gain': props.get('ob_ir_gain', {}).get('supported', False),
        'ir_exposure': props.get('ob_ir_exposure', {}).get('supported', False),
        'laser_on_off': props.get('ob_laser_enable', {}).get('supported', False),
        'depth_registration': False,   # supported by hardware, disabled by policy until calibration is VALIDATED
    }
    return {'depth': depth, 'ir': ir, 'color': color, 'controls': controls,
            'serial': (props.get('xn_serial_number') or {}).get('value'), 'firmware': (info.get('provenance') or {}).get('firmware', '5.8.22'),
            'detected_at': (info.get('provenance') or {}).get('detected_at', '2026-10-21 17:37 IST'),
            'source': {'depth_ir': info.get('provenance', {}).get('source', 'read-only OpenNI enumeration, 21 Oct 2026 (no stream)'),
                       'color': color_src},
            'not_served': {k: sorted(v) for k, v in ASTRA_NOT_SERVED.items()}}


def validate_astra(req, detected=None):
    det = detected or astra_detected()
    out = {}
    for key in ('depth', 'color', 'ir'):
        val = req.get(key, ASTRA_DEFAULTS[key])
        parse_mode(val)
        allowed = det[key] or [ASTRA_DEFAULTS[key]]
        if val not in allowed:
            raise SettingsError('%s mode %s is not offered by this camera (detected: %s)' % (key, val, ', '.join(allowed)))
        if stream_mbps(key, val) > USB2_BUDGET_MBPS:
            raise SettingsError('%s mode %s needs about %.0f MB/s, more than the Astra\'s USB 2.0 link can carry (~%.0f MB/s)'
                                % (key, val, stream_mbps(key, val), USB2_BUDGET_MBPS))
        out[key] = val
    unknown = set(req) - {'depth', 'color', 'ir'}
    if unknown:
        raise SettingsError('unknown Astra setting(s): %s' % ', '.join(sorted(unknown)))
    return out


def astra_driver_values(path=None, detected=None, streams=None):
    """Values the Vision Lab worker passes to the Astra driver. Invalid/missing settings -> defaults (unchanged launch).
    streams: the viewer mode's enabled streams ({'depth','rgb','ir'} flags); if the saved modes together exceed the
    USB 2.0 budget for this combination, this session uses the defaults and the reason is logged."""
    values, _ = stored('astra', path)
    try:
        values = validate_astra(values, detected)
        if streams is not None:
            bw = astra_bandwidth(values, streams)
            if bw['total_mbps'] > USB2_BUDGET_MBPS:
                raise SettingsError('saved modes need %.0f MB/s together for this viewer mode (USB 2.0 budget %.0f)'
                                    % (bw['total_mbps'], USB2_BUDGET_MBPS))
    except SettingsError as exc:
        log('astra_settings_rejected_at_start', error=str(exc))
        values = dict(ASTRA_DEFAULTS)
    d, c, i = (parse_mode(values[k]) for k in ('depth', 'color', 'ir'))
    return {'depth_width': str(d[0]), 'depth_height': str(d[1]), 'depth_fps': str(d[2]),
            'color_width': str(c[0]), 'color_height': str(c[1]), 'color_fps': str(c[2]),
            'ir_width': str(i[0]), 'ir_height': str(i[1]), 'ir_fps': str(i[2])}


def run_astra_detect(timeout_s=40, runner=None):
    """Runtime read-only OpenNI enumeration (astra_device_info.py: get/query functions only; stream objects are
    created to list their modes but never started). Saves a dated copy used by astra_detected(); the shipped
    config file is never modified. Raises SettingsError on any problem (previous data stays in use)."""
    env = dict(os.environ, LD_LIBRARY_PATH=str(ASTRA_RUNTIME / 'lib'))
    run = runner or (lambda: subprocess.run(['/usr/bin/python3', str(ASTRA_INFO_TOOL)], cwd=str(ASTRA_RUNTIME / 'lib'), env=env,
                                            capture_output=True, text=True, timeout=timeout_s))
    try:
        res = run()
        line = next(l for l in res.stdout.splitlines() if l.startswith('ATLAS_DEVICE_INFO '))
        info = json.loads(line.split(' ', 1)[1])
    except (StopIteration, ValueError, OSError, subprocess.SubprocessError) as exc:
        log('astra_detect_failed', error=str(exc)[:200])
        raise SettingsError('Astra detection failed: %s' % str(exc)[:120])
    if info.get('streams_started') is not False or not info.get('sensors', {}).get('depth', {}).get('video_modes'):
        log('astra_detect_rejected', reason='unexpected tool output')
        raise SettingsError('Astra detection returned no depth modes; previous data kept')
    serial = (info.get('device_properties', {}).get('xn_serial_number') or {}).get('value')
    info['provenance'] = {'source': 'runtime read-only OpenNI enumeration from the Camera settings page (no stream started)',
                          'detected_at': time.strftime('%Y-%m-%d %H:%M %Z'), 'serial': serial, 'firmware': '5.8.22' if serial == '17122120830' else 'see device_properties'}
    ASTRA_DETECTED_STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ASTRA_DETECTED_STATE.with_suffix('.tmp'); tmp.write_text(json.dumps(info, indent=1)); os.replace(tmp, ASTRA_DETECTED_STATE)
    log('astra_detect_ok', serial=serial, depth=len(info['sensors']['depth']['video_modes']))
    return {'serial': serial, 'detected_at': info['provenance']['detected_at'],
            'modes': {k: len(info['sensors'].get(k, {}).get('video_modes', [])) for k in ('depth', 'ir', 'color')}}


# ---------------------------------------------------------------- Pi Camera capabilities
ARGUS_MODE = re.compile(r'GST_ARGUS: (\d+) x (\d+) FR = ([\d.]+) fps.*?Analog Gain range min ([\d.]+), max ([\d.]+); '
                        r'Exposure Range min (\d+), max (\d+)')


def parse_argus(text):
    modes, current, pipeline = [], {}, None
    for line in text.splitlines():
        m = ARGUS_MODE.search(line)
        if m:
            w, h, fr, g0, g1, e0, e1 = m.groups()
            mode = {'index': len(modes), 'width': int(w), 'height': int(h), 'max_fps': round(float(fr), 1),
                    'gain': [float(g0), float(g1)], 'exposure_ns': [int(e0), int(e1)]}
            if all(x['width'] != mode['width'] or x['height'] != mode['height'] for x in modes):
                modes.append(mode)
            continue
        if 'Available Sensor modes' in line:
            modes = []
        for key, pat in (('sensor_mode', r'Camera mode\s*=\s*(\d+)'), ('stream_w', r'Output Stream W = (\d+)'),
                         ('stream_h', r'H = (\d+)'), ('sensor_fps', r'Frame Rate = ([\d.]+)')):
            mm = re.search(pat, line)
            if mm and (key != 'stream_h' or 'Output Stream' in line):
                current[key] = float(mm.group(1)) if key == 'sensor_fps' else int(mm.group(1))
        if 'Camera node started, pipeline:' in line:
            pipeline = line.split('pipeline:', 1)[1].strip()
    if pipeline:
        for key, pat in (('width', r'width=(\d+)'), ('height', r'height=(\d+)'), ('framerate', r'framerate=(\d+)/1')):
            mm = re.search(pat, pipeline)
            if mm:
                current[key] = int(mm.group(1))
        current['pipeline'] = pipeline[:400]
    return modes, current


def picam_detected(journal_text=None):
    src = 'Argus sensor modes printed when atlas-camera last started (this boot)'
    if journal_text is None:
        try:
            journal_text = subprocess.run(['journalctl', '--user', '-u', 'atlas-camera', '-b', '-o', 'cat', '--no-pager', '-n', '400'],
                                          capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            journal_text = ''
    modes, current = parse_argus(journal_text)
    if modes:
        try:
            PICAM_CACHE.parent.mkdir(parents=True, exist_ok=True)
            PICAM_CACHE.write_text(json.dumps({'modes': modes, 'unix': time.time()}))
        except OSError:
            pass
    else:
        try:
            cached = json.loads(PICAM_CACHE.read_text())
            modes = cached['modes']
            src = 'cached Argus modes from %s (atlas-camera log of this boot unavailable)' % time.strftime('%d %b %H:%M', time.localtime(cached['unix']))
        except (OSError, ValueError, KeyError):
            src = 'no sensor modes reported yet'
    return {'modes': modes, 'current': current, 'source': src}


def picam_sizes(modes, sensor_mode):
    pool = [m for m in modes if sensor_mode in (-1, m['index'])]
    if not pool:
        return []
    maxw = max(m['width'] for m in pool)
    maxh = max(m['height'] for m in pool)
    return ['%dx%d' % s for s in PICAM_SIZES if s[0] <= maxw and s[1] <= maxh]


def picam_max_fps(modes, sensor_mode, width, height):
    pool = [m for m in modes if sensor_mode in (-1, m['index']) and m['width'] >= width and m['height'] >= height]
    return int(max(m['max_fps'] for m in pool)) if pool else 0


def validate_picam(req, detected=None):
    det = detected or picam_detected()
    modes = det['modes']
    if not modes:
        raise SettingsError('Pi Camera sensor modes not detected yet; cannot validate')
    out = dict(PICAM_DEFAULTS)
    unknown = set(req) - set(PICAM_DEFAULTS)
    if unknown:
        raise SettingsError('unknown Pi Camera setting(s): %s' % ', '.join(sorted(unknown)))
    out.update(req)
    sm = int(out['sensor_mode'])
    if sm != -1 and sm not in [m['index'] for m in modes]:
        raise SettingsError('sensor mode %s not offered (detected 0..%d)' % (sm, len(modes) - 1))
    size = '%dx%d' % (int(out['width']), int(out['height']))
    if size not in picam_sizes(modes, sm):
        raise SettingsError('resolution %s not available for sensor mode %s' % (size, 'auto' if sm == -1 else sm))
    limit = picam_max_fps(modes, sm, int(out['width']), int(out['height']))
    fr = out['framerate']
    if not isinstance(fr, int) or isinstance(fr, bool) or not 1 <= fr <= limit:
        raise SettingsError('frame rate must be a whole number 1..%d for %s' % (limit, size))
    for k, spec in PICAM_CONTROLS.items():
        v = out[k]
        if 'bool' in spec:
            if not isinstance(v, bool):
                raise SettingsError('%s must be true or false' % k)
        elif 'enum' in spec:
            if isinstance(v, bool) or v not in spec['enum']:
                raise SettingsError('%s must be one of %s' % (k, sorted(spec['enum'])))
        else:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not spec['min'] <= v <= spec['max']:
                raise SettingsError('%s must be between %s and %s' % (k, spec['min'], spec['max']))
            if spec.get('int') and not isinstance(v, int):
                raise SettingsError('%s must be a whole number' % k)
    out['width'], out['height'], out['sensor_mode'] = int(out['width']), int(out['height']), sm
    return out


def picam_ros_args(path=None, detected=None):
    """ros2 parameters for atlas-camera. Missing/invalid settings -> the exact pre-#11 values."""
    values, saved = stored('picam', path)
    if saved:
        try:
            values = validate_picam(values, detected)
        except SettingsError as exc:
            log('picam_settings_rejected_at_start', error=str(exc))
            values = dict(PICAM_DEFAULTS)
    args = []
    order = ('width', 'height', 'framerate', 'jpeg_quality', 'edge_enhancement', 'noise_reduction',
             'exposure_compensation', 'saturation', 'white_balance_mode')
    fmt = {'edge_enhancement': '%.2f', 'noise_reduction': '%.2f', 'exposure_compensation': '%.2f', 'saturation': '%.2f'}
    for k in order:
        v = values[k]
        args += ['-p', '%s:=%s' % (k, (fmt[k] % v) if k in fmt else v)]
    extras = {'sensor_mode': -1, 'rotate_180': True, 'ae_lock': False, 'awb_lock': False, 'ae_antibanding': 1}
    for k, default in extras.items():         # only non-default extras are passed, so the default launch is unchanged
        if values[k] != default:
            args += ['-p', '%s:=%s' % (k, str(values[k]).lower() if isinstance(values[k], bool) else values[k])]
    return args


# ---------------------------------------------------------------- recommendation (evidence only)
def recommendation(cam):
    if cam == 'astra':
        return {'settings': dict(ASTRA_DEFAULTS),
                'reason': 'Depth 160x120@30 is the only depth mode measured on this Jetson (24 Oct: 60 s, ~14 fps, CPU 67%). '
                          'Higher depth modes have 4x/16x the pixels and are not measured yet. IR 640x480@30 verified 21 Oct.'}
    return {'settings': dict(PICAM_DEFAULTS),
            'reason': '1280x720 at 10 fps is the measured production setting (AI annotator and camera obstacles). '
                      'Other modes are not benchmarked on ATLAS yet, so none is recommended over it.'}


def capabilities(cam):
    if cam == 'astra':
        det = astra_detected()
        return {'camera': 'astra', 'name': 'Orbbec Astra Pro', 'detected': det, 'manufacturer': MANUFACTURER['astra'],
                'formats': FORMATS['astra'], 'usb_budget_mbps': USB2_BUDGET_MBPS,
                'mbps': {k: {m: round(stream_mbps(k, m), 1) for m in det[k]} for k in ('depth', 'color', 'ir')},
                'verified': ASTRA_VERIFIED, 'applies': 'at the next Vision Lab Start (camera is never restarted by Apply)'}
    if cam == 'picam':
        det = picam_detected()
        opts = {str(sm): {'sizes': picam_sizes(det['modes'], sm),
                          'max_fps': {s: picam_max_fps(det['modes'], sm, *map(int, s.split('x'))) for s in picam_sizes(det['modes'], sm)}}
                for sm in [-1] + [m['index'] for m in det['modes']]}
        return {'camera': 'picam', 'name': 'Raspberry Pi Camera Module 3 (IMX708)', 'detected': det, 'options': opts,
                'controls': PICAM_CONTROLS, 'unsupported': PICAM_UNSUPPORTED, 'manufacturer': MANUFACTURER['picam'], 'formats': FORMATS['picam'],
                'verified': PICAM_VERIFIED, 'applies': 'restarts the Pi camera (about 5 s) while ATLAS is parked'}
    raise SettingsError('unknown camera')
