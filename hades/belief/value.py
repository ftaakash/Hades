"""
hades/belief/value.py
----------------------
Information-theoretic value functions for HADES v3.0.

Replaces the heuristic expected_ig / expected_reliable_ig / hades_utility
methods in hades/simulator/environment.py.

Key changes from v0
~~~~~~~~~~~~~~~~~~~
* EIG is computed by proper Bayesian expectation over obs_classes, NOT
  by an affinity-boost heuristic.
* Reliability enters via the contaminated likelihood, NOT as a
  post-hoc multiplicative factor (fixes double-counting defect).
* mu is deleted. ManipRisk enters through contaminated_likelihood (phi_hat).
* lam is the only free parameter. Default lam=1.0.

References
~~~~~~~~~~
* Naghshvar & Javidi (2013). Active sequential hypothesis testing.
  Annals of Statistics 41(6). → P3 (EIG)
* Settles et al. (2008). Active learning with real annotation costs.
  NIPS 2008 Workshop. → P4b (EIG/cost + reliability)
* HADES v3.0 objective: docs/REFRAME.md
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional

from hades.belief.likelihood import (
    LikelihoodTable,
    OBS_CLASSES,
    contaminated_likelihood,
)


# ---------------------------------------------------------------------------
# Entropy
# ---------------------------------------------------------------------------

def entropy(beliefs: Dict[str, float]) -> float:
    """
    Shannon entropy H(beliefs) in bits.

    H = -sum_h p(h) * log2(p(h))

    H = 0   iff beliefs are certain (one hypothesis has probability 1).
    H = log2(|H|)  iff beliefs are uniform.
    """
    h = 0.0
    for p in beliefs.values():
        if p > 1e-12:
            h -= p * math.log2(p)
    return h


# ---------------------------------------------------------------------------
# Terminal utility
# ---------------------------------------------------------------------------

def terminal_utility(beliefs: Dict[str, float]) -> float:
    """
    U_terminal: expected utility of making the best terminal decision now.

    v1 implementation: negative entropy (higher = more certain = better).
        U_terminal = -H(beliefs)

    This is a proper strictly concave utility over distributions.
    Frozen at this definition for the paper (see docs/REFRAME.md).

    Alternative (max-belief) is available as terminal_utility_maxbelief()
    for sensitivity analysis only.
    """
    return -entropy(beliefs)


def terminal_utility_maxbelief(beliefs: Dict[str, float]) -> float:
    """Alternative: probability of being correct under greedy decision."""
    return max(beliefs.values()) if beliefs else 0.0


# ---------------------------------------------------------------------------
# Expected Information Gain (proper Bayesian EIG)
# ---------------------------------------------------------------------------

def eig(
    source: str,
    beliefs: Dict[str, float],
    table: LikelihoodTable,
    r_hat: float,
    phi_hat: float,
    *,
    source_relevance: Optional[Dict[str, float]] = None,
    under_targeted_attack: bool = False,
) -> float:
    """
    Expected Information Gain from querying `source` given current beliefs.

    EIG(q) = H(beliefs_now) - E_{e ~ p(e|q)} [H(beliefs_after(e))]

    where:
        p(e | q) = sum_H P(H) * p(e | H, q, r_hat, phi_hat)
        beliefs_after(e) = Bayesian update using obs e

    This is a PROPER Bayesian computation (no affinity-boost heuristic).
    EIG >= 0 always. EIG = 0 iff all observations produce the same posterior.

    Parameters
    ----------
    source : str
        Evidence source to evaluate.
    beliefs : Dict[str, float]
        Current belief distribution (priors), must sum to 1.
    table : LikelihoodTable
        Nominal likelihoods P(obs | H, source).
    r_hat : float
        Policy-visible reliability estimate in [0,1].
    phi_hat : float
        Policy-visible manipulation risk estimate in [0,1].
    source_relevance : Dict[str, float], optional
        {hyp: relevance} for contaminated likelihood computation.
        If None, uses table.p_obs (nominal only).
    under_targeted_attack : bool
        Whether attacker targets this source.

    Returns
    -------
    float: EIG in bits, >= 0.
    """
    h_before = entropy(beliefs)

    # For each possible observation class, compute:
    #   p_obs(e) = marginal = sum_H P(H) * P(e | H, q)
    #   beliefs_after(e) = posterior after observing e
    #   H(beliefs_after(e))
    expected_h_after = 0.0

    for obs_class in OBS_CLASSES:
        # Compute unnormalized posterior weights for this obs
        unnorm: Dict[str, float] = {}
        for hyp, prior in beliefs.items():
            if source_relevance is not None:
                rel = source_relevance.get(hyp, 0.0)
                lik = contaminated_likelihood(
                    obs_class=obs_class,
                    hyp=hyp,
                    source_relevance=rel,
                    r_hat=r_hat,
                    phi_hat=phi_hat,
                    under_targeted_attack=under_targeted_attack,
                )
            else:
                lik = table.get(source, hyp, obs_class)
            unnorm[hyp] = prior * lik

        # Marginal probability of this observation
        p_obs_e = sum(unnorm.values())
        if p_obs_e < 1e-12:
            continue  # Observation is impossible; skip

        # Normalize to get posterior
        posterior = {h: v / p_obs_e for h, v in unnorm.items()}
        h_after = entropy(posterior)

        expected_h_after += p_obs_e * h_after

    return max(0.0, h_before - expected_h_after)


# ---------------------------------------------------------------------------
# Value of Information (VoI) — the HADES v3.0 objective
# ---------------------------------------------------------------------------

def voi(
    source: str,
    beliefs: Dict[str, float],
    table: LikelihoodTable,
    cost: float,
    lam: float,
    r_hat: float,
    phi_hat: float,
    *,
    source_relevance: Optional[Dict[str, float]] = None,
    under_targeted_attack: bool = False,
) -> float:
    """
    Value of Information: V(q) = EIG(q) - lam * Cost(q).

    This is the HADES v3.0 policy objective (replaces old hades_utility).

    Notes
    -----
    * mu is DELETED. Manipulation risk enters via contaminated_likelihood.
    * lam is the single free parameter (budget-normalized). Default 1.0.
    * At phi_hat=0, r_hat=1: reduces to pure EIG/cost (P4 regime).
    * At phi_hat>0: EIG is degraded by attacker injection; policy
      automatically prefers less-forgeable sources.

    Parameters
    ----------
    source : str
    beliefs : Dict[str, float]
    table : LikelihoodTable
    cost : float         Source query cost in budget units.
    lam : float          Budget penalty weight. Default 1.0.
    r_hat : float        Policy-visible reliability estimate.
    phi_hat : float      Policy-visible manipulation risk estimate.
    """
    assert cost > 0, f"cost must be > 0, got {cost}"
    assert lam >= 0, f"lam must be >= 0, got {lam}"

    expected_ig = eig(
        source=source,
        beliefs=beliefs,
        table=table,
        r_hat=r_hat,
        phi_hat=phi_hat,
        source_relevance=source_relevance,
        under_targeted_attack=under_targeted_attack,
    )
    return expected_ig - lam * cost


def robust_voi(
    source: str,
    beliefs: Dict[str, float],
    table: LikelihoodTable,
    cost: float,
    lam: float,
    phi_budget: float,
    r_hat: float,
    phi_hat_candidates: Optional[List[float]] = None,
    *,
    source_relevance: Optional[Dict[str, float]] = None,
) -> float:
    """
    Robust VoI (minimax): max_q min_{phi in Phi_budget} V(q; phi).

    Stage C only: evaluates V(q) at multiple phi values and returns the
    worst-case (min) over the attacker's phi budget.

    Parameters
    ----------
    phi_budget : float
        Maximum phi_hat the attacker can apply. Discretized into candidates.
    phi_hat_candidates : List[float], optional
        Explicit phi values to sweep. Defaults to [0, phi_budget/2, phi_budget].
    """
    if phi_hat_candidates is None:
        phi_hat_candidates = [0.0, phi_budget / 2.0, phi_budget]
    phi_hat_candidates = [max(0.0, min(1.0, p)) for p in phi_hat_candidates]

    worst_case_voi = float("inf")
    for phi in phi_hat_candidates:
        v = voi(
            source=source,
            beliefs=beliefs,
            table=table,
            cost=cost,
            lam=lam,
            r_hat=r_hat,
            phi_hat=phi,
            source_relevance=source_relevance,
            under_targeted_attack=(phi > 0.0),
        )
        if v < worst_case_voi:
            worst_case_voi = v

    return worst_case_voi if worst_case_voi != float("inf") else 0.0
