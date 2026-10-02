"""hades/evaluation/metrics.py — Episode-level metric extraction (Phase 6).

Primary metric
--------------
TPM — Final posterior mass on the true hypothesis: P(H_true | E_1:T).

Secondary metrics
-----------------
- correct_hyp : bool, argmax(final_beliefs) == true_hypothesis
- posterior_quality_gap : P5.tpm − P3.tpm (computed downstream)
- manip_reliance : high_phi_queries / n_queries
- total_cost : sum of query costs
- flip_rate : first-query differs from reference policy (behavioral diagnostic)

All metrics are computed per-episode and stored as flat dicts for paired
statistical analysis. The inferential unit is the episode, not the turn.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class EpisodeMetrics:
    """Flat metric record for one episode."""
    # Identity
    policy: str
    scenario: str
    corruption_regime: str
    estimator_regime: str
    lam: float
    seed: int
    true_hypothesis: str

    # Primary
    tpm: float  # P(H_true | E_1:T)

    # Secondary
    correct_hyp: bool
    max_belief: float
    leading_hyp: str
    n_queries: int
    manip_reliance: float
    total_cost: float
    high_phi_queries: int

    # Integrity
    beliefs_sum_to_one: bool = True
    budget_consistent: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)


def extract_tpm(final_beliefs: Dict[str, float], true_hypothesis: str) -> float:
    """Extract TPM (True Posterior Mass) from final beliefs.

    TPM = P(H_true | E_1:T), the posterior probability assigned to the
    true hypothesis at the end of the episode.

    Returns 0.0 if true_hypothesis not found in beliefs.
    """
    return final_beliefs.get(true_hypothesis, 0.0)


def extract_metrics(
    result,  # EpisodeResult from integration runner
    lam: float,
    corruption_regime: str,
    estimator_regime: str,
) -> EpisodeMetrics:
    """Convert an IntegrationRunner EpisodeResult into flat EpisodeMetrics.

    Parameters
    ----------
    result : EpisodeResult
        From hades.integration.runner
    lam : float
        Lambda value used for this episode
    corruption_regime : str
        Corruption regime label
    estimator_regime : str
        Estimator regime label
    """
    tpm = extract_tpm(result.final_beliefs, result.true_hypothesis)

    return EpisodeMetrics(
        policy=result.policy_name,
        scenario=result.scenario_name,
        corruption_regime=corruption_regime,
        estimator_regime=estimator_regime,
        lam=lam,
        seed=result.seed,
        true_hypothesis=result.true_hypothesis,
        tpm=tpm,
        correct_hyp=result.correct_hyp,
        max_belief=result.max_belief,
        leading_hyp=result.leading_hyp,
        n_queries=result.n_queries,
        manip_reliance=result.manip_reliance,
        total_cost=result.total_cost,
        high_phi_queries=result.high_phi_queries,
        beliefs_sum_to_one=result.beliefs_sum_to_one,
        budget_consistent=result.budget_consistent,
    )


def pair_episodes(
    all_metrics: List[EpisodeMetrics],
    policy_a: str = "P5_robust_voi",
    policy_b: str = "P3_ig",
) -> List[Dict]:
    """Create paired (P5, P3) records matched on (scenario, regime, estimator, lam, seed).

    Returns list of dicts with keys: cell_key, tpm_a, tpm_b, tpm_diff,
    correct_a, correct_b, plus all cell-identity fields.
    """
    # Index by (policy, scenario, regime, estimator, lam, seed)
    index: Dict[tuple, EpisodeMetrics] = {}
    for m in all_metrics:
        key = (m.policy, m.scenario, m.corruption_regime,
               m.estimator_regime, m.lam, m.seed)
        index[key] = m

    pairs = []
    # Find all cells where both policies exist
    cells_a = {k[1:] for k in index if k[0] == policy_a}
    cells_b = {k[1:] for k in index if k[0] == policy_b}
    matched = sorted(cells_a & cells_b)

    for cell in matched:
        ma = index[(policy_a,) + cell]
        mb = index[(policy_b,) + cell]
        pairs.append({
            "scenario": cell[0],
            "corruption_regime": cell[1],
            "estimator_regime": cell[2],
            "lam": cell[3],
            "seed": cell[4],
            "tpm_a": ma.tpm,
            "tpm_b": mb.tpm,
            "tpm_diff": ma.tpm - mb.tpm,
            "correct_a": ma.correct_hyp,
            "correct_b": mb.correct_hyp,
            "manip_reliance_a": ma.manip_reliance,
            "manip_reliance_b": mb.manip_reliance,
        })
    return pairs
