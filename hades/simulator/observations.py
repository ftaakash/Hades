"""
hades/simulator/observations.py
--------------------------------
Observation model for the synthetic simulator.

Each evidence source has a *likelihood matrix*:
    P(observation_class | true_hypothesis)

An observation_class is one of:
  - "strong_support"   → raises posterior of true hypothesis significantly
  - "weak_support"     → raises posterior slightly
  - "neutral"          → no discrimination
  - "misleading"       → raises wrong hypothesis

Reliability attenuates the signal: a low-reliability source returns
"neutral" more often than its nominal likelihood would predict.

Manipulation risk is modelled here too — under an adversarial corruption
regime the observation is first drawn from the nominal likelihood, then
optionally replaced by a "misleading" outcome with probability
= manipulation_risk_true (for targeted attacks).

These two values (reliability, manipulation_risk) are conceptually and
numerically independent, as required by the merged research plan.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Observation classes and their posterior-update weights.
# weight > 1 → supports; weight = 1 → neutral; weight < 1 → weakens
OBS_CLASSES: Dict[str, float] = {
    "strong_support":    6.0,
    "weak_support":      2.0,
    "neutral":           1.0,
    "weak_contra":       0.5,
    "strong_contra":     0.2,
}


@dataclass(frozen=True)
class ObservationModel:
    """
    Likelihood of each observation class given the true hypothesis matches
    the evidence source's domain (positive case) vs. does not (negative case).

    positive_probs: distribution over OBS_CLASSES when source IS relevant
                    to the true hypothesis.
    negative_probs: distribution when source is NOT relevant.

    Both must sum to 1.
    """
    name: str
    positive_probs: Dict[str, float]   # P(obs_class | relevant hypothesis)
    negative_probs: Dict[str, float]   # P(obs_class | irrelevant hypothesis)

    def __post_init__(self) -> None:
        for d, label in [(self.positive_probs, "positive"), (self.negative_probs, "negative")]:
            s = sum(d.values())
            if abs(s - 1.0) > 1e-6:
                raise ValueError(f"{self.name} {label}_probs must sum to 1 (got {s})")
            for k in d:
                if k not in OBS_CLASSES:
                    raise ValueError(f"Unknown obs class {k!r} in {self.name}")

    def sample(
        self,
        rng: random.Random,
        *,
        is_relevant: bool,
        reliability_true: float,
        manipulation_risk_true: float,
        under_targeted_attack: bool = False,
    ) -> str:
        """
        Draw one observation class.

        1. Nominal draw from positive/negative probs.
        2. Reliability degradation: with prob (1-reliability_true) → override to "neutral".
        3. Targeted attack: with prob manipulation_risk_true → override to "misleading" class
           (only if under_targeted_attack=True, i.e., this source is being actively forged).

        Note: reliability and manipulation_risk are INDEPENDENT parameters.
        A source can be reliable-but-forgeable or unreliable-but-tamper-proof.
        """
        probs = self.positive_probs if is_relevant else self.negative_probs
        classes = list(probs.keys())
        weights = [probs[c] for c in classes]
        obs_class = rng.choices(classes, weights=weights, k=1)[0]

        # Reliability degradation — attenuates signal toward neutral
        if rng.random() > reliability_true:
            obs_class = "neutral"

        # Targeted manipulation — independently replaces with misleading signal
        if under_targeted_attack and rng.random() < manipulation_risk_true:
            obs_class = "strong_contra"  # attacker steers us to wrong hypothesis

        return obs_class

    def likelihood(self, obs_class: str, *, is_relevant: bool) -> float:
        """
        Return P(obs_class | is_relevant) from the nominal (pre-corruption) model.

        This is the accessor required by hades/belief/* for computing EIG
        and contaminated likelihood tables without sampling.

        Parameters
        ----------
        obs_class : str
            One of the keys in OBS_CLASSES.
        is_relevant : bool
            True if the source is relevant to the hypothesis being evaluated.
        """
        probs = self.positive_probs if is_relevant else self.negative_probs
        return probs.get(obs_class, 0.0)

    def as_matrix(self) -> Dict[str, Dict[str, float]]:
        """
        Return the full likelihood matrix as a nested dict:
            result["positive"][obs_class] = P(obs_class | relevant)
            result["negative"][obs_class] = P(obs_class | not relevant)
        """
        return {
            "positive": dict(self.positive_probs),
            "negative": dict(self.negative_probs),
        }


# ---------------------------------------------------------------------------
# Default observation model used across all simulator scenarios
# ---------------------------------------------------------------------------
DEFAULT_OBS_MODEL = ObservationModel(
    name="default",
    positive_probs={
        "strong_support": 0.45,
        "weak_support":   0.30,
        "neutral":        0.15,
        "weak_contra":    0.07,
        "strong_contra":  0.03,
    },
    negative_probs={
        "strong_support": 0.03,
        "weak_support":   0.07,
        "neutral":        0.25,
        "weak_contra":    0.35,
        "strong_contra":  0.30,
    },
)
