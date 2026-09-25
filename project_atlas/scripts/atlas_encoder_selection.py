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
    if excluded != sorted(set(excluded)) or any(i not in (1, 2, 3, 4) for i in excluded):
        raise ValueError('excluded_encoders must contain unique M1..M4 channel numbers')
    if len(excluded) > 1:
        raise ValueError('at least three explicitly commissioned encoder channels are required')
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
        selected = [f'M{i + 1}' for i in range(4) if i not in excluded]
        rejected = [f'M{i + 1}' for i in excluded]
        return ('DEGRADED', 0.5,
                f'{"/".join(selected)} selected; {"/".join(rejected)} feedback excluded')
    if len(faults) >= 2 or (faults and fault_age > 5.0):
        return 'CRITICAL', 0.0, 'multiple or persistent encoder fault'
    if faults:
        return 'DEGRADED', 0.5, 'temporary single encoder fault'
    return ('HEALTHY' if traction else 'READY'), 1.0, 'all selected feedback available'


class EncoderDeltaEstimator:
    """Dynamic three-of-four consensus over per-wheel increments.

    Every non-statically-excluded channel remains a candidate.  For each sample
    interval the largest group of at least three mutually coherent wheel deltas
    is selected and its median is integrated.  A weak/intermittent channel can
    therefore move between M3 and M4 without silently corrupting odometry.
    A two-versus-two split fails closed. Invalid intervals are rebased, not
    integrated later as a catch-up jump.
    """
    def __init__(self, relative_tolerance=0.45, absolute_tolerance_m=0.002):
        self.previous = None
        self.previous_valid = set()
        self.relative_tolerance = float(relative_tolerance)
        self.absolute_tolerance_m = float(absolute_tolerance_m)
        self.last_accepted = ()
        self.last_rejected = ()
        self.last_deltas = (0.0, 0.0, 0.0, 0.0)

    def _cluster(self, deltas):
        best = ()
        for center_index, center in deltas.items():
            group = []
            for index, value in deltas.items():
                tolerance = max(
                    self.absolute_tolerance_m,
                    self.relative_tolerance * max(abs(center), abs(value)),
                )
                if abs(value - center) <= tolerance:
                    group.append(index)
            candidate = tuple(sorted(group))
            if len(candidate) > len(best):
                best = candidate
            elif len(candidate) == len(best) and candidate:
                current_spread = max(deltas[i] for i in candidate) - min(deltas[i] for i in candidate)
                best_spread = max(deltas[i] for i in best) - min(deltas[i] for i in best)
                if current_spread < best_spread:
                    best = candidate
        return best

    def update(self, distances, valid_indexes):
        if len(distances) != 4:
            raise ValueError('four raw diagnostic distances required')
        current = tuple(float(d) for d in distances)
        valid = {i for i in valid_indexes if 0 <= i < 4 and math.isfinite(current[i])}
        common = valid & self.previous_valid
        delta = 0.0
        accepted = ()
        deltas = {}
        if self.previous is not None and len(common) >= 3:
            deltas = {i: current[i] - self.previous[i] for i in common}
            accepted = self._cluster(deltas)
            if len(accepted) >= 3:
                delta = statistics.median(deltas[i] for i in accepted)
            else:
                accepted = ()
        self.last_accepted = accepted
        self.last_rejected = tuple(sorted(common - set(accepted))) if accepted else tuple(sorted(common))
        self.last_deltas = tuple(
            deltas.get(i, 0.0) for i in range(4)
        )
        self.previous = current
        self.previous_valid = valid
        return delta
