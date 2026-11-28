"""Stage32 A4: READ-ONLY Astra Pro identity, firmware and calibration-property inspection (OpenNI C API via ctypes).

Binds ONLY get/query functions: no setProperty, no invoke, no stream start, no firmware/EEPROM/reset call exists in this
file (tests/test_vision3d_stage32_ir.py checks that statically). A depth and an IR stream OBJECT are created only to ask
which read-only properties they support and to read their get-only factory constants and advertised video modes;
neither stream is started, so no frames are produced. OBEXTENSION_ID_CAM_PARAMS (14) is NOT read again (it returned
all-NaN in Stage 30); only whether the device claims to support it is queried.
"""
import ctypes as C
import json
import math
from pathlib import Path

ROOT = Path('/home/jetson/project-atlas-migration/astra-20261021/astra-arm64-stage29-v2')
SENSORS = {'ir': 1, 'color': 2, 'depth': 3}
PIXEL = {100: 'DEPTH_1_MM', 101: 'DEPTH_100_UM', 102: 'SHIFT_9_2', 103: 'SHIFT_9_3', 200: 'RGB888', 201: 'YUV422',
         202: 'GRAY8', 203: 'GRAY16', 204: 'JPEG', 205: 'YUYV', 207: 'LOG'}
DEVICE_PROPS = {'firmware_version': 0, 'driver_version': 1, 'hardware_version': 2, 'serial_number': 3, 'error_state': 4,
                'image_registration': 5, 'ob_ir_gain': 11, 'ob_ir_exposure': 12, 'ob_ldp_enable': 13, 'ob_cam_params': 14,
                'ob_laser_enable': 15, 'ob_serial_number': 16, 'ob_device_type': 17, 'ob_update_firmware': 18,
                'xn_serial_number': 0x1080F006, 'xn_version': 0x1080F007, 'xn_sensor_platform_string': 0x1080FF7C,
                'xn_d2c_resolution': 0x1080FFC6}
STREAM_PROPS = {'horizontal_fov_rad': 1, 'vertical_fov_rad': 2, 'max_value': 4, 'min_value': 5,
                'const_shift': 0x10801007, 'pixel_size_factor': 0x10801008, 'max_shift': 0x10801009,
                'param_coeff': 0x1080100A, 'shift_scale': 0x1080100B, 'zero_plane_distance_mm': 0x1080100C,
                'zero_plane_pixel_size_mm': 0x1080100D, 'emitter_dcmos_distance_cm': 0x1080100E,
                'dcmos_rcmos_distance_cm': 0x1080100F, 'depth_sensor_calibration_info': 0x10801012}
# what each READ gets decoded as; anything not here is only queried for support
DEVICE_READS = {'firmware_version': 'bytes', 'driver_version': 'i4x4', 'hardware_version': 'i32', 'serial_number': 'str',
                'ob_serial_number': 'str', 'ob_device_type': 'str', 'xn_serial_number': 'str', 'xn_version': 'xnver',
                'xn_sensor_platform_string': 'str'}
STREAM_READS = {'horizontal_fov_rad': 'f32', 'vertical_fov_rad': 'f32', 'max_value': 'i32', 'min_value': 'i32',
                'const_shift': 'u64', 'pixel_size_factor': 'u64', 'max_shift': 'u64', 'param_coeff': 'u64', 'shift_scale': 'u64',
                'zero_plane_distance_mm': 'f64',   # header says u64; firmware 5.8.22 returns IEEE double bits (130.0)
                'zero_plane_pixel_size_mm': 'f64', 'emitter_dcmos_distance_cm': 'f64',
                'dcmos_rcmos_distance_cm': 'f64'}


class DeviceInfo(C.Structure):
    _fields_ = [('uri', C.c_char * 256), ('vendor', C.c_char * 256), ('name', C.c_char * 256),
                ('usbVendorId', C.c_uint16), ('usbProductId', C.c_uint16)]


class VideoMode(C.Structure):
    _fields_ = [('pixelFormat', C.c_int), ('resolutionX', C.c_int), ('resolutionY', C.c_int), ('fps', C.c_int)]


class SensorInfo(C.Structure):
    _fields_ = [('sensorType', C.c_int), ('numSupportedVideoModes', C.c_int), ('pSupportedVideoModes', C.POINTER(VideoMode))]


SIZES = {'i32': 4, 'u64': 8, 'f32': 4, 'f64': 8, 'i4x4': 16, 'xnver': 33}   # PS1080 getters need the exact size (rc 4 otherwise)


def decode(kind, buf, size):
    raw = bytes(buf[:size])
    if kind == 'str':
        return raw.split(b'\0')[0].decode(errors='replace')
    if kind == 'bytes':
        return raw.hex()
    if kind == 'xnver':   # XnVersions, pack(1): major, minor, build, chip, fpga, system, SDK{maj,min,maint,build}, HW, FW, Sensor, Chip
        import struct
        f = struct.unpack('<BBHIHHBBBHiiii', raw[:33].ljust(33, b'\0'))
        return {'fw_major': f[0], 'fw_minor': f[1], 'fw_build': f[2], 'chip': hex(f[3]), 'fpga': f[4], 'system_version': f[5],
                'sdk': '%d.%d.%d.%d' % f[6:10], 'hw_ver_enum': f[10], 'fw_ver_enum': f[11], 'sensor_ver_enum': f[12], 'chip_ver_enum': f[13]}
    fmt = {'i32': C.c_int32, 'u64': C.c_uint64, 'f32': C.c_float, 'f64': C.c_double}.get(kind)
    if kind == 'i4x4':
        return list((C.c_int32 * 4).from_buffer_copy(raw.ljust(16, b'\0')))
    v = fmt.from_buffer_copy(raw.ljust(C.sizeof(fmt), b'\0')).value
    return v if not isinstance(v, float) or math.isfinite(v) else None


def main():
    sdk = C.CDLL(str(ROOT / 'lib/libOpenNI2.so'))
    ptr = C.c_void_p

    def bind(name, args, ret=C.c_int):
        f = getattr(sdk, name); f.argtypes = args; f.restype = ret; return f
    bind('oniInitialize', [C.c_int]); bind('oniShutdown', [], None)
    bind('oniSetLogFileOutput', [C.c_int]); bind('oniSetLogConsoleOutput', [C.c_int])
    bind('oniGetDeviceList', [C.POINTER(C.POINTER(DeviceInfo)), C.POINTER(C.c_int)])
    bind('oniReleaseDeviceList', [C.POINTER(DeviceInfo)])
    bind('oniDeviceOpen', [C.c_char_p, C.POINTER(ptr)]); bind('oniDeviceClose', [ptr])
    bind('oniDeviceIsPropertySupported', [ptr, C.c_int])
    bind('oniDeviceGetProperty', [ptr, C.c_int, ptr, C.POINTER(C.c_int)])
    bind('oniDeviceGetSensorInfo', [ptr, C.c_int], C.POINTER(SensorInfo))
    bind('oniDeviceCreateStream', [ptr, C.c_int, C.POINTER(ptr)]); bind('oniStreamDestroy', [ptr], None)
    bind('oniStreamIsPropertySupported', [ptr, C.c_int])
    bind('oniStreamGetProperty', [ptr, C.c_int, ptr, C.POINTER(C.c_int)])
    out = {'mode': 'READ ONLY', 'streams_started': False, 'cam_params_reread': False}
    listing = C.POINTER(DeviceInfo)(); count = C.c_int(); device = ptr(); initialized = False; streams = []
    try:
        sdk.oniSetLogFileOutput(0); sdk.oniSetLogConsoleOutput(0)
        if sdk.oniInitialize(2003) != 0:
            raise RuntimeError('OpenNI init failed')
        initialized = True
        if sdk.oniGetDeviceList(C.byref(listing), C.byref(count)) != 0:
            raise RuntimeError('enumeration failed')
        devs = [listing[i] for i in range(count.value)]
        out['devices'] = [{'uri': d.uri.decode(), 'vendor': d.vendor.decode(), 'name': d.name.decode(),
                           'usb': '%04x:%04x' % (d.usbVendorId, d.usbProductId)} for d in devs]
        found = [d for d in devs if (d.usbVendorId, d.usbProductId) == (0x2bc5, 0x0403)]
        if len(found) != 1 or sdk.oniDeviceOpen(found[0].uri, C.byref(device)) != 0:
            raise RuntimeError('exact Astra open failed')
        props = {}
        for name, pid in DEVICE_PROPS.items():
            entry = {'supported': bool(sdk.oniDeviceIsPropertySupported(device, pid))}
            if name in DEVICE_READS:
                buf = (C.c_uint8 * 256)(); size = C.c_int(SIZES.get(DEVICE_READS[name], 256))
                rc = sdk.oniDeviceGetProperty(device, pid, C.cast(buf, ptr), C.byref(size))
                entry.update(rc=rc, bytes=size.value, value=decode(DEVICE_READS[name], buf, size.value) if rc == 0 else None)
            props[name] = entry
        out['device_properties'] = props
        sensors = {}
        for name, st in SENSORS.items():
            info = sdk.oniDeviceGetSensorInfo(device, st)
            if not info:
                sensors[name] = {'present': False}; continue
            modes = [info.contents.pSupportedVideoModes[i] for i in range(info.contents.numSupportedVideoModes)]
            sensors[name] = {'present': True, 'video_modes': ['%dx%d@%d %s' % (m.resolutionX, m.resolutionY, m.fps,
                                                                               PIXEL.get(m.pixelFormat, m.pixelFormat)) for m in modes]}
            if name in ('depth', 'ir'):
                stream = ptr()
                rc = sdk.oniDeviceCreateStream(device, st, C.byref(stream))   # object only; never started
                sensors[name]['stream_object_rc'] = rc
                if rc == 0:
                    streams.append(stream); sp = {}
                    for pname, pid in STREAM_PROPS.items():
                        e = {'supported': bool(sdk.oniStreamIsPropertySupported(stream, pid))}
                        if pname in STREAM_READS and e['supported']:
                            buf = (C.c_uint8 * 64)(); size = C.c_int(SIZES[STREAM_READS[pname]])
                            r = sdk.oniStreamGetProperty(stream, pid, C.cast(buf, ptr), C.byref(size))
                            e.update(rc=r, value=decode(STREAM_READS[pname], buf, size.value) if r == 0 else None)
                        sp[pname] = e
                    sensors[name]['stream_properties'] = sp
        out['sensors'] = sensors
    finally:
        for s in streams:
            sdk.oniStreamDestroy(s)
        if device:
            sdk.oniDeviceClose(device)
        if listing:
            sdk.oniReleaseDeviceList(listing)
        if initialized:
            sdk.oniShutdown()
    print('ATLAS_DEVICE_INFO ' + json.dumps(out, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()
