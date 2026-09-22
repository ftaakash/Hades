"""P3 -- Information-Gain policy (proper Bayesian EIG).

Rule: argmax EIG(source) over available sources.

EIG is computed via hades.belief.value.eig() using the contaminated
likelihood model.  Reliability (r_hat) enters through the likelihood,
NOT as a post-hoc multiplier.

Citation: Naghshvar & Javidi (2013). Active sequential hypothesis testing.
          Annals of Statistics 41(6), pp. 2567–2611.
          ECC-AHT (2026). [see docs/literature_matrix.csv]
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from hades.belief.likelihood import LikelihoodTable, make_default_table
from hades.belief.value import eig
from hades.policies.base import InvestigationState, Policy, _argmax_tiebreak
from hades.query_menu import QuerySpec


class IGPolicy(Policy):
    """P3: argmax Expected Information Gain.

    Uses proper Bayesian EIG with contaminated likelihood
    (reliability enters inside the model, not post-hoc).
    Operates in clean regime: under_targeted_attack=False.
    """

    name = "ig"

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
            # No beliefs yet: fall back to first available alphabetically
            return min(available)

        scores: Dict[str, float] = {}
        for src_name, spec in available.items():
            r_hat = getattr(spec, "reliability_estimated", 1.0)
            phi_hat = getattr(spec, "manipulation_risk_estimated", 0.0)
            affinity = getattr(spec, "hypothesis_affinity", {})

            table = likelihood_table or make_default_table(
                sources=[src_name],
                hypotheses=list(state.beliefs.keys()),
                relevance={(src_name, h): affinity.get(h, 0.5)
                           for h in state.beliefs},
            )

            scores[src_name] = eig(
                source=src_name,
                beliefs=state.beliefs,
                table=table,
                r_hat=r_hat,
                phi_hat=phi_hat,
                source_relevance={h: affinity.get(h, 0.5) for h in state.beliefs},
                under_targeted_attack=False,
            )

        return _argmax_tiebreak(scores)
