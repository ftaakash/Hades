"""
tests/test_simulator.py
------------------------
Unit tests for the HADES minimal simulator.

Tests cover:
  1. SimEvidenceSource field validation
  2. SimEnv: reset, step, belief update, probability invariant
  3. ObservationModel: positive/negative probs sum to 1, sampling
  4. Information gain: monotonicity, boundary cases
  5. Scenario A: IG ≈ ERHG when reliability identical
  6. Scenario B: reliability flip (core G1 mechanism)
  7. Scenario C: cost flip
  8. Scenario D: manipulation risk flip
  9. Scenario E: all equal → no meaningful difference
 10. Evaluator truth never leaks into policy-visible state
"""
from __future__ import annotations

import math
import pytest

# Make sure imports work from repo root
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hades.simulator.environment import SimEnv, SimEvidenceSource, SimScenario, _normalize
from hades.simulator.observations import ObservationModel, OBS_CLASSES, DEFAULT_OBS_MODEL
from hades.simulator.scenarios import (
    SCENARIO_A_NO_RELIABILITY_DIFF,
    SCENARIO_B_RELIABILITY_FLIP,
    SCENARIO_C_COST_FLIP,
    SCENARIO_D_MANIPULATION_FLIP,
    SCENARIO_E_NO_DISTINCTION,
    ALL_SCENARIOS,
    HYPOTHESES,
)


# ==========================================================================
# 1. SimEvidenceSource validation
# ==========================================================================

class TestSimEvidenceSource:
    def _valid_src(self, **overrides) -> SimEvidenceSource:
        kw = dict(
            name="test_src",
            cost=1.0,
            reliability_true=0.85,
            reliability_estimated=0.80,
            manipulation_risk_true=0.15,
            manipulation_risk_estimated=0.15,
            hypothesis_affinity={"H1": 0.8, "H2": 0.3},
        )
        kw.update(overrides)
        return SimEvidenceSource(**kw)

    def test_valid_source_creates(self):
        src = self._valid_src()
        assert src.name == "test_src"
        assert src.cost == 1.0

    def test_zero_cost_raises(self):
        with pytest.raises(AssertionError):
            self._valid_src(cost=0.0)

    def test_reliability_out_of_range_raises(self):
        with pytest.raises(AssertionError):
            self._valid_src(reliability_true=1.5)

    def test_manip_risk_out_of_range_raises(self):
        with pytest.raises(AssertionError):
            self._valid_src(manipulation_risk_estimated=-0.1)

    def test_affinity_out_of_range_raises(self):
        with pytest.raises(AssertionError):
            self._valid_src(hypothesis_affinity={"H1": 1.1})

    def test_reliability_and_manip_risk_are_independent(self):
        """A source can have high reliability but high manipulation risk."""
        src = self._valid_src(reliability_true=0.99, manipulation_risk_true=0.95)
        assert src.reliability_true == 0.99
        assert src.manipulation_risk_true == 0.95


# ==========================================================================
# 2. SimEnv: reset and step
# ==========================================================================

class TestSimEnvBasics:
    def test_reset_returns_uniform_beliefs(self):
        env = SimEnv(SCENARIO_A_NO_RELIABILITY_DIFF, seed=0)
        obs = env.reset()
        beliefs = obs.belief_distribution
        expected = 1.0 / len(HYPOTHESES)
        for h in HYPOTHESES:
            assert abs(beliefs[h] - expected) < 1e-9

    def test_step_consumes_budget(self):
        env = SimEnv(SCENARIO_A_NO_RELIABILITY_DIFF, seed=0, budget=10.0)
        env.reset(true_hypothesis="H_execution")
        env.step("auth_events")  # cost = 1.0
        assert abs(env.remaining_budget - 9.0) < 1e-9

    def test_step_increments_query_count(self):
        env = SimEnv(SCENARIO_A_NO_RELIABILITY_DIFF, seed=0)
        env.reset(true_hypothesis="H_execution")
        env.step("auth_events")
        env.step("process_events")
        assert env.queries_used == 2

    def test_step_without_reset_raises(self):
        env = SimEnv(SCENARIO_A_NO_RELIABILITY_DIFF, seed=0)
        with pytest.raises(RuntimeError):
            env.step("auth_events")

    def test_step_insufficient_budget_raises(self):
        env = SimEnv(SCENARIO_A_NO_RELIABILITY_DIFF, seed=0, budget=0.5)
        env.reset(true_hypothesis="H_execution")
        with pytest.raises(RuntimeError):
            env.step("auth_events")  # cost = 1.0

    def test_step_unknown_source_raises(self):
        env = SimEnv(SCENARIO_A_NO_RELIABILITY_DIFF, seed=0)
        env.reset(true_hypothesis="H_execution")
        with pytest.raises(KeyError):
            env.step("nonexistent_source")

    def test_probability_invariant_maintained(self):
        """Beliefs must always sum to 1 after each step."""
        env = SimEnv(SCENARIO_B_RELIABILITY_FLIP, seed=42, budget=20.0)
        env.reset(true_hypothesis="H_lateral_movement")
        for src in env.sources:
            if env.remaining_budget >= src.cost:
                env.step(src.name)
                total = sum(env.beliefs.values())
                assert abs(total - 1.0) < 1e-6, f"Invariant violated: sum={total}"

    def test_identical_seed_produces_identical_results(self):
        """Determinism: same seed → same observation sequence."""
        env1 = SimEnv(SCENARIO_B_RELIABILITY_FLIP, seed=7)
        env1.reset(true_hypothesis="H_execution")
        obs1 = env1.step("auth_events")

        env2 = SimEnv(SCENARIO_B_RELIABILITY_FLIP, seed=7)
        env2.reset(true_hypothesis="H_execution")
        obs2 = env2.step("auth_events")

        assert obs1.obs_class == obs2.obs_class


# ==========================================================================
# 3. ObservationModel
# ==========================================================================

class TestObservationModel:
    def test_positive_probs_sum_to_one(self):
        s = sum(DEFAULT_OBS_MODEL.positive_probs.values())
        assert abs(s - 1.0) < 1e-9

    def test_negative_probs_sum_to_one(self):
        s = sum(DEFAULT_OBS_MODEL.negative_probs.values())
        assert abs(s - 1.0) < 1e-9

    def test_invalid_probs_raises(self):
        with pytest.raises(ValueError):
            ObservationModel(
                name="bad",
                positive_probs={"strong_support": 0.5, "neutral": 0.3},  # doesn't sum to 1
                negative_probs={"strong_support": 0.5, "neutral": 0.5},
            )

    def test_unknown_obs_class_raises(self):
        with pytest.raises(ValueError):
            ObservationModel(
                name="bad2",
                positive_probs={"UNKNOWN_CLASS": 1.0},
                negative_probs={"neutral": 1.0},
            )

    def test_sample_returns_valid_class(self):
        import random
        rng = random.Random(0)
        for _ in range(100):
            cls = DEFAULT_OBS_MODEL.sample(
                rng, is_relevant=True,
                reliability_true=0.9,
                manipulation_risk_true=0.1,
            )
            assert cls in OBS_CLASSES

    def test_high_reliability_returns_more_signal(self):
        """High reliability → more non-neutral observations."""
        import random
        rng = random.Random(42)
        neutral_count_high = sum(
            1 for _ in range(1000)
            if DEFAULT_OBS_MODEL.sample(rng, is_relevant=True,
               reliability_true=0.99, manipulation_risk_true=0.0) == "neutral"
        )
        rng2 = random.Random(42)
        neutral_count_low = sum(
            1 for _ in range(1000)
            if DEFAULT_OBS_MODEL.sample(rng2, is_relevant=True,
               reliability_true=0.10, manipulation_risk_true=0.0) == "neutral"
        )
        assert neutral_count_high < neutral_count_low

    def test_reliability_and_manip_risk_are_independent(self):
        """
        Targeted-attack override (strong_contra) depends on manipulation_risk,
        independent of reliability_true.  With manip=0.0, no attack overrides
        occur regardless of reliability.  With manip=1.0, ALL observations are
        overridden to strong_contra regardless of reliability.
        """
        import random
        # manip=0.0 under targeted attack -> attack override never fires
        rng = random.Random(0)
        no_attack = [
            DEFAULT_OBS_MODEL.sample(rng, is_relevant=True,
               reliability_true=1.0, manipulation_risk_true=0.0,
               under_targeted_attack=True)
            for _ in range(500)
        ]
        # manip=1.0 under targeted attack -> ALL are strong_contra
        rng2 = random.Random(0)
        full_attack = [
            DEFAULT_OBS_MODEL.sample(rng2, is_relevant=True,
               reliability_true=1.0, manipulation_risk_true=1.0,
               under_targeted_attack=True)
            for _ in range(500)
        ]
        # With manip=0, zero attack overrides (strong_contra from attack path)
        # Note: strong_contra can still appear from negative_probs, but with
        # reliability=1.0 and is_relevant=True, positive_probs are used, so
        # strong_contra prob is only 0.03 from nominal draw.
        attack_override_count_no = sum(1 for c in no_attack if c == "strong_contra")
        attack_override_count_full = sum(1 for c in full_attack if c == "strong_contra")
        # With manip=1 ALL should be strong_contra; with manip=0 << all
        assert all(c == "strong_contra" for c in full_attack), (
            "With manip=1.0 ALL observations should be strong_contra (attack override)"
        )
        assert attack_override_count_no < 100, (
            f"With manip=0, expected few strong_contra, got {attack_override_count_no}/500"
        )


# ==========================================================================
# 4. Information Gain: monotonicity and boundaries
# ==========================================================================

class TestInformationGain:
    def test_ig_nonnegative(self):
        env = SimEnv(SCENARIO_B_RELIABILITY_FLIP, seed=0)
        env.reset(true_hypothesis="H_lateral_movement")
        for src in env.sources:
            ig = env.expected_ig(src.name)
            assert ig >= 0.0, f"IG({src.name}) = {ig} < 0"

    def test_ig_zero_when_uniform_and_no_distinction(self):
        """Scenario E: all sources have equal affinity → IGs should be equal."""
        env = SimEnv(SCENARIO_E_NO_DISTINCTION, seed=0)
        env.reset(true_hypothesis="H_execution")
        igs = [env.expected_ig(s.name) for s in env.sources]
        assert max(igs) - min(igs) < 1e-9, f"Scenario E IGs differ: {igs}"

    def test_erhg_le_ig_for_any_source(self):
        """ERHG = IG × reliability_estimated ≤ IG since reliability ≤ 1."""
        env = SimEnv(SCENARIO_B_RELIABILITY_FLIP, seed=5)
        env.reset(true_hypothesis="H_lateral_movement")
        for src in env.sources:
            ig = env.expected_ig(src.name)
            erhg = env.expected_reliable_ig(src.name)
            assert erhg <= ig + 1e-9, f"ERHG > IG for {src.name}: {erhg} > {ig}"


# ==========================================================================
# 5-8. Order-flip scenarios
# ==========================================================================

def _pick(env, policy):
    scores = {
        s.name: policy(env, s) for s in env.sources
    }
    return max(scores, key=lambda k: (scores[k], k))


def p3_ig(env, src): return env.expected_ig(src.name)
def p4_ic(env, src): return env.expected_ig(src.name) / src.cost
def p4b_erhg(env, src): return env.expected_ig(src.name) * src.reliability_estimated / src.cost
def p5_hades(env, src, lam=1.0, mu=1.0): return env.hades_utility(src.name, lam, mu)


class TestScenarioA:
    def test_ig_equals_erhg_choice(self):
        """When reliability identical, IG and ERHG should pick the same source."""
        env = SimEnv(SCENARIO_A_NO_RELIABILITY_DIFF, seed=0)
        for hyp in HYPOTHESES:
            env.reset(true_hypothesis=hyp, seed=0)
            choice_ig = _pick(env, p3_ig)
            choice_erhg = _pick(env, p4b_erhg)
            assert choice_ig == choice_erhg, (
                f"Scenario A: IG→{choice_ig} ≠ ERHG→{choice_erhg} for hyp={hyp}. "
                f"Reliability differs unexpectedly."
            )


class TestScenarioB:
    def test_reliability_flip_exists(self):
        """
        G1 v3.0 core test: reliability enters contaminated likelihood, NOT as
        a post-hoc multiplier.

        process_tree: r_hat=0.50, discriminating (high affinity to H_execution only)
        auth_events:  r_hat=0.90, broadly relevant

        Under Bayesian EIG with contaminated likelihood:
        - process_tree's signal is attenuated by r_hat=0.50 -> noisy EIG
        - auth_events has higher r_hat -> less attenuation -> higher or comparable EIG

        Key assertion: auth_events EIG > process_tree EIG (reliability flip).
        A policy that ignores reliability and only looks at raw affinity would
        prefer process_tree; EIG correctly accounts for reliability.
        """
        env = SimEnv(SCENARIO_B_RELIABILITY_FLIP, seed=0)
        env.reset(true_hypothesis="H_execution", seed=0)

        ig_auth = env.expected_ig("auth_events")
        ig_process = env.expected_ig("process_tree")

        # auth_events (r_hat=0.90) should have HIGHER EIG than process_tree (r_hat=0.50)
        # even though process_tree is more discriminating in its affinity structure.
        # This IS the reliability flip: reliability inside EIG changes relative ordering.
        assert ig_auth > ig_process, (
            f"Reliability flip: auth_events (r_hat=0.90) should have higher EIG than "
            f"process_tree (r_hat=0.50). auth={ig_auth:.4f}, process={ig_process:.4f}"
        )

        # VoI (P5) should also prefer auth_events since cost is equal
        voi_auth = env.voi("auth_events", lam=1.0)
        voi_process = env.voi("process_tree", lam=1.0)
        assert voi_auth > voi_process, (
            f"VoI should also prefer auth_events over process_tree. "
            f"voi_auth={voi_auth:.4f}, voi_process={voi_process:.4f}"
        )

    def test_erhg_alone_flips_order(self):
        """
        In v3.0, expected_reliable_ig() == expected_ig() (reliability is inside EIG).
        This test verifies that auth_events scores higher than process_tree for both
        methods — consistent ordering is the v3.0 flip mechanism.
        """
        env = SimEnv(SCENARIO_B_RELIABILITY_FLIP, seed=0)
        env.reset(true_hypothesis="H_execution", seed=0)
        ig_auth = env.expected_ig("auth_events")
        ig_process = env.expected_ig("process_tree")
        erhg_auth = env.expected_reliable_ig("auth_events")
        erhg_process = env.expected_reliable_ig("process_tree")
        # Both methods should agree on the ordering
        assert ig_auth > ig_process, (
            f"EIG: auth({ig_auth:.4f}) should beat process_tree({ig_process:.4f}) via reliability"
        )
        assert erhg_auth > erhg_process, (
            f"ERHG: auth({erhg_auth:.4f}) should beat process_tree({erhg_process:.4f})"
        )
        # And they should agree with each other (v3.0 equivalence)
        assert ig_auth == erhg_auth, "expected_ig and expected_reliable_ig should be equal in v3.0"


class TestScenarioC:
    def test_cost_flip_exists(self):
        """
        IG should prefer expensive_auth (highest IG absolute value);
        IG/cost should prefer cheap_process or powershell_events
        (much lower cost makes them dominant on cost-normalized basis).
        """
        env = SimEnv(SCENARIO_C_COST_FLIP, seed=0)
        env.reset(true_hypothesis="H_lateral_movement", seed=0)
        choice_ig = _pick(env, p3_ig)
        choice_ic = _pick(env, p4_ic)
        # expensive_auth has highest raw IG (high affinity + r_hat=0.90)
        assert choice_ig == "expensive_auth", (
            f"Expected IG->expensive_auth (highest raw EIG), got {choice_ig}. "
            f"Scores: {[(s.name, round(env.expected_ig(s.name),4)) for s in env.sources]}"
        )
        # IC ordering: expensive_auth IC = IG/4.0 is much lower than cheap sources
        assert choice_ic != choice_ig, (
            f"Cost flip: IG/cost policy should differ from raw IG policy. "
            f"Both picked {choice_ig}"
        )


class TestScenarioD:
    def test_manip_risk_flip_independent_of_reliability(self):
        """
        v3.0 reframed Scenario D:
        trusted_sensor and forgeable_sysmon have identical r_hat=0.85, same affinities.

        In CLEAN regime (under_targeted_attack=False):
        - phi_hat has NO effect on EIG (contaminated_likelihood uses it only under attack)
        - EIG and VoI are IDENTICAL -> policy is indifferent
        This is CORRECT v3.0 behavior: adversarial corruption is regime-gated.

        Under TARGETED ATTACK regime (under_targeted_attack=True):
        - forgeable_sysmon (phi_hat=0.85) gets contaminated with strong_contra -> lower EIG
        - trusted_sensor (phi_hat=0.02) stays high -> higher EIG
        This tests manipulation_risk as independent decision axis via likelihood (not mu).
        """
        from hades.belief.value import eig as _eig
        from hades.belief.likelihood import make_default_table

        env = SimEnv(SCENARIO_D_MANIPULATION_FLIP, seed=0)
        env.reset(true_hypothesis="H_lateral_movement", seed=0)

        # --- Clean regime: EIG should be identical ---
        ig_trusted_clean = env.expected_ig("trusted_sensor")
        ig_forgeable_clean = env.expected_ig("forgeable_sysmon")
        assert abs(ig_trusted_clean - ig_forgeable_clean) < 1e-9, (
            f"In clean regime, EIG should be equal (phi_hat has no effect). "
            f"trusted={ig_trusted_clean:.6f}, forgeable={ig_forgeable_clean:.6f}"
        )

        # --- Targeted attack regime: compute EIG manually with under_targeted_attack=True ---
        src_t = env._get_source("trusted_sensor")
        src_f = env._get_source("forgeable_sysmon")
        beliefs = dict(env._beliefs)

        table_t = make_default_table(
            ["trusted_sensor"], env.hypotheses,
            {("trusted_sensor", h): src_t.hypothesis_affinity.get(h, 0.0) for h in env.hypotheses}
        )
        table_f = make_default_table(
            ["forgeable_sysmon"], env.hypotheses,
            {("forgeable_sysmon", h): src_f.hypothesis_affinity.get(h, 0.0) for h in env.hypotheses}
        )

        ig_trusted_attacked = _eig(
            source="trusted_sensor", beliefs=beliefs, table=table_t,
            r_hat=src_t.reliability_estimated, phi_hat=src_t.manipulation_risk_estimated,
            source_relevance={h: src_t.hypothesis_affinity.get(h, 0.0) for h in env.hypotheses},
            under_targeted_attack=True,
        )
        ig_forgeable_attacked = _eig(
            source="forgeable_sysmon", beliefs=beliefs, table=table_f,
            r_hat=src_f.reliability_estimated, phi_hat=src_f.manipulation_risk_estimated,
            source_relevance={h: src_f.hypothesis_affinity.get(h, 0.0) for h in env.hypotheses},
            under_targeted_attack=True,
        )

        assert ig_trusted_attacked > ig_forgeable_attacked, (
            f"Under targeted attack, trusted_sensor (phi=0.02) should have higher EIG "
            f"than forgeable_sysmon (phi=0.85). "
            f"trusted={ig_trusted_attacked:.4f}, forgeable={ig_forgeable_attacked:.4f}"
        )


class TestScenarioE:
    def test_all_policies_equivalent_when_no_distinction(self):
        """All sources identical → all policies choose same (alphabetical first)."""
        env = SimEnv(SCENARIO_E_NO_DISTINCTION, seed=0)
        env.reset(true_hypothesis="H_execution", seed=0)

        choice_ig = _pick(env, p3_ig)
        choice_ic = _pick(env, p4_ic)
        choice_erhg = _pick(env, p4b_erhg)
        choice_hades = _pick(env, lambda e, s: p5_hades(e, s, 1.0, 1.0))

        assert choice_ig == choice_ic == choice_erhg == choice_hades, (
            f"Scenario E: policies should be equivalent. "
            f"IG={choice_ig}, IC={choice_ic}, ERHG={choice_erhg}, HADES={choice_hades}"
        )


# ==========================================================================
# 9. Evaluator truth leakage
# ==========================================================================

class TestLeakage:
    def test_policy_observation_has_no_evaluator_fields(self):
        """PolicyObservation must not expose true_hypothesis or reliability_true."""
        from hades.simulator.environment import PolicyObservation
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(PolicyObservation)}
        prohibited = {"true_hypothesis", "reliability_true", "manipulation_risk_true",
                      "corruption_regime", "evaluator_truth"}
        leaked = field_names & prohibited
        assert not leaked, f"PolicyObservation leaks evaluator fields: {leaked}"

    def test_evidence_source_exposes_both_true_and_estimated(self):
        """Confirms we have distinct true vs estimated fields."""
        src = SCENARIO_B_RELIABILITY_FLIP.sources[0]
        assert hasattr(src, "reliability_true")
        assert hasattr(src, "reliability_estimated")
        assert hasattr(src, "manipulation_risk_true")
        assert hasattr(src, "manipulation_risk_estimated")
        # In Scenario B, they intentionally differ
        assert src.reliability_true != src.reliability_estimated or \
               src.name not in ("process_tree",)

    def test_evaluator_truth_is_separate(self):
        """evaluator_truth() should not be exposed through policy-facing methods."""
        env = SimEnv(SCENARIO_B_RELIABILITY_FLIP, seed=0)
        env.reset(true_hypothesis="H_execution")
        pol_obs = env.step("auth_events")
        # PolicyObservation should not have evaluator_info
        assert not hasattr(pol_obs, "evaluator_info")
        assert not hasattr(pol_obs, "true_hypothesis")


# ==========================================================================
# 10. All scenarios: sanity
# ==========================================================================

class TestAllScenarios:
    def test_all_scenarios_have_valid_structure(self):
        for sc in ALL_SCENARIOS:
            assert len(sc.hypotheses) >= 2
            assert len(sc.sources) >= 2
            for src in sc.sources:
                assert src.cost > 0

    def test_all_scenarios_reset_and_step(self):
        for sc in ALL_SCENARIOS:
            env = SimEnv(sc, seed=0, budget=20.0)
            env.reset(true_hypothesis=sc.hypotheses[0])
            obs = env.step(sc.sources[0].name)
            assert obs.obs_class in OBS_CLASSES
            assert abs(sum(obs.belief_distribution.values()) - 1.0) < 1e-6
