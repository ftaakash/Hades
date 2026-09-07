"""Policy interface every HADES acquisition policy implements.

A policy sees the current investigation state (which evidence sources
have already been queried, what came back, remaining budget) and picks
the name of the next evidence source to query from the fixed
`query_menu.QUERY_MENU` -- or returns `None` to stop. This is the
plugin surface: dropping a new file in `hades/policies/` that
subclasses `Policy` makes that policy comparable to every other one
across every regime via the harness, with no other code changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from hades.query_menu import QuerySpec


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
    """
    queried_sources: List[str] = field(default_factory=list)
    history: List[QueryRecord] = field(default_factory=list)
    remaining_budget: int = 0
    candidate_timestamps: Set[str] = field(default_factory=set)


class Policy(ABC):
    """Base class for all acquisition policies (P0 random ... P5 HADES, P6 LLM)."""

    name: str = "base"

    @abstractmethod
    def select_query(
        self,
        state: InvestigationState,
        menu: Dict[str, QuerySpec],
    ) -> Optional[str]:
        """Return the menu key to query next, or None to stop the episode."""
        raise NotImplementedError
