"""P7 -- Bayes Active Learning: Expected Error Reduction (anti-strawman).

Rule: argmax over sources of expected reduction in 0-1 loss (i.e., expected
  improvement in the probability of picking the correct hypothesis).

This is the P7 anti-strawman baseline from Settles (2008) §4, included to
prevent the strawman critique that HADES only needs to beat EIG.  P7 is a
stronger probabilistic baseline than P3/P4.

EER(q) = P(correct now) - E_{e}[ P(correct after observing e from q) ]
       = max_h P(H=h) - E_{e ~ p(e|q)} [ max_h' P(H=h' | e, q) ]

where "P(correct)" is the greedy maximum-belief decision rule.

A positive EER means querying source q is expected to improve the
probability that the leading hypothesis is the true one.  argmax EER is the
Bayesian error-reduction policy.

Citation: Settles, B. (2008). Active learning with real annotation costs.
          NIPS 2008 Workshop. §4: Expected Error Reduction.
          Roy and McCallum (2001). Toward optimal active learning through
          sampling estimation of error reduction. ICML 2001.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from hades.belief.likelihood import LikelihoodTable, OBS_CLASSES, contaminated_likelihood, make_default_table
from hades.policies.base import InvestigationState, Policy, _argmax_tiebreak
from hades.query_menu import QuerySpec


def _p_correct(beliefs: Dict[str, float]) -> float:
    """Probability of being correct under greedy maximum-belief decision."""
    return max(beliefs.values()) if beliefs else 0.0


class BayesALPolicy(Policy):
    """P7: argmax Expected Error Reduction (Bayes Active Learning anti-strawman).

    Selects the query that maximally reduces expected 0-1 loss under the
    current belief distribution.  Stronger than EIG as a comparison baseline.
    """

    name = "bayes_al"

    def select_query(
        self,
        state: InvestigationState,
        menu: Dict[str, QuerySpec],
        likelihood_table: Optional[LikelihoodTable] = None,
        estimators: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        available = self._available(state, menu)
        if not available or state.remaining_budget <= 0:
            return None

        if not state.beliefs:
            return min(available)

        p_correct_now = _p_correct(state.beliefs)

        scores: Dict[str, float] = {}
        for src_name, spec in available.items():
            r_hat = getattr(spec, "reliability_estimated", 1.0)
            phi_hat = getattr(spec, "manipulation_risk_estimated", 0.0)
            affinity = getattr(spec, "hypothesis_affinity", {})

            # Compute expected p_correct after observing each obs_class
            expected_p_correct_after = 0.0

            for obs_class in OBS_CLASSES:
                # Unnormalized posterior
                unnorm: Dict[str, float] = {}
                for hyp, prior in state.beliefs.items():
                    rel = affinity.get(hyp, 0.5)
                    lik = contaminated_likelihood(
                        obs_class=obs_class,
                        hyp=hyp,
                        source_relevance=rel,
                        r_hat=r_hat,
                        phi_hat=phi_hat,
                        under_targeted_attack=False,
                    )
                    unnorm[hyp] = prior * lik

                p_obs_e = sum(unnorm.values())
                if p_obs_e < 1e-12:
                    continue

                posterior = {h: v / p_obs_e for h, v in unnorm.items()}
                expected_p_correct_after += p_obs_e * _p_correct(posterior)

            # EER = improvement in P(correct): positive = beneficial query
            scores[src_name] = p_correct_now - expected_p_correct_after

        return _argmax_tiebreak(scores)
