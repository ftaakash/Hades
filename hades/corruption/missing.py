"""R1 — Missing / Dropped Observations corruptor.

Models: telemetry agent outage, log pipeline failure, network partition.

Mechanism: with probability `p_drop` the true observation is replaced
with 'neutral' (uninformative). The source answers, but carries no signal.
This reduces information but does not mislead.

Intensities: {0.10, 0.25, 0.50} — matching the F1 sweep noise levels.

Invariants
----------
- Does not modify ground truth.
- Deterministic given rng state.
- 'neutral' is always a valid obs_class member.
"""
from __future__ import annotations

import random
from typing import Optional

from hades.corruption.base import Corruptor, ObsContext, OBS_CLASSES


class MissingCorruptor(Corruptor):
    """R1: Drop observations with probability p_drop → 'neutral'.

    Parameters
    ----------
    p_drop : float
        Probability of replacing the true observation with 'neutral'.
        Typical values: 0.10 (mild), 0.25 (moderate), 0.50 (severe).
    """

    regime = "R1_missing"

    def __init__(self, p_drop: float = 0.25) -> None:
        assert 0.0 <= p_drop <= 1.0, f"p_drop must be in [0,1], got {p_drop}"
        self.p_drop = p_drop

    def corrupt(
        self,
        obs_class: str,
        ctx: ObsContext,
        rng: random.Random,
    ) -> str:
        assert obs_class in OBS_CLASSES, f"Unknown obs_class: {obs_class}"
        if rng.random() < self.p_drop:
            return "neutral"
        return obs_class

    def __repr__(self) -> str:
        return f"MissingCorruptor(p_drop={self.p_drop})"
