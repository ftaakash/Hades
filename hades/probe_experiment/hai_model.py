"""
hades/probe_experiment/hai_model.py
-----------------------------------
Phase 7V: defender model and episode loop for the HAI replication
(docs/phase7v_hai_replication_protocol.md).

The defender model is estimated from the DEVELOPMENT version (HAI 20.07) only and then applied
unchanged to the confirmatory versions, so the confirmatory attacks are held out in every sense
(different collection campaign, different attack set, partly different scenarios).

  prior_h          episode-class frequencies in the development set
  prior_s          P(source q stale-spoofed | h): development frequency, Beta(0.5, 0.5)-smoothed,
                   0 for control outputs (not spoofable) and under NORMAL
  lik_query H      Dirichlet(1)-smoothed development frequency of o for healthy readings
  lik_query C      cover-up: rho * [o = 0] + (1 - rho) * healthy, rho = assumed_forge_rate (v2 value)
  lik_query D      uniform
  lik_probe        Beta(1, 1)-smoothed development FAIL rates for healthy and spoofed readings
                   (degraded = spoofed)
  utility          v2 structure: miss L_MISS, false alarm 1, misattribution 0.5 * L_MISS
  costs            query 1, probe 2, budget 6 (pre-registered; not data-derived)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np

from hades.probe_experiment.belief import ActionSpace, JointBelief, action_space
from hades.probe_experiment.hai import MAX_READS, SOURCES, SOURCE_NAMES, Episode
from hades.probe_experiment.world import COMPROMISED, DEGRADED, HEALTHY, M, N_OBS, NS, DefenderModel

HAI_MODEL_VERSION = "probe-hai-model-1.0"
QUERY_COST, PROBE_COST, BUDGET = 1.0, 2.0, 6.0
L_MISS, L_FA, MISATTRIB = 5.0, 1.0, 0.5
ASSUMED_FORGE_RATE = 0.9
DEGRADE_PRIOR = 0.01


def fit_model(dev: List[Episode]) -> DefenderModel:
    K = len(SOURCES)
    hs = np.array([e.h_true for e in dev])
    prior_h = np.bincount(hs, minlength=M).astype(float)
    prior_h /= prior_h.sum()

    prior_s = np.zeros((M, K, NS))
    for h in range(M):
        E = [e for e in dev if e.h_true == h]
        for q, (_, _, spoofable) in enumerate(SOURCES):
            pc = 0.0
            if h > 0 and spoofable:
                pc = (sum(q in e.compromised for e in E) + 0.5) / (len(E) + 1.0)
            prior_s[h, q] = [1.0 - pc - DEGRADE_PRIOR, DEGRADE_PRIOR, pc]

    lik_query = np.zeros((K, N_OBS, M, NS))
    for q in range(K):
        for h in range(M):
            cnt = np.ones(N_OBS)
            for e in dev:
                if e.h_true == h and q not in e.compromised:
                    cnt += np.bincount(e.query_obs[q], minlength=N_OBS)
            lik_query[q, :, h, HEALTHY] = cnt / cnt.sum()
        cover = np.zeros(N_OBS)
        cover[0] = 1.0
        lik_query[q, :, :, COMPROMISED] = (ASSUMED_FORGE_RATE * cover[:, None]
                                          + (1 - ASSUMED_FORGE_RATE) * lik_query[q, :, :, HEALTHY])
        lik_query[q, :, :, DEGRADED] = 1.0 / N_OBS

    fail_h = [1.0, 1.0]
    fail_c = [1.0, 1.0]
    for e in dev:
        for q in range(K):
            tgt = fail_c if q in e.compromised else fail_h
            tgt[0] += e.probe_obs[q].sum()
            tgt[1] += MAX_READS - e.probe_obs[q].sum()
    p_fail_h = fail_h[0] / sum(fail_h)
    p_fail_c = fail_c[0] / sum(fail_c)
    lik_probe = np.zeros((K, 2, NS))
    lik_probe[:, 1] = [p_fail_h, p_fail_c, p_fail_c]
    lik_probe[:, 0] = 1.0 - lik_probe[:, 1]

    U = np.zeros((M, M))
    for d in range(M):
        for h in range(M):
            U[d, h] = 0.0 if d == h else (-L_MISS if d == 0 else (-L_FA if h == 0 else -MISATTRIB * L_MISS))
    model = DefenderModel(
        world_id=-2007, source_names=list(SOURCE_NAMES), accuracy=np.full(K, np.nan),
        evidence_cost=np.full(K, QUERY_COST), probe_cost=np.full(K, PROBE_COST), prior_h=prior_h,
        prior_s=prior_s, lik_query=lik_query, lik_probe=lik_probe, utility=U, budget=BUDGET,
        assumed_forge_rate=ASSUMED_FORGE_RATE,
        params={"p_fail_healthy": p_fail_h, "p_fail_spoofed": p_fail_c, "n_dev": float(len(dev))})
    model.validate()
    return model


@dataclass
class HaiResult:
    policy: str
    episode: int
    h_true: int
    decision: int
    regret: float
    norm_regret: float
    spend: float
    n_queries: int
    n_probes: int
    n_compromised_read: int
    actions: List[str] = field(default_factory=list)


def run_hai_episode(policy, model: DefenderModel, ep: Episode, ep_id: int,
                    actions: ActionSpace | None = None) -> HaiResult:
    """Same loop as simulator.run_episode, with observations read from the recorded episode."""
    actions = actions or action_space(model)
    if hasattr(policy, "reset"):
        policy.reset(model)
    belief = JointBelief.from_prior(model)
    budget = float(model.budget)
    rng = np.random.default_rng([7_7_5_2, ep_id, sum(map(ord, policy.name))])
    nq = np.zeros(model.n_sources, int)
    npb = np.zeros(model.n_sources, int)
    comp_read = 0
    log: List[str] = []
    while (actions.cost <= budget + 1e-9).any():
        a = policy.select(belief, model, actions, budget, rng)
        if a is None or actions.cost[a] > budget + 1e-9:
            raise RuntimeError(f"{policy.name} returned an unaffordable/no action with budget left")
        q = int(actions.source[a])
        if actions.kind[a] == 0:
            o = int(ep.query_obs[q, min(nq[q], MAX_READS - 1)])
            comp_read += int(q in ep.compromised)
            nq[q] += 1
        else:
            o = int(ep.probe_obs[q, min(npb[q], MAX_READS - 1)])
            npb[q] += 1
        belief.update(actions, a, o)
        if hasattr(policy, "observe"):
            policy.observe(actions, a, o)
        budget -= actions.cost[a]
        log.append(f"{actions.names[a]}={o}")
    spent = model.budget - budget
    assert abs(spent - model.budget) < 1e-9, "spend not matched to budget"
    d = belief.bayes_decision(model.utility)
    regret = float(model.utility[ep.h_true, ep.h_true] - model.utility[d, ep.h_true])
    return HaiResult(policy.name, ep_id, ep.h_true, d, regret, regret / float(-model.utility.min()), spent,
                     int(nq.sum()), int(npb.sum()), comp_read, log)
