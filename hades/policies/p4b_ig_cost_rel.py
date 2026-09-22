"""P4b -- EIG with reliability-weighted cost (Settles et al. 2008 ablation).

Rule: argmax EIG(source, r_hat-likelihood) / Cost(source).

This is the ablation variant that explicitly weights EIG by source
reliability before dividing by cost.  In v3.0 the EIG already
incorporates r_hat via the contaminated likelihood, so this policy is
functionally a sensitivity control that inflates the cost divisor by the
unreliability factor (1 - r_hat), making unreliable sources appear more
expensive.

Effective score: EIG(source) / (Cost * (2 - r_hat))
  -> At r_hat=1.0 (perfect reliability): score = EIG / Cost  (same as P4)
  -> At r_hat=0.5: score = EIG / (1.5 * Cost)               (penalised)

Citation: Settles, B., Craven, M., & Friedland, L. (2008).
          Active learning with real annotation costs.
          NIPS 2008 Workshop on Cost-Sensitive Learning. §3.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from hades.belief.likelihood import LikelihoodTable, make_default_table
from hades.belief.value import eig
from hades.policies.base import InvestigationState, Policy, _argmax_tiebreak
from hades.query_menu import QuerySpec

_MIN_COST = 1e-6


class IGCostRelPolicy(Policy):
    """P4b: argmax EIG / (Cost * (2 - r_hat)).

    Reliability penalty inflates effective cost for unreliable sources,
    making them less attractive without adding μ back.
    """

    name = "ig_cost_rel"

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

        scores: Dict[str, float] = {}
        for src_name, spec in available.items():
            r_hat = getattr(spec, "reliability_estimated", 1.0)
            phi_hat = getattr(spec, "manipulation_risk_estimated", 0.0)
            cost = max(getattr(spec, "cost", 1.0), _MIN_COST)
            affinity = getattr(spec, "hypothesis_affinity", {})

            # Effective cost is inflated by unreliability: cost * (2 - r_hat)
            # At r_hat=1: no penalty. At r_hat=0: cost doubled.
            effective_cost = cost * (2.0 - r_hat)

            table = likelihood_table or make_default_table(
                sources=[src_name],
                hypotheses=list(state.beliefs.keys()),
                relevance={(src_name, h): affinity.get(h, 0.5)
                           for h in state.beliefs},
            )

            ig_val = eig(
                source=src_name,
                beliefs=state.beliefs,
                table=table,
                r_hat=r_hat,
                phi_hat=phi_hat,
                source_relevance={h: affinity.get(h, 0.5) for h in state.beliefs},
                under_targeted_attack=False,
            )
            scores[src_name] = ig_val / effective_cost

        return _argmax_tiebreak(scores)
