"""P3_nom / P3_nom_cost -- nominal-EIG baselines for Phase 7C-A cost attribution.

Background
----------
The existing P3 (``hades/policies/p3_ig.py``) feeds the policy-visible
``r_hat`` into the contaminated likelihood, so it is *reliability-aware*
EIG rather than nominal EIG. Phase 7C-A pre-run validation confirmed this:
P3's choice flips when only ``r_hat`` changes. That is why Phase 6D found
``P5_no_cost == P3``. See docs/phase7c_cost_attribution_protocol.md.

The two policies here are the nominal baselines the attribution design needs:

    P3_nom(q)      = EIG_nominal(q)                    (r = 1, phi = 0)
    P3_nom_cost(q) = EIG_nominal(q) - lam * Cost(q)

They read NO reliability or manipulation fields. Apart from that they use
the same candidate menu, likelihood table construction, affinity default
(0.5), budget filter and tie-break (`_argmax_tiebreak`) as P3 and P5.

``RhatIGCostPolicy`` (P3_rhat_cost = existing P3 - lam * Cost) is included only
to prove algebraically, in tests, that it is identical to P5_no_phi. It is not
run as a separate arm.

Citation: Naghshvar & Javidi (2013), active sequential hypothesis testing.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from hades.belief.likelihood import LikelihoodTable, make_default_table
from hades.belief.value import eig
from hades.policies.base import InvestigationState, Policy, _argmax_tiebreak
from hades.query_menu import QuerySpec


def _nominal_eig(src_name: str, spec: Any, state: InvestigationState,
                 likelihood_table: Optional[LikelihoodTable]) -> float:
    """EIG under the nominal likelihood: r_hat=1, phi_hat=0, no forgery term."""
    affinity = getattr(spec, "hypothesis_affinity", {})
    table = likelihood_table or make_default_table(
        sources=[src_name],
        hypotheses=list(state.beliefs.keys()),
        relevance={(src_name, h): affinity.get(h, 0.5) for h in state.beliefs},
    )
    return eig(
        source=src_name,
        beliefs=state.beliefs,
        table=table,
        r_hat=1.0,
        phi_hat=0.0,
        source_relevance={h: affinity.get(h, 0.5) for h in state.beliefs},
        under_targeted_attack=False,
    )


class NominalIGPolicy(Policy):
    """P3_nom: argmax EIG_nominal(q). Ignores r_hat and phi_hat entirely."""

    name = "ig_nominal"

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
        scores = {n: _nominal_eig(n, s, state, likelihood_table)
                  for n, s in available.items()}
        return _argmax_tiebreak(scores)


class NominalIGCostPolicy(Policy):
    """P3_nom_cost: argmax EIG_nominal(q) - lam * Cost(q)."""

    name = "ig_nominal_cost"

    def __init__(self, lam: float = 1.0) -> None:
        assert lam >= 0, f"lam must be >= 0, got {lam}"
        self.lam = lam

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
        scores = {
            n: _nominal_eig(n, s, state, likelihood_table)
               - self.lam * getattr(s, "cost", 1.0)
            for n, s in available.items()
        }
        return _argmax_tiebreak(scores)


class RhatIGCostPolicy(Policy):
    """P3_rhat_cost: existing P3 (r_hat-aware EIG) - lam * Cost.

    Algebraically identical to P5_no_phi. Kept only for the equivalence test.
    """

    name = "ig_rhat_cost"

    def __init__(self, lam: float = 1.0) -> None:
        self.lam = lam

    def select_query(self, state, menu, likelihood_table=None, estimators=None):
        available = self._available(state, menu)
        if not available or state.remaining_budget <= 0:
            return None
        if not state.beliefs:
            return min(available)
        scores = {}
        for n, s in available.items():
            affinity = getattr(s, "hypothesis_affinity", {})
            table = likelihood_table or make_default_table(
                sources=[n], hypotheses=list(state.beliefs.keys()),
                relevance={(n, h): affinity.get(h, 0.5) for h in state.beliefs},
            )
            scores[n] = eig(
                source=n, beliefs=state.beliefs, table=table,
                r_hat=getattr(s, "reliability_estimated", 1.0),
                phi_hat=getattr(s, "manipulation_risk_estimated", 0.0),
                source_relevance={h: affinity.get(h, 0.5) for h in state.beliefs},
                under_targeted_attack=False,
            ) - self.lam * getattr(s, "cost", 1.0)
        return _argmax_tiebreak(scores)
