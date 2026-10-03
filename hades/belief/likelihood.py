"""
hades/belief/likelihood.py
---------------------------
Contaminated observation likelihood model for HADES v3.0.

Replaces the heuristic expected_ig mechanism in hades/simulator/environment.py.

Design
~~~~~~
The key insight: manipulation risk is NOT a separate penalty term (old mu).
Instead, it modulates the observation likelihood directly:

    p(e | H, q, r_hat, phi_hat) =
        r_hat   * p_nominal(e | H, q)          # reliable signal
      + (1-r_hat) * p_noise(e)                  # noise (source unreliable)
      [+ phi_hat * p_forged(e | H_wrong)]       # adversarial injection (Stage B/C)

When r_hat=1 and phi_hat=0: pure nominal likelihood (clean regime R0).
When r_hat<1: observation is attenuated by unreliability.
When phi_hat>0 under targeted attack: adversary injects observations supporting
the wrong hypothesis.

This resolves the v0 double-counting defect where reliability was baked into
expected_ig() *and* multiplied again in expected_reliable_ig().

References
~~~~~~~~~~
* Settles et al. (2008) — uncertainty sampling with cost (P4b)
* Naghshvar & Javidi (2013) — active sequential hypothesis testing (P3)
* HADES threat model: docs/threat_model.md (R0-R4)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Observation classes (must match hades/simulator/observations.py)
# ---------------------------------------------------------------------------
OBS_CLASSES = [
    "strong_support",
    "weak_support",
    "neutral",
    "weak_contra",
    "strong_contra",
]

# Default uniform noise distribution (used when source is unreliable)
_UNIFORM_NOISE: Dict[str, float] = {c: 1.0 / len(OBS_CLASSES) for c in OBS_CLASSES}

# Default forged distribution: observations look like contradictions
_FORGED_CONTRA: Dict[str, float] = {
    "strong_support": 0.03,
    "weak_support":   0.07,
    "neutral":        0.10,
    "weak_contra":    0.30,
    "strong_contra":  0.50,
}


# ---------------------------------------------------------------------------
# LikelihoodTable
# ---------------------------------------------------------------------------

@dataclass
class LikelihoodTable:
    """
    Stores P(obs_class | hypothesis, source) for all (source, hyp, obs_class) triples.

    Invariant: for each (source, hyp), probabilities over obs_classes sum to 1.0.

    p_obs[(source, hyp, obs_class)] -> float in [0, 1]
    """
    p_obs: Dict[Tuple[str, str, str], float] = field(default_factory=dict)

    def get(self, source: str, hyp: str, obs_class: str) -> float:
        """Return P(obs_class | hyp, source). Raises KeyError if unknown."""
        key = (source, hyp, obs_class)
        if key not in self.p_obs:
            raise KeyError(
                f"No likelihood entry for (source={source!r}, hyp={hyp!r}, "
                f"obs_class={obs_class!r}). Available sources: "
                f"{sorted({k[0] for k in self.p_obs})}"
            )
        return self.p_obs[key]

    def validate(self) -> None:
        """Assert all (source, hyp) slices sum to 1.0 within tolerance."""
        from collections import defaultdict
        sums: Dict[Tuple[str, str], float] = defaultdict(float)
        for (src, hyp, _obs), p in self.p_obs.items():
            sums[(src, hyp)] += p
        for (src, hyp), s in sums.items():
            if abs(s - 1.0) > 1e-6:
                raise ValueError(
                    f"Likelihood for (source={src!r}, hyp={hyp!r}) sums to "
                    f"{s:.8f} (expected 1.0)"
                )

    def as_matrix(self, source: str) -> Dict[str, Dict[str, float]]:
        """
        Return P(obs | H, source) as a nested dict:
            result[hyp][obs_class] = probability
        """
        result: Dict[str, Dict[str, float]] = {}
        for (src, hyp, obs_class), p in self.p_obs.items():
            if src == source:
                if hyp not in result:
                    result[hyp] = {}
                result[hyp][obs_class] = p
        return result


# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------

def nominal_likelihood(
    relevance: float,
    obs_class: str,
    positive_probs: Optional[Dict[str, float]] = None,
    negative_probs: Optional[Dict[str, float]] = None,
) -> float:
    """
    Return P_nominal(obs_class | H, source) for a source with given relevance.

    relevance in [0, 1]: how informative this source is for this hypothesis.
      * relevance >= 0.5: hypothesis is "supported" by this source.
        Use positive_probs (strong_support has high weight).
      * relevance < 0.5: hypothesis is "contradicted" by this source.
        Use negative_probs (strong_contra has high weight).

    Defaults are calibrated to the HADES observation model in
    hades/simulator/observations.py (DEFAULT_OBS_MODEL).
    """
    if positive_probs is None:
        positive_probs = {
            "strong_support": 0.45,
            "weak_support":   0.35,
            "neutral":        0.15,
            "weak_contra":    0.04,
            "strong_contra":  0.01,
        }
    if negative_probs is None:
        negative_probs = {
            "strong_support": 0.03,
            "weak_support":   0.07,
            "neutral":        0.10,
            "weak_contra":    0.30,
            "strong_contra":  0.50,
        }

    if obs_class not in OBS_CLASSES:
        raise KeyError(f"Unknown obs_class {obs_class!r}")

    if relevance >= 0.5:
        return positive_probs[obs_class]
    else:
        return negative_probs[obs_class]


def contaminated_likelihood(
    obs_class: str,
    hyp: str,
    source_relevance: float,
    r_hat: float,
    phi_hat: float,
    *,
    under_targeted_attack: bool = False,
    positive_probs: Optional[Dict[str, float]] = None,
    negative_probs: Optional[Dict[str, float]] = None,
    noise_dist: Optional[Dict[str, float]] = None,
    forged_dist: Optional[Dict[str, float]] = None,
) -> float:
    """
    Contaminated likelihood for HADES v3.0:

        clean (phi-unaware, or phi_hat = 0):
            p(e | H, q, r_hat) = r_hat * p_nominal(e | H, q) + (1 - r_hat) * p_noise(e)

        phi-aware (under_targeted_attack=True and phi_hat > 0):
            p(e | H, q, r_hat, phi_hat) =
                (1 - phi_hat) * [ r_hat * p_nominal + (1 - r_hat) * p_noise ]
              +      phi_hat  * p_forged(e)

    Both forms are proper distributions over OBS_CLASSES (sum to 1).

    Phase 7C notes
    --------------
    * `under_targeted_attack` selects whether the caller MODELS manipulation.
      Baselines (P3/P4/P4b/P7) and the evaluator's belief update pass False,
      so their behaviour is unchanged. P5 passes `phi_hat > 0` — a decision
      derived only from the policy-visible estimate, never from ground truth.
    * Pre-7C, the phi branch was `result + phi_hat * p_forged` (unnormalized,
      sum = 1 + phi_hat). EIG computed from it was biased and clamped to 0 at
      high phi_hat. Replaced by the mixture above. See docs/phase7c_phi_dataflow.md.

    Parameters
    ----------
    obs_class : str
        The observed class to compute likelihood for.
    hyp : str
        Hypothesis being evaluated (used only for relevance lookup by caller).
    source_relevance : float
        Affinity of this source to this hypothesis in [0,1].
    r_hat : float
        Policy-visible reliability estimate in [0,1].
    phi_hat : float
        Policy-visible manipulation risk estimate in [0,1].
    under_targeted_attack : bool
        If True, include the forged-evidence mixture component weighted by phi_hat.
    """
    assert 0.0 <= r_hat <= 1.0, f"r_hat={r_hat} out of [0,1]"
    assert 0.0 <= phi_hat <= 1.0, f"phi_hat={phi_hat} out of [0,1]"

    noise = noise_dist or _UNIFORM_NOISE
    forged = forged_dist or _FORGED_CONTRA

    p_nom = nominal_likelihood(source_relevance, obs_class, positive_probs, negative_probs)
    p_noi = noise.get(obs_class, 0.0)

    result = r_hat * p_nom + (1.0 - r_hat) * p_noi

    if under_targeted_attack and phi_hat > 0.0:
        p_for = forged.get(obs_class, 0.0)
        result = (1.0 - phi_hat) * result + phi_hat * p_for

    return max(1e-12, result)



def make_default_table(
    sources: Iterable[str],
    hypotheses: Iterable[str],
    relevance: Dict[Tuple[str, str], float],
) -> LikelihoodTable:
    """
    Build a LikelihoodTable from a relevance matrix.

    Parameters
    ----------
    sources : Iterable[str]
        Evidence source names.
    hypotheses : Iterable[str]
        Hypothesis IDs.
    relevance : Dict[(source, hyp), float]
        Relevance matrix. Values in [0, 1]. Missing entries default to 0.0.

    Returns
    -------
    LikelihoodTable with nominal (r_hat=1, phi_hat=0) likelihoods.
    """
    sources = list(sources)
    hypotheses = list(hypotheses)
    table = LikelihoodTable()

    for src in sources:
        for hyp in hypotheses:
            rel = relevance.get((src, hyp), 0.0)
            row_sum = 0.0
            row: Dict[str, float] = {}
            for obs_class in OBS_CLASSES:
                p = nominal_likelihood(rel, obs_class)
                row[obs_class] = p
                row_sum += p
            # Normalize row to sum exactly to 1.0
            for obs_class in OBS_CLASSES:
                table.p_obs[(src, hyp, obs_class)] = row[obs_class] / row_sum

    table.validate()
    return table
