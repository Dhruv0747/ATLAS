"""Bounded read-only RGB/depth/PointCloud2 decoding. No ROS or device ownership.

Depth is axial Z, NOT Euclidean range; measurements explicitly expose both.
No RGB/depth registration or robot-frame transform is assumed.
"""
import math
import struct
import zlib

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 1280 * 720
MAX_POINTS = 6000


def stamp(msg):
    s = msg.header.stamp
    return s.sec + s.nanosec * 1e-9


def image_layout(m):
    sizes = {'16UC1': 2, 'mono16': 2, '32FC1': 4, 'mono8': 1, 'rgb8': 3, 'bgr8': 3}
    bpp = sizes.get(m.encoding)
    if not bpp:
        raise ValueError('MODE UNSUPPORTED: ' + m.encoding)
    if not (0 < m.width <= 1280 and 0 < m.height <= 720 and m.width*m.height <= MAX_PIXELS):
        raise ValueError('image dimensions exceed budget')
    if m.step < m.width*bpp or m.step*m.height > MAX_BYTES or len(m.data) != m.step*m.height:
        raise ValueError('invalid image buffer/stride')
    return bpp


def depth_at(m, u, v):
    image_layout(m)
    if not (0 <= u < m.width and 0 <= v < m.height):
        raise ValueError('pixel outside image')
    endian = '>' if m.is_bigendian else '<'
    if m.encoding == '16UC1':
        raw = struct.unpack_from(endian+'H', m.data, v*m.step+u*2)[0]
        z = raw / 1000.0 if raw not in (0, 65535) else float('nan')
    elif m.encoding == '32FC1':
        z = struct.unpack_from(endian+'f', m.data, v*m.step+u*4)[0]
    else:
        raise ValueError('depth requires 16UC1 millimetres or 32FC1 metres')
    return z if math.isfinite(z) and z > 0 else None


def intrinsics(m, info):
    if info is None or info.width != m.width or info.height != m.height:
        raise ValueError('matching CameraInfo unavailable')
    if info.header.frame_id != m.header.frame_id:
        raise ValueError('CameraInfo frame mismatch')
    # Use K on the raw image; non-zero distortion needs rectification first.
    if any(not math.isfinite(float(x)) or abs(float(x)) > 1e-9 for x in info.d):
        raise ValueError('distorted image: rectification required for XYZ')
    fx, fy, cx, cy = (info.k[i] for i in (0, 4, 2, 5))
    if not all(math.isfinite(x) for x in (fx, fy, cx, cy)) or fx <= 0 or fy <= 0:
        raise ValueError('invalid calibration')
    return fx, fy, cx, cy


def measure(m, info, u, v):
    z = depth_at(m, u, v)
    out = {'pixel': [u, v], 'valid': z is not None, 'depth_z_m': z,
           'frame': m.header.frame_id, 'source_stamp': stamp(m), 'xyz_m': None, 'range_m': None}
    if z is not None:
        try:
            fx, fy, cx, cy = intrinsics(m, info)
            xyz = [(u-cx)*z/fx, (v-cy)*z/fy, z]
            out.update(xyz_m=xyz, range_m=math.sqrt(sum(x*x for x in xyz)))
        except ValueError as e:
            out['xyz_unavailable_reason'] = str(e)
    return out


def _png(w, h, rows):
    def chunk(kind, data):
        return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!2I5B', w,h,8,2,0,0,0))+
            chunk(b'IDAT', zlib.compress(b''.join(b'\0'+r for r in rows), 1))+chunk(b'IEND', b''))


def preview(m, kind, max_width=240):
    """Convert only on demand, <=43,200 displayed pixels, never interpolate ranges."""
    bpp = image_layout(m)
    step = max(1, math.ceil(m.width/max_width), math.ceil(m.height/180))
    xs, ys = range(0,m.width,step), range(0,m.height,step)
    rows, valid, invalid = [], 0, 0
    for y in ys:
        row = bytearray()
        for x in xs:
            if kind == 'depth':
                z = depth_at(m,x,y)
                if z is None:
                    rgb = (0,0,0); invalid += 1
                else:
                    t = min(1.0,z/5.0); rgb = (int(255*(1-t)),int(255*(1-abs(2*t-1))),int(255*t)); valid += 1
            elif m.encoding in ('rgb8','bgr8'):
                rgb = m.data[y*m.step+x*bpp:y*m.step+x*bpp+3]
                if m.encoding == 'bgr8': rgb = rgb[::-1]
            elif m.encoding == 'mono8':
                rgb = (m.data[y*m.step+x],)*3
            elif kind == 'ir' and m.encoding in ('mono16','16UC1'):
                g = min(255,struct.unpack_from(('>' if m.is_bigendian else '<')+'H',m.data,y*m.step+x*2)[0]//16)
                rgb = (g,)*3
            else:
                raise ValueError('MODE UNSUPPORTED for '+kind)
            row.extend(rgb)
        rows.append(bytes(row))
    return _png(len(xs),len(ys),rows), {'sampled_valid':valid,'sampled_invalid':invalid,
                                      'sample_stride':step,'source_width':m.width,'source_height':m.height}


def cloud_points(m, limit=MAX_POINTS):
    """Decode actual PointCloud2 XYZ float32 with row padding and byte order."""
    limit = min(MAX_POINTS,max(1,int(limit)))
    if not m.header.frame_id.endswith('optical_frame'):
        raise ValueError('verified camera optical frame required for this viewer')
    if not (0 < m.width*m.height <= MAX_PIXELS and 0 < m.point_step <= 256):
        raise ValueError('cloud dimensions exceed budget')
    if m.row_step < m.width*m.point_step or len(m.data) != m.row_step*m.height or len(m.data)>MAX_BYTES:
        raise ValueError('invalid cloud buffer/stride')
    fields = {f.name:f for f in m.fields}
    if any(k not in fields or fields[k].datatype != 7 or fields[k].count != 1 or
           not (0 <= fields[k].offset <= m.point_step-4) for k in ('x','y','z')):
        raise ValueError('XYZ float32 fields unavailable')
    stride = max(1,math.ceil(m.width*m.height/limit)); points=[]
    for n in range(0,m.width*m.height,stride):
        v,u=divmod(n,m.width); base=v*m.row_step+u*m.point_step
        xyz=[struct.unpack_from(('>' if m.is_bigendian else '<')+'f',m.data,base+fields[k].offset)[0] for k in ('x','y','z')]
        if all(math.isfinite(x) for x in xyz) and xyz[2]>0: points.append(xyz)
    return {'points':points,'frame':m.header.frame_id,'source_stamp':stamp(m),'sample_stride':stride,
            'source_points':m.width*m.height,'units':'metres','source':'PointCloud2 (not RGB registered)'}


def obstacle_prototype(points, z_min=.2, z_max=2.0):
    """Shadow camera-frame summary ONLY; no Nav2 output or ground-removal claim."""
    candidates=[p for p in points[:MAX_POINTS] if len(p)==3 and all(math.isfinite(v) for v in p)
                and z_min<=p[2]<=z_max and abs(p[0])<=.5 and abs(p[1])<=.5]
    return {'shadow_only':True,'frame':'camera optical (not base_link)',
            'candidate_count':len(candidates),'nearest_z_m':min((p[2] for p in candidates),default=None),
            'limitation':'ROI includes floors/walls; no LiDAR comparison without calibrated extrinsics'}
