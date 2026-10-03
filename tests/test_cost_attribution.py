"""tests/test_cost_attribution.py -- Phase 7C-A pre-run validation (CAG-1, CAG-5).

Checks for the nominal cost-matched baseline P3_nom_cost:
  * equal costs           -> identical choice to P3_nom (score differs by a constant)
  * different costs        -> divergence comes ONLY from the cost term
  * r_hat / phi_hat        -> no effect on P3_nom or P3_nom_cost
  * oracle fields          -> never referenced
Also documents that the pre-existing P3 is r_hat-aware, and that
P3_rhat_cost is identical to P5_no_phi.
"""
from __future__ import annotations

import inspect
import random
from types import SimpleNamespace as NS

import pytest

from hades.policies.p3_cost import (
    NominalIGCostPolicy, NominalIGPolicy, RhatIGCostPolicy, _nominal_eig,
)
from hades.policies.p3_ig import IGPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy
from scripts.run_mechanism_ablation import P5NoPhi

HYPS = ["H1", "H2", "H3"]


def _state(rng):
    w = [rng.random() + 0.05 for _ in HYPS]
    s = sum(w)
    return NS(beliefs={h: x / s for h, x in zip(HYPS, w)}, remaining_budget=100.0)


def _menu(rng, n=5, equal_cost=False, r=None, phi=None):
    menu = {}
    for i in range(n):
        name = f"src_{i}"
        menu[name] = NS(
            name=name,
            cost=1.0 if equal_cost else rng.choice([1.0, 1.5, 2.0, 4.0]),
            reliability_estimated=r if r is not None else rng.uniform(0.3, 1.0),
            manipulation_risk_estimated=phi if phi is not None else rng.uniform(0.0, 0.9),
            hypothesis_affinity={h: rng.uniform(0.05, 0.95) for h in HYPS},
        )
    return menu


def _pick(policy, state, menu):
    policy._available = lambda s, m: m
    return policy.select_query(state, menu)


class TestCAG1Validity:
    def test_equal_costs_identical_to_nominal(self):
        rng = random.Random(0)
        for _ in range(300):
            st, m = _state(rng), _menu(rng, equal_cost=True)
            for lam in (0.5, 1.0, 2.0):
                assert _pick(NominalIGCostPolicy(lam), st, m) == _pick(NominalIGPolicy(), st, m)

    def test_lam_zero_identical_to_nominal(self):
        rng = random.Random(1)
        for _ in range(300):
            st, m = _state(rng), _menu(rng)
            assert _pick(NominalIGCostPolicy(0.0), st, m) == _pick(NominalIGPolicy(), st, m)

    def test_divergence_attributable_only_to_cost(self):
        """P3_nom_cost == independent argmax of (nominal EIG - lam*cost); diverges sometimes."""
        rng = random.Random(2)
        diverged = 0
        for _ in range(300):
            st, m = _state(rng), _menu(rng)
            lam = 1.0
            ref = max(m, key=lambda n: (_nominal_eig(n, m[n], st, None) - lam * m[n].cost, n))
            got = _pick(NominalIGCostPolicy(lam), st, m)
            assert got == ref
            diverged += int(got != _pick(NominalIGPolicy(), st, m))
        assert diverged > 0, "cost term never changed a decision -- test menu too weak"

    def test_scenario_c_cost_flip(self):
        """Scenario C under the nominal likelihood.

        Nominal EIG thresholds relevance at 0.5, so expensive_auth TIES for max
        nominal EIG with network_events and powershell_events (0.5368). The
        cost-matched policy must never choose the cost-4 source, and must pick
        the max-EIG source among the cheapest.
        """
        from hades.simulator.scenarios import SCENARIO_C_COST_FLIP as C
        from hades.simulator.environment import SimEnv
        env = SimEnv(C, seed=0)
        env.reset(true_hypothesis="H_lateral_movement", seed=0)
        st = NS(beliefs=dict(env._beliefs), remaining_budget=10.0)
        menu = {s.name: s for s in C.sources}
        eigs = {n: _nominal_eig(n, s, st, None) for n, s in menu.items()}
        assert abs(eigs["expensive_auth"] - max(eigs.values())) < 1e-12
        cst = _pick(NominalIGCostPolicy(1.0), st, menu)
        assert cst != "expensive_auth"
        assert menu[cst].cost == 1.0 and abs(eigs[cst] - max(eigs.values())) < 1e-12


class TestCAG5Contamination:
    @pytest.mark.parametrize("cls", [NominalIGPolicy, NominalIGCostPolicy])
    def test_invariant_to_rhat_and_phi(self, cls):
        rng = random.Random(3)
        for _ in range(200):
            st = _state(rng)
            base = _menu(rng)
            pol = cls() if cls is NominalIGPolicy else cls(1.0)
            ref = _pick(pol, st, base)
            for r, phi in ((0.3, 0.0), (1.0, 0.9), (0.6, 0.5)):
                alt = {n: NS(**{**vars(s), "reliability_estimated": r,
                                "manipulation_risk_estimated": phi})
                       for n, s in base.items()}
                assert _pick(pol, st, alt) == ref

    def test_no_oracle_or_estimate_fields_in_source(self):
        import hades.policies.p3_cost as mod
        for cls in (NominalIGPolicy, NominalIGCostPolicy):
            src = inspect.getsource(cls)
            assert "_true" not in src
            assert "reliability_estimated" not in src
            assert "manipulation_risk_estimated" not in src
        assert "_true" not in inspect.getsource(mod._nominal_eig)


class TestExistingBaselineFacts:
    def test_existing_p3_is_rhat_aware(self):
        """Documents the pre-run finding: legacy P3 is NOT nominal EIG."""
        st = NS(beliefs={"H1": 0.5, "H2": 0.3, "H3": 0.2}, remaining_budget=10.0)
        def mk(r):
            return {
                "a": NS(name="a", cost=1.0, reliability_estimated=r,
                        manipulation_risk_estimated=0.0,
                        hypothesis_affinity={"H1": 0.9, "H2": 0.1, "H3": 0.1}),
                "b": NS(name="b", cost=1.0, reliability_estimated=0.95,
                        manipulation_risk_estimated=0.0,
                        hypothesis_affinity={"H1": 0.7, "H2": 0.3, "H3": 0.6}),
            }
        assert _pick(IGPolicy(), st, mk(0.3)) != _pick(IGPolicy(), st, mk(0.95))

    def test_existing_p3_is_phi_invariant(self):
        rng = random.Random(4)
        for _ in range(100):
            st, m = _state(rng), _menu(rng)
            alt = {n: NS(**{**vars(s), "manipulation_risk_estimated": 0.0}) for n, s in m.items()}
            assert _pick(IGPolicy(), st, m) == _pick(IGPolicy(), st, alt)

    def test_rhat_cost_identical_to_p5_no_phi(self):
        rng = random.Random(5)
        for _ in range(300):
            st, m = _state(rng), _menu(rng)
            for lam in (0.5, 1.0, 2.0):
                assert _pick(RhatIGCostPolicy(lam), st, m) == _pick(P5NoPhi(lam), st, m)

    def test_p5_full_equals_p5_no_phi_when_phi_zero(self):
        rng = random.Random(6)
        for _ in range(200):
            st, m = _state(rng), _menu(rng, phi=0.0)
            assert _pick(RobustVoIPolicy(lam=1.0), st, m) == _pick(P5NoPhi(1.0), st, m)
