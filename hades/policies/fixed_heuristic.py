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
        self, state: InvestigationState, menu: Dict[str, QuerySpec],
        likelihood_table=None, estimators=None,
    ) -> Optional[str]:
        if state.remaining_budget <= 0:
            return None
        # Cycle through DEFAULT_ORDER, but only return sources present in menu.
        # This makes the policy robust to test menus with different key names.
        available_in_order = [s for s in DEFAULT_ORDER if s in menu
                              and menu[s].cost <= state.remaining_budget]
        if not available_in_order:
            # Fallback: any affordable menu item (alphabetical for determinism)
            affordable = sorted(k for k, v in menu.items()
                                if getattr(v, "cost", 1.0) <= state.remaining_budget)
            return affordable[0] if affordable else None
        n_done = len(state.history)
        return available_in_order[n_done % len(available_in_order)]
