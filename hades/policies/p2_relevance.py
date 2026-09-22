"""P2 -- Relevance-driven baseline (static adaptive).

Rule: argmax over available sources of relevance[leading_hyp][source].
Cooldown: once a source is queried, skip it for the rest of the episode
(handled naturally by harness; policy just re-scores remaining menu).

This is a simple static adaptive baseline -- it adapts to the current
leading hypothesis but uses no information-theoretic optimisation.

Citation: Expert relevance matrix in hades/belief/relevance.py.
          Based on ATT&CK/Sigma source provenance (see relevance.py).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from hades.belief.relevance import RELEVANCE
from hades.policies.base import InvestigationState, Policy, _argmax_tiebreak
from hades.query_menu import QuerySpec


class RelevancePolicy(Policy):
    """P2: argmax relevance[leading_hyp][source].

    Falls back to uniform scoring when leading_hyp is unknown or not in
    the relevance matrix, so the policy always returns a valid choice.
    """

    name = "relevance"

    def select_query(
        self,
        state: InvestigationState,
        menu: Dict[str, QuerySpec],
        likelihood_table: Any = None,
        estimators: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        available = self._available(state, menu)
        if not available:
            return None
        if state.remaining_budget <= 0:
            return None

        leading = state.leading_hyp or ""

        scores: Dict[str, float] = {}
        for src_name in available:
            key = (leading, src_name)
            scores[src_name] = RELEVANCE.get(key, 0.5)  # default mid-relevance

        return _argmax_tiebreak(scores)
