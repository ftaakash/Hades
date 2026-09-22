"""P5 -- HADES Robust-VoI policy (the method under study).

Rule: argmax V(q) where V(q) = EIG(q; r_hat, phi_hat) - lam * Cost(q).

V(q) is the Value of Information under the contaminated likelihood model.
Manipulation risk (phi_hat) degrades EIG automatically via the contaminated
observation likelihood -- no separate mu penalty.

Robust variant (P5r): argmax min_{phi in [0, phi_hat]} V(q; phi).
This is the minimax robust policy from docs/REFRAME.md (Stage C / Phase 7).
The standard variant (use_robust=False) is used for Phase 3 kill gate.

No mu parameter. mu is deleted in v3.0.
lam is the only free parameter (budget-normalised). Default: lam=1.0.

References
----------
HADES v3.0 objective: docs/REFRAME.md.
Contaminated likelihood: hades/belief/likelihood.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from hades.belief.likelihood import LikelihoodTable, make_default_table
from hades.belief.value import robust_voi, voi
from hades.policies.base import InvestigationState, Policy, _argmax_tiebreak
from hades.query_menu import QuerySpec


class RobustVoIPolicy(Policy):
    """P5: argmax V(q) = EIG(q; r_hat, phi_hat) - lam * Cost(q).

    Parameters
    ----------
    lam : float
        Budget penalty weight. Default 1.0.
    use_robust : bool
        If True, use minimax robust_voi (Phase 7 / Stage C).
        If False (default), use standard voi consistent with F1 kill gate.
    phi_budget : float
        Attacker phi budget for robust variant. Ignored if use_robust=False.
    phi_hat_candidates : list[float], optional
        Explicit phi values to sweep for robust variant.
    """

    name = "robust_voi"

    def __init__(
        self,
        lam: float = 1.0,
        use_robust: bool = False,
        phi_budget: float = 0.5,
        phi_hat_candidates: Optional[List[float]] = None,
    ) -> None:
        assert lam >= 0, f"lam must be >= 0, got {lam}"
        self.lam = lam
        self.use_robust = use_robust
        self.phi_budget = phi_budget
        self.phi_hat_candidates = phi_hat_candidates

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
            cost = getattr(spec, "cost", 1.0)
            affinity = getattr(spec, "hypothesis_affinity", {})

            table = likelihood_table or make_default_table(
                sources=[src_name],
                hypotheses=list(state.beliefs.keys()),
                relevance={(src_name, h): affinity.get(h, 0.5)
                           for h in state.beliefs},
            )
            source_rel = {h: affinity.get(h, 0.5) for h in state.beliefs}

            if self.use_robust:
                score = robust_voi(
                    source=src_name,
                    beliefs=state.beliefs,
                    table=table,
                    cost=cost,
                    lam=self.lam,
                    phi_budget=self.phi_budget,
                    r_hat=r_hat,
                    phi_hat_candidates=self.phi_hat_candidates,
                    source_relevance=source_rel,
                )
            else:
                score = voi(
                    source=src_name,
                    beliefs=state.beliefs,
                    table=table,
                    cost=cost,
                    lam=self.lam,
                    r_hat=r_hat,
                    phi_hat=phi_hat,
                    source_relevance=source_rel,
                    under_targeted_attack=False,
                )

            scores[src_name] = score

        return _argmax_tiebreak(scores)
