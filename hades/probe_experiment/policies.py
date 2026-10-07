"""
hades/probe_experiment/policies.py
----------------------------------
Phase 7J policy set (protocol §6). Every policy

* sees only ``DefenderModel``, the shared ``JointBelief``, the ``ActionSpace`` and the
  remaining budget (no truth, no attacker identity, no attack budget);
* has the same action space (query or probe any source);
* makes no terminal decision: the simulator applies the same Bayes decision on the
  same exact posterior for everyone.

Policies differ **only in how an action is scored**:

    objective   what a unit of acquisition buys
                  h_info      reduction of H(H)              (information about H)
                  joint_info  reduction of H(H, S_1..S_K)    (information about H and source state)
                  decision    increase of max_d E[U(d,H)]    (decision value / VoI)
    model       which model scores the look-ahead
                  joint       exact joint P(H, S | E): source state persists and probes inform it
                  rhat        H-only model with contaminated likelihood
                              r_hat*p_nom + (1-r_hat)*uniform; probes update r_hat only
                  rhat_frozen same, but r_hat is never updated by a hypothetical outcome
                  nominal     every source assumed HEALTHY
    horizon     1 (myopic) or 2 (best follow-up action included)
    cost        value per unit cost (unit-free) or raw value

Two-step score of a first action a (for horizon 2, cost-aware):
    score(a) = max( V1(a)/c_a , max_{b affordable after a} V2(a,b)/(c_a + c_b) )
    V1(a)    = E_o[f(E+o)] - f(E)
    V2(a,b)  = E_o E_o'[f(E+o+o')] - f(E)          (b fixed before seeing o)

Fallback: the ``decision`` objective has VoI plateaus (no single outcome can flip the
decision). When every affordable score is <= 1e-12, decision-objective policies fall back
to the same look-ahead with the ``h_info`` objective of their own model. Fallback use is
logged and reported (protocol §7.3).

Ties: alphabetical max of (score rounded to 1e-12, action name), deterministic (AGENTS.md).

Citations: EIG — Lindley 1956; Naghshvar & Javidi 2013. Cost-aware EIG — Settles et al.
2008. Decision-theoretic VoI — Howard 1966; Heckerman, Breese & Rommelse 1995
(troubleshooting). Minimum-entropy measurement selection over component states —
de Kleer & Williams 1987 (GDE), the nearest prior art to P_JOINT_EIG_COST.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from hades.probe_experiment.belief import (
    ActionSpace, JointBelief, _entropy, branch, objective_after, objective_now, one_step,
)
from hades.probe_experiment.world import DefenderModel, HEALTHY, M, NS, N_OBS

POLICY_VERSION = "probe-policies-1.0"
ZERO = 1e-12


def argmax_tiebreak(scores: np.ndarray, mask: np.ndarray, names: List[str]) -> int:
    best = None
    for a in np.flatnonzero(mask):
        key = (round(float(scores[a]), 12), names[a])
        if best is None or key > best[0]:
            best = (key, int(a))
    if best is None:
        raise RuntimeError("no affordable action")
    return best[1]


# ---------------------------------------------------------------------------
# H-only reliability model (P3_RHAT family, P5_LEGACY, PF-5 ablation)
# ---------------------------------------------------------------------------
@dataclass
class RelState:
    p_h: np.ndarray        # (M,)
    m: np.ndarray          # (K, NS) source-state marginals; r_hat = m[:, HEALTHY]

    def copy(self) -> "RelState":
        return RelState(self.p_h.copy(), self.m.copy())


def _rel_lik(model: DefenderModel, st: RelState, mode: str) -> np.ndarray:
    """Evidence likelihood (K, O, M) for the H-only scoring models."""
    nom = model.lik_query[:, :, :, HEALTHY]                         # (K, O, M)
    if mode == "nominal":
        return nom
    if mode == "legacy":                                            # HADES 1.0 phi-mixture
        return np.einsum("qs,qohs->qoh", st.m, model.lik_query)
    r = st.m[:, HEALTHY][:, None, None]
    return r * nom + (1.0 - r) / N_OBS


def rel_one_step(model: DefenderModel, actions: ActionSpace, st: RelState, mode: str,
                 objective: str, update_rhat: bool):
    """Returns p_o (A, O), f_after (A, O) and a branch(a, o) -> RelState closure."""
    K = model.n_sources
    A = actions.n
    L = _rel_lik(model, st, mode)                                   # (K, O, M)
    p_o = np.zeros((A, N_OBS))
    f_after = np.zeros((A, N_OBS))
    f_now = _rel_objective(st.p_h, model, objective)
    # evidence actions
    joint = L * st.p_h[None, None, :]                               # (K, O, M)
    po_q = joint.sum(-1)
    post = joint / np.where(po_q > 0, po_q, 1.0)[..., None]
    p_o[:K] = po_q
    f_after[:K] = _rel_objective_batch(post, model, objective)
    # probe actions: H unchanged under this model
    pz = np.einsum("qs,qzs->qz", st.m, model.lik_probe)            # (K, 2)
    p_o[K:, :2] = pz
    f_after[K:, :2] = f_now

    def br(a: int, o: int) -> RelState:
        nxt = st.copy()
        q = int(actions.source[a])
        if a < K:
            nxt.p_h = post[q, o].copy()
        elif update_rhat and mode != "nominal":
            w = st.m[q] * model.lik_probe[q, o]
            nxt.m[q] = w / w.sum()
        return nxt

    return p_o, f_after, f_now, br


def _rel_objective(p_h: np.ndarray, model: DefenderModel, objective: str) -> float:
    if objective == "h_info":
        return -float(_entropy(p_h))
    if objective == "decision":
        return float((model.utility @ p_h).max())
    raise KeyError(f"objective {objective} not defined for H-only models")


def _rel_objective_batch(post: np.ndarray, model: DefenderModel, objective: str) -> np.ndarray:
    if objective == "h_info":
        return -_entropy(post)
    return np.einsum("dh,...h->...d", model.utility, post).max(-1)


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------
class Policy:
    name = "base"

    def __init__(self) -> None:
        self.fallback_steps = 0
        self.steps = 0

    def select(self, belief: JointBelief, model: DefenderModel, actions: ActionSpace,
               budget: float, rng: np.random.Generator) -> int:
        raise NotImplementedError


class RandomCostMatched(Policy):
    """P0_RANDOM_COST_MATCHED: uniform over affordable actions; spends the same fixed budget."""
    name = "P0_RANDOM_COST_MATCHED"

    def select(self, belief, model, actions, budget, rng):
        self.steps += 1
        ok = np.flatnonzero(actions.cost <= budget + 1e-9)
        return int(rng.choice(ok))


class LookaheadPolicy(Policy):
    def __init__(self, name: str, objective: str, model_kind: str, horizon: int,
                 cost_aware: bool, allow_probes: bool = True, legacy_lam: Optional[float] = None):
        super().__init__()
        self.name = name
        self.objective = objective
        self.model_kind = model_kind
        self.horizon = horizon
        self.cost_aware = cost_aware
        self.allow_probes = allow_probes
        self.legacy_lam = legacy_lam

    # -- one-step quantities under this policy's scoring model -------------
    def _step(self, model, actions, state, objective):
        if self.model_kind == "joint":
            la = one_step(state, actions, model.utility)
            f0 = objective_now(state, objective, model.utility)
            f1 = objective_after(la, objective)
            return la.p_o, f1, f0, (lambda a, o: branch(state, actions, la, a, o))
        mode = {"rhat": "rhat", "rhat_frozen": "rhat", "nominal": "nominal", "legacy": "legacy"}[self.model_kind]
        return rel_one_step(model, actions, state, mode, objective,
                            update_rhat=self.model_kind in ("rhat", "legacy"))

    def _initial_state(self, belief: JointBelief):
        if self.model_kind == "joint":
            return belief
        return RelState(belief.p_h.copy(), belief.source_marginal())

    def scores(self, belief, model, actions, budget, objective=None) -> np.ndarray:
        objective = objective or self.objective
        allowed = actions.cost <= budget + 1e-9
        if not self.allow_probes:
            allowed &= actions.kind == 0
        state = self._initial_state(belief)
        p_o, f1, f0, br = self._step(model, actions, state, objective)
        v1 = (p_o * f1).sum(-1) - f0
        c = actions.cost
        if self.legacy_lam is not None:                       # HADES 1.0 form: value - lam * cost/B
            return np.where(allowed, v1 - self.legacy_lam * c / model.budget, -np.inf)
        s = v1 / c if self.cost_aware else v1.copy()
        if self.horizon >= 2:
            for a in np.flatnonzero(allowed):
                follow = allowed & (c[a] + c <= budget + 1e-9)
                if not follow.any():
                    continue
                e2 = np.zeros(actions.n)
                for o in np.flatnonzero(p_o[a] > 0):
                    p2, f2, _, _ = self._step(model, actions, br(a, o), objective)
                    e2 += p_o[a, o] * (p2 * f2).sum(-1)
                v2 = e2 - f0
                pair = v2 / (c[a] + c) if self.cost_aware else v2
                s[a] = max(s[a], pair[follow].max())
        return np.where(allowed, s, -np.inf)

    def select(self, belief, model, actions, budget, rng):
        self.steps += 1
        allowed = actions.cost <= budget + 1e-9
        if not self.allow_probes:
            allowed &= actions.kind == 0
        s = self.scores(belief, model, actions, budget)
        if self.objective == "decision" and s[allowed].max() <= ZERO:
            self.fallback_steps += 1
            s = self.scores(belief, model, actions, budget, objective="h_info")
        return argmax_tiebreak(s, allowed, actions.names)


def make_policies() -> Dict[str, Policy]:
    """The frozen policy set (protocol §6). Returns fresh instances."""
    P = LookaheadPolicy
    ps: List[Policy] = [
        RandomCostMatched(),
        P("P3_NOM", "h_info", "nominal", 1, cost_aware=False),
        P("P3_NOM_COST", "h_info", "nominal", 1, cost_aware=True),
        P("P3_RHAT", "h_info", "rhat", 1, cost_aware=False),
        P("P3_RHAT_COST", "h_info", "rhat", 1, cost_aware=True),
        P("P3_RHAT_COST_LA2", "h_info", "rhat", 2, cost_aware=True),
        P("P5_LEGACY", "h_info", "legacy", 1, cost_aware=False, legacy_lam=1.0),
        P("P_JOINT_HEIG_COST", "h_info", "joint", 2, cost_aware=True),
        P("P_JOINT_EIG_COST", "joint_info", "joint", 2, cost_aware=True),
        P("P_PROBE", "decision", "joint", 2, cost_aware=True),
        P("P_PROBE_NO_S", "decision", "rhat_frozen", 2, cost_aware=True),
        P("P_PROBE_NO_PROBE", "decision", "joint", 2, cost_aware=True, allow_probes=False),
    ]
    return {p.name: p for p in ps}


PRIMARY_CANDIDATE = "P_PROBE"
PRIMARY_COMPARATOR = "P_JOINT_EIG_COST"
