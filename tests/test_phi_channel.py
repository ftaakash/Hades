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
    """Test whether P5 actually passes under_targeted_attack to the VoI computation."""

    def test_p5_never_sets_attack_flag(self):
        """Verify P5 (standard variant) calls voi with under_targeted_attack=False.

        This test documents the CURRENT behaviour. If P5 always passes False,
        then phi_hat can never affect its decisions, explaining the 6D result.
        """
        from hades.policies.p5_robust_voi import RobustVoIPolicy
        import inspect

        # Check the source code of select_query
        source = inspect.getsource(RobustVoIPolicy.select_query)

        # P5 standard (use_robust=False) should call voi() with under_targeted_attack=False
        # This is the ROOT CAUSE of P5_no_phi ≡ P5_full
        if "under_targeted_attack=False" in source:
            # Expected: P5 never activates the phi channel
            pass
        elif "under_targeted_attack" not in source:
            # voi() default is False, so this is equivalent
            pass
        else:
            # P5 does set it to True somewhere — investigate
            pytest.fail("P5 passes under_targeted_attack=True somewhere; "
                        "this contradicts the ablation finding P5_no_phi ≡ P5_full")
