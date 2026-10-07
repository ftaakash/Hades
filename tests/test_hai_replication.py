"""
tests/test_hai_replication.py
-----------------------------
Phase 7V mechanism tests (docs/phase7v_hai_replication_protocol.md). Uses synthetic episodes only, so it never
reads the confirmatory HAI versions; all must pass before the replication run.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np

from hades.probe_experiment import hai
from hades.probe_experiment.belief import action_space
from hades.probe_experiment.hai import MAX_READS, SOURCE_NAMES, SOURCES, Episode
from hades.probe_experiment.hai_eval import evaluate_hai_gates, prior_only_regret
from hades.probe_experiment.hai_model import BUDGET, HaiResult, fit_model, run_hai_episode
from hades.probe_experiment.joint_confirm import CANDIDATE, COMPARATORS, JOINT_POLICY_NAMES, make_joint_policies

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "experiments" / "phase7v_hai_replication_v1.json"
META = ROOT / "configs" / "data" / "hai_attack_metadata.json"
K = len(SOURCES)


def synth(n: int = 60, seed: int = 0):
    rng = np.random.default_rng(seed)
    eps = []
    for i in range(n):
        h = int(rng.integers(0, 3))
        comp = [] if h == 0 else [int(q) for q in rng.choice([0, 1, 2, 6], size=int(rng.integers(0, 2)), replace=False)]
        qo = np.zeros((K, MAX_READS), int)
        for q, (_, cls, _) in enumerate(SOURCES):
            p = 0.03 if h == 0 else (0.5 if (cls == 1) == (h == 1) else 0.08)
            qo[q] = np.where(rng.random(MAX_READS) < p, cls, 0)
            if q in comp:
                qo[q] = 0
        po = (rng.random((K, MAX_READS)) < np.array([[0.65 if q in comp else 0.3] for q in range(K)])).astype(int)
        eps.append(Episode("synthetic", "t", str(i), h, i if h else 0, comp, qo, po))
    return eps


class TestModel:
    def test_valid_and_structural_zeros(self):
        m = fit_model(synth())
        m.validate()
        for q, (_, _, spoofable) in enumerate(SOURCES):
            assert m.prior_s[0, q, 2] == 0
            if not spoofable:
                assert (m.prior_s[:, q, 2] == 0).all()
        assert m.budget == BUDGET and m.source_names == SOURCE_NAMES
        assert m.params["p_fail_spoofed"] > m.params["p_fail_healthy"]

    def test_cover_up_puts_mass_on_quiet(self):
        m = fit_model(synth())
        assert (m.lik_query[:, 0, 1:, 2] >= m.lik_query[:, 0, 1:, 0]).all()


class TestLeakage:
    def test_leak_select_signature(self):
        for p in make_joint_policies().values():
            assert set(inspect.signature(p.select).parameters) == {"belief", "model", "actions", "budget", "rng"}

    def test_leak_actions_ignore_labels(self):
        """Same observations, different ground-truth labels: identical action sequences and decisions."""
        eps = synth(20, 1)
        m = fit_model(synth())
        acts = action_space(m)
        for e in eps:
            relabelled = Episode(e.version, e.file, e.onset, (e.h_true + 1) % 3, 99, [3, 4], e.query_obs, e.probe_obs)
            for p in JOINT_POLICY_NAMES:
                a = run_hai_episode(make_joint_policies()[p], m, e, 0, acts)
                b = run_hai_episode(make_joint_policies()[p], m, relabelled, 0, acts)
                assert a.actions == b.actions and a.decision == b.decision, p

    def test_leak_model_fit_on_dev_only(self):
        cfg = json.loads(CONFIG.read_text())
        assert cfg["dev_version"] == "hai-20.07" and cfg["dev_version"] not in cfg["confirm_versions"]
        src = (ROOT / "scripts" / "run_hai_replication.py").read_text()
        assert src.count("fit_model(") == 1 and "model = fit_model(dev)" in src


class TestHarness:
    def test_spend_exact_and_regret_range(self):
        m = fit_model(synth())
        acts = action_space(m)
        for i, e in enumerate(synth(15, 2)):
            for p in make_joint_policies().values():
                r: HaiResult = run_hai_episode(p, m, e, i, acts)
                assert abs(r.spend - m.budget) < 1e-9, p.name
                assert 0 <= r.norm_regret <= 1

    def test_reads_beyond_six_repeat_last(self):
        m = fit_model(synth())
        e = synth(1, 3)[0]
        r = run_hai_episode(make_joint_policies()["P3_NOM"], m, e, 0)
        assert len(r.actions) >= 1

    def test_prior_only_regret(self):
        U = np.array([[0, -5, -5], [-1, 0, -2.5], [-1, -2.5, 0]], float)
        r = prior_only_regret(U, np.array([0.5, 0.237, 0.263]), np.array([0, 1, 2]))
        assert np.allclose(r, [0.2, 0.5, 0.0])

    def test_config_matches_code(self):
        cfg = json.loads(CONFIG.read_text())
        assert cfg["status"] == "FROZEN" and cfg["pilot_decision_deadline"] == "2026-11-11"
        assert tuple(cfg["policies"]) == JOINT_POLICY_NAMES
        assert cfg["candidate"] == CANDIDATE and tuple(cfg["comparators"]) == COMPARATORS
        assert cfg["adapter"]["sources"] == SOURCE_NAMES and cfg["adapter"]["hai_version"] == hai.HAI_VERSION
        assert cfg["adapter"]["sub_seconds"] == hai.SUB and cfg["adapter"]["max_reads"] == hai.MAX_READS
        assert cfg["practical_threshold_rrr"] == 0.1 and cfg["alpha_one_sided"] == 0.025

    def test_metadata_sources_known(self):
        meta = json.loads(META.read_text())
        for v in ("hai-20.07", "hai-21.03", "hai-22.04"):
            for names in meta[v]["spoofed"].values():
                assert set(names) <= set(SOURCE_NAMES)
                assert all(SOURCES[SOURCE_NAMES.index(n)][2] for n in names)


class TestGates:
    def _arrays(self, gain, n=120, seed=0):
        rng = np.random.default_rng(seed)
        h = rng.integers(0, 3, n)
        base = {p: (rng.random(n) < 0.3) * 0.5 for p in JOINT_POLICY_NAMES}
        base[CANDIDATE] = base[COMPARATORS[0]] * (rng.random(n) >= gain)
        base[COMPARATORS[1]] = base[COMPARATORS[0]].copy()
        base["P3_NOM"] = base[COMPARATORS[0]] * 0.5
        return base, h, np.zeros(n, int), np.full(n, 0.6)

    def test_proceed_on_clear_gain(self):
        a, h, c, pr = self._arrays(0.6)
        assert evaluate_hai_gates(a, h, c, pr, True, True)["verdict"] == "PROCEED"

    def test_kill_without_gain(self):
        a, h, c, pr = self._arrays(0.0)
        assert evaluate_hai_gates(a, h, c, pr, True, True)["verdict"] == "KILL"

    def test_kill_on_spend(self):
        a, h, c, pr = self._arrays(0.6)
        assert evaluate_hai_gates(a, h, c, pr, False, True)["verdict"] == "KILL"

    def test_inconclusive_when_underpowered(self):
        """Point estimate above threshold, one half against it: neither PROCEED nor KILL."""
        n = 30
        h = np.array([0] * 10 + [1] * 10 + [2] * 10)
        x = np.zeros(n)
        x[10:20] = 0.5
        cand = x.copy()
        cand[[10, 12, 14]] = 0.0                     # gain on even indices only
        cand[11] = 1.0                               # loss on an odd index
        a = {p: x.copy() for p in JOINT_POLICY_NAMES}
        a[CANDIDATE] = cand
        a["P3_NOM"] = x * 0.5
        g = evaluate_hai_gates(a, h, np.zeros(n, int), np.full(n, 0.6), True, True)
        assert g["HG-3"]["pass"] and not g["HG-6"]["pass"]
        assert g["verdict"] == "INCONCLUSIVE"

    def test_invalid_when_evidence_useless(self):
        a, h, c, pr = self._arrays(0.6)
        assert evaluate_hai_gates(a, h, c, np.zeros_like(pr), True, True)["verdict"] == "INVALID"
