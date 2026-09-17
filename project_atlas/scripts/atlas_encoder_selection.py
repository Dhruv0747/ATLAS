"""Pure encoder selection and incremental odometry helpers (no hardware I/O)."""
import math
import statistics

WHEEL_NAMES = ('back_left', 'back_right', 'front_left', 'front_right')
ENCODER_NAMES = ('M1_REAR_LEFT', 'M2_REAR_RIGHT', 'M3_FRONT_LEFT', 'M4_FRONT_RIGHT')


def validate_selection(config):
    """Fail closed on missing/invalid commissioning configuration."""
    if not isinstance(config, dict):
        raise ValueError('encoder selection must be a mapping')
    excluded = config.get('excluded_encoders')
    if not isinstance(excluded, list) or any(type(i) is not int for i in excluded):
        raise ValueError('excluded_encoders must be an explicit list of channel numbers')
    if excluded not in ([], [4]):
        raise ValueError('only all-four or explicitly commissioned M1/M2/M3 is supported')
    validated = config.get('navigation_validated')
    if type(validated) is not bool:
        raise ValueError('navigation_validated must be explicitly true or false')
    timeout = config.get('packet_timeout_s')
    if type(timeout) not in (int, float) or not 0.1 <= timeout <= 1.0:
        raise ValueError('packet_timeout_s must be between 0.1 and 1.0 seconds')
    return tuple(i - 1 for i in excluded), validated, float(timeout)


def feedback_state(excluded, faults, packet_fresh, qualifying, traction, fault_age):
    if not packet_fresh:
        return 'CRITICAL', 0.0, 'encoder packet missing or stale'
    if qualifying:
        return 'QUALIFYING', 0.0, 'waiting for startup qualification'
    if excluded:
        if faults:
            return 'CRITICAL', 0.0, 'additional selected encoder failed'
        return 'DEGRADED', 0.5, 'M1/M2/M3 selected; M4 feedback excluded'
    if len(faults) >= 2 or (faults and fault_age > 5.0):
        return 'CRITICAL', 0.0, 'multiple or persistent encoder fault'
    if faults:
        return 'DEGRADED', 0.5, 'temporary single encoder fault'
    return ('HEALTHY' if traction else 'READY'), 1.0, 'all selected feedback available'


class EncoderDeltaEstimator:
    """Median of per-wheel increments, never a jump between cumulative medians.

    At least three channels must be valid in BOTH samples. Invalid intervals
    are rebased, not integrated later as a catch-up jump. This remains a wheel
    distance approximation; steering geometry and metric scales need ground
    validation and are not magically corrected by rejecting M4.
    """
    def __init__(self):
        self.previous = None
        self.previous_valid = set()

    def update(self, distances, valid_indexes):
        if len(distances) != 4:
            raise ValueError('four raw diagnostic distances required')
        current = tuple(float(d) for d in distances)
        valid = {i for i in valid_indexes if 0 <= i < 4 and math.isfinite(current[i])}
        common = valid & self.previous_valid
        delta = 0.0
        if self.previous is not None and len(common) >= 3:
            delta = statistics.median(current[i] - self.previous[i] for i in common)
        self.previous = current
        self.previous_valid = valid
        return delta
