"""Independent AMCL processing evidence, deliberately without motion authority."""
import math


class ProcessingHealth:
    def __init__(self, processing_timeout_s=0.5, pose_timeout_s=2.5):
        if not all(math.isfinite(x) and x > 0 for x in (processing_timeout_s, pose_timeout_s)):
            raise ValueError('timeouts must be positive and finite')
        self.timeout = processing_timeout_s
        self.pose_timeout = pose_timeout_s
        self.latest = None
        self.received = None
        self.session = None
        self.sequence = self.scan_stamp = self.pose_sequence = self.pose_stamp = -1
        self.samples = 0
        self.reason = 'NO_PROCESSING_EVIDENCE'

    def ingest(self, data, now_s, monotonic_s):
        try:
            if not isinstance(data, dict) or data.get('schema') != 1:
                raise ValueError('SCHEMA')
            if not all(math.isfinite(x) for x in (now_s, monotonic_s)):
                raise ValueError('CLOCK')
            session = data['session']
            if not isinstance(session, str) or not 1 <= len(session) <= 128:
                raise ValueError('SESSION')
            for key in ('seq','scan_stamp_ns','processed_stamp_ns','pose_seq',
                        'last_pose_stamp_ns','valid_returns','scan_size'):
                if type(data[key]) is not int or not 0 <= data[key] < 2**63:
                    raise ValueError('INTEGER_FIELD')
            for key in ('filter_update_attempted','filter_update_succeeded',
                        'initial_pose_known','tf_available'):
                if type(data[key]) is not bool:
                    raise ValueError('BOOLEAN_FIELD')
            scan, processed = data['scan_stamp_ns']/1e9, data['processed_stamp_ns']/1e9
            if not (0 <= now_s-scan <= self.timeout and
                    0 <= now_s-processed <= self.timeout and scan <= processed):
                raise ValueError('SOURCE_STALE_OR_FUTURE')
            if not 0 < data['valid_returns'] <= data['scan_size']:
                raise ValueError('NO_VALID_RETURNS')
            if not data['initial_pose_known'] or not data['tf_available']:
                raise ValueError('INITIAL_POSE_OR_TF_MISSING')
            if data['filter_update_attempted'] and not data['filter_update_succeeded']:
                raise ValueError('FILTER_UPDATE_FAILED')
            if data['last_pose_stamp_ns'] > data['scan_stamp_ns']:
                raise ValueError('POSE_FROM_FUTURE')
            if session != self.session:
                self.session = session
                self.sequence = self.scan_stamp = self.pose_sequence = self.pose_stamp = -1
                self.samples = 0
            if data['seq'] <= self.sequence or data['scan_stamp_ns'] <= self.scan_stamp:
                raise ValueError('NONADVANCING_SCAN_OR_SEQUENCE')
            if data['pose_seq'] < self.pose_sequence or data['last_pose_stamp_ns'] < self.pose_stamp:
                raise ValueError('POSE_REGRESSION')
            if (self.pose_sequence >= 0 and data['pose_seq'] == self.pose_sequence
                    and data['last_pose_stamp_ns'] != self.pose_stamp):
                raise ValueError('POSE_STAMP_CHANGED_WITHOUT_PUBLICATION')
            self.sequence, self.scan_stamp = data['seq'], data['scan_stamp_ns']
            self.pose_sequence, self.pose_stamp = data['pose_seq'], data['last_pose_stamp_ns']
            self.latest, self.received = dict(data), monotonic_s
            self.samples += 1
            self.reason = 'OK' if self.samples >= 2 else 'WARMING_UP'
            return True
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            self.latest, self.received = None, None
            self.samples = 0
            self.reason = str(exc)
            return False

    def snapshot(self, now_s, monotonic_s):
        result = dict(processing_state='UNAVAILABLE', reason=self.reason,
                      pose_publication_state='UNKNOWN', pose_age_s=None,
                      position_validity='NOT_ESTABLISHED', navigation_authorized=False)
        if self.latest is None:
            return result
        data = self.latest
        elapsed = monotonic_s-self.received
        scan_age, process_age = now_s-data['scan_stamp_ns']/1e9, now_s-data['processed_stamp_ns']/1e9
        if not all(math.isfinite(x) and 0 <= x <= self.timeout
                   for x in (elapsed,scan_age,process_age)):
            result['reason'] = 'PROCESSING_STALE_OR_CLOCK_RESET'
            return result
        pose_age = now_s-data['last_pose_stamp_ns']/1e9 if data['pose_seq'] else None
        result.update(processing_state='PROCESSING' if self.samples >= 2 else 'WARMING_UP',
                      scan_age_s=scan_age, processing_age_s=process_age,
                      pose_age_s=pose_age, pose_seq=data['pose_seq'],
                      scan_sequence=data['seq'], session=data['session'],
                      filter_updated=data['filter_update_attempted'] and data['filter_update_succeeded'],
                      pose_publication_state=('RECENT_PUBLICATION' if pose_age is not None
                          and 0 <= pose_age <= self.pose_timeout else 'NO_RECENT_PUBLICATION'))
        return result
