"""R3 — Misleading / Plausible Decoy corruptor.

Models: adversarially crafted log entries that appear plausible but point
toward the wrong hypothesis. Unlike R1 (silence) and R2 (staleness),
R3 actively injects false signal with hypothesis specificity.

Mechanism: with probability `p_inject`, the true observation is replaced
with a plausible decoy obs_class. The decoy class is chosen to point
AWAY from the true hypothesis:
  - 'signal' is replaced with the obs_class that would be most consistent
    with a hypothesis OTHER than the true one.
  - For simplicity in v3.0: the decoy is always 'weak_signal' at mild
    injection, or 'noise' at severe injection.

This models an attacker who can inject syntactically valid but semantically
misleading log entries into the telemetry stream.

R3 is non-targeted (random selection of decoy hypothesis).
Targeted decoy injection is R4 (targeted.py).

Intensities: p_inject ∈ {0.10, 0.25, 0.50}
"""
from __future__ import annotations

import random
from typing import Optional

from hades.corruption.base import Corruptor, ObsContext, OBS_CLASSES, SUPPORTING, CONTRA

# Decoy replacement: replace true observation with a misleading class.
# Mild injection → weak_contra (slightly misleading)
# Severe injection → strong_contra (maximally misleading)
_DECOY_MILD = "weak_contra"
_DECOY_SEVERE = "strong_contra"
_SEVERE_THRESHOLD = 0.35


class MisleadingCorruptor(Corruptor):
    """R3: Plausible decoy injection — replaces true obs with misleading class.

    Parameters
    ----------
    p_inject : float
        Probability of replacing observation with a decoy. [0, 1].
    """

    regime = "R3_misleading"

    def __init__(self, p_inject: float = 0.25) -> None:
        assert 0.0 <= p_inject <= 1.0, f"p_inject must be in [0,1], got {p_inject}"
        self.p_inject = p_inject

    def corrupt(
        self,
        obs_class: str,
        ctx: ObsContext,
        rng: random.Random,
    ) -> str:
        assert obs_class in OBS_CLASSES, f"Unknown obs_class: {obs_class}"
        if rng.random() >= self.p_inject:
            return obs_class

        # Choose decoy class based on injection severity:
        # Supporting obs get replaced with contra (attacker points away from truth)
        # Neutral obs get mild contra push
        # Contra obs are left alone (counter-evidence stays)
        if obs_class in SUPPORTING:
            decoy = _DECOY_SEVERE if self.p_inject >= _SEVERE_THRESHOLD else _DECOY_MILD
        elif obs_class == "neutral":
            decoy = _DECOY_MILD
        else:
            # Already counter-evidence — no further misleading needed
            return obs_class

        assert decoy in OBS_CLASSES
        return decoy

    def __repr__(self) -> str:
        return f"MisleadingCorruptor(p_inject={self.p_inject})"
