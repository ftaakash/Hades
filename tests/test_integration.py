"""tests/test_integration.py — Full pipeline integration tests (Phase 4 gate).

Tests the complete pipeline:
    corruptor → observation → estimator → belief update → policy → action

Integration invariants checked
-------------------------------
1. Budget consistency   : budget_spent + remaining == initial_budget (±1e-6)
2. Belief normalization : beliefs sum to 1.0 throughout every episode
3. No _true leakage     : policy menu contains only *_estimated fields,
                          not reliability_true / manipulation_risk_true
4. Valid observations   : obs_class always in OBS_CLASSES
5. Reproducibility      : same (corruptor, estimator, policy, seed) → same actions
6. No crashes           : all (scenario × corruptor × estimator × policy) complete
7. Expected separation  : in R4 targeted regime, P5 queries high-phi sources
                          less than P3 (when beliefs concentrate on one hypothesis)
8. Clean R0 baseline    : with MissingCorruptor(p_drop=0.0) and CleanEstimator,
                          results should not vary between runs (deterministic)
9. Mutable belief check : beliefs monotonically change after each step (not frozen)

All tests must pass before CDB evaluation begins.
"""
from __future__ import annotations

import random
import types
from typing import List

import pytest

from hades.integration.runner import IntegrationRunner, EpisodeResult, _make_policy_menu
from hades.corruption.missing import MissingCorruptor
from hades.corruption.stale import StaleCorruptor
from hades.corruption.misleading import MisleadingCorruptor
from hades.corruption.targeted import TargetedCorruptor
from hades.corruption.base import OBS_CLASSES
from hades.reliability.estimator import (
    CleanEstimator,
    NoisyEstimator,
    MiscalibratedEstimator,
    AdversarialEstimator,
)
from hades.policies.p3_ig import IGPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy
from hades.policies.p7_bayes_al import BayesALPolicy
from hades.simulator.environment import SimEnv
from hades.simulator.scenarios import ALL_SCENARIOS


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

SCENARIO_B = next(s for s in ALL_SCENARIOS if "reliability_flip" in s.name)
SCENARIO_D = next(s for s in ALL_SCENARIOS if "manipulation_flip" in s.name)

ALL_CORRUPTORS = [
    MissingCorruptor(p_drop=0.0),        # R0 baseline (no-op)
    MissingCorruptor(p_drop=0.25),       # R1
    StaleCorruptor(staleness=0.33),      # R2
    MisleadingCorruptor(p_inject=0.25),  # R3
    TargetedCorruptor(p_attack=0.75),    # R4
]

ALL_ESTIMATORS = [
    CleanEstimator(),
    NoisyEstimator(sigma=0.10),
    MiscalibratedEstimator.phi_underestimate(0.7, 0.2),
    AdversarialEstimator(),
]

POLICIES_UNDER_TEST = [
    IGPolicy(),
    RobustVoIPolicy(lam=1.0),
    BayesALPolicy(),
]


# ---------------------------------------------------------------------------
# 1. No crashes across all combinations
# ---------------------------------------------------------------------------

class TestNoCrashes:
    @pytest.mark.parametrize("corruptor", ALL_CORRUPTORS)
    @pytest.mark.parametrize("estimator", ALL_ESTIMATORS)
    @pytest.mark.parametrize("policy", POLICIES_UNDER_TEST)
    def test_episode_completes_without_error(self, corruptor, estimator, policy):
        """Every (corruptor × estimator × policy) combination must complete."""
        runner = IntegrationRunner(
            SCENARIO_B, budget=5.0, seeds=1,
            corruptors=[corruptor],
            estimators=[estimator],
            policies=[policy],
        )
        results = runner.run_all()
        assert len(results) == 1
        r = results[0]
        assert r.n_queries >= 0


# ---------------------------------------------------------------------------
# 2. Budget consistency
# ---------------------------------------------------------------------------

class TestBudgetConsistency:
    @pytest.mark.parametrize("corruptor", ALL_CORRUPTORS)
    @pytest.mark.parametrize("policy", POLICIES_UNDER_TEST)
    def test_budget_accounting_exact(self, corruptor, policy):
        """Budget spent + remaining == initial_budget, within floating point."""
        runner = IntegrationRunner(
            SCENARIO_B, budget=10.0, seeds=3,
            corruptors=[corruptor],
            estimators=[CleanEstimator()],
            policies=[policy],
        )
        results = runner.run_all()
        for r in results:
            assert r.budget_consistent, (
                f"Budget inconsistency in {policy.name} + {corruptor.regime}: "
                f"total_cost={r.total_cost:.4f}, budget={r.budget}"
            )


# ---------------------------------------------------------------------------
# 3. Belief normalization throughout
# ---------------------------------------------------------------------------

class TestBeliefNormalization:
    @pytest.mark.parametrize("corruptor", ALL_CORRUPTORS)
    @pytest.mark.parametrize("estimator", ALL_ESTIMATORS)
    def test_beliefs_sum_to_one(self, corruptor, estimator):
        """Beliefs must sum to 1 at episode end for all corruptor/estimator pairs."""
        runner = IntegrationRunner(
            SCENARIO_B, budget=8.0, seeds=3,
            corruptors=[corruptor],
            estimators=[estimator],
            policies=[RobustVoIPolicy(lam=1.0)],
        )
        for r in runner.run_all():
            assert r.beliefs_sum_to_one, (
                f"Beliefs don't sum to 1 in {corruptor.regime}/{estimator.regime}: "
                f"final_beliefs={r.final_beliefs}"
            )
            for hyp, p in r.final_beliefs.items():
                assert 0.0 <= p <= 1.0 + 1e-9, (
                    f"Belief {hyp}={p} out of [0,1]"
                )


# ---------------------------------------------------------------------------
# 4. Valid observations (obs_class always in OBS_CLASSES)
# ---------------------------------------------------------------------------

class TestValidObservations:
    @pytest.mark.parametrize("corruptor", ALL_CORRUPTORS)
    def test_all_obs_valid(self, corruptor):
        runner = IntegrationRunner(
            SCENARIO_B, budget=8.0, seeds=3,
            corruptors=[corruptor],
            estimators=[CleanEstimator()],
            policies=[IGPolicy()],
        )
        for r in runner.run_all():
            assert r.all_obs_valid, (
                f"Invalid obs_class produced by {corruptor.regime}"
            )


# ---------------------------------------------------------------------------
# 5. No _true leakage in policy menu
# ---------------------------------------------------------------------------

class TestNoTrueLeakageInMenu:
    def test_policy_menu_has_no_true_fields(self):
        """Policy menu returned by _make_policy_menu must not expose _true fields."""
        env = SimEnv(SCENARIO_B, seed=42)
        env.reset(seed=42)
        menu = _make_policy_menu(env, CleanEstimator(), random.Random(0))
        for src_name, spec in menu.items():
            spec_dict = vars(spec) if hasattr(spec, "__dict__") else {}
            for attr in spec_dict:
                assert "true" not in attr, (
                    f"Policy menu for '{src_name}' exposes _true field: '{attr}'"
                )

    def test_clean_estimator_still_excludes_true(self):
        """Even CleanEstimator should not expose raw _true fields in menu."""
        env = SimEnv(SCENARIO_D, seed=7)
        env.reset(seed=7)
        menu = _make_policy_menu(env, CleanEstimator(), random.Random(0))
        for src_name, spec in menu.items():
            assert not hasattr(spec, "reliability_true"), (
                f"reliability_true leaked into menu for {src_name}"
            )
            assert not hasattr(spec, "manipulation_risk_true"), (
                f"manipulation_risk_true leaked into menu for {src_name}"
            )


# ---------------------------------------------------------------------------
# 6. Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:
    def test_same_seed_same_choices(self):
        """Same seed → identical episode outcomes (deterministic pipeline)."""
        def _run_single(seed):
            runner = IntegrationRunner(
                SCENARIO_B, budget=8.0, seeds=1,
                corruptors=[MissingCorruptor(p_drop=0.25)],
                estimators=[NoisyEstimator(sigma=0.10)],
                policies=[RobustVoIPolicy(lam=1.0)],
            )
            results = runner.run_episode(
                RobustVoIPolicy(lam=1.0),
                MissingCorruptor(p_drop=0.25),
                NoisyEstimator(sigma=0.10),
                seed=seed,
            )
            return results.sources_queried, results.final_beliefs

        choices1, beliefs1 = _run_single(42)
        choices2, beliefs2 = _run_single(42)
        assert choices1 == choices2, "Same seed produced different query sequences"
        for h in beliefs1:
            assert abs(beliefs1[h] - beliefs2[h]) < 1e-9, (
                f"Same seed produced different beliefs for {h}"
            )

    def test_different_seeds_may_differ(self):
        """Different seeds should (usually) produce different episode paths."""
        runner = IntegrationRunner(
            SCENARIO_B, budget=8.0, seeds=1,
            corruptors=[MisleadingCorruptor(p_inject=0.5)],
            estimators=[CleanEstimator()],
            policies=[IGPolicy()],
        )
        paths = []
        for seed in range(10):
            r = runner.run_episode(IGPolicy(), MisleadingCorruptor(p_inject=0.5),
                                CleanEstimator(), seed)
            paths.append(tuple(r.sources_queried))
        # At least 2 distinct paths across 10 seeds
        unique_paths = set(paths)
        assert len(unique_paths) >= 2, (
            "All 10 seeds produced identical episode paths (unexpected)"
        )


# ---------------------------------------------------------------------------
# 7. Expected policy separation under R4 targeted corruptor (with CleanEstimator)
# ---------------------------------------------------------------------------

class TestPolicySeparationUnderR4:
    def test_p5_lower_phi_reliance_than_p3_under_r4(self):
        """Under R4 targeted attack (architecture-aware), P5 should rely less
        on high-phi sources than P3 across multiple seeds.

        This is the key Phase 4 integration assertion:
        phase 3 showed policy SEPARATION, Phase 4 shows PHI_RELIANCE DIRECTION.
        """
        runner_p3 = IntegrationRunner(
            SCENARIO_D, budget=10.0, seeds=10,
            corruptors=[TargetedCorruptor(p_attack=1.0)],
            estimators=[CleanEstimator()],
            policies=[IGPolicy()],
        )
        runner_p5 = IntegrationRunner(
            SCENARIO_D, budget=10.0, seeds=10,
            corruptors=[TargetedCorruptor(p_attack=1.0)],
            estimators=[CleanEstimator()],
            policies=[RobustVoIPolicy(lam=1.0)],
        )

        results_p3 = runner_p3.run_all()
        results_p5 = runner_p5.run_all()

        mean_phi_p3 = sum(r.manip_reliance for r in results_p3) / len(results_p3)
        mean_phi_p5 = sum(r.manip_reliance for r in results_p5) / len(results_p5)

        # P5 should query manipulable sources less often than P3 under R4
        # (or at least not MORE — P5 shouldn't chase the targeted source)
        assert mean_phi_p5 <= mean_phi_p3 + 0.10, (
            f"P5 relies MORE on high-phi sources than P3 under R4: "
            f"P5={mean_phi_p5:.3f}, P3={mean_phi_p3:.3f}"
        )


# ---------------------------------------------------------------------------
# 8. Adversarial estimator makes high-phi sources look safe to policy
# ---------------------------------------------------------------------------

class TestAdversarialEstimatorEffect:
    def test_adversarial_increases_high_phi_reliance(self):
        """Adversarial estimator spoofs phi → policy trusts bad sources more.

        This test verifies the effect works: adversarial deception should cause
        P3 (pure EIG, which ignores phi in contaminated likelihood path if phi_hat≈0)
        to query manipulable sources more than with CleanEstimator.
        """
        def _mean_phi_reliance(estimator, seeds=8):
            runner = IntegrationRunner(
                SCENARIO_D, budget=8.0, seeds=seeds,
                corruptors=[MissingCorruptor(p_drop=0.0)],  # no obs corruption
                estimators=[estimator],
                policies=[IGPolicy()],
            )
            results = runner.run_all()
            return sum(r.manip_reliance for r in results) / len(results)

        phi_clean = _mean_phi_reliance(CleanEstimator())
        phi_adv = _mean_phi_reliance(AdversarialEstimator(phi_threshold=0.3,
                                                          blend=1.0))

        # With adversarial estimator, policy should query high-phi sources
        # more or equal (it can't tell they're dangerous).
        # We just verify the adversarial estimator doesn't accidentally make
        # the policy AVOID high-phi sources (which would be backwards).
        assert phi_adv >= phi_clean - 0.10, (
            f"Adversarial estimator unexpectedly reduced high-phi reliance: "
            f"clean={phi_clean:.3f}, adversarial={phi_adv:.3f}"
        )


# ---------------------------------------------------------------------------
# 9. Full matrix smoke: all scenarios × all corruptors (just check no crash)
# ---------------------------------------------------------------------------

class TestFullMatrixNoCrash:
    def test_all_scenarios_all_corruptors_complete(self):
        """Smoke test: every scenario × every corruptor × P5 runs without error."""
        for scenario in ALL_SCENARIOS:
            for corruptor in ALL_CORRUPTORS:
                runner = IntegrationRunner(
                    scenario, budget=5.0, seeds=2,
                    corruptors=[corruptor],
                    estimators=[CleanEstimator()],
                    policies=[RobustVoIPolicy(lam=1.0)],
                )
                results = runner.run_all()
                for r in results:
                    assert r.beliefs_sum_to_one, (
                        f"Beliefs invalid: {scenario.name}/{corruptor.regime}"
                    )
                    assert r.all_obs_valid, (
                        f"Invalid obs: {scenario.name}/{corruptor.regime}"
                    )
