"""Policy interface every HADES acquisition policy implements (v3.0).

A policy sees the current investigation state (which evidence sources
have already been queried, what came back, remaining budget, current
Bayesian beliefs) and picks the name of the next evidence source to
query from the fixed `query_menu.QUERY_MENU` -- or returns `None` to
stop. This is the plugin surface: dropping a new file in
`hades/policies/` that subclasses `Policy` makes that policy comparable
to every other one across every regime via the harness, with no other
code changes.

v3.0 changes
~~~~~~~~~~~~
* InvestigationState gains `beliefs` (Bayesian posterior), `leading_hyp`,
  and `remaining_budget` typed as float (was int).
* Policy.select_query signature extended to accept `likelihood_table` and
  `estimators` for P3-P5.
* Deterministic tie-break: alphabetical max on (score, name).
  All policies MUST use `_argmax_tiebreak()` for reproducibility.
* Policies read ONLY `*_estimated` fields.  `*_true` is evaluator-only.
  `TestLeakage` enforces this.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from hades.query_menu import QuerySpec


# ---------------------------------------------------------------------------
# Investigation state (policy-visible view of the episode)
# ---------------------------------------------------------------------------

@dataclass
class QueryRecord:
    """One completed query: what we asked, what came back."""
    source: str
    sql: str
    observation: str
    n_candidates_found: int


@dataclass
class InvestigationState:
    """Everything a policy is allowed to see when choosing its next action.

    Policies must treat this as read-only; the harness owns mutation.

    v3.0 fields
    -----------
    beliefs         : current Bayesian posterior over hypotheses (sum==1)
    leading_hyp     : argmax belief (alphabetical tie-break)
    remaining_budget: budget left in cost units (float to allow fractional costs)
    """
    queried_sources: List[str] = field(default_factory=list)
    history: List[QueryRecord] = field(default_factory=list)
    remaining_budget: float = 0
    candidate_timestamps: Set[str] = field(default_factory=set)
    # v3.0 Bayesian state
    beliefs: Dict[str, float] = field(default_factory=dict)
    leading_hyp: str = ""


# ---------------------------------------------------------------------------
# Tie-break utility (shared by all policies)
# ---------------------------------------------------------------------------

def _argmax_tiebreak(scores: Dict[str, float]) -> Optional[str]:
    """
    Return the key with the highest score.

    Deterministic tie-break: alphabetical max on (score, name) so that
    identical runs with identical seeds always produce identical queries.
    Returns None if scores is empty or all values are -inf.
    """
    if not scores:
        return None
    best_name = max(scores, key=lambda k: (scores[k], k))
    if not math.isfinite(scores[best_name]):
        return None
    return best_name


# ---------------------------------------------------------------------------
# Policy base class
# ---------------------------------------------------------------------------

class Policy(ABC):
    """Base class for all acquisition policies (P0 random … P5 HADES, P6 LLM).

    All subclasses must:
    - Use only `*_estimated` fields from menu QuerySpec entries.
    - Use `_argmax_tiebreak()` for deterministic source selection.
    - Return None when remaining_budget <= 0 (budget exhausted).
    - Never access `*_true` fields (enforced by TestLeakage).

    mu is deleted in v3.0. ManipRisk enters through contaminated likelihood.
    """

    name: str = "base"

    @abstractmethod
    def select_query(
        self,
        state: InvestigationState,
        menu: Dict[str, QuerySpec],
        likelihood_table: Any = None,  # hades.belief.likelihood.LikelihoodTable
        estimators: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Return the menu key to query next, or None to stop the episode."""
        raise NotImplementedError

    def _available(
        self, state: InvestigationState, menu: Dict[str, QuerySpec]
    ) -> Dict[str, QuerySpec]:
        """Return sources still within budget and not blocked."""
        return {
            k: v for k, v in menu.items()
            if getattr(v, "cost", 1.0) <= state.remaining_budget
        }
