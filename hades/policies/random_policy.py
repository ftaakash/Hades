"""P0 -- random baseline: pick a source uniformly at random every turn.

This is the lower bound every other policy (P1 fixed heuristic, P2
relevance, P3 information gain, P4 IG/cost, P5 HADES, P6 LLM) has to
beat. If a "smarter" policy doesn't clear this, something is wrong
with it, not with the benchmark.
"""
from __future__ import annotations

import random
from typing import Dict, Optional

from hades.policies.base import InvestigationState, Policy
from hades.query_menu import QuerySpec


class RandomPolicy(Policy):
    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def select_query(
        self, state: InvestigationState, menu: Dict[str, QuerySpec],
        likelihood_table=None, estimators=None,
    ) -> Optional[str]:
        if state.remaining_budget <= 0:
            return None
        affordable = [k for k, v in menu.items()
                      if getattr(v, "cost", 1.0) <= state.remaining_budget]
        if not affordable:
            return None
        return self._rng.choice(affordable)
