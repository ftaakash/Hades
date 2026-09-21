"""
hades/belief/posterior.py
--------------------------
Bayesian belief update for HADES v3.0.

Replaces SimEnv._update_beliefs() (which used weight-inversion heuristics).

Design
~~~~~~
Standard Bayes rule:

    P(H | e, q) propto P(H) * P(e | H, q, r_hat, phi_hat)

where P(e | H, q, r_hat, phi_hat) is the contaminated likelihood from
hades/belief/likelihood.py.

The probability invariant (beliefs sum to 1.0) is validated at every call.
Violations raise RuntimeError loudly — never silently corrected.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from hades.belief.likelihood import LikelihoodTable, contaminated_likelihood


def update(
    beliefs: Dict[str, float],
    obs_class: str,
    source: str,
    table: LikelihoodTable,
    r_hat: float,
    phi_hat: float,
    *,
    source_relevance: Optional[Dict[str, float]] = None,
    under_targeted_attack: bool = False,
) -> Dict[str, float]:
    """
    Bayesian belief update: P(H | e, q) propto P(H) * P(e | H, q).

    Parameters
    ----------
    beliefs : Dict[str, float]
        Current prior beliefs over hypotheses. Must sum to 1.0.
    obs_class : str
        Observed evidence class (e.g., 'strong_support').
    source : str
        Evidence source that produced the observation.
    table : LikelihoodTable
        P(obs | H, source) lookup table (nominal, r_hat=1 likelihoods).
    r_hat : float
        Policy-visible reliability estimate for this source.
    phi_hat : float
        Policy-visible manipulation risk estimate for this source.
    source_relevance : Dict[str, float], optional
        {hyp: relevance} for contaminated likelihood computation.
        If None, uses table.p_obs directly (nominal only).
    under_targeted_attack : bool
        Whether to apply adversarial contamination (phi_hat active).

    Returns
    -------
    Dict[str, float]
        Updated beliefs summing to exactly 1.0.

    Raises
    ------
    RuntimeError
        If beliefs do not sum to 1.0 before or after update.
    """
    _validate_beliefs(beliefs, context="before update")

    new_beliefs: Dict[str, float] = {}
    for hyp, prior in beliefs.items():
        if source_relevance is not None:
            rel = source_relevance.get(hyp, 0.0)
            # Use contaminated likelihood (unnormalized mixing weight)
            lik = contaminated_likelihood(
                obs_class=obs_class,
                hyp=hyp,
                source_relevance=rel,
                r_hat=r_hat,
                phi_hat=phi_hat,
                under_targeted_attack=under_targeted_attack,
            )
        else:
            # Use precomputed table (nominal, clean regime)
            lik = table.get(source, hyp, obs_class)

        new_beliefs[hyp] = prior * lik

    # Normalize
    total = sum(new_beliefs.values())
    if total < 1e-12:
        # All likelihoods collapsed — reset to uniform (degenerate case)
        n = len(beliefs)
        new_beliefs = {h: 1.0 / n for h in beliefs}
    else:
        new_beliefs = {h: v / total for h, v in new_beliefs.items()}

    _validate_beliefs(new_beliefs, context="after update")
    return new_beliefs


def _validate_beliefs(beliefs: Dict[str, float], context: str = "") -> None:
    """Assert beliefs sum to 1.0 and all values are in [0,1]. Fails loudly."""
    s = sum(beliefs.values())
    if abs(s - 1.0) > 1e-4:
        raise RuntimeError(
            f"[posterior.update] Probability invariant violated {context}: "
            f"beliefs sum to {s:.8f}. State={beliefs}"
        )
    for h, p in beliefs.items():
        if not (-1e-9 <= p <= 1.0 + 1e-9):
            raise RuntimeError(
                f"[posterior.update] Belief {h}={p:.8f} out of [0,1] {context}."
            )
