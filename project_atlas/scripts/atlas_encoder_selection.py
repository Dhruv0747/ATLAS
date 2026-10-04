"""Pure encoder selection and incremental odometry helpers (no hardware I/O)."""
import math
import statistics

WHEEL_NAMES = ('back_left', 'back_right', 'front_left', 'front_right')
ENCODER_NAMES = ('M1_REAR_LEFT', 'M2_REAR_RIGHT', 'M3_FRONT_LEFT', 'M4_FRONT_RIGHT')


def four_wheel_path_scales(curvature, wheelbase_m, track_width_m, positions):
    """Return wheel-path/body-centre ratios for four-wheel steering."""
    curvature = float(curvature)
    wheelbase_m = float(wheelbase_m)
    track_width_m = float(track_width_m)
    if (not math.isfinite(curvature) or not math.isfinite(wheelbase_m)
            or not math.isfinite(track_width_m) or wheelbase_m <= 0.0
            or track_width_m <= 0.0 or len(positions) != 4):
        raise ValueError(
            'valid curvature, wheelbase, track width and four positions required'
        )
    half_l, half_t = wheelbase_m / 2.0, track_width_m / 2.0
    coordinates = {
        'rear_left': (-half_l, half_t), 'back_left': (-half_l, half_t),
        'rear_right': (-half_l, -half_t), 'back_right': (-half_l, -half_t),
        'front_left': (half_l, half_t), 'front_right': (half_l, -half_t),
    }
    scales = []
    for position in positions:
        if position not in coordinates:
            raise ValueError(f'unknown wheel position: {position}')
        x_m, y_m = coordinates[position]
        scales.append(math.hypot(1.0 - curvature * y_m, curvature * x_m))
    return tuple(scales)


class EncoderLinkMonitor:
    """Track shared controller-packet loss and post-recovery qualification.

    Wheel disagreement is deliberately handled separately by
    ``EncoderDeltaEstimator``.  Mixing those two failure classes made a
    two-versus-two wheel disagreement look like all four encoders had vanished.
    """

    def __init__(self, timeout_s, qualify_s=3.0):
        self.timeout_s = float(timeout_s)
        self.qualify_s = float(qualify_s)
        self.fresh = False
        self.healthy_since = 0.0
        self.stale_events = 0
        self.recoveries = 0
        self.ever_fresh = False

    def update(self, packet_stamp, now):
        packet_stamp = float(packet_stamp)
        now = float(now)
        fresh = (
            packet_stamp > 0.0
            and 0.0 <= now - packet_stamp <= self.timeout_s
        )
        if fresh and not self.fresh:
            if self.ever_fresh:
                self.recoveries += 1
            self.healthy_since = now
            self.ever_fresh = True
        elif not fresh and self.fresh:
            self.stale_events += 1
            self.healthy_since = 0.0
        self.fresh = fresh
        qualifying = (
            fresh
            and (
                self.healthy_since <= 0.0
                or now - self.healthy_since < self.qualify_s
            )
        )
        return fresh, qualifying


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
    def __init__(self, relative_tolerance=0.45, absolute_tolerance_m=0.004):
        # Controller counts arrive in short bursts.  During a very slow 4WS
        # arc the three commissioned channels can legitimately quantize to
        # body-centre increments spread by just under 4 mm even after wheel-
        # path normalization.  A 2 mm floor falsely removed all three before
        # enough travel accumulated.  The relative tolerance still governs
        # larger increments, while stale/missing channels remain fail-closed.
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

    def update(self, distances, valid_indexes, normalization_scales=None):
        if len(distances) != 4:
            raise ValueError('four raw diagnostic distances required')
        current = tuple(float(d) for d in distances)
        scales = ((1.0,) * 4 if normalization_scales is None
                  else tuple(float(value) for value in normalization_scales))
        if len(scales) != 4 or any(
                not math.isfinite(value) or value <= 0.0 for value in scales):
            raise ValueError('four positive finite normalization scales required')
        valid = {i for i in valid_indexes if 0 <= i < 4 and math.isfinite(current[i])}
        common = valid & self.previous_valid
        delta = 0.0
        accepted = ()
        deltas = {}
        if self.previous is not None and len(common) >= 3:
            deltas = {
                i: (current[i] - self.previous[i]) / scales[i]
                for i in common
            }
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
