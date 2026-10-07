"""
hades/probe_experiment/simulator.py
-----------------------------------
Episode sampling and execution (plan §7H). Evaluator-side: holds the ground truth.

Pairing (common random numbers): the truth draw (H_true, degraded sources, adversary
presence) depends only on (world_seed, episode); the attacker condition only changes
what the adversary does. The k-th query of source q and the k-th probe of source q
use the same uniforms under every policy, so policies differ only through their
choices.

Cost matching: costs are integers, the minimum action cost is 1 and the budget is an
integer, and every policy must act while any action is affordable. Every policy
therefore spends exactly the budget (checked in ``run_episode``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from hades.probe_experiment.attacker import Attacker
from hades.probe_experiment.belief import ActionSpace, JointBelief, action_space
from hades.probe_experiment.world import (
    COMPROMISED, DEGRADED, FAIL, HEALTHY, M, N_OBS, PASS, DefenderModel,
)

MAX_PER_SOURCE = 64


@dataclass(frozen=True)
class Condition:
    name: str
    family: str          # "NONE" for clean
    budget: int          # number of sources the attacker may control


@dataclass
class EpisodeTruth:
    """Evaluator-only. Never passed to a policy."""
    h_true: int
    degraded: np.ndarray            # bool (K,)
    u_present: float
    u_query: np.ndarray             # (K, MAX, 3): forge coin, forge pick, emission
    u_probe: np.ndarray             # (K, MAX)


def sample_truth(model: DefenderModel, world_seed: int, episode: int) -> EpisodeTruth:
    rng = np.random.default_rng([7_7_1_0, world_seed, episode])
    h = int(rng.choice(M, p=model.prior_h))
    K = model.n_sources
    degr_p = model.prior_s[h, :, DEGRADED]
    degraded = rng.random(K) < degr_p
    return EpisodeTruth(
        h_true=h, degraded=degraded, u_present=float(rng.random()),
        u_query=rng.random((K, MAX_PER_SOURCE, 3)), u_probe=rng.random((K, MAX_PER_SOURCE)),
    )


@dataclass
class EpisodeResult:
    policy: str
    condition: str
    world_id: int
    episode: int
    h_true: int
    decision: int
    regret: float
    norm_regret: float
    spend: float
    n_queries: int
    n_probes: int
    n_probes_suspicious: int
    exposure: int                  # evidence answers produced by a controlled source
    n_forged: int
    n_compromised: int
    n_resolved: int                # controlled sources with final P(COMPROMISED|E) > 0.5
    n_false_flags: int             # uncontrolled sources with final P(COMPROMISED|E) > 0.5
    actions: List[str] = field(default_factory=list)


SUSPICIOUS = 0.10   # a source is "suspicious" when P(S_q = COMPROMISED | E) >= 0.10 at decision time


# Extra attacker families registered by later experiments (phase 7T). Each factory is
# called as factory(cond, model, truth, world_seed, episode) and returns an object with
# the Attacker interface. v2 families are untouched.
EXTRA_ATTACKERS: Dict[str, object] = {}


def make_attacker(cond: Condition, model: DefenderModel, truth: EpisodeTruth, world_seed: int, episode: int):
    if cond.family in EXTRA_ATTACKERS:
        return EXTRA_ATTACKERS[cond.family](cond, model, truth, world_seed, episode)
    return Attacker.create(cond.family, cond.budget, model, truth.h_true,
                           kappa=model.params.get("benign_coupling", 0.0), u_present=truth.u_present)


def _emit_query(model: DefenderModel, truth: EpisodeTruth, att: Attacker, q: int, k: int) -> tuple[int, bool]:
    u_forge, u_pick, u_emit = truth.u_query[q, k]
    h = truth.h_true
    if q in att.compromised:
        forged = att.forge(q, h, u_forge, u_pick)
        if forged is not None:
            return forged, True
        probs = model.lik_query[q, :, h, HEALTHY]       # honest answer from a controlled source
    elif truth.degraded[q]:
        probs = np.full(N_OBS, 1.0 / N_OBS)
    else:
        probs = model.lik_query[q, :, h, HEALTHY]
    return int(np.searchsorted(np.cumsum(probs), u_emit, side="right").clip(0, N_OBS - 1)), False


def _emit_probe(model: DefenderModel, truth: EpisodeTruth, att: Attacker, q: int, k: int) -> int:
    u = truth.u_probe[q, k]
    if q in att.compromised:
        p_fail = model.lik_probe[q, FAIL, COMPROMISED] * (1.0 - att.probe_evasion)
    elif truth.degraded[q]:
        p_fail = model.lik_probe[q, FAIL, DEGRADED]
    else:
        p_fail = model.lik_probe[q, FAIL, HEALTHY]
    return FAIL if u < p_fail else PASS


def run_episode(policy, model: DefenderModel, cond: Condition, world_seed: int, episode: int,
                actions: Optional[ActionSpace] = None) -> EpisodeResult:
    actions = actions or action_space(model)
    truth = sample_truth(model, world_seed, episode)
    att = make_attacker(cond, model, truth, world_seed, episode)
    if hasattr(policy, "reset"):
        policy.reset(model)
    belief = JointBelief.from_prior(model)
    budget = float(model.budget)
    rng = np.random.default_rng([7_7_2_0, world_seed, episode, sum(map(ord, policy.name))])
    counts_q = np.zeros(model.n_sources, int)
    counts_p = np.zeros(model.n_sources, int)
    n_probe_susp = exposure = n_forged = 0
    log: List[str] = []

    while (actions.cost <= budget + 1e-9).any():
        a = policy.select(belief, model, actions, budget, rng)
        if a is None or actions.cost[a] > budget + 1e-9:
            raise RuntimeError(f"{policy.name} returned an unaffordable/no action with budget left")
        q = int(actions.source[a])
        if actions.kind[a] == 0:
            was_controlled = q in att.compromised
            o, forged = _emit_query(model, truth, att, q, counts_q[q])
            counts_q[q] += 1
            exposure += int(was_controlled)
            n_forged += int(forged)
            att.observe_query(q)
        else:
            if belief.source_marginal()[q, COMPROMISED] >= SUSPICIOUS:
                n_probe_susp += 1
            o = _emit_probe(model, truth, att, q, counts_p[q])
            counts_p[q] += 1
            att.observe_probe(q)
        belief.update(actions, a, o)
        if hasattr(policy, "observe"):
            policy.observe(actions, a, o)      # the policy sees its own outcome, nothing else
        budget -= actions.cost[a]
        log.append(f"{actions.names[a]}={o}")

    spent = model.budget - budget
    assert abs(spent - model.budget) < 1e-9, "spend not matched to budget"
    d = belief.bayes_decision(model.utility)
    regret = float(model.utility[truth.h_true, truth.h_true] - model.utility[d, truth.h_true])
    max_loss = float(-model.utility.min())
    p_c = belief.source_marginal()[:, COMPROMISED]
    controlled = np.zeros(model.n_sources, bool)
    controlled[list(att.compromised)] = True
    return EpisodeResult(
        policy=policy.name, condition=cond.name, world_id=model.world_id, episode=episode,
        h_true=truth.h_true, decision=d, regret=regret, norm_regret=regret / max_loss, spend=spent,
        n_queries=int(counts_q.sum()), n_probes=int(counts_p.sum()), n_probes_suspicious=n_probe_susp,
        exposure=exposure, n_forged=n_forged, n_compromised=int(controlled.sum()),
        n_resolved=int((controlled & (p_c > 0.5)).sum()),
        n_false_flags=int((~controlled & (p_c > 0.5)).sum()), actions=log,
    )
