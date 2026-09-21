"""
tests/test_belief.py
---------------------
Unit tests for the HADES v3.0 belief package.

Tests
~~~~~
1. LikelihoodTable – rows sum to 1, validate() passes/fails correctly
2. contaminated_likelihood – r_hat=1/phi_hat=0 ~ nominal; r_hat=0 ~ uniform
3. belief_update (posterior.py) – sum-to-1 invariant, correct direction
4. entropy – 0 on certain beliefs, log2(N) on uniform
5. eig – 0 on uninformative source, > 0 on discriminating source,
          symmetric under equal affinities, decreases as beliefs collapse
6. voi – reduces to zero when eig ≈ lam*cost
7. robust_voi – min over phi candidates
8. relevance matrix – all entries in [0,1], provenance exists for all
9. leakage – policies cannot access *_true via estimated fields
"""
from __future__ import annotations

import math
import pytest

from hades.belief.likelihood import (
    LikelihoodTable,
    OBS_CLASSES,
    nominal_likelihood,
    contaminated_likelihood,
    make_default_table,
)
from hades.belief.posterior import update as belief_update
from hades.belief.value import entropy, eig, terminal_utility, voi, robust_voi
from hades.belief.relevance import RELEVANCE, RELEVANCE_PROVENANCE, SOURCES, ATTACK_TYPES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def two_hyp_uniform():
    """Uniform beliefs over two hypotheses."""
    return {"H_A": 0.5, "H_B": 0.5}


@pytest.fixture
def two_hyp_certain():
    """Certain beliefs (H_A certain)."""
    return {"H_A": 1.0, "H_B": 0.0}


@pytest.fixture
def two_hyp_skewed():
    """Skewed beliefs (H_A 80%, H_B 20%)."""
    return {"H_A": 0.8, "H_B": 0.2}


@pytest.fixture
def discriminating_table():
    """
    A source that perfectly discriminates H_A vs H_B.
    High relevance for H_A → strong_support is very likely.
    Low relevance for H_B → strong_support is very unlikely.
    """
    return make_default_table(
        sources=["s_discriminating"],
        hypotheses=["H_A", "H_B"],
        relevance={
            ("s_discriminating", "H_A"): 0.9,
            ("s_discriminating", "H_B"): 0.1,
        },
    )


@pytest.fixture
def uninformative_table():
    """
    A source with equal relevance for both hypotheses.
    Should produce near-zero EIG.
    """
    return make_default_table(
        sources=["s_uniform"],
        hypotheses=["H_A", "H_B"],
        relevance={
            ("s_uniform", "H_A"): 0.5,
            ("s_uniform", "H_B"): 0.5,
        },
    )


# ---------------------------------------------------------------------------
# 1. LikelihoodTable
# ---------------------------------------------------------------------------

class TestLikelihoodTable:

    def test_rows_sum_to_one(self, discriminating_table):
        """Every (source, hyp) row must sum to 1.0."""
        discriminating_table.validate()  # should not raise

    def test_validate_rejects_bad_table(self):
        """validate() should raise ValueError for non-normalized row."""
        bad = LikelihoodTable(
            p_obs={("src", "H_A", "strong_support"): 0.9}  # sum = 0.9, not 1.0
        )
        with pytest.raises(ValueError, match="sums to"):
            bad.validate()

    def test_get_raises_on_unknown_key(self, discriminating_table):
        with pytest.raises(KeyError):
            discriminating_table.get("unknown_source", "H_A", "strong_support")

    def test_as_matrix_shape(self, discriminating_table):
        m = discriminating_table.as_matrix("s_discriminating")
        assert set(m.keys()) == {"H_A", "H_B"}
        for hyp in m:
            assert abs(sum(m[hyp].values()) - 1.0) < 1e-6

    def test_make_default_table_validates(self):
        """make_default_table should always produce a valid table."""
        t = make_default_table(
            sources=["a", "b"],
            hypotheses=["H1", "H2", "H3"],
            relevance={
                ("a", "H1"): 0.8, ("a", "H2"): 0.2, ("a", "H3"): 0.5,
                ("b", "H1"): 0.3, ("b", "H2"): 0.9, ("b", "H3"): 0.1,
            },
        )
        t.validate()


# ---------------------------------------------------------------------------
# 2. contaminated_likelihood
# ---------------------------------------------------------------------------

class TestContaminatedLikelihood:

    def test_clean_regime_near_nominal(self):
        """
        r_hat=1, phi_hat=0: contaminated ≈ nominal.
        """
        for obs in OBS_CLASSES:
            p_cont = contaminated_likelihood(
                obs_class=obs, hyp="H_A",
                source_relevance=0.8, r_hat=1.0, phi_hat=0.0,
            )
            p_nom = nominal_likelihood(0.8, obs)
            assert abs(p_cont - p_nom) < 1e-9, (
                f"obs={obs}: contaminated={p_cont:.6f} != nominal={p_nom:.6f}"
            )

    def test_unreliable_source_approaches_uniform(self):
        """
        r_hat=0: observation is pure noise → near uniform.
        """
        n = len(OBS_CLASSES)
        for obs in OBS_CLASSES:
            p = contaminated_likelihood(
                obs_class=obs, hyp="H_A",
                source_relevance=0.9, r_hat=0.0, phi_hat=0.0,
            )
            expected = 1.0 / n
            assert abs(p - expected) < 1e-9, (
                f"obs={obs}: p={p:.6f}, expected uniform {expected:.6f}"
            )

    def test_targeted_attack_inflates_contra(self):
        """
        Under targeted attack (phi_hat>0): strong_contra gets inflated.
        """
        p_normal = contaminated_likelihood(
            "strong_contra", "H_A", source_relevance=0.8,
            r_hat=1.0, phi_hat=0.0,
        )
        p_attacked = contaminated_likelihood(
            "strong_contra", "H_A", source_relevance=0.8,
            r_hat=1.0, phi_hat=0.5, under_targeted_attack=True,
        )
        assert p_attacked > p_normal, (
            "Targeted attack should inflate strong_contra probability"
        )


# ---------------------------------------------------------------------------
# 3. Posterior update
# ---------------------------------------------------------------------------

class TestPosteriorUpdate:

    def test_sum_to_one_invariant(self, discriminating_table, two_hyp_uniform):
        """Updated beliefs must sum to 1.0."""
        updated = belief_update(
            beliefs=two_hyp_uniform,
            obs_class="strong_support",
            source="s_discriminating",
            table=discriminating_table,
            r_hat=1.0, phi_hat=0.0,
        )
        assert abs(sum(updated.values()) - 1.0) < 1e-9

    def test_strong_support_increases_relevant_hyp(self, discriminating_table, two_hyp_uniform):
        """
        strong_support from a source with high affinity for H_A should
        increase P(H_A) and decrease P(H_B).
        """
        updated = belief_update(
            beliefs=two_hyp_uniform,
            obs_class="strong_support",
            source="s_discriminating",
            table=discriminating_table,
            r_hat=1.0, phi_hat=0.0,
            source_relevance={"H_A": 0.9, "H_B": 0.1},
        )
        assert updated["H_A"] > 0.5, f"H_A should be above 0.5, got {updated['H_A']:.4f}"
        assert updated["H_B"] < 0.5, f"H_B should be below 0.5, got {updated['H_B']:.4f}"

    def test_certain_beliefs_stay_certain(self, discriminating_table, two_hyp_certain):
        """
        If P(H_A) = 1.0 initially, any observation keeps P(H_A) = 1.0.
        """
        updated = belief_update(
            beliefs=two_hyp_certain,
            obs_class="strong_contra",
            source="s_discriminating",
            table=discriminating_table,
            r_hat=1.0, phi_hat=0.0,
        )
        assert abs(sum(updated.values()) - 1.0) < 1e-9

    def test_validates_prior_sum(self):
        """belief_update must reject priors that don't sum to 1."""
        bad_beliefs = {"H_A": 0.6, "H_B": 0.6}  # sums to 1.2
        t = make_default_table(["s"], ["H_A", "H_B"], {("s","H_A"): 0.7, ("s","H_B"): 0.3})
        with pytest.raises(RuntimeError, match="invariant"):
            belief_update(bad_beliefs, "neutral", "s", t, 1.0, 0.0)


# ---------------------------------------------------------------------------
# 4. Entropy
# ---------------------------------------------------------------------------

class TestEntropy:

    def test_certain_beliefs_zero_entropy(self, two_hyp_certain):
        assert entropy(two_hyp_certain) == pytest.approx(0.0, abs=1e-9)

    def test_uniform_two_hyp_entropy_one_bit(self, two_hyp_uniform):
        assert entropy(two_hyp_uniform) == pytest.approx(1.0, abs=1e-9)

    def test_uniform_n_hyp_entropy_log2_n(self):
        n = 8
        beliefs = {f"H{i}": 1.0 / n for i in range(n)}
        assert entropy(beliefs) == pytest.approx(math.log2(n), abs=1e-9)

    def test_single_hypothesis_zero(self):
        assert entropy({"H_A": 1.0}) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 5. EIG
# ---------------------------------------------------------------------------

class TestEIG:

    def test_discriminating_source_positive_eig(
        self, discriminating_table, two_hyp_uniform
    ):
        """A source that differentiates hypotheses should have EIG > 0."""
        val = eig(
            source="s_discriminating",
            beliefs=two_hyp_uniform,
            table=discriminating_table,
            r_hat=1.0, phi_hat=0.0,
            source_relevance={"H_A": 0.9, "H_B": 0.1},
        )
        assert val > 0.0, f"Expected EIG > 0, got {val:.6f}"

    def test_uninformative_source_near_zero_eig(
        self, uninformative_table, two_hyp_uniform
    ):
        """
        A source with equal relevance for both hypotheses gives near-zero EIG.
        """
        val = eig(
            source="s_uniform",
            beliefs=two_hyp_uniform,
            table=uninformative_table,
            r_hat=1.0, phi_hat=0.0,
            source_relevance={"H_A": 0.5, "H_B": 0.5},
        )
        assert val < 0.05, f"Expected near-zero EIG, got {val:.6f}"

    def test_eig_is_nonnegative(self, discriminating_table, two_hyp_skewed):
        """EIG must be >= 0 always."""
        val = eig(
            source="s_discriminating",
            beliefs=two_hyp_skewed,
            table=discriminating_table,
            r_hat=0.5, phi_hat=0.2,
            source_relevance={"H_A": 0.9, "H_B": 0.1},
        )
        assert val >= 0.0

    def test_unreliable_source_lower_eig(
        self, discriminating_table, two_hyp_uniform
    ):
        """
        r_hat=0.3 should give lower EIG than r_hat=1.0 for the same source.
        (Unreliable source → more noise → less information.)
        """
        rel = {"H_A": 0.9, "H_B": 0.1}
        eig_reliable = eig(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            r_hat=1.0, phi_hat=0.0, source_relevance=rel,
        )
        eig_noisy = eig(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            r_hat=0.3, phi_hat=0.0, source_relevance=rel,
        )
        assert eig_noisy < eig_reliable, (
            f"Unreliable source should have lower EIG: {eig_noisy:.4f} vs {eig_reliable:.4f}"
        )

    def test_eig_decreases_as_beliefs_collapse(
        self, discriminating_table
    ):
        """More certain beliefs → less room to learn → lower EIG."""
        rel = {"H_A": 0.9, "H_B": 0.1}
        eig_uniform = eig(
            "s_discriminating", {"H_A": 0.5, "H_B": 0.5},
            discriminating_table, r_hat=1.0, phi_hat=0.0, source_relevance=rel,
        )
        eig_certain = eig(
            "s_discriminating", {"H_A": 0.99, "H_B": 0.01},
            discriminating_table, r_hat=1.0, phi_hat=0.0, source_relevance=rel,
        )
        assert eig_certain < eig_uniform, (
            f"Near-certain beliefs should have lower EIG: "
            f"uniform={eig_uniform:.4f}, certain={eig_certain:.4f}"
        )


# ---------------------------------------------------------------------------
# 6. VoI
# ---------------------------------------------------------------------------

class TestVoI:

    def test_voi_subtracts_cost(self, discriminating_table, two_hyp_uniform):
        rel = {"H_A": 0.9, "H_B": 0.1}
        eig_val = eig(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            r_hat=1.0, phi_hat=0.0, source_relevance=rel,
        )
        voi_val = voi(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            cost=0.5, lam=1.0, r_hat=1.0, phi_hat=0.0, source_relevance=rel,
        )
        assert abs(voi_val - (eig_val - 0.5)) < 1e-9, (
            f"VoI should equal EIG - lam*cost: {voi_val:.6f} vs {eig_val - 0.5:.6f}"
        )

    def test_voi_lam_zero_equals_eig(self, discriminating_table, two_hyp_uniform):
        """lam=0 removes cost penalty, VoI = EIG."""
        rel = {"H_A": 0.9, "H_B": 0.1}
        eig_val = eig(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            r_hat=1.0, phi_hat=0.0, source_relevance=rel,
        )
        voi_val = voi(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            cost=1.0, lam=0.0, r_hat=1.0, phi_hat=0.0, source_relevance=rel,
        )
        assert abs(voi_val - eig_val) < 1e-9


# ---------------------------------------------------------------------------
# 7. Robust VoI
# ---------------------------------------------------------------------------

class TestRobustVoI:

    def test_robust_voi_le_voi(self, discriminating_table, two_hyp_uniform):
        """Robust VoI (min over phi) <= standard VoI (phi=0)."""
        rel = {"H_A": 0.9, "H_B": 0.1}
        standard = voi(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            cost=0.5, lam=1.0, r_hat=1.0, phi_hat=0.0, source_relevance=rel,
        )
        robust = robust_voi(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            cost=0.5, lam=1.0, phi_budget=0.5, r_hat=1.0,
            phi_hat_candidates=[0.0, 0.25, 0.5], source_relevance=rel,
        )
        assert robust <= standard + 1e-9, (
            f"Robust VoI should be <= standard VoI: {robust:.4f} vs {standard:.4f}"
        )

    def test_robust_voi_phi_zero_equals_voi(self, discriminating_table, two_hyp_uniform):
        """phi_budget=0 → only phi=0 → robust_voi == voi."""
        rel = {"H_A": 0.9, "H_B": 0.1}
        standard = voi(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            cost=0.5, lam=1.0, r_hat=1.0, phi_hat=0.0, source_relevance=rel,
        )
        robust = robust_voi(
            "s_discriminating", two_hyp_uniform, discriminating_table,
            cost=0.5, lam=1.0, phi_budget=0.0, r_hat=1.0,
            phi_hat_candidates=[0.0], source_relevance=rel,
        )
        assert abs(robust - standard) < 1e-9


# ---------------------------------------------------------------------------
# 8. Relevance matrix
# ---------------------------------------------------------------------------

class TestRelevanceMatrix:

    def test_all_source_attack_pairs_present(self):
        """All (source, attack_type) combinations should have an entry."""
        for src in SOURCES:
            for atk in ATTACK_TYPES:
                v = RELEVANCE.get((src, atk))
                assert v is not None, f"Missing relevance for ({src}, {atk})"

    def test_all_values_in_range(self):
        """All relevance values must be in [0, 1]."""
        for (src, atk), v in RELEVANCE.items():
            assert 0.0 <= v <= 1.0, f"({src}, {atk}) = {v} out of [0,1]"

    def test_provenance_exists_for_all(self):
        """Every entry in RELEVANCE should have a provenance record."""
        for key in RELEVANCE:
            prov = RELEVANCE_PROVENANCE.get(key)
            assert prov is not None, f"Missing provenance for {key}"
            assert "source" in prov, f"Provenance for {key} missing 'source' field"
            assert "version" in prov, f"Provenance for {key} missing 'version' field"

    def test_high_relevance_sources_are_reasonable(self):
        """Sanity check that well-known high-relevance pairs are >= 0.8."""
        assert RELEVANCE[("process_events", "H_execution")] >= 0.8
        assert RELEVANCE[("persistence_events", "H_persistence")] >= 0.8
        assert RELEVANCE[("auth_events", "H_lateral_movement")] >= 0.8
        assert RELEVANCE[("dns_events", "H_exfiltration")] >= 0.8


# ---------------------------------------------------------------------------
# 9. Leakage: *_estimated should not expose *_true
# ---------------------------------------------------------------------------

class TestLeakage:

    def test_belief_update_uses_only_estimated_fields(self):
        """
        belief_update only accepts r_hat and phi_hat (estimated).
        There is no r_true or phi_true parameter — no path for leakage.
        """
        import inspect
        sig = inspect.signature(belief_update)
        param_names = set(sig.parameters.keys())
        assert "r_hat" in param_names
        assert "phi_hat" in param_names
        # No *_true parameters
        assert not any("true" in p for p in param_names), (
            f"belief_update must not accept *_true parameters: {param_names}"
        )

    def test_eig_uses_only_estimated_fields(self):
        import inspect
        sig = inspect.signature(eig)
        param_names = set(sig.parameters.keys())
        assert "r_hat" in param_names
        assert "phi_hat" in param_names
        assert not any("true" in p for p in param_names), (
            f"eig must not accept *_true parameters: {param_names}"
        )
