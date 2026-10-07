"""
hades/probe_experiment/robust.py
--------------------------------
Phase 7T: robust-acquisition follow-up (docs/phase7t_robust_acquisition_protocol.md).

Motivated by an exploratory observation in the killed v2 pilot: against attackers the
defender's model does not match, model-based acquisition lost its edge, and against a
policy-aware attacker random acquisition beat every model-based policy.

Two candidate policies, both built on the primary v2 comparator P_JOINT_EIG_COST
(two-step joint (H,S) information gain per unit cost), so each differs from it in one way:

P_RAND_JEIG      randomisation. Samples the next action with probability proportional to
                 its (non-negative) P_JOINT_EIG_COST score; uniform if every score is 0.
                 No temperature or other tuned parameter. Cf. probability matching /
                 information-directed sampling (Russo & Van Roy 2014) and mixed
                 strategies in security games (Tambe 2011).

P_MINIMAX_JEIG   model robustness. Keeps an exact posterior under each of three
                 compromised-source models known at design time (cover-up, misattribution,
                 noise) and scores each action by its worst-case P_JOINT_EIG_COST score
                 over the three models. Cf. robust / minimax Bayesian experimental design.

New held-out attacker A_DECOY_MIGRATE (never used to design, tune or test a policy):
controls B sources chosen uniformly at random; each controlled source reports one
sticky decoy class (fixed per episode, never the true hypothesis) with prob 0.80; a
probe of a controlled source passes with an extra prob 0.30; and when the defender
probes a controlled source the attacker abandons it and takes over the unprobed,
uncontrolled source the defender has queried most. Under BENIGN it is present with
prob kappa and its decoy is an intrusion class.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Set

import numpy as np

from hades.probe_experiment.belief import ActionSpace, JointBelief, action_space
from hades.probe_experiment.policies import LookaheadPolicy, Policy, argmax_tiebreak, make_policies
from hades.probe_experiment.simulator import EXTRA_ATTACKERS, Condition, EpisodeTruth
from hades.probe_experiment.world import COMPROMISED, HEALTHY, M, N_OBS, DefenderModel

ROBUST_VERSION = "probe-robust-1.0"
NEW_FAMILY = "A_DECOY_MIGRATE"
DECOY_FORGE_RATE = 0.80
DECOY_PROBE_EVASION = 0.30


# ---------------------------------------------------------------------------
# New held-out attacker
# ---------------------------------------------------------------------------
@dataclass
class DecoyMigrateAttacker:
    family: str
    budget: int
    present: bool
    decoy: int
    compromised: Set[int] = field(default_factory=set)
    queried: Dict[int, int] = field(default_factory=dict)
    probed: Set[int] = field(default_factory=set)
    log: List[str] = field(default_factory=list)
    probe_evasion: float = DECOY_PROBE_EVASION

    def observe_query(self, q: int) -> None:
        self.queried[q] = self.queried.get(q, 0) + 1

    def observe_probe(self, q: int) -> None:
        self.probed.add(q)
        if self.present and q in self.compromised:
            self.compromised.discard(q)
            cands = [s for s, n in self.queried.items() if s not in self.probed and s not in self.compromised]
            if cands:
                new = max(cands, key=lambda s: (self.queried[s], -s))
                self.compromised.add(new)
                self.log.append(f"migrate:{q}->{new}")

    def forge(self, q: int, h_true: int, u_forge: float, u_pick: float):
        return self.decoy if u_forge < DECOY_FORGE_RATE else None


def _make_decoy_migrate(cond: Condition, model: DefenderModel, truth: EpisodeTruth, world_seed: int, episode: int):
    rng = np.random.default_rng([7_7_3_0, world_seed, episode])
    kappa = model.params.get("benign_coupling", 0.0)
    present = cond.budget > 0 and (truth.h_true != 0 or truth.u_present < kappa)
    others = [h for h in range(M) if h != truth.h_true and (truth.h_true != 0 or h != 0)]
    decoy = int(rng.choice(others))
    targets = rng.choice(model.n_sources, size=min(cond.budget, model.n_sources), replace=False) if present else []
    return DecoyMigrateAttacker(family=NEW_FAMILY, budget=cond.budget, present=present, decoy=decoy,
                                compromised=set(int(t) for t in targets))


EXTRA_ATTACKERS[NEW_FAMILY] = _make_decoy_migrate


# ---------------------------------------------------------------------------
# Candidate policies
# ---------------------------------------------------------------------------
def _jeig() -> LookaheadPolicy:
    return LookaheadPolicy("P_JOINT_EIG_COST", "joint_info", "joint", 2, cost_aware=True)


class RandomizedJointEIG(Policy):
    """P_RAND_JEIG: sample actions with probability proportional to the P_JOINT_EIG_COST score."""
    name = "P_RAND_JEIG"

    def __init__(self) -> None:
        super().__init__()
        self._inner = _jeig()

    def probabilities(self, belief, model, actions, budget) -> np.ndarray:
        allowed = actions.cost <= budget + 1e-9
        s = self._inner.scores(belief, model, actions, budget)
        w = np.where(allowed, np.maximum(s, 0.0), 0.0)
        if w.sum() <= 0:
            w = allowed.astype(float)
        return w / w.sum()

    def select(self, belief, model, actions, budget, rng):
        self.steps += 1
        p = self.probabilities(belief, model, actions, budget)
        return int(rng.choice(actions.n, p=p))


def alternative_models(model: DefenderModel) -> Dict[str, DefenderModel]:
    """Compromised-source models known at design time: cover-up (the defender's own), misattribution, noise."""
    out = {"COVER": model}
    nom = model.lik_query[:, :, :, HEALTHY]
    F = np.zeros((N_OBS, M))
    F[2, 1] = F[1, 2] = 1.0                 # intrusion -> the other intrusion class
    F[1:, 0] = 0.5                          # benign -> random intrusion indicator
    mis = copy.deepcopy(model)
    mis.lik_query[:, :, :, COMPROMISED] = 0.7 * F[None] + 0.3 * nom
    out["MISATTRIB"] = mis
    noise = copy.deepcopy(model)
    noise.lik_query[:, :, :, COMPROMISED] = 1.0 / N_OBS
    out["NOISE"] = noise
    for m in out.values():
        m.validate()
    return out


class MinimaxJointEIG(Policy):
    """P_MINIMAX_JEIG: worst-case P_JOINT_EIG_COST score over three compromised-source models."""
    name = "P_MINIMAX_JEIG"

    def __init__(self) -> None:
        super().__init__()
        self._inner = _jeig()
        self._models: Dict[str, DefenderModel] = {}
        self._acts: Dict[str, ActionSpace] = {}
        self._beliefs: Dict[str, JointBelief] = {}

    def reset(self, model: DefenderModel) -> None:
        self._models = alternative_models(model)
        self._acts = {k: action_space(m) for k, m in self._models.items() if k != "COVER"}
        self._beliefs = {k: JointBelief.from_prior(m) for k, m in self._models.items() if k != "COVER"}

    def observe(self, actions: ActionSpace, a: int, o: int) -> None:
        for k, b in self._beliefs.items():
            b.update(self._acts[k], a, o)

    def model_scores(self, belief, model, actions, budget) -> Dict[str, np.ndarray]:
        if not self._models:
            self.reset(model)
        out = {"COVER": self._inner.scores(belief, model, actions, budget)}
        for k, b in self._beliefs.items():
            out[k] = self._inner.scores(b, self._models[k], self._acts[k], budget)
        return out

    def select(self, belief, model, actions, budget, rng):
        self.steps += 1
        allowed = actions.cost <= budget + 1e-9
        s = np.min(np.stack(list(self.model_scores(belief, model, actions, budget).values())), axis=0)
        return argmax_tiebreak(s, allowed, actions.names)


ROBUST_POLICY_NAMES = ("P0_RANDOM_COST_MATCHED", "P3_NOM", "P3_RHAT_COST", "P_JOINT_HEIG_COST",
                       "P_JOINT_EIG_COST", "P_PROBE", "P_RAND_JEIG", "P_MINIMAX_JEIG")
CANDIDATES = ("P_RAND_JEIG", "P_MINIMAX_JEIG")
COMPARATORS = ("P_JOINT_EIG_COST", "P0_RANDOM_COST_MATCHED")


def make_robust_policies() -> Dict[str, Policy]:
    base = make_policies()
    ps = {n: base[n] for n in ROBUST_POLICY_NAMES if n in base}
    ps["P_RAND_JEIG"] = RandomizedJointEIG()
    ps["P_MINIMAX_JEIG"] = MinimaxJointEIG()
    return {n: ps[n] for n in ROBUST_POLICY_NAMES}
