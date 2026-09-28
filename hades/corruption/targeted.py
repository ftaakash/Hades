"""R4 — Targeted / Adaptive Suppression corruptor.

Models: a sophisticated attacker who observes the analyst's query history
and suppresses/corrupts the evidence source most likely to discriminate
the true hypothesis.

This is the most adversarially powerful regime. Unlike R1-R3 (passive
corruption), R4 actively tracks what the analyst has queried and
targets the source that would help the most.

Targeting strategy
------------------
At each step, the attacker identifies the source with the highest affinity
to the CURRENT LEADING HYPOTHESIS in the policy's belief distribution.
If that source is being queried RIGHT NOW, the attacker degrades its output:

  'strong_support' → 'strong_contra'  (complete reversal — attacker misleads)
  'weak_support'   → 'strong_contra'  (complete reversal)
  'neutral'        → 'strong_contra'  (active misdirection injected)
  'weak_contra'    → 'strong_contra'  (amplified — push harder wrong way)
  'strong_contra'  → 'strong_contra'  (unchanged, already maximally misleading)

Activation condition: the source being queried must be the PREDICTED BEST
source, AND the attacker's capability p_attack must succeed (Bernoulli draw).

This models a threat actor who can selectively forger/suppress the most
informative telemetry channel, consistent with docs/threat_model.md R4.

Note: in clean-regime evaluation, the attacker is never activated
even if p_attack > 0 (controlled by the harness calling corrupt()).
"""
from __future__ import annotations

import random
from typing import Optional

from hades.corruption.base import Corruptor, ObsContext, OBS_CLASSES


class TargetedCorruptor(Corruptor):
    """R4: Adaptive attacker suppresses the analyst's highest-value source.

    Parameters
    ----------
    p_attack : float
        Probability that the attacker successfully corrupts the target source.
        Think of this as the attacker's operational capability.
        Typical: 0.50 (partial capability), 1.0 (full control).
    """

    regime = "R4_targeted"

    def __init__(self, p_attack: float = 0.75) -> None:
        assert 0.0 <= p_attack <= 1.0, f"p_attack must be in [0,1], got {p_attack}"
        self.p_attack = p_attack

    def _find_leading_hyp(self, beliefs: dict) -> str:
        """Return the current leading hypothesis (alphabetical tie-break)."""
        if not beliefs:
            return ""
        return max(beliefs, key=lambda h: (beliefs[h], h))

    def _is_targeted_source(self, ctx: ObsContext) -> bool:
        """Return True if this source is the attacker's target.

        Target = source with the highest affinity to the leading hypothesis.
        If no beliefs are available, no targeting is possible.
        """
        if not ctx.current_beliefs or not ctx.hypothesis_affinity:
            return False

        leading = self._find_leading_hyp(ctx.current_beliefs)
        if not leading:
            return False

        # Find source with max affinity to leading hypothesis
        # (In a real scenario the attacker knows all sources; here we use
        #  the context's own affinity to decide if this source is the target)
        target_affinity = ctx.hypothesis_affinity.get(leading, 0.0)

        # Is this source the most-informative one for the leading hyp?
        # We compare against a 0.6 threshold: affinity >= 0.6 → targeted
        return target_affinity >= 0.60

    def corrupt(
        self,
        obs_class: str,
        ctx: ObsContext,
        rng: random.Random,
    ) -> str:
        assert obs_class in OBS_CLASSES, f"Unknown obs_class: {obs_class}"

        # Only attack if this is the high-value source AND capacity permits
        if self._is_targeted_source(ctx) and rng.random() < self.p_attack:
            # Full suppression: replace with strong_contra (maximally misleading)
            # This models attacker who forges evidence pointing firmly away from
            # the true hypothesis while appearing as valid counter-evidence.
            return "strong_contra"

        return obs_class

    def __repr__(self) -> str:
        return f"TargetedCorruptor(p_attack={self.p_attack})"
