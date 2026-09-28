"""R2 — Stale / Delayed Observations corruptor.

Models: event log pipeline lag, delayed SIEM ingestion, cached telemetry
returning outdated data rather than the current investigation window.

Mechanism: stale observations skew toward 'neutral' or 'weak_signal' by
blending the true signal toward an older, uninformative distribution.
The intensity is parameterised by staleness lag (no_lag, 1h, 24h).

Staleness model
---------------
At staleness=0.0 (no_lag): observation unchanged.
At staleness=1.0 (24h): observation probabilistically degraded:
  'signal'      → becomes 'weak_signal' with p=staleness,
                  then 'neutral'       with p=staleness²
  'weak_signal' → becomes 'neutral'   with p=staleness
  'neutral'     → unchanged
  'noise'       → unchanged (noise is time-invariant)

This means stale observations drift toward (weakened → neutral) but
still preserve some of the original classification at low staleness.

Intensities: 0.0 (no_lag), 0.33 (~1h), 1.0 (24h)
"""
from __future__ import annotations

import random

from hades.corruption.base import Corruptor, ObsContext, OBS_CLASSES


_DEGRADATION_PATH = {
    "strong_support": ["weak_support", "neutral"],
    "weak_support":   ["neutral"],
    "neutral":        [],
    "weak_contra":    [],
    "strong_contra":  ["weak_contra"],
}


class StaleCorruptor(Corruptor):
    """R2: Stale observations drift signal → weak_signal → neutral.

    Parameters
    ----------
    staleness : float
        Staleness intensity in [0, 1].
        0.0 = no_lag (clean), 0.33 ≈ 1h lag, 1.0 = 24h lag (fully stale).
    """

    regime = "R2_stale"

    def __init__(self, staleness: float = 0.33) -> None:
        assert 0.0 <= staleness <= 1.0, f"staleness must be in [0,1], got {staleness}"
        self.staleness = staleness

    def corrupt(
        self,
        obs_class: str,
        ctx: ObsContext,
        rng: random.Random,
    ) -> str:
        assert obs_class in OBS_CLASSES, f"Unknown obs_class: {obs_class}"
        if self.staleness == 0.0:
            return obs_class

        path = _DEGRADATION_PATH.get(obs_class, [])
        current = obs_class
        prob = self.staleness
        for degraded in path:
            if rng.random() < prob:
                current = degraded
                prob = self.staleness  # each step re-rolls at same intensity
            else:
                break  # stop degrading once a step is survived
        return current

    def __repr__(self) -> str:
        return f"StaleCorruptor(staleness={self.staleness})"
