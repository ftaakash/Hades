"""tests/test_phi_channel.py — φ-channel semantic / behavioural test.

PURPOSE
-------
Determine whether the contaminated likelihood model actually produces
materially different values when phi_hat varies, and whether this
translates into policy-level VoI changes.

RESULT CLASSIFICATION:
A. likelihood doesn't change → implementation/model-semantic problem
B. likelihood changes but VoI/policy unchanged → scientific result (φ behaviorally irrelevant)
C. likelihood and VoI change → φ channel is functional, scenario design issue
"""
from __future__ import annotations

import pytest
import math
from hades.belief.likelihood import (
    contaminated_likelihood, OBS_CLASSES, make_default_table,
)
from hades.belief.value import eig, voi


# Shared test fixtures
HYPOTHESES = ["H1", "H2", "H3"]
DEFAULT_BELIEFS = {"H1": 0.5, "H2": 0.3, "H3": 0.2}
SOURCE = "test_source"
DEFAULT_RELEVANCE = {SOURCE: {h: 0.7 if h == "H1" else 0.3 for h in HYPOTHESES}}


def _make_table():
    return make_default_table(
        sources=[SOURCE],
        hypotheses=HYPOTHESES,
        relevance={(SOURCE, h): DEFAULT_RELEVANCE[SOURCE][h] for h in HYPOTHESES},
    )


class TestPhiLikelihoodLevel:
    """Test whether contaminated_likelihood changes with phi_hat."""

    def test_phi_changes_likelihood_under_attack(self):
        """When under_targeted_attack=True, varying phi_hat MUST change likelihood."""
        r_hat = 0.8
        obs_class = "strong_support"
        relevance = 0.7

        lik_phi0 = contaminated_likelihood(
            obs_class, "H1", relevance, r_hat, phi_hat=0.0,
            under_targeted_attack=True)
        lik_phi5 = contaminated_likelihood(
            obs_class, "H1", relevance, r_hat, phi_hat=0.5,
            under_targeted_attack=True)
        lik_phi9 = contaminated_likelihood(
            obs_class, "H1", relevance, r_hat, phi_hat=0.9,
            under_targeted_attack=True)

        # phi_hat > 0 under attack should change the likelihood
        assert lik_phi5 != lik_phi0, (
            f"phi_hat=0.5 gives same likelihood as phi_hat=0.0: {lik_phi0}")
        assert lik_phi9 != lik_phi0, (
            f"phi_hat=0.9 gives same likelihood as phi_hat=0.0: {lik_phi0}")
        assert lik_phi9 != lik_phi5, (
            f"phi_hat=0.9 gives same likelihood as phi_hat=0.5: {lik_phi5}")

    def test_phi_has_no_effect_without_attack_flag(self):
        """When under_targeted_attack=False, phi_hat should NOT change likelihood."""
        r_hat = 0.8
        obs_class = "strong_support"
        relevance = 0.7

        lik_phi0 = contaminated_likelihood(
            obs_class, "H1", relevance, r_hat, phi_hat=0.0,
            under_targeted_attack=False)
        lik_phi5 = contaminated_likelihood(
            obs_class, "H1", relevance, r_hat, phi_hat=0.5,
            under_targeted_attack=False)
        lik_phi9 = contaminated_likelihood(
            obs_class, "H1", relevance, r_hat, phi_hat=0.9,
            under_targeted_attack=False)

        assert lik_phi0 == lik_phi5 == lik_phi9, (
            f"phi_hat changed likelihood without attack: "
            f"phi0={lik_phi0}, phi5={lik_phi5}, phi9={lik_phi9}")

    def test_phi_magnitude_across_obs_classes(self):
        """Verify phi changes are material, not just rounding noise."""
        r_hat = 0.8
        relevance = 0.7

        phi_values = [0.0, 0.5, 0.9]
        for obs in OBS_CLASSES:
            liks = [contaminated_likelihood(
                obs, "H1", relevance, r_hat, phi_hat=phi,
                under_targeted_attack=True) for phi in phi_values]
            # At least one obs class should show > 1% absolute difference
            max_change = max(abs(liks[i] - liks[j])
                            for i in range(len(liks))
                            for j in range(i+1, len(liks)))
            # Report but don't require every obs class changes
            if max_change > 0.01:
                return  # Found material change
        pytest.fail("No obs class showed > 1% absolute change with phi_hat")


class TestPhiEIGLevel:
    """Test whether EIG changes when phi_hat varies."""

    def test_eig_changes_with_phi_under_attack(self):
        """EIG should differ when phi_hat varies AND under_targeted_attack=True."""
        table = _make_table()
        rel = DEFAULT_RELEVANCE[SOURCE]

        eig_phi0 = eig(SOURCE, DEFAULT_BELIEFS, table, r_hat=0.8, phi_hat=0.0,
                       source_relevance=rel, under_targeted_attack=True)
        eig_phi5 = eig(SOURCE, DEFAULT_BELIEFS, table, r_hat=0.8, phi_hat=0.5,
                       source_relevance=rel, under_targeted_attack=True)
        eig_phi9 = eig(SOURCE, DEFAULT_BELIEFS, table, r_hat=0.8, phi_hat=0.9,
                       source_relevance=rel, under_targeted_attack=True)

        # Report values for diagnosis
        print(f"\n  EIG under attack: phi=0.0→{eig_phi0:.6f}, "
              f"phi=0.5→{eig_phi5:.6f}, phi=0.9→{eig_phi9:.6f}")

        # These should differ
        assert abs(eig_phi5 - eig_phi0) > 1e-6 or abs(eig_phi9 - eig_phi0) > 1e-6, (
            f"EIG unchanged with phi_hat: {eig_phi0:.8f}")

    def test_eig_unchanged_without_attack_flag(self):
        """EIG should NOT change when under_targeted_attack=False, regardless of phi_hat."""
        table = _make_table()
        rel = DEFAULT_RELEVANCE[SOURCE]

        eig_phi0 = eig(SOURCE, DEFAULT_BELIEFS, table, r_hat=0.8, phi_hat=0.0,
                       source_relevance=rel, under_targeted_attack=False)
        eig_phi9 = eig(SOURCE, DEFAULT_BELIEFS, table, r_hat=0.8, phi_hat=0.9,
                       source_relevance=rel, under_targeted_attack=False)

        assert abs(eig_phi0 - eig_phi9) < 1e-12, (
            f"EIG changed without attack flag: phi0={eig_phi0}, phi9={eig_phi9}")


class TestPhiVoILevel:
    """Test whether VoI changes with phi_hat."""

    def test_voi_changes_with_phi_under_attack(self):
        """VoI should differ when phi_hat varies AND under_targeted_attack=True."""
        table = _make_table()
        rel = DEFAULT_RELEVANCE[SOURCE]

        voi_phi0 = voi(SOURCE, DEFAULT_BELIEFS, table, cost=1.0, lam=1.0,
                       r_hat=0.8, phi_hat=0.0,
                       source_relevance=rel, under_targeted_attack=True)
        voi_phi9 = voi(SOURCE, DEFAULT_BELIEFS, table, cost=1.0, lam=1.0,
                       r_hat=0.8, phi_hat=0.9,
                       source_relevance=rel, under_targeted_attack=True)

        print(f"\n  VoI under attack: phi=0.0→{voi_phi0:.6f}, phi=0.9→{voi_phi9:.6f}")
        assert abs(voi_phi0 - voi_phi9) > 1e-6, (
            f"VoI unchanged with phi_hat under attack")


class TestPhiPolicyLevel:
    """Phase 7C: P5 must model phi using only policy-visible estimates."""

    @staticmethod
    def _spec(name, r_hat, phi_hat, cost=1.0, affinity=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            name=name, cost=cost,
            reliability_estimated=r_hat,
            manipulation_risk_estimated=phi_hat,
            hypothesis_affinity=affinity or {"H1": 0.7, "H2": 0.3, "H3": 0.3},
        )

    @staticmethod
    def _state(beliefs, remaining_budget=10.0):
        from types import SimpleNamespace
        return SimpleNamespace(beliefs=dict(beliefs), remaining_budget=remaining_budget,
                               queried=set(), queried_sources=set(), history=[])

    def _select(self, policy, menu):
        # Bypass _available() variations by passing an already-filtered menu
        policy._available = lambda state, m: m
        return policy.select_query(self._state(DEFAULT_BELIEFS), menu)

    def test_likelihood_is_normalized_under_phi(self):
        """phi-aware likelihood must sum to 1 over obs classes (7C bugfix)."""
        for phi in (0.0, 0.3, 0.85, 1.0):
            for rel in (0.2, 0.7):
                total = sum(contaminated_likelihood(
                    o, "H1", rel, 0.8, phi, under_targeted_attack=True)
                    for o in OBS_CLASSES)
                assert abs(total - 1.0) < 1e-9, (phi, rel, total)

    def test_eig_decreases_monotonically_with_phi(self):
        table = _make_table()
        rel = DEFAULT_RELEVANCE[SOURCE]
        eigs = [eig(SOURCE, DEFAULT_BELIEFS, table, r_hat=0.8, phi_hat=p,
                    source_relevance=rel, under_targeted_attack=True)
                for p in (0.0, 0.25, 0.5, 0.85)]
        assert all(a > b for a, b in zip(eigs, eigs[1:])), eigs
        assert eigs[-1] > 0.0, "EIG should not collapse to 0 (pre-7C clamp bug)"

    def test_p5_selection_changes_with_phi(self):
        """PHI-3: two otherwise-identical sources; phi_hat alone flips P5's choice."""
        from hades.policies.p5_robust_voi import RobustVoIPolicy
        menu_a = {"a_src": self._spec("a_src", 0.85, 0.85),
                  "b_src": self._spec("b_src", 0.85, 0.02)}
        menu_b = {"a_src": self._spec("a_src", 0.85, 0.02),
                  "b_src": self._spec("b_src", 0.85, 0.85)}
        assert self._select(RobustVoIPolicy(lam=0.0), menu_a) == "b_src"
        assert self._select(RobustVoIPolicy(lam=0.0), menu_b) == "a_src"

    def test_p3_unaffected_by_phi(self):
        """Baseline P3 is phi-unaware: same choice regardless of phi_hat."""
        from hades.policies.p3_ig import IGPolicy as P3
        menu_a = {"a_src": self._spec("a_src", 0.85, 0.85),
                  "b_src": self._spec("b_src", 0.85, 0.02)}
        menu_b = {"a_src": self._spec("a_src", 0.85, 0.02),
                  "b_src": self._spec("b_src", 0.85, 0.85)}
        # Equal EIG -> deterministic tie-break = alphabetical max (score, name)
        assert self._select(P3(), menu_a) == self._select(P3(), menu_b) == "b_src"

    def test_p5_phi_zero_matches_clean_voi(self):
        """phi_hat=0 reproduces pre-7C P5 scores exactly."""
        table = _make_table()
        rel = DEFAULT_RELEVANCE[SOURCE]
        v_clean = voi(SOURCE, DEFAULT_BELIEFS, table, cost=1.0, lam=1.0,
                      r_hat=0.8, phi_hat=0.0, source_relevance=rel,
                      under_targeted_attack=False)
        v_flag = voi(SOURCE, DEFAULT_BELIEFS, table, cost=1.0, lam=1.0,
                     r_hat=0.8, phi_hat=0.0, source_relevance=rel,
                     under_targeted_attack=True)
        assert v_clean == v_flag

    def test_p5_reads_no_oracle_fields(self):
        """PHI-5: P5 source must not reference *_true or env attack state."""
        from hades.policies.p5_robust_voi import RobustVoIPolicy
        import inspect
        src = inspect.getsource(RobustVoIPolicy.select_query)
        assert "_true" not in src
        assert "under_targeted_attack=(phi_hat > 0.0)" in src
