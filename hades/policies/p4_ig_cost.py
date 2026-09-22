"""P4 -- Cost-aware IG policy (EIG / cost).

Rule: argmax EIG(source) / Cost(source) over available sources.

EIG/cost normalises information gain against acquisition latency so that
a cheap-but-nearly-as-informative source is preferred over an expensive
marginally-more-informative one.  Zero-cost guard: if cost <= 0 the
source is treated as cost 1e-6 to avoid division by zero but flagged.

Citation: Settles, B. (2008). Active learning with real annotation costs.
          NIPS 2008 Workshop on Cost-Sensitive Learning.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from hades.belief.likelihood import LikelihoodTable, make_default_table
from hades.belief.value import eig
from hades.policies.base import InvestigationState, Policy, _argmax_tiebreak
from hades.query_menu import QuerySpec

_MIN_COST = 1e-6  # guard against zero-division


class IGCostPolicy(Policy):
    """P4: argmax EIG(source) / Cost(source)."""

    name = "ig_cost"

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
            scores[src_name] = ig_val / cost

        return _argmax_tiebreak(scores)
