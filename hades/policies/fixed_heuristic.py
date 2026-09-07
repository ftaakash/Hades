"""P1 -- fixed expert-order baseline: a hand-authored triage sequence.

Encodes a plausible default human-analyst investigation order --
process, then network, then auth, then persistence, then DNS, then
PowerShell, then object-access -- and repeats it if budget remains
after one full pass. This is the "simple operational baseline" from
the design notes: no adaptivity at all, just a sensible fixed order.
"""
from __future__ import annotations

from typing import Dict, Optional

from hades.policies.base import InvestigationState, Policy
from hades.query_menu import QuerySpec

DEFAULT_ORDER = (
    "process_events",
    "network_events",
    "auth_events",
    "persistence_events",
    "dns_events",
    "powershell_events",
    "object_access_events",
)


class FixedHeuristicPolicy(Policy):
    name = "fixed_heuristic"

    def select_query(
        self, state: InvestigationState, menu: Dict[str, QuerySpec]
    ) -> Optional[str]:
        if state.remaining_budget <= 0:
            return None
        n_done = len(state.history)
        return DEFAULT_ORDER[n_done % len(DEFAULT_ORDER)]
