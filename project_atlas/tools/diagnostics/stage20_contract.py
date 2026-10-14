"""Fail-closed checkpoint evidence contract. No ROS or production imports."""
import math

CRITERIA = {
    'declared_before_comparison': True,
    'ekf_position_max_m': 0.01, 'ekf_yaw_max_rad': math.radians(0.5),
    'ekf_covariance_relative_max': 0.01, 'input_payload_and_header_match': True,
    'consumer_order_required': True, 'tf_lookup_error_count': 0,
    'amcl_repeated_runs_min': 20, 'amcl_jump_threshold_m': 0.5,
    'amcl_statistical_gate': 'Predeclare confidence intervals from faithful baseline ensembles; no single-run claim',
}

def checkpoint_errors(e):
    errors = []
    for name in ('startup_before_sources', 'consumer_order_verified',
                 'parameters_verified', 'map_verified', 'service_events_complete',
                 'tf_history_complete', 'loss_accounting_complete'):
        if e.get(name) is not True:
            errors.append(name)
    state, covariance = e.get('ekf_state', []), e.get('ekf_covariance', [])
    if len(state) != 15 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in state):
        errors.append('full_15_state')
    if len(covariance) != 225 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in covariance):
        errors.append('full_225_covariance')
    if not e.get('actual_relative_reference'):
        errors.append('actual_relative_reference')
    if e.get('amcl_rng_restored') is not True and e.get('amcl_startup_ensemble_verified') is not True:
        errors.append('amcl_internal_state_or_startup_ensemble')
    return errors

def ready_for_candidates(e):
    return not checkpoint_errors(e) and e.get('baseline_failure_reproduced') is True
