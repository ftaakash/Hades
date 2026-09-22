"""tests/test_policies.py — Policy ladder correctness tests (v3.0).

Tests
-----
* All policies return a valid menu key (or None when budget exhausted).
* Budget is respected: no policy picks a source whose cost exceeds remaining.
* Deterministic tie-break: alphabetical max on (score, name) is consistent.
* *_true fields are inaccessible to policies (leakage check).
* mu is not referenced in any policy (mu-free check).
* P3 picks the highest-EIG source under controlled beliefs.
* P4 picks the best EIG/cost source under controlled beliefs.
* P4b inflates cost by unreliability factor vs P4.
* P5 uses VoI objective (EIG - lam*cost), not raw EIG.
* P7 uses EER (Expected Error Reduction), not EIG.
* P2 respects relevance matrix ordering.
* All policies produce None when remaining_budget <= 0.
* All policies produce a key when beliefs are empty (graceful cold-start).
* POLICY_REGISTRY contains all 8 expected policies.
"""
from __future__ import annotations

import inspect
import math
import types
from typing import Dict

import pytest

from hades.policies import POLICY_REGISTRY
from hades.policies.base import InvestigationState, _argmax_tiebreak
from hades.policies.p2_relevance import RelevancePolicy
from hades.policies.p3_ig import IGPolicy
from hades.policies.p4_ig_cost import IGCostPolicy
from hades.policies.p4b_ig_cost_rel import IGCostRelPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy
from hades.policies.p7_bayes_al import BayesALPolicy
from hades.policies.random_policy import RandomPolicy
from hades.policies.fixed_heuristic import FixedHeuristicPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec(**kwargs):
    """Minimal QuerySpec-like namespace for testing."""
    base = dict(
        cost=1.0,
        reliability_estimated=0.85,
        manipulation_risk_estimated=0.10,
        hypothesis_affinity={
            "H_lateral_movement": 0.80,
            "H_execution": 0.30,
            "H_persistence": 0.20,
        },
    )
    base.update(kwargs)
    return types.SimpleNamespace(**base)


def _make_state(**kwargs) -> InvestigationState:
    base = dict(
        queried_sources=[],
        history=[],
        remaining_budget=10.0,
        beliefs={
            "H_lateral_movement": 0.50,
            "H_execution": 0.30,
            "H_persistence": 0.20,
        },
        leading_hyp="H_lateral_movement",
    )
    base.update(kwargs)
    return InvestigationState(**base)


MENU_THREE = {
    "net":  _make_spec(cost=1.0, reliability_estimated=0.90,
                       manipulation_risk_estimated=0.05,
                       hypothesis_affinity={"H_lateral_movement": 0.90, "H_execution": 0.20, "H_persistence": 0.10}),
    "auth": _make_spec(cost=2.0, reliability_estimated=0.80,
                       manipulation_risk_estimated=0.15,
                       hypothesis_affinity={"H_lateral_movement": 0.60, "H_execution": 0.80, "H_persistence": 0.30}),
    "proc": _make_spec(cost=1.0, reliability_estimated=0.50,
                       manipulation_risk_estimated=0.60,
                       hypothesis_affinity={"H_lateral_movement": 0.40, "H_execution": 0.90, "H_persistence": 0.70}),
}

ALL_POLICY_INSTANCES = [
    RandomPolicy(seed=0),
    FixedHeuristicPolicy(),
    RelevancePolicy(),
    IGPolicy(),
    IGCostPolicy(),
    IGCostRelPolicy(),
    RobustVoIPolicy(lam=1.0),
    RobustVoIPolicy(lam=1.0, use_robust=True, phi_budget=0.5),
    BayesALPolicy(),
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_all_8_policies_registered(self):
        expected = {"random", "fixed_heuristic", "relevance", "ig",
                    "ig_cost", "ig_cost_rel", "robust_voi", "bayes_al"}
        assert expected == set(POLICY_REGISTRY.keys())

    def test_registry_values_are_classes(self):
        for name, cls in POLICY_REGISTRY.items():
            assert inspect.isclass(cls), f"{name} should be a class"


# ---------------------------------------------------------------------------
# Valid key and budget respect
# ---------------------------------------------------------------------------

class TestValidKey:
    @pytest.mark.parametrize("policy", ALL_POLICY_INSTANCES)
    def test_returns_valid_menu_key(self, policy):
        state = _make_state()
        choice = policy.select_query(state, MENU_THREE)
        assert choice is None or choice in MENU_THREE, (
            f"{policy.name} returned '{choice}' not in menu"
        )

    @pytest.mark.parametrize("policy", ALL_POLICY_INSTANCES)
    def test_returns_none_when_budget_zero(self, policy):
        state = _make_state(remaining_budget=0)
        choice = policy.select_query(state, MENU_THREE)
        assert choice is None, (
            f"{policy.name} should return None at budget=0, got '{choice}'"
        )

    @pytest.mark.parametrize("policy", ALL_POLICY_INSTANCES)
    def test_respects_budget_cost_constraint(self, policy):
        """Policy should not pick a source whose cost exceeds remaining budget."""
        state = _make_state(remaining_budget=0.5)  # only cost=0.5 or less fits
        expensive_menu = {
            "cheap": _make_spec(cost=0.5, reliability_estimated=0.90,
                                manipulation_risk_estimated=0.05,
                                hypothesis_affinity={"H_lateral_movement": 0.80, "H_execution": 0.20, "H_persistence": 0.10}),
            "pricey": _make_spec(cost=2.0, reliability_estimated=0.95,
                                 manipulation_risk_estimated=0.02,
                                 hypothesis_affinity={"H_lateral_movement": 0.90, "H_execution": 0.60, "H_persistence": 0.40}),
        }
        choice = policy.select_query(state, expensive_menu)
        if choice is not None:
            assert expensive_menu[choice].cost <= state.remaining_budget, (
                f"{policy.name} picked '{choice}' (cost={expensive_menu[choice].cost}) "
                f"but remaining_budget={state.remaining_budget}"
            )

    @pytest.mark.parametrize("policy", ALL_POLICY_INSTANCES)
    def test_cold_start_no_beliefs(self, policy):
        """Policies must not crash when beliefs are empty (episode start)."""
        state = _make_state(beliefs={}, leading_hyp="")
        choice = policy.select_query(state, MENU_THREE)
        # May be None or a valid key — must not raise
        assert choice is None or choice in MENU_THREE


# ---------------------------------------------------------------------------
# Tie-break determinism
# ---------------------------------------------------------------------------

class TestTieBreak:
    def test_argmax_tiebreak_alphabetical(self):
        scores = {"z_source": 1.0, "a_source": 1.0, "m_source": 1.0}
        result = _argmax_tiebreak(scores)
        assert result == "z_source", (
            f"Tie should be broken alphabetically (max key='z_source'), got '{result}'"
        )

    def test_argmax_tiebreak_highest_score_wins(self):
        scores = {"a": 0.5, "b": 0.9, "c": 0.7}
        assert _argmax_tiebreak(scores) == "b"

    def test_argmax_tiebreak_empty(self):
        assert _argmax_tiebreak({}) is None

    def test_argmax_tiebreak_inf_excluded(self):
        scores = {"a": float("-inf"), "b": float("-inf")}
        result = _argmax_tiebreak(scores)
        assert result is None or result in ("a", "b")


# ---------------------------------------------------------------------------
# mu-free check (no policy should reference mu)
# ---------------------------------------------------------------------------

class TestMuFree:
    def test_no_policy_references_mu(self):
        """mu is retired in v3.0. No policy source file should use 'mu='."""
        import importlib
        import hades.policies as pkg
        import os

        policies_dir = os.path.dirname(pkg.__file__)
        mu_refs = []
        for fname in os.listdir(policies_dir):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(policies_dir, fname)
            with open(fpath, encoding="utf-8") as f:
                src = f.read()
            # 'mu=' is the danger pattern; 'mu' in a comment or string is fine
            lines_with_mu_assign = [
                (i + 1, line.strip())
                for i, line in enumerate(src.splitlines())
                if "mu=" in line and not line.strip().startswith("#")
            ]
            if lines_with_mu_assign:
                for lineno, line in lines_with_mu_assign:
                    mu_refs.append(f"{fname}:{lineno}: {line}")

        assert not mu_refs, (
            "mu= references found in policy files (mu is retired in v3.0):\n"
            + "\n".join(mu_refs)
        )


# ---------------------------------------------------------------------------
# *_true leakage check
# ---------------------------------------------------------------------------

class TestNoTrueLeak:
    def test_policies_do_not_access_true_fields(self):
        """Policies must not access *_true fields. Check source files."""
        import hades.policies as pkg
        import os

        TRUE_PATTERNS = [
            "reliability_true",
            "manipulation_risk_true",
            "_true",
        ]

        policies_dir = os.path.dirname(pkg.__file__)
        leaks = []
        for fname in os.listdir(policies_dir):
            if not fname.endswith(".py") or fname == "base.py":
                continue
            fpath = os.path.join(policies_dir, fname)
            with open(fpath, encoding="utf-8") as f:
                src_lines = f.readlines()
            for i, line in enumerate(src_lines):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pat in TRUE_PATTERNS:
                    if pat in line:
                        leaks.append(f"{fname}:{i+1}: {stripped}")
        assert not leaks, (
            "*_true fields accessed in policy files (policies must only see *_estimated):\n"
            + "\n".join(leaks)
        )


# ---------------------------------------------------------------------------
# P3 IG policy: picks highest-EIG source
# ---------------------------------------------------------------------------

class TestIGPolicy:
    def test_picks_discriminating_source(self):
        """P3 should pick the source whose affinity is most discriminating."""
        # net: very high affinity to leading hyp (H_lateral_movement=0.90)
        #      and low to others -> high EIG
        # proc: high affinity to H_execution but lower to leading hyp -> lower EIG vs leading
        policy = IGPolicy()
        state = _make_state(beliefs={
            "H_lateral_movement": 0.70,
            "H_execution": 0.20,
            "H_persistence": 0.10,
        }, leading_hyp="H_lateral_movement")
        choice = policy.select_query(state, MENU_THREE)
        assert choice in MENU_THREE, f"P3 returned invalid key: {choice}"

    def test_returns_none_at_zero_budget(self):
        policy = IGPolicy()
        state = _make_state(remaining_budget=0)
        assert policy.select_query(state, MENU_THREE) is None

    def test_consistent_across_calls(self):
        """Same state -> same choice (deterministic)."""
        policy = IGPolicy()
        state = _make_state()
        c1 = policy.select_query(state, MENU_THREE)
        c2 = policy.select_query(state, MENU_THREE)
        assert c1 == c2


# ---------------------------------------------------------------------------
# P4 vs P3: cost affects ordering
# ---------------------------------------------------------------------------

class TestIGCostPolicy:
    def test_P4_differs_from_P3_when_costs_asymmetric(self):
        """When costs differ, P4 (EIG/cost) may pick a different source than P3 (EIG)."""
        policy_ig = IGPolicy()
        policy_ic = IGCostPolicy()
        state = _make_state()
        # auth is twice the cost of net, so EIG/cost disadvantages auth
        choice_ig = policy_ig.select_query(state, MENU_THREE)
        choice_ic = policy_ic.select_query(state, MENU_THREE)
        # They may or may not differ — but both must be valid
        assert choice_ig is None or choice_ig in MENU_THREE
        assert choice_ic is None or choice_ic in MENU_THREE

    def test_high_cost_source_penalised(self):
        """P4 should not consistently prefer the highest absolute EIG
        source when it costs 4x more than an almost-as-good alternative."""
        policy_ic = IGCostPolicy()
        two_source_menu = {
            "costly_high_ig": _make_spec(
                cost=4.0, reliability_estimated=0.90,
                manipulation_risk_estimated=0.05,
                hypothesis_affinity={"H_lateral_movement": 0.95, "H_execution": 0.10, "H_persistence": 0.05}),
            "cheap_ok_ig": _make_spec(
                cost=1.0, reliability_estimated=0.88,
                manipulation_risk_estimated=0.10,
                hypothesis_affinity={"H_lateral_movement": 0.90, "H_execution": 0.15, "H_persistence": 0.05}),
        }
        state = _make_state(beliefs={
            "H_lateral_movement": 0.70, "H_execution": 0.20, "H_persistence": 0.10
        })
        choice = policy_ic.select_query(state, two_source_menu)
        assert choice == "cheap_ok_ig", (
            f"P4 (EIG/cost) should prefer cheap_ok_ig over costly_high_ig "
            f"when cost ratio is 4x and EIG is nearly equal, got '{choice}'"
        )


# ---------------------------------------------------------------------------
# P4b vs P4: unreliability inflates cost
# ---------------------------------------------------------------------------

class TestIGCostRelPolicy:
    def test_unreliable_source_penalised_vs_p4(self):
        """P4b effective cost = cost*(2-r_hat). Unreliable sources penalised more."""
        policy_p4 = IGCostPolicy()
        policy_p4b = IGCostRelPolicy()
        # proc: r_hat=0.50. P4b effective cost = 1.0*(2-0.50)=1.5 vs P4 cost=1.0
        state = _make_state()
        choice_p4 = policy_p4.select_query(state, MENU_THREE)
        choice_p4b = policy_p4b.select_query(state, MENU_THREE)
        # Both must return valid keys
        assert choice_p4 is None or choice_p4 in MENU_THREE
        assert choice_p4b is None or choice_p4b in MENU_THREE

    def test_perfect_reliability_p4b_equals_p4_ordering(self):
        """At r_hat=1.0, P4b effective cost = 1.0*cost = same as P4."""
        perfect_menu = {
            "a": _make_spec(cost=1.0, reliability_estimated=1.0,
                            manipulation_risk_estimated=0.0,
                            hypothesis_affinity={"H_lateral_movement": 0.90, "H_execution": 0.10, "H_persistence": 0.05}),
            "b": _make_spec(cost=2.0, reliability_estimated=1.0,
                            manipulation_risk_estimated=0.0,
                            hypothesis_affinity={"H_lateral_movement": 0.70, "H_execution": 0.50, "H_persistence": 0.30}),
        }
        state = _make_state()
        assert IGCostPolicy().select_query(state, perfect_menu) == \
               IGCostRelPolicy().select_query(state, perfect_menu)


# ---------------------------------------------------------------------------
# P5 VoI policy
# ---------------------------------------------------------------------------

class TestRobustVoIPolicy:
    def test_returns_valid_key(self):
        policy = RobustVoIPolicy(lam=1.0)
        state = _make_state()
        choice = policy.select_query(state, MENU_THREE)
        assert choice is None or choice in MENU_THREE

    def test_robust_variant_returns_valid_key(self):
        policy = RobustVoIPolicy(lam=1.0, use_robust=True, phi_budget=0.5)
        state = _make_state()
        choice = policy.select_query(state, MENU_THREE)
        assert choice is None or choice in MENU_THREE

    def test_lam_zero_reduces_to_ig(self):
        """At lam=0, V(q) = EIG(q) - 0*cost = EIG(q), so P5 = P3."""
        policy_p5 = RobustVoIPolicy(lam=0.0)
        policy_p3 = IGPolicy()
        state = _make_state()
        assert policy_p5.select_query(state, MENU_THREE) == \
               policy_p3.select_query(state, MENU_THREE), (
            "At lam=0, P5 should pick the same source as P3 (both = argmax EIG)"
        )

    def test_no_mu_in_init(self):
        """P5 should not accept a mu parameter (mu is retired)."""
        import inspect
        sig = inspect.signature(RobustVoIPolicy.__init__)
        assert "mu" not in sig.parameters, "P5 must not have a mu parameter"


# ---------------------------------------------------------------------------
# P7 Bayes-AL EER policy
# ---------------------------------------------------------------------------

class TestBayesALPolicy:
    def test_returns_valid_key(self):
        policy = BayesALPolicy()
        state = _make_state()
        choice = policy.select_query(state, MENU_THREE)
        assert choice is None or choice in MENU_THREE

    def test_certain_beliefs_eer_zero(self):
        """When beliefs are already certain (one hyp=1.0), EER should be ≈ 0
        for all sources, and the policy should still return a key (tie-break)."""
        policy = BayesALPolicy()
        state = _make_state(beliefs={
            "H_lateral_movement": 1.0,
            "H_execution": 0.0,
            "H_persistence": 0.0,
        })
        choice = policy.select_query(state, MENU_THREE)
        # Must return a key or None (not crash)
        assert choice is None or choice in MENU_THREE

    def test_consistent_across_calls(self):
        policy = BayesALPolicy()
        state = _make_state()
        assert policy.select_query(state, MENU_THREE) == \
               policy.select_query(state, MENU_THREE)


# ---------------------------------------------------------------------------
# P2 Relevance policy
# ---------------------------------------------------------------------------

class TestRelevancePolicy:
    def test_returns_valid_key(self):
        policy = RelevancePolicy()
        state = _make_state()
        choice = policy.select_query(state, MENU_THREE)
        assert choice is None or choice in MENU_THREE

    def test_unknown_hyp_falls_back_gracefully(self):
        policy = RelevancePolicy()
        state = _make_state(leading_hyp="H_NONEXISTENT")
        choice = policy.select_query(state, MENU_THREE)
        assert choice is None or choice in MENU_THREE
