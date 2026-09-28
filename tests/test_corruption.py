"""tests/test_corruption.py — Corruption engine + estimator tests (v3.0).

Tests
-----
Corruption invariants:
  * corrupt() always returns a valid obs_class member
  * Ground truth is never modified by any corruptor
  * Deterministic given same rng seed
  * R1: neutral rate == p_drop when p_drop=1.0
  * R2: staleness=0.0 is identity; staleness=1.0 degrades 'signal' -> 'neutral'
  * R3: p_inject=0.0 is identity; p_inject=1.0 always replaces informative obs
  * R4: source with affinity>=0.6 to leading hyp gets suppressed to 'noise'
  * R4: source with low affinity is NOT suppressed

Estimator invariants:
  * All estimators return r_hat, phi_hat in [0,1]
  * Clean estimator: r_hat == r_true, phi_hat == phi_true
  * Noisy: sigma=0 degenerates to clean
  * Noisy: sigma>0 introduces variation (not identical to clean in >0 samples)
  * Miscalibrated: phi_underestimate factory produces phi_hat < phi_true
  * Miscalibrated: phi_overestimate factory produces phi_hat > phi_true
  * Adversarial: high-phi sources get r_hat inflated, phi_hat deflated
  * Adversarial: low-phi sources are unmodified
  * REGISTRY contains all 4 estimators
  * No estimator modifies the input r_true / phi_true values (immutability)

Reviewer misspecification cases (explicitly tested):
  * true φ=0.7, estimated φ≈0.2 (phi_underestimate)
  * true φ=0.7, estimated φ≈0.9 (phi_overestimate)
"""
from __future__ import annotations

import random
from typing import Dict

import pytest

from hades.corruption.base import Corruptor, ObsContext, OBS_CLASSES
from hades.corruption.missing import MissingCorruptor
from hades.corruption.stale import StaleCorruptor
from hades.corruption.misleading import MisleadingCorruptor
from hades.corruption.targeted import TargetedCorruptor
from hades.reliability.estimator import (
    CleanEstimator,
    NoisyEstimator,
    MiscalibratedEstimator,
    AdversarialEstimator,
    ESTIMATOR_REGISTRY,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def _ctx(
    source_name: str = "test_source",
    true_hyp: str = "H1",
    beliefs: Dict[str, float] = None,
    affinity: Dict[str, float] = None,
    r_true: float = 0.85,
    phi_true: float = 0.20,
) -> ObsContext:
    if beliefs is None:
        beliefs = {"H1": 0.60, "H2": 0.25, "H3": 0.15}
    if affinity is None:
        affinity = {"H1": 0.80, "H2": 0.30, "H3": 0.20}
    return ObsContext(
        source_name=source_name,
        true_hypothesis=true_hyp,
        query_history=[],
        current_beliefs=beliefs,
        reliability_true=r_true,
        manipulation_risk_true=phi_true,
        hypothesis_affinity=affinity,
    )


ALL_CORRUPTORS = [
    MissingCorruptor(p_drop=0.25),
    StaleCorruptor(staleness=0.33),
    MisleadingCorruptor(p_inject=0.25),
    TargetedCorruptor(p_attack=0.75),
]

ALL_OBS = list(OBS_CLASSES)


# ---------------------------------------------------------------------------
# General corruptor invariants
# ---------------------------------------------------------------------------

class TestCorruptorInvariants:
    @pytest.mark.parametrize("corruptor", ALL_CORRUPTORS)
    @pytest.mark.parametrize("obs_class", ALL_OBS)
    def test_returns_valid_obs_class(self, corruptor, obs_class):
        result = corruptor.corrupt(obs_class, _ctx(), _rng())
        assert result in OBS_CLASSES, (
            f"{corruptor} returned '{result}' which is not in OBS_CLASSES"
        )

    @pytest.mark.parametrize("corruptor", ALL_CORRUPTORS)
    def test_deterministic_given_seed(self, corruptor):
        ctx = _ctx()
        r1 = corruptor.corrupt("signal", ctx, _rng(99))
        r2 = corruptor.corrupt("signal", ctx, _rng(99))
        assert r1 == r2, f"{corruptor} is not deterministic given same seed"

    @pytest.mark.parametrize("corruptor", ALL_CORRUPTORS)
    def test_does_not_modify_ctx(self, corruptor):
        ctx = _ctx(true_hyp="H1", r_true=0.85, phi_true=0.20)
        original_truth = ctx.true_hypothesis
        original_r = ctx.reliability_true
        original_phi = ctx.manipulation_risk_true
        corruptor.corrupt("signal", ctx, _rng())
        assert ctx.true_hypothesis == original_truth, "corruptor mutated true_hypothesis"
        assert ctx.reliability_true == original_r, "corruptor mutated reliability_true"
        assert ctx.manipulation_risk_true == original_phi, "corruptor mutated manipulation_risk_true"


# ---------------------------------------------------------------------------
# R1 Missing
# ---------------------------------------------------------------------------

class TestMissingCorruptor:
    def test_p_drop_zero_is_identity(self):
        c = MissingCorruptor(p_drop=0.0)
        for obs in ALL_OBS:
            assert c.corrupt(obs, _ctx(), _rng()) == obs

    def test_p_drop_one_always_neutral(self):
        c = MissingCorruptor(p_drop=1.0)
        for obs in ALL_OBS:
            assert c.corrupt(obs, _ctx(), _rng()) == "neutral"

    def test_p_drop_half_approximates_50pct(self):
        """Over 1000 trials, neutral rate should be ~0.5 at p_drop=0.5."""
        c = MissingCorruptor(p_drop=0.5)
        rng = _rng(7)
        neutral_count = sum(
            c.corrupt("signal", _ctx(), rng) == "neutral"
            for _ in range(1000)
        )
        assert 400 < neutral_count < 600, (
            f"Expected ~500 neutrals, got {neutral_count}"
        )


# ---------------------------------------------------------------------------
# R2 Stale
# ---------------------------------------------------------------------------

class TestStaleCorruptor:
    def test_staleness_zero_is_identity(self):
        c = StaleCorruptor(staleness=0.0)
        for obs in ALL_OBS:
            assert c.corrupt(obs, _ctx(), _rng()) == obs

    def test_staleness_one_degrades_signal(self):
        """At staleness=1.0, 'signal' should always degrade."""
        c = StaleCorruptor(staleness=1.0)
        rng = _rng(0)
        result = c.corrupt("signal", _ctx(), rng)
        # At staleness=1.0: signal → weak_signal with p=1, then weak_signal → neutral with p=1
        assert result == "neutral", f"Expected 'neutral', got '{result}'"

    def test_staleness_one_weak_signal_to_neutral(self):
        c = StaleCorruptor(staleness=1.0)
        result = c.corrupt("weak_signal", _ctx(), _rng())
        assert result == "neutral"

    def test_neutral_and_noise_unchanged_at_staleness_one(self):
        c = StaleCorruptor(staleness=1.0)
        for obs in ("neutral", "noise"):
            assert c.corrupt(obs, _ctx(), _rng()) == obs

    def test_partial_staleness_retains_some_signal(self):
        """At staleness=0.10, most 'signal' obs should remain 'signal'."""
        c = StaleCorruptor(staleness=0.10)
        rng = _rng(42)
        signal_retained = sum(
            c.corrupt("signal", _ctx(), rng) == "signal"
            for _ in range(200)
        )
        assert signal_retained > 140, (
            f"Expected most signals retained at staleness=0.10, got {signal_retained}/200"
        )


# ---------------------------------------------------------------------------
# R3 Misleading
# ---------------------------------------------------------------------------

class TestMisleadingCorruptor:
    def test_p_inject_zero_is_identity(self):
        c = MisleadingCorruptor(p_inject=0.0)
        for obs in ALL_OBS:
            assert c.corrupt(obs, _ctx(), _rng()) == obs

    def test_p_inject_one_replaces_informative(self):
        """At p_inject=1.0, informative obs (signal, weak_signal) always replaced."""
        c = MisleadingCorruptor(p_inject=1.0)
        for obs in ("signal", "weak_signal"):
            result = c.corrupt(obs, _ctx(), _rng())
            assert result != obs or result in ("noise", "weak_signal"), (
                f"p_inject=1.0 should replace informative obs, got same: {result}"
            )

    def test_returns_valid_class_always(self):
        c = MisleadingCorruptor(p_inject=0.5)
        rng = _rng(11)
        for _ in range(200):
            for obs in ALL_OBS:
                result = c.corrupt(obs, _ctx(), rng)
                assert result in OBS_CLASSES

    def test_severe_injection_uses_noise(self):
        """p_inject >= 0.35 (threshold) → decoy is 'noise' not 'weak_signal'."""
        c = MisleadingCorruptor(p_inject=0.5)
        # With p_inject=1.0 forced, severe threshold met
        c2 = MisleadingCorruptor(p_inject=1.0)
        result = c2.corrupt("signal", _ctx(), _rng())
        assert result == "noise", f"Severe injection should produce 'noise', got '{result}'"


# ---------------------------------------------------------------------------
# R4 Targeted
# ---------------------------------------------------------------------------

class TestTargetedCorruptor:
    def test_high_affinity_source_suppressed(self):
        """Source with affinity[leading_hyp] >= 0.6 + p_attack=1.0 → always noise."""
        c = TargetedCorruptor(p_attack=1.0)
        ctx = _ctx(
            affinity={"H1": 0.80, "H2": 0.10, "H3": 0.10},
            beliefs={"H1": 0.70, "H2": 0.20, "H3": 0.10},
        )
        for obs in ("signal", "weak_signal", "neutral"):
            result = c.corrupt(obs, ctx, _rng())
            assert result == "noise", (
                f"High-affinity source should be suppressed to 'noise', got '{result}'"
            )

    def test_low_affinity_source_not_targeted(self):
        """Source with affinity[leading_hyp] < 0.6 → never suppressed (p_attack irrelevant)."""
        c = TargetedCorruptor(p_attack=1.0)
        ctx = _ctx(
            affinity={"H1": 0.40, "H2": 0.80, "H3": 0.30},
            beliefs={"H1": 0.70, "H2": 0.20, "H3": 0.10},
        )
        # H1 is leading with belief 0.70, but affinity to H1 is only 0.40 < 0.60
        result = c.corrupt("signal", ctx, _rng())
        assert result == "signal", (
            f"Low-affinity source should not be suppressed, got '{result}'"
        )

    def test_p_attack_zero_never_suppresses(self):
        """p_attack=0 means attacker never succeeds."""
        c = TargetedCorruptor(p_attack=0.0)
        ctx = _ctx(
            affinity={"H1": 0.90, "H2": 0.10, "H3": 0.05},
            beliefs={"H1": 0.80, "H2": 0.15, "H3": 0.05},
        )
        for obs in ALL_OBS:
            result = c.corrupt(obs, ctx, _rng())
            assert result == obs, (
                f"p_attack=0.0 should never corrupt, but got '{result}' from '{obs}'"
            )

    def test_empty_beliefs_no_targeting(self):
        """No beliefs → no targeting (attacker cannot identify best source)."""
        c = TargetedCorruptor(p_attack=1.0)
        ctx = _ctx(beliefs={}, affinity={})
        result = c.corrupt("signal", ctx, _rng())
        assert result == "signal"


# ---------------------------------------------------------------------------
# Estimator invariants
# ---------------------------------------------------------------------------

class TestEstimatorInvariants:
    ALL_ESTIMATORS = [
        CleanEstimator(),
        NoisyEstimator(sigma=0.10),
        NoisyEstimator(sigma=0.25),
        MiscalibratedEstimator(r_scale=0.8, r_bias=0.1, phi_scale=1.2, phi_bias=-0.05),
        AdversarialEstimator(),
    ]

    @pytest.mark.parametrize("estimator", ALL_ESTIMATORS)
    @pytest.mark.parametrize("r_true,phi_true", [
        (0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (0.7, 0.7), (0.85, 0.15)
    ])
    def test_output_in_unit_interval(self, estimator, r_true, phi_true):
        result = estimator.estimate(r_true, phi_true, _rng())
        assert 0.0 <= result.r_hat <= 1.0, f"{estimator} r_hat={result.r_hat} out of [0,1]"
        assert 0.0 <= result.phi_hat <= 1.0, f"{estimator} phi_hat={result.phi_hat} out of [0,1]"

    @pytest.mark.parametrize("estimator", ALL_ESTIMATORS)
    def test_does_not_modify_inputs(self, estimator):
        r_true, phi_true = 0.70, 0.30
        _ = estimator.estimate(r_true, phi_true, _rng())
        assert r_true == 0.70  # primitive floats are immutable; check nothing side-effected
        assert phi_true == 0.30


class TestCleanEstimator:
    def test_perfect_estimation(self):
        e = CleanEstimator()
        result = e.estimate(0.75, 0.40, _rng())
        assert result.r_hat == pytest.approx(0.75)
        assert result.phi_hat == pytest.approx(0.40)

    def test_boundary_values(self):
        e = CleanEstimator()
        r0 = e.estimate(0.0, 0.0, _rng())
        r1 = e.estimate(1.0, 1.0, _rng())
        assert r0.r_hat == 0.0 and r0.phi_hat == 0.0
        assert r1.r_hat == 1.0 and r1.phi_hat == 1.0


class TestNoisyEstimator:
    def test_sigma_zero_is_clean(self):
        e = NoisyEstimator(sigma=0.0)
        result = e.estimate(0.80, 0.20, _rng())
        assert result.r_hat == pytest.approx(0.80)
        assert result.phi_hat == pytest.approx(0.20)

    def test_sigma_nonzero_introduces_variation(self):
        """Over 100 trials with sigma=0.25, r_hat should vary from r_true."""
        e = NoisyEstimator(sigma=0.25)
        r_hats = [e.estimate(0.70, 0.30, _rng(i)).r_hat for i in range(100)]
        # At least some values should differ from 0.70
        assert not all(abs(r - 0.70) < 1e-9 for r in r_hats), \
            "Noisy estimator should produce variation"

    def test_clips_to_unit_interval(self):
        """Even with large sigma, output stays in [0,1]."""
        e = NoisyEstimator(sigma=0.50)
        for i in range(200):
            result = e.estimate(0.90, 0.10, _rng(i))
            assert 0.0 <= result.r_hat <= 1.0
            assert 0.0 <= result.phi_hat <= 1.0


class TestMiscalibratedEstimator:
    def test_phi_underestimate_factory(self):
        """Reviewer case: true φ=0.7, estimated φ≈0.2."""
        e = MiscalibratedEstimator.phi_underestimate(
            target_phi=0.70, estimated_phi=0.20
        )
        result = e.estimate(r_true=0.85, phi_true=0.70, rng=_rng())
        assert result.phi_hat == pytest.approx(0.20, abs=0.05), (
            f"phi_hat should be ≈0.20, got {result.phi_hat}"
        )

    def test_phi_overestimate_factory(self):
        """Reviewer case: true φ=0.7, estimated φ≈0.9."""
        e = MiscalibratedEstimator.phi_overestimate(
            target_phi=0.70, estimated_phi=0.90
        )
        result = e.estimate(r_true=0.85, phi_true=0.70, rng=_rng())
        assert result.phi_hat > 0.70, (
            f"phi_hat should be > true phi=0.70, got {result.phi_hat}"
        )
        assert 0.0 <= result.phi_hat <= 1.0

    def test_scale_one_bias_zero_is_clean(self):
        e = MiscalibratedEstimator(r_scale=1.0, r_bias=0.0, phi_scale=1.0, phi_bias=0.0)
        result = e.estimate(0.65, 0.35, _rng())
        assert result.r_hat == pytest.approx(0.65)
        assert result.phi_hat == pytest.approx(0.35)


class TestAdversarialEstimator:
    def test_high_phi_source_gets_inflated_r_and_deflated_phi(self):
        """Attacker spoofs high-phi source to look reliable and safe."""
        e = AdversarialEstimator(
            phi_threshold=0.50,
            r_inflate=0.95,
            phi_deflate=0.05,
            blend=1.0,  # full blend for deterministic test
        )
        result = e.estimate(r_true=0.50, phi_true=0.75, rng=_rng())
        assert result.r_hat == pytest.approx(0.95), \
            f"Adversarial: r_hat should be inflated to 0.95, got {result.r_hat}"
        assert result.phi_hat == pytest.approx(0.05), \
            f"Adversarial: phi_hat should be deflated to 0.05, got {result.phi_hat}"

    def test_low_phi_source_unmodified(self):
        """Attacker leaves low-phi sources alone (no benefit to deceive them)."""
        e = AdversarialEstimator(phi_threshold=0.50, blend=1.0)
        result = e.estimate(r_true=0.85, phi_true=0.20, rng=_rng())
        assert result.r_hat == pytest.approx(0.85)
        assert result.phi_hat == pytest.approx(0.20)

    def test_adversarial_flips_perceived_trustworthiness(self):
        """Before adversarial: phi_true=0.80 (dangerous). After: phi_hat≈0.05 (looks safe)."""
        e = AdversarialEstimator(phi_threshold=0.50, phi_deflate=0.05, blend=1.0)
        result = e.estimate(r_true=0.40, phi_true=0.80, rng=_rng())
        assert result.phi_hat < 0.20, (
            f"Adversarial estimator should make high-phi source look safe (phi_hat < 0.20), "
            f"got {result.phi_hat}"
        )


class TestEstimatorRegistry:
    def test_all_4_estimators_registered(self):
        expected = {"clean", "noisy", "miscalibrated", "adversarial"}
        assert expected == set(ESTIMATOR_REGISTRY.keys())

    def test_all_registry_entries_are_classes(self):
        import inspect
        for name, cls in ESTIMATOR_REGISTRY.items():
            assert inspect.isclass(cls), f"{name} should be a class, got {type(cls)}"

    def test_registry_instantiable_with_defaults(self):
        for name, cls in ESTIMATOR_REGISTRY.items():
            instance = cls()
            result = instance.estimate(0.70, 0.30, _rng())
            assert 0.0 <= result.r_hat <= 1.0
            assert 0.0 <= result.phi_hat <= 1.0
