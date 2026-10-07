"""
tests/test_joint_belief.py
--------------------------
Phase 7U mechanism tests (docs/phase7u_joint_belief_protocol.md). All must pass before the calibration.
Uses development world seeds (0-99) only.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np

from hades.probe_experiment.joint_confirm import (
    CANDIDATE, COMPARATORS, JOINT_POLICY_NAMES, NEW_FAMILY, ColludeCheapAttacker, _make_collude_cheap,
    make_joint_policies,
)
from hades.probe_experiment.joint_eval import (
    ALL_CONDITIONS, KNOWN_CELLS, PRIMARY_CELLS, evaluate_joint_gates, required_worlds,
)
from hades.probe_experiment.simulator import EXTRA_ATTACKERS, Condition, run_episode, sample_truth
from hades.probe_experiment.world import WorldDistribution, distribution_as_dict, generate_world

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "experiments" / "phase7u_joint_belief_v1.json"


class TestColludeCheap:
    def test_registered_alongside_decoy(self):
        assert EXTRA_ATTACKERS[NEW_FAMILY] is _make_collude_cheap
        assert "A_DECOY_MIGRATE" in EXTRA_ATTACKERS

    def test_targets_cheapest_sources(self):
        m = generate_world(3)
        order = sorted(range(m.n_sources), key=lambda q: (m.evidence_cost[q], q))
        for e in range(40):
            t = sample_truth(m, 3, e)
            a = _make_collude_cheap(Condition("x", NEW_FAMILY, 2), m, t, 3, e)
            if a.present:
                assert a.compromised == set(order[:2])

    def test_shared_lie_never_truth(self):
        m = generate_world(4)
        for e in range(60):
            t = sample_truth(m, 4, e)
            a = _make_collude_cheap(Condition("x", NEW_FAMILY, 3), m, t, 4, e)
            assert a.lie != t.h_true
            if t.h_true == 0:
                assert a.lie != 0
            assert {a.forge(q, t.h_true, 0.1, 0.9) for q in a.compromised} <= {a.lie}

    def test_presence_follows_kappa(self):
        m = generate_world(6)
        k = m.params["benign_coupling"]
        for e in range(60):
            t = sample_truth(m, 6, e)
            a = _make_collude_cheap(Condition("x", NEW_FAMILY, 1), m, t, 6, e)
            assert a.present == (t.h_true != 0 or t.u_present < k)

    def test_forge_rate_and_no_adaptation(self):
        a = ColludeCheapAttacker(NEW_FAMILY, 1, True, 2, compromised={0})
        assert a.forge(0, 1, 0.84, 0.0) == 2 and a.forge(0, 1, 0.86, 0.0) is None
        a.observe_probe(0)
        a.observe_query(1)
        assert a.compromised == {0}


class TestLeakage:
    def test_leak_select_signature(self):
        for p in make_joint_policies().values():
            assert set(inspect.signature(p.select).parameters) == {"belief", "model", "actions", "budget", "rng"}

    def test_leak_first_action_independent_of_attacker(self):
        m = generate_world(11)
        for name in (CANDIDATE, *COMPARATORS):
            firsts = set()
            for cond in [Condition("CLEAN", "NONE", 0), Condition("x", NEW_FAMILY, 3),
                         Condition("y", "A_DECOY_MIGRATE", 1), Condition("z", "A_COVER", 2)]:
                for e in range(4):
                    firsts.add(run_episode(make_joint_policies()[name], m, cond, 11, e).actions[0].split("=")[0])
            assert len(firsts) == 1, name


class TestHarness:
    def test_policy_set(self):
        assert CANDIDATE == "P_JOINT_HEIG_COST" and COMPARATORS == ("P3_RHAT_COST_LA2", "P_JOINT_EIG_COST")
        assert tuple(make_joint_policies()) == JOINT_POLICY_NAMES

    def test_spend_exact(self):
        for w in (2, 7):
            m = generate_world(w)
            for c in (Condition("x", NEW_FAMILY, 3), Condition("CLEAN", "NONE", 0)):
                for p in make_joint_policies().values():
                    assert abs(run_episode(p, m, c, w, 0).spend - m.budget) < 1e-9, p.name

    def test_config_matches_code(self):
        cfg = json.loads(CONFIG.read_text())
        assert cfg["status"] == "FROZEN" and cfg["pilot_decision_deadline"] == "2026-11-11"
        assert cfg["world_distribution"] == distribution_as_dict(WorldDistribution())
        assert tuple(cfg["conditions"]) == ALL_CONDITIONS
        assert tuple(cfg["primary_cells"]) == PRIMARY_CELLS and tuple(cfg["known_cells"]) == KNOWN_CELLS
        assert tuple(cfg["policies"]) == JOINT_POLICY_NAMES
        assert cfg["candidate"] == CANDIDATE and tuple(cfg["comparators"]) == COMPARATORS
        assert cfg["practical_threshold_rrr"] == 0.1 and cfg["power"]["alpha_one_sided"] == 0.025
        assert cfg["power"]["calibration_world_seeds"][0] >= 910040 and cfg["pilot_world_seed_start"] >= 2_400_000

    def test_required_worlds_clamped(self):
        assert required_worlds({"a": {"sd_d": 0.0, "mean_comparator": 0.2}})["n_worlds"] == 50
        assert required_worlds({"a": {"sd_d": 1.0, "mean_comparator": 0.01}})["n_worlds"] == 400

    def _agg(self, gain):
        rng = np.random.default_rng(0)
        agg = {}
        for w in range(60):
            agg[str(w)] = {c: {} for c in ALL_CONDITIONS}
            for c in ALL_CONDITIONS:
                for p in JOINT_POLICY_NAMES:
                    base = 0.3 + 0.05 * rng.random()
                    if c == "CLEAN" and p == "P3_NOM":
                        base = 0.05
                    if c in PRIMARY_CELLS and p == CANDIDATE:
                        base *= 1 - gain
                    agg[str(w)][c][p] = {"norm_regret": base * 12, "n": 12}
        return agg

    def test_gates_proceed_on_clear_gain(self):
        assert evaluate_joint_gates(self._agg(0.5), True, True)["verdict"] == "PROCEED"

    def test_gates_kill_without_gain(self):
        assert evaluate_joint_gates(self._agg(0.0), True, True)["verdict"] == "KILL"

    def test_gates_kill_on_spend(self):
        assert evaluate_joint_gates(self._agg(0.5), False, True)["verdict"] == "KILL"
