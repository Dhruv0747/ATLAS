"""Offline geometry admission and scalar depth statistics. No device/ROS access.

Validation of a document is not proof of physical camera accuracy. This module
does not publish clouds, persist frames, fit calibration or authorize deployment.
"""
import math
import statistics


def validate_calibration(c, serial, width, height, frame):
    """Reject fallback/foreign/mismatched calibration before metric geometry."""
    if not serial or c.get('device_serial') != serial:
        raise ValueError('device serial mismatch or missing')
    if c.get('source') not in ('factory_verified', 'measured_target'):
        raise ValueError('unverified calibration source')
    if c.get('independently_validated') is not True or not c.get('validation_evidence'):
        raise ValueError('independent physical validation missing')
    if (c.get('width'), c.get('height'), c.get('frame_id')) != (width, height, frame):
        raise ValueError('resolution/frame mismatch; no implicit scaling')
    if width <= 0 or height <= 0 or not frame.endswith('_optical_frame'):
        raise ValueError('invalid geometry identity')
    k = c.get('k', [])
    d = c.get('d', [])
    if len(k) != 9 or len(d) != 5 or c.get('distortion_model') != 'plumb_bob':
        raise ValueError('unsupported or malformed camera model')
    if not all(isinstance(x, (float, int)) and not isinstance(x, bool)
               and math.isfinite(x) for x in k + d):
        raise ValueError('nonfinite or nonnumeric calibration')
    if not (k[0] > 0 and k[4] > 0 and 0 <= k[2] < width and 0 <= k[5] < height
            and k[1] == k[3] == k[6] == k[7] == 0 and k[8] == 1):
        raise ValueError('invalid intrinsic matrix')
    return {'document_valid': True, 'physical_accuracy_proven_by_this_check': False}


def depth_statistics(frames, target_m, units_to_m, roi):
    """Summarize an explicit flat-target ROI from in-memory numeric frames.

    Caller supplies measured axial target distance and documented units. Values
    outside the target must not enter ROI. Outputs are scalars, never frames.
    """
    if not math.isfinite(target_m) or target_m <= 0:
        raise ValueError('measured target distance required')
    if not math.isfinite(units_to_m) or units_to_m <= 0:
        raise ValueError('documented unit conversion required')
    x0, y0, x1, y1 = roi
    if not frames or not (0 <= x0 < x1 and 0 <= y0 < y1):
        raise ValueError('empty frames/ROI')
    medians, values, total, invalid = [], [], 0, 0
    for frame in frames:
        if not frame or any(len(row) != len(frame[0]) for row in frame):
            raise ValueError('malformed frame')
        if y1 > len(frame) or x1 > len(frame[0]):
            raise ValueError('ROI outside frame')
        current = []
        for row in frame[y0:y1]:
            for raw in row[x0:x1]:
                total += 1
                if not math.isfinite(raw) or raw <= 0:
                    invalid += 1
                    continue
                current.append(raw * units_to_m)
        if current:
            medians.append(statistics.median(current))
            values.extend(current)
    if not values:
        raise ValueError('no valid target depth')
    median = statistics.median(values)
    return {'frames': len(frames), 'frames_with_valid_depth': len(medians),
            'median_m': median, 'signed_error_m': median - target_m,
            'median_absolute_error_m': statistics.median(abs(v-target_m) for v in values),
            'frame_median_population_std_m': statistics.pstdev(medians),
            'invalid_percent': 100 * invalid / total,
            'measured_to_reference_ratio': median / target_m,
            'accuracy_pass': None, 'note': 'No acceptance threshold or physical truth inferred'}
