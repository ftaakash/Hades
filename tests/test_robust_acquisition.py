"""
tests/test_robust_acquisition.py
--------------------------------
Phase 7T mechanism tests for the robust-acquisition pilot (docs/phase7t_robust_acquisition_protocol.md).
All must pass before the calibration. Uses development world seeds (0-99) only.
"""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import numpy as np

from hades.probe_experiment import robust as robust_mod
from hades.probe_experiment.belief import JointBelief, action_space
from hades.probe_experiment.robust import (
    CANDIDATES, COMPARATORS, NEW_FAMILY, ROBUST_POLICY_NAMES, DecoyMigrateAttacker, MinimaxJointEIG,
    RandomizedJointEIG, _make_decoy_migrate, alternative_models, make_robust_policies,
)
from hades.probe_experiment.robust_eval import (
    ALL_CONDITIONS, KNOWN_CELLS, PRIMARY_CELLS, evaluate_robust_gates, required_worlds,
)
from hades.probe_experiment.simulator import EXTRA_ATTACKERS, Condition, run_episode, sample_truth
from hades.probe_experiment.world import WorldDistribution, distribution_as_dict, generate_world

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "experiments" / "phase7t_robust_pilot_v1.json"


# ---------------------------------------------------------------------------
# Held-out attacker
# ---------------------------------------------------------------------------
class TestDecoyMigrate:
    def test_registered(self):
        assert EXTRA_ATTACKERS[NEW_FAMILY] is _make_decoy_migrate

    def test_decoy_never_true_hypothesis(self):
        m = generate_world(3)
        for e in range(60):
            t = sample_truth(m, 3, e)
            a = _make_decoy_migrate(Condition("x", NEW_FAMILY, 2), m, t, 3, e)
            assert a.decoy != t.h_true
            if t.h_true == 0:
                assert a.decoy != 0

    def test_presence_follows_kappa(self):
        m = generate_world(4)
        kappa = m.params["benign_coupling"]
        for e in range(60):
            t = sample_truth(m, 4, e)
            a = _make_decoy_migrate(Condition("x", NEW_FAMILY, 1), m, t, 4, e)
            assert a.present == (t.h_true != 0 or t.u_present < kappa)
            assert len(a.compromised) == (1 if a.present else 0)

    def test_budget_zero_absent(self):
        m = generate_world(4)
        t = sample_truth(m, 4, 0)
        assert not _make_decoy_migrate(Condition("x", NEW_FAMILY, 0), m, t, 4, 0).present

    def test_migrates_on_probe_to_most_queried_unprobed(self):
        a = DecoyMigrateAttacker(NEW_FAMILY, 1, True, 1, compromised={0})
        for q in (1, 2, 2, 0):
            a.observe_query(q)
        a.observe_probe(0)
        assert a.compromised == {2}
        a.observe_probe(1)                  # probing an uncontrolled source does nothing
        assert a.compromised == {2}

    def test_forge_rate(self):
        a = DecoyMigrateAttacker(NEW_FAMILY, 1, True, 2, compromised={0})
        assert a.forge(0, 0, 0.79, 0.5) == 2
        assert a.forge(0, 0, 0.81, 0.5) is None


# ---------------------------------------------------------------------------
# Candidate policies
# ---------------------------------------------------------------------------
class TestRandomizedJointEIG:
    def test_probabilities_valid_and_proportional(self):
        m = generate_world(7)
        acts = action_space(m)
        b = JointBelief.from_prior(m)
        pol = RandomizedJointEIG()
        p = pol.probabilities(b, m, acts, 12.0)
        assert abs(p.sum() - 1) < 1e-12 and (p >= 0).all()
        s = np.maximum(pol._inner.scores(b, m, acts, 12.0), 0)
        if s.sum() > 0:
            assert np.allclose(p, s / s.sum())

    def test_unaffordable_actions_never_sampled(self):
        m = generate_world(7)
        acts = action_space(m)
        p = RandomizedJointEIG().probabilities(JointBelief.from_prior(m), m, acts, 1.0)
        assert (p[acts.cost > 1.0 + 1e-9] == 0).all()

    def test_reproducible(self):
        m = generate_world(8)
        c = Condition("x", NEW_FAMILY, 2)
        r1 = run_episode(make_robust_policies()["P_RAND_JEIG"], m, c, 8, 0)
        r2 = run_episode(make_robust_policies()["P_RAND_JEIG"], m, c, 8, 0)
        assert r1.actions == r2.actions


class TestMinimaxJointEIG:
    def test_alternative_models_valid(self):
        alts = alternative_models(generate_world(9))
        assert set(alts) == {"COVER", "MISATTRIB", "NOISE"}

    def test_score_is_elementwise_min(self):
        m = generate_world(9)
        acts = action_space(m)
        pol = MinimaxJointEIG()
        pol.reset(m)
        b = JointBelief.from_prior(m)
        sc = pol.model_scores(b, m, acts, 12.0)
        mn = np.min(np.stack(list(sc.values())), axis=0)
        for v in sc.values():
            assert (mn <= v + 1e-15).all()

    def test_alternative_beliefs_stay_normalised(self):
        m = generate_world(10)
        acts = action_space(m)
        pol = MinimaxJointEIG()
        pol.reset(m)
        for a, o in [(0, 1), (acts.n - 1, 0), (1, 2)]:
            pol.observe(acts, a, o)
        for b in pol._beliefs.values():
            b.validate()

    def test_reset_clears_history(self):
        m = generate_world(10)
        acts = action_space(m)
        pol = MinimaxJointEIG()
        pol.reset(m)
        fresh = {k: b.p_h.copy() for k, b in pol._beliefs.items()}
        pol.observe(acts, 0, 1)
        pol.reset(m)
        for k, b in pol._beliefs.items():
            assert np.allclose(b.p_h, fresh[k])


# ---------------------------------------------------------------------------
# Leakage (RG-6)
# ---------------------------------------------------------------------------
class TestLeakage:
    def test_leak_select_signature(self):
        for p in make_robust_policies().values():
            assert set(inspect.signature(p.select).parameters) == {"belief", "model", "actions", "budget", "rng"}

    def test_leak_candidate_classes_use_no_truth(self):
        """The candidate classes never touch episode truth or attacker state."""
        src = "\n".join(inspect.getsource(c) for c in (RandomizedJointEIG, MinimaxJointEIG))
        names = {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute)}
        for bad in ("EpisodeTruth", "h_true", "compromised", "degraded", "u_present", "att", "attacker"):
            assert bad not in names, bad

    def test_leak_first_action_independent_of_truth_and_attacker(self):
        m = generate_world(11)
        for name in ("P_MINIMAX_JEIG", "P_JOINT_EIG_COST"):
            firsts = set()
            for cond in [Condition("CLEAN", "NONE", 0), Condition("x", "A_COVER", 3),
                         Condition("y", NEW_FAMILY, 2), Condition("z", "A_TRUST_HARVEST", 1)]:
                for e in range(4):
                    r = run_episode(make_robust_policies()[name], m, cond, 11, e)
                    firsts.add(r.actions[0].split("=")[0])
            assert len(firsts) == 1, name

    def test_leak_minimax_actions_are_function_of_observations(self):
        m = generate_world(12)
        acts = action_space(m)
        seq = []
        for h in range(2):
            pol = MinimaxJointEIG()
            pol.reset(m)
            b = JointBelief.from_prior(m)
            for a, o in [(0, 0), (acts.n - 1, 1)]:
                b.update(acts, a, o)
                pol.observe(acts, a, o)
            seq.append(pol.select(b, m, acts, 6.0, np.random.default_rng(h)))
        assert seq[0] == seq[1]


# ---------------------------------------------------------------------------
# Spend, config, gates
# ---------------------------------------------------------------------------
class TestHarness:
    def test_spend_exact_all_policies(self):
        for w in (2, 6):
            m = generate_world(w)
            for c in (Condition("x", NEW_FAMILY, 3), Condition("CLEAN", "NONE", 0)):
                for p in make_robust_policies().values():
                    r = run_episode(p, m, c, w, 0)
                    assert abs(r.spend - m.budget) < 1e-9, p.name

    def test_config_matches_code(self):
        cfg = json.loads(CONFIG.read_text())
        assert cfg["status"] == "FROZEN"
        assert cfg["world_distribution"] == distribution_as_dict(WorldDistribution())
        assert tuple(cfg["conditions"]) == ALL_CONDITIONS
        assert tuple(cfg["primary_cells"]) == PRIMARY_CELLS and tuple(cfg["known_cells"]) == KNOWN_CELLS
        assert tuple(cfg["policies"]) == ROBUST_POLICY_NAMES
        assert tuple(cfg["candidates"]) == CANDIDATES and tuple(cfg["comparators"]) == COMPARATORS
        assert cfg["practical_threshold_rrr"] == 0.1 and cfg["power"]["alpha_one_sided"] == 0.0125
        assert cfg["pilot_decision_deadline"] == "2026-11-11"
        lo, hi = cfg["power"]["calibration_world_seeds"]
        assert lo >= 900040 and cfg["pilot_world_seed_start"] >= 1_100_000

    def test_required_worlds_clamped(self):
        assert required_worlds({"a": {"sd_d": 0.0, "mean_comparator": 0.2}})["n_worlds"] == 50
        assert required_worlds({"a": {"sd_d": 1.0, "mean_comparator": 0.01}})["n_worlds"] == 400

    def _agg(self, gain):
        rng = np.random.default_rng(0)
        agg = {}
        for w in range(60):
            agg[str(w)] = {}
            for c in ALL_CONDITIONS:
                agg[str(w)][c] = {}
                for p in ROBUST_POLICY_NAMES:
                    base = 0.3 + 0.05 * rng.random()
                    if c == "CLEAN" and p == "P3_NOM":
                        base = 0.05
                    if c in PRIMARY_CELLS and p in CANDIDATES:
                        base *= 1 - gain
                    agg[str(w)][c][p] = {"norm_regret": base * 12, "n": 12, "n_queries": 60}
        return agg

    def test_gates_proceed_on_clear_gain(self):
        g = evaluate_robust_gates(self._agg(0.5), True, True)
        assert g["verdict"] == "PROCEED" and set(g["passing_candidates"]) == set(CANDIDATES)

    def test_gates_kill_without_gain(self):
        assert evaluate_robust_gates(self._agg(0.0), True, True)["verdict"] == "KILL"

    def test_gates_kill_on_leak(self):
        assert evaluate_robust_gates(self._agg(0.5), True, False)["verdict"] == "KILL"
