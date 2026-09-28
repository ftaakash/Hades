"""hades/reliability/estimator.py — Reliability Estimator Regimes (v3.0).

Policy's visibility into reliability is mediated by a ReliabilityEstimator.
The estimator takes a source's TRUE reliability values and returns the
ESTIMATED (policy-visible) values that will be reported in r_hat / phi_hat.

Four regimes
------------
Clean        : r_hat = r_true, phi_hat = phi_true (oracle baseline)
Noisy        : r_hat = clip(r_true + N(0,sigma), 0, 1)  (estimation noise)
Miscalibrated: r_hat = clip(scale * r_true + bias, 0, 1) (systematic error)
Adversarial  : attacker inflates r_hat for high-phi_hat sources to look safe

These regimes are orthogonal to the corruption regimes (R1-R4). A source
can be BOTH corrupted (R4) AND mis-estimated (Adversarial), which is the
most challenging condition.

Invariants
----------
- estimators produce (r_hat, phi_hat) in [0,1]²
- They never modify reliability_true / manipulation_risk_true
- Deterministic given rng state
- Policy reads ONLY the estimated values returned here

Misspecification experiments (reviewer feedback)
--------------------------------------------------
The reviewer explicitly requested:
    true φ=0.7, estimated φ=0.2 (under-estimate)
    true φ=0.7, estimated φ=0.9 (over-estimate)

NoisyEstimator covers this via sigma. MiscalibratedEstimator provides
controlled systematic bias. See test_corruption.py for exact test cases.
"""
from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class EstimatorResult:
    """Policy-visible reliability estimates for one source."""
    r_hat: float        # estimated operational reliability in [0,1]
    phi_hat: float      # estimated manipulation risk in [0,1]


class ReliabilityEstimator(ABC):
    """Abstract base: maps (r_true, phi_true) → (r_hat, phi_hat)."""

    regime: str = "estimator_unknown"

    @abstractmethod
    def estimate(
        self,
        r_true: float,
        phi_true: float,
        rng: random.Random,
        source_name: str = "",
    ) -> EstimatorResult:
        """Return policy-visible (r_hat, phi_hat) estimates."""
        raise NotImplementedError

    @staticmethod
    def _clip(v: float) -> float:
        return max(0.0, min(1.0, v))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(regime={self.regime})"


# ---------------------------------------------------------------------------
# Clean — perfect estimation (oracle baseline)
# ---------------------------------------------------------------------------

class CleanEstimator(ReliabilityEstimator):
    """r_hat = r_true, phi_hat = phi_true. Perfect, no estimation error.

    This is the oracle upper bound. A policy using this estimator
    has perfect knowledge of source reliability. It establishes the
    best-case HADES performance.
    """

    regime = "clean"

    def estimate(
        self,
        r_true: float,
        phi_true: float,
        rng: random.Random,
        source_name: str = "",
    ) -> EstimatorResult:
        return EstimatorResult(
            r_hat=self._clip(r_true),
            phi_hat=self._clip(phi_true),
        )


# ---------------------------------------------------------------------------
# Noisy — Gaussian estimation noise (realistic misspecification)
# ---------------------------------------------------------------------------

class NoisyEstimator(ReliabilityEstimator):
    """r_hat = clip(r_true + N(0, sigma), 0, 1).

    Models imperfect reliability measurement: SIEM health scores,
    vendor SLAs that don't match observed behaviour, or sampling noise.

    Parameters
    ----------
    sigma : float
        Standard deviation of estimation noise. Key values from reviewer:
        - 0.0 → degenerates to CleanEstimator
        - 0.10 → mild noise (realistic)
        - 0.25 → severe noise
        - 0.50 → extreme / near-random
    same_rng_for_r_and_phi : bool
        If True, same rng draw used for both r and phi (correlated).
        If False (default), independent draws (uncorrelated).
    """

    regime = "noisy"

    def __init__(
        self,
        sigma: float = 0.10,
        same_rng_for_r_and_phi: bool = False,
    ) -> None:
        assert sigma >= 0.0, f"sigma must be >= 0, got {sigma}"
        self.sigma = sigma
        self.same_rng = same_rng_for_r_and_phi

    def estimate(
        self,
        r_true: float,
        phi_true: float,
        rng: random.Random,
        source_name: str = "",
    ) -> EstimatorResult:
        if self.sigma == 0.0:
            return EstimatorResult(
                r_hat=self._clip(r_true),
                phi_hat=self._clip(phi_true),
            )

        noise_r = rng.gauss(0, self.sigma)
        noise_phi = noise_r if self.same_rng else rng.gauss(0, self.sigma)

        return EstimatorResult(
            r_hat=self._clip(r_true + noise_r),
            phi_hat=self._clip(phi_true + noise_phi),
        )

    def __repr__(self) -> str:
        return f"NoisyEstimator(sigma={self.sigma})"


# ---------------------------------------------------------------------------
# Miscalibrated — systematic over/under estimation
# ---------------------------------------------------------------------------

class MiscalibratedEstimator(ReliabilityEstimator):
    """r_hat = clip(scale * r_true + bias, 0, 1).

    Models systematic estimation error — e.g., an analyst team that
    consistently over-trusts vendor reliability claims, or a SIEM that
    systematically under-reports errors.

    Also models the explicit misspecification scenarios from the reviewer:
        true φ=0.7, estimated φ=0.2  → bias=-0.5 on phi
        true φ=0.7, estimated φ=0.9  → bias=+0.2 on phi

    Parameters
    ----------
    r_scale : float    Multiplicative factor for r_true
    r_bias  : float    Additive bias for r_true
    phi_scale : float  Multiplicative factor for phi_true
    phi_bias  : float  Additive bias for phi_true
    """

    regime = "miscalibrated"

    def __init__(
        self,
        r_scale: float = 1.0,
        r_bias: float = 0.0,
        phi_scale: float = 1.0,
        phi_bias: float = 0.0,
    ) -> None:
        self.r_scale = r_scale
        self.r_bias = r_bias
        self.phi_scale = phi_scale
        self.phi_bias = phi_bias

    def estimate(
        self,
        r_true: float,
        phi_true: float,
        rng: random.Random,
        source_name: str = "",
    ) -> EstimatorResult:
        return EstimatorResult(
            r_hat=self._clip(self.r_scale * r_true + self.r_bias),
            phi_hat=self._clip(self.phi_scale * phi_true + self.phi_bias),
        )

    @classmethod
    def phi_underestimate(cls, target_phi: float = 0.7, estimated_phi: float = 0.2):
        """Factory: systematic phi underestimation (attacker looks 'safe').

        Example: true φ=0.7, estimated φ=0.2
        phi_bias = estimated_phi - phi_scale * target_phi
        """
        scale = estimated_phi / target_phi if target_phi > 0 else 0.0
        return cls(phi_scale=scale, phi_bias=0.0)

    @classmethod
    def phi_overestimate(cls, target_phi: float = 0.7, estimated_phi: float = 0.9):
        """Factory: systematic phi overestimation (over-cautious assessment)."""
        scale = estimated_phi / target_phi if target_phi > 0 else 0.0
        return cls(phi_scale=scale, phi_bias=0.0)

    def __repr__(self) -> str:
        return (f"MiscalibratedEstimator("
                f"r_scale={self.r_scale}, r_bias={self.r_bias}, "
                f"phi_scale={self.phi_scale}, phi_bias={self.phi_bias})")


# ---------------------------------------------------------------------------
# Adversarial — attacker forges reliability signals to appear trustworthy
# ---------------------------------------------------------------------------

class AdversarialEstimator(ReliabilityEstimator):
    """Attacker inflates r_hat and deflates phi_hat for manipulated sources.

    Models: attacker controls the reliability telemetry feed itself —
    the SIEM health dashboard, SLA reporting, or observability tools.
    By spoofing these, the attacker makes compromised sources look reliable.

    Targeting: applies deception to sources with phi_true >= phi_threshold.
    Other sources are estimated cleanly (no benefit to the attacker).

    Effect:
        r_hat  → inflated toward r_inflate (makes source look reliable)
        phi_hat → deflated toward phi_deflate (hides manipulation risk)

    Parameters
    ----------
    phi_threshold : float
        Sources with phi_true >= this value are deception targets.
    r_inflate : float
        r_hat is moved toward this value for targeted sources.
    phi_deflate : float
        phi_hat is moved toward this value for targeted sources.
    blend : float
        Interpolation weight in [0,1] for the adversarial target:
        r_hat = (1-blend)*r_true + blend*r_inflate
    """

    regime = "adversarial"

    def __init__(
        self,
        phi_threshold: float = 0.50,
        r_inflate: float = 0.90,
        phi_deflate: float = 0.05,
        blend: float = 0.80,
    ) -> None:
        assert 0.0 <= phi_threshold <= 1.0
        assert 0.0 <= blend <= 1.0
        self.phi_threshold = phi_threshold
        self.r_inflate = r_inflate
        self.phi_deflate = phi_deflate
        self.blend = blend

    def estimate(
        self,
        r_true: float,
        phi_true: float,
        rng: random.Random,
        source_name: str = "",
    ) -> EstimatorResult:
        if phi_true >= self.phi_threshold:
            # Attacker spoofs: high-phi source looks reliable and safe
            r_hat = self._clip(
                (1.0 - self.blend) * r_true + self.blend * self.r_inflate
            )
            phi_hat = self._clip(
                (1.0 - self.blend) * phi_true + self.blend * self.phi_deflate
            )
        else:
            # Clean source: no deception needed
            r_hat = self._clip(r_true)
            phi_hat = self._clip(phi_true)

        return EstimatorResult(r_hat=r_hat, phi_hat=phi_hat)

    def __repr__(self) -> str:
        return (f"AdversarialEstimator(phi_threshold={self.phi_threshold}, "
                f"r_inflate={self.r_inflate}, phi_deflate={self.phi_deflate}, "
                f"blend={self.blend})")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ESTIMATOR_REGISTRY: Dict[str, type] = {
    "clean":         CleanEstimator,
    "noisy":         NoisyEstimator,
    "miscalibrated": MiscalibratedEstimator,
    "adversarial":   AdversarialEstimator,
}
