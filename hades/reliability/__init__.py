"""hades/reliability — Reliability Estimator Engine (v3.0).

Implements four estimator quality regimes:

    Clean           : r_hat == r_true (perfect estimation, oracle baseline)
    Noisy           : r_hat = r_true + Gaussian(0, sigma), clipped to [0,1]
    Miscalibrated   : r_hat = r_true * scale + bias (systematic over/under)
    Adversarial     : attacker inflates r_hat for manipulable sources

These estimators are used by the F1/F5 sweep and Phase 4 CDB evaluation to
model the policy's uncertainty about telemetry reliability.

Key invariant: estimators modify only the ESTIMATED fields visible to policies.
The TRUE values (reliability_true, manipulation_risk_true) are never altered.
"""
from hades.reliability.estimator import (
    ReliabilityEstimator,
    CleanEstimator,
    NoisyEstimator,
    MiscalibratedEstimator,
    AdversarialEstimator,
    EstimatorResult,
    ESTIMATOR_REGISTRY,
)

__all__ = [
    "ReliabilityEstimator",
    "CleanEstimator",
    "NoisyEstimator",
    "MiscalibratedEstimator",
    "AdversarialEstimator",
    "EstimatorResult",
    "ESTIMATOR_REGISTRY",
]
