"""
tests/test_probe_experiment.py
------------------------------
Phase 7K deterministic mechanism tests for the HADES 2.0 probe-value experiment
(plan §9, protocol §10). All must pass before any stochastic run.

The deterministic cases below are hand-built belief states (3 sources), not pilot
worlds. Several of them were located by enumerating small hand-built models; the
search never touched development, calibration or pilot world seeds.
"""
from __future__ import annotations

import ast
import inspect
import itertools
import json
from pathlib import Path

import numpy as np
import pytest

from hades.probe_experiment import attacker as attacker_mod
from hades.probe_experiment import policies as policies_mod
from hades.probe_experiment.attacker import Attacker
from hades.probe_experiment.belief import JointBelief, action_space, objective_after, objective_now, one_step
from hades.probe_experiment.evaluation import (
    ALL_CONDITIONS, PRIMARY_CELLS, bootstrap_rrr, evaluate_gates, holm, required_worlds, rrr, wilcoxon_one_sided,
)
from hades.probe_experiment.policies import LookaheadPolicy, Policy, make_policies
from hades.probe_experiment.simulator import Condition, run_episode, sample_truth
from hades.probe_experiment.world import (
    COMPROMISED, HEALTHY, M, NS, DefenderModel, WorldDistribution, build_model, distribution_as_dict,
    generate_world,
)

ROOT = Path(__file__).resolve().parents[1]


def mk(acc, cost, pcost, comp, kappa=1.0, lm=10.0, b=0.5, degr=None, dc=0.95, fp=0.02, dd=0.9):
    K = len(acc)
    return build_model(0, np.array(acc, float), np.array(cost, float), np.array(pcost, float), b,
                       np.array(comp, float), kappa, np.zeros(K) if degr is None else np.array(degr, float),
                       dc, fp, dd, lm, params={"benign_coupling": kappa})


def choose(name, model, belief=None, budget=6):
    acts = action_space(model)
    pol = make_policies()[name]
    belief = belief or JointBelief.from_prior(model)
    return acts.names[pol.select(belief, model, acts, budget, np.random.default_rng(0))]


def value_of(model, belief, action_name, objective):
    acts = action_space(model)
    la = one_step(belief, acts, model.utility)
    a = acts.names.index(action_name)
    return float((la.p_o[a] * objective_after(la, objective)[a]).sum() - objective_now(belief, objective, model.utility))


# ---------------------------------------------------------------------------
# 9.1 Source-state sensitivity
# ---------------------------------------------------------------------------
class TestSourceStateSensitivity:
    def test_probe_value_zero_without_state_uncertainty(self):
        m = mk([0.8, 0.7, 0.6], [1, 1, 1], [1, 1, 1], [0.0, 0.0, 0.0])
        b = JointBelief.from_prior(m)
        for obj in ("h_info", "joint_info", "decision"):
            assert abs(value_of(m, b, "probe:edr", obj)) < 1e-12

    def test_probe_value_grows_with_state_uncertainty(self):
        vals = []
        for pi in (0.05, 0.2, 0.4):
            m = mk([0.8, 0.7, 0.6], [1, 1, 1], [1, 1, 1], [pi, 0.0, 0.0])
            vals.append(value_of(m, JointBelief.from_prior(m), "probe:edr", "joint_info"))
        assert 0 < vals[0] < vals[1] < vals[2]

    def test_probe_decision_value_after_suspicious_report(self):
        # The edr says BENIGN; whether edr is compromised now decides CLOSE vs respond.
        m = mk([0.9, 0.6, 0.6], [1, 1, 1], [1, 1, 1], [0.4, 0.0, 0.0], lm=10.0, b=0.5)
        b = JointBelief.from_prior(m)
        b.update(action_space(m), 0, 0)
        assert value_of(m, b, "probe:edr", "decision") > 0.0
        m0 = mk([0.9, 0.6, 0.6], [1, 1, 1], [1, 1, 1], [0.0, 0.0, 0.0], lm=10.0, b=0.5)
        b0 = JointBelief.from_prior(m0)
        b0.update(action_space(m0), 0, 0)
        assert abs(value_of(m0, b0, "probe:edr", "decision")) < 1e-12


# ---------------------------------------------------------------------------
# 9.2 Hypothesis sensitivity
# ---------------------------------------------------------------------------
class TestHypothesisSensitivity:
    def test_evidence_value_depends_on_p_h(self):
        vals = []
        for b in (0.98, 0.7, 1 / 3):
            m = mk([0.8, 0.7, 0.6], [1, 1, 1], [1, 1, 1], [0.1, 0.1, 0.1], b=b)
            vals.append(value_of(m, JointBelief.from_prior(m), "query:edr", "h_info"))
        assert vals[0] < vals[1] < vals[2]

    def test_source_beliefs_held_fixed(self):
        m1 = mk([0.8, 0.7, 0.6], [1, 1, 1], [1, 1, 1], [0.1, 0.1, 0.1], kappa=1.0, b=0.9)
        m2 = mk([0.8, 0.7, 0.6], [1, 1, 1], [1, 1, 1], [0.1, 0.1, 0.1], kappa=1.0, b=0.4)
        b1, b2 = JointBelief.from_prior(m1), JointBelief.from_prior(m2)
        assert np.allclose(b1.source_marginal(), b2.source_marginal())
        assert value_of(m1, b1, "query:edr", "decision") != pytest.approx(value_of(m2, b2, "query:edr", "decision"))


# ---------------------------------------------------------------------------
# 9.3 Probe-selection flip and separation from the primary comparator
# ---------------------------------------------------------------------------
class TestBehaviouralSeparation:
    def test_flip_vs_p3_rhat_cost_sanity(self):
        """Expected by construction (H-only EIG gives a probe zero one-step value). Sanity only."""
        m = mk([0.7, 0.8, 0.6], [2, 1, 2], [1, 3, 3], [0.2, 0.6, 0.6], kappa=0.0, lm=1.0, b=0.7)
        assert choose("P_PROBE", m) == "probe:sysmon"
        assert choose("P3_RHAT_COST", m) == "query:sysmon"

    def test_probe_chosen_where_joint_eig_queries(self):
        m = mk([0.7, 0.8, 0.6], [2, 1, 2], [1, 3, 3], [0.2, 0.6, 0.6], kappa=0.0, lm=1.0, b=0.7)
        assert choose("P_PROBE", m) == "probe:sysmon"
        assert choose("P_JOINT_EIG_COST", m) == "query:sysmon"

    def test_joint_eig_probes_where_decision_value_does_not(self):
        """Separation runs both ways: the primary comparator is not blind to probes."""
        m = mk([0.95, 0.8, 0.8], [1, 1, 1], [1, 1, 1], [0.6, 0.4, 0.6], kappa=0.5, lm=3.0, b=0.7)
        assert choose("P_JOINT_EIG_COST", m) == "probe:edr"
        assert choose("P_PROBE", m) == "query:edr"

    def test_two_step_rhat_baseline_can_probe(self):
        """P3_RHAT_COST_LA2 discovers probe-then-query; the myopic version cannot."""
        m = mk([0.95, 0.5, 0.5], [3, 2, 2], [1, 3, 2], [0.6, 0.4, 0.4], kappa=0.0, lm=10.0, b=0.3)
        assert choose("P3_RHAT_COST_LA2", m) == "probe:edr"
        assert choose("P3_RHAT_COST", m) == "query:edr"


# ---------------------------------------------------------------------------
# 9.4 Cost isolation
# ---------------------------------------------------------------------------
class TestCostIsolation:
    def test_flip_with_all_costs_equal(self):
        m = mk([0.5, 0.9, 0.6], [1, 1, 1], [1, 1, 1], [0.05, 0.6, 0.2], kappa=1.0, lm=1.0, b=0.7)
        b = JointBelief.from_prior(m)
        b.update(action_space(m), 2, 0)          # auth_log reported BENIGN
        assert choose("P_PROBE", m, b) == "probe:auth_log"
        assert choose("P3_RHAT_COST", m, b) == "query:auth_log"


# ---------------------------------------------------------------------------
# 9.5 Source-state ablation
# ---------------------------------------------------------------------------
class TestSourceStateAblation:
    def test_no_s_probes_are_dominated(self):
        for case in [([0.7, 0.8, 0.6], [2, 1, 2], [1, 3, 3], [0.2, 0.6, 0.6], 0.0, 1.0, 0.7),
                     ([0.9, 0.6, 0.6], [1, 1, 1], [1, 1, 1], [0.4, 0.0, 0.0], 1.0, 10.0, 0.5)]:
            m = mk(*case[:4], kappa=case[4], lm=case[5], b=case[6])
            acts = action_space(m)
            pol = make_policies()["P_PROBE_NO_S"]
            s = pol.scores(JointBelief.from_prior(m), m, acts, 6)
            # a probe can only borrow value from the follow-up query, so it is always dominated
            assert s[acts.kind == 1].max() < s[acts.kind == 0].max()

    def test_ablation_collapses_probe_choice(self):
        m = mk([0.7, 0.8, 0.6], [2, 1, 2], [1, 3, 3], [0.2, 0.6, 0.6], kappa=0.0, lm=1.0, b=0.7)
        assert choose("P_PROBE", m).startswith("probe")
        assert choose("P_PROBE_NO_S", m).startswith("query")

    def test_zero_state_uncertainty_matches_ablation(self):
        rng = np.random.default_rng(3)
        for _ in range(20):
            acc = rng.uniform(0.5, 0.95, 3)
            m = mk(acc, rng.integers(1, 4, 3), rng.integers(1, 4, 3), [0, 0, 0], lm=float(rng.uniform(1, 20)),
                   b=float(rng.uniform(0.3, 0.8)))
            assert choose("P_PROBE", m) == choose("P_PROBE_NO_S", m)
            assert not choose("P_PROBE", m).startswith("probe")

    def test_no_probe_variant_never_probes(self):
        m = mk([0.7, 0.8, 0.6], [2, 1, 2], [1, 3, 3], [0.2, 0.6, 0.6], kappa=0.0, lm=1.0, b=0.7)
        for c in [Condition("A", "A_COVER", 2), Condition("C", "NONE", 0)]:
            for e in range(5):
                r = run_episode(make_policies()["P_PROBE_NO_PROBE"], m, c, 0, e)
                assert r.n_probes == 0


# ---------------------------------------------------------------------------
# 9.6 Oracle isolation (PF-7). Test names contain "leak" so the analysis can re-run them.
# ---------------------------------------------------------------------------
class TestLeakage:
    FORBIDDEN = ("true", "truth", "attack", "attacker", "family", "compromised_set", "h_true", "schedule")

    def test_leak_select_signature(self):
        for p in make_policies().values():
            params = set(inspect.signature(p.select).parameters)
            assert params == {"belief", "model", "actions", "budget", "rng"}

    def test_leak_defender_model_fields(self):
        import dataclasses
        for f in dataclasses.fields(DefenderModel):
            assert not any(k in f.name.lower() for k in self.FORBIDDEN), f.name
        m = generate_world(5)
        assert not any(k in key.lower() for key in m.params for k in ("true", "attack", "budget_att"))

    def test_leak_policy_module_imports(self):
        tree = ast.parse(Path(policies_mod.__file__).read_text())
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any("simulator" in m or "attacker" in m for m in mods if m)

    def test_leak_first_action_independent_of_truth_and_attacker(self):
        m = generate_world(11)
        firsts = set()
        for cond in [Condition("CLEAN", "NONE", 0), Condition("x", "A_COVER", 3),
                     Condition("y", "A_MISATTRIB", 1), Condition("z", "A_TRUST_HARVEST", 2)]:
            for e in range(4):
                r = run_episode(make_policies()["P_PROBE"], m, cond, 11, e)
                firsts.add(r.actions[0].split("=")[0])
        assert len(firsts) == 1

    def test_leak_actions_are_function_of_observations(self):
        """Same observation history -> same next action, whatever the hidden truth."""
        m = generate_world(12)
        acts = action_space(m)
        for name, pol in make_policies().items():
            if name == "P0_RANDOM_COST_MATCHED":
                continue
            seq = []
            for h in range(2):   # two different hidden truths behind an identical history
                b = JointBelief.from_prior(m)
                for a, o in [(0, 0), (acts.n - 1, 1)]:
                    b.update(acts, a, o)
                seq.append(pol.select(b, m, acts, 6.0, np.random.default_rng(h)))
            assert seq[0] == seq[1], name


# ---------------------------------------------------------------------------
# 9.7 Posterior normalisation and exactness
# ---------------------------------------------------------------------------
class TestPosterior:
    def test_matches_brute_force_enumeration(self):
        m = mk([0.8, 0.6, 0.7], [1, 1, 1], [1, 1, 1], [0.3, 0.1, 0.2], kappa=0.4, degr=[0.05, 0.1, 0.0])
        acts = action_space(m)
        b = JointBelief.from_prior(m)
        hist = [(0, 0), (3, 1), (1, 2), (0, 1), (5, 0)]
        for a, o in hist:
            b.update(acts, a, o)
        post = np.zeros(M)
        for h in range(M):
            for S in itertools.product(range(NS), repeat=3):
                p = m.prior_h[h] * np.prod([m.prior_s[h, q, S[q]] for q in range(3)])
                for a, o in hist:
                    q = acts.source[a]
                    p *= acts.lik[a, o, h, S[q]]
                post[h] += p
        assert np.allclose(b.p_h, post / post.sum())

    @pytest.mark.parametrize("cond", ALL_CONDITIONS)
    def test_normalised_under_every_condition(self, cond):
        m = generate_world(21)
        fam, bud = ("NONE", 0) if cond == "CLEAN" else (cond.rsplit("_B", 1)[0], int(cond.rsplit("_B", 1)[1]))
        for name, pol in make_policies().items():
            run_episode(pol, m, Condition(cond, fam, bud), 21, 0)   # validate() raises on any violation


# ---------------------------------------------------------------------------
# 9.8 Reproducibility, spend matching, world generation, attacker semantics
# ---------------------------------------------------------------------------
class TestReproducibility:
    def test_same_seed_same_outcome(self):
        m = generate_world(31)
        c = Condition("A2", "A_TRUST_HARVEST", 2)
        for name in make_policies():
            r1 = run_episode(make_policies()[name], m, c, 31, 4)
            r2 = run_episode(make_policies()[name], generate_world(31), c, 31, 4)
            assert r1.actions == r2.actions and r1.regret == r2.regret

    def test_spend_exactly_budget(self):
        for w in range(3):
            m = generate_world(40 + w)
            for name, pol in make_policies().items():
                r = run_episode(pol, m, Condition("A1", "A_COVER", 1), 40 + w, 0)
                assert r.spend == m.budget

    def test_world_generation_in_range(self):
        d = WorldDistribution()
        for s in range(30):
            m = generate_world(s)
            assert d.k_min <= m.n_sources <= d.k_max
            assert m.evidence_cost.min() == 1 and m.probe_cost.min() >= 1
            assert np.all(m.evidence_cost == np.round(m.evidence_cost))
            assert d.compromise_prior[0] <= m.params["compromise_prior"] <= d.compromise_prior[1]

    def test_config_matches_code(self):
        cfg = json.loads((ROOT / "configs/experiments/phase7l_probe_pilot_v2.json").read_text())
        assert cfg["world_distribution"] == distribution_as_dict()
        assert set(cfg["policies"]) == set(make_policies())
        assert tuple(cfg["primary_cells"]) == PRIMARY_CELLS
        assert cfg["primary_comparator"] == "P_JOINT_EIG_COST"
        assert cfg["practical_threshold_rrr"] == 0.10


class TestAttacker:
    def test_trust_harvest_first_answer_honest_then_takeover(self):
        m = generate_world(50)
        att = Attacker.create("A_TRUST_HARVEST", 2, m, h_true=1, kappa=0.0, u_present=0.9)
        assert att.present and not att.compromised
        att.observe_query(3)
        assert att.compromised == {3}
        att.observe_probe(3)
        assert att.forge(3, 1, 0.0, 0.0) is None          # lies low right after a probe
        assert att.forge(3, 1, 0.0, 0.0) == 0             # then covers up

    def test_heldout_targets_trusted_sources(self):
        m = generate_world(51)
        att = Attacker.create("A_MISATTRIB", 1, m, h_true=2, kappa=0.0, u_present=0.9)
        trust = m.accuracy * (1 - m.prior_s[1, :, COMPROMISED])
        assert att.compromised == {int(np.argmax(trust))}
        assert att.forge(next(iter(att.compromised)), 2, 0.0, 0.0) == 1   # misattribution

    def test_benign_presence_follows_kappa(self):
        m = generate_world(52)
        assert not Attacker.create("A_COVER", 2, m, 0, kappa=0.3, u_present=0.5).present
        assert Attacker.create("A_COVER", 2, m, 0, kappa=0.3, u_present=0.1).present
        assert not Attacker.create("NONE", 0, m, 1, kappa=1.0, u_present=0.0).present

    def test_truth_shared_across_conditions(self):
        m = generate_world(53)
        t1, t2 = sample_truth(m, 53, 7), sample_truth(m, 53, 7)
        assert t1.h_true == t2.h_true and np.array_equal(t1.u_query, t2.u_query)


# ---------------------------------------------------------------------------
# Analysis code (frozen with the protocol)
# ---------------------------------------------------------------------------
class TestAnalysis:
    def test_rrr_and_bootstrap(self):
        yx = np.full(100, 0.2)
        yp = np.full(100, 0.15)
        assert rrr(yp, yx) == pytest.approx(0.25)
        r = bootstrap_rrr(yp + np.random.default_rng(0).normal(0, 0.01, 100), yx)
        assert r["ci95"][0] > 0 and r["p_one_sided"] < 0.01

    def test_holm(self):
        adj = holm({"a": 0.01, "b": 0.04, "c": 0.03})
        assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}

    def test_wilcoxon_direction(self):
        rng = np.random.default_rng(1)
        assert wilcoxon_one_sided(rng.normal(0.5, 1, 200)) < 0.01
        assert wilcoxon_one_sided(rng.normal(-0.5, 1, 200)) > 0.9

    def test_required_worlds(self):
        small = required_worlds(0.01, 0.2)
        big = required_worlds(0.05, 0.2)
        assert small["n_worlds"] == 50 and big["n_worlds"] > small["n_worlds"]
        assert required_worlds(1.0, 0.01)["n_worlds"] == 400

    def test_gates_run_on_synthetic_data(self):
        rng = np.random.default_rng(2)
        pols = list(make_policies())
        agg, params = {}, {}
        for w in range(60):
            agg[str(w)] = {c: {p: {"norm_regret": float(rng.uniform(0, 3)), "n": 12, "n_probes": 5,
                                   "n_probes_suspicious": 3, "episodes_probing_suspicious": 4}
                               for p in pols} for c in ALL_CONDITIONS}
            params[str(w)] = {"compromise_prior": rng.uniform(0.02, 0.4), "probe_cost_ratio": rng.uniform(0.25, 2),
                              "probe_accuracy": rng.uniform(0.5, 0.99), "informativeness": rng.uniform(0.45, 0.95),
                              "loss_asymmetry": rng.uniform(1, 20)}
        g = evaluate_gates(agg, params, spend_ok=True, leakage_tests_ok=True)
        assert g["verdict"] in ("PROCEED", "KILL", "INVALID")
        assert {"PF-1", "PF-5", "PF-10", "phase_map"} <= set(g)
