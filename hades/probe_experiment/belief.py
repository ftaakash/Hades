"""
hades/probe_experiment/belief.py
--------------------------------
Exact joint posterior P(H, S_1..S_K | E) under the defender's model, and vectorised
one-step look-ahead over all actions.

Representation: sources are conditionally independent given H, and every action
touches one source, so the posterior factorises as

    P(H=h, S | E) = p_h[h] * prod_q cond[h, q, S_q]

with p_h normalised over h and each cond[h, q, :] normalised over states. This is
exact (no approximation) and keeps every array normalised by construction; the
invariant is still checked loudly after each update (AGENTS.md).

The joint posterior is substrate, not contribution (plan §1.2).

Actions: a in [0, K) is query(q=a); a in [K, 2K) is probe(q=a-K).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from hades.probe_experiment.world import DefenderModel, M, NS, N_OBS

N_OUT = N_OBS  # outcome axis width; probes use outcomes {0, 1} and pad outcome 2 with p=0
EPS = 1e-300


@dataclass(frozen=True)
class ActionSpace:
    names: List[str]
    kind: np.ndarray      # 0 = query, 1 = probe
    source: np.ndarray    # source index
    cost: np.ndarray
    lik: np.ndarray       # (A, N_OUT, M, NS) p(outcome | h, s_source)

    @property
    def n(self) -> int:
        return len(self.names)


def action_space(model: DefenderModel) -> ActionSpace:
    K = model.n_sources
    A = 2 * K
    lik = np.zeros((A, N_OUT, M, NS))
    lik[:K] = model.lik_query                                   # (K, O, M, NS)
    lik[K:, :2] = model.lik_probe[:, :, None, :]                # broadcast over h
    names = [f"query:{n}" for n in model.source_names] + [f"probe:{n}" for n in model.source_names]
    kind = np.array([0] * K + [1] * K)
    source = np.concatenate([np.arange(K), np.arange(K)])
    cost = np.concatenate([model.evidence_cost, model.probe_cost])
    return ActionSpace(names=names, kind=kind, source=source, cost=cost, lik=lik)


def _entropy(p: np.ndarray, axis: int = -1) -> np.ndarray:
    """Shannon entropy in bits along ``axis``."""
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(p > 1e-15, -p * np.log2(np.where(p > 1e-15, p, 1.0)), 0.0)
    return t.sum(axis=axis)


class JointBelief:
    def __init__(self, p_h: np.ndarray, cond: np.ndarray):
        self.p_h = p_h
        self.cond = cond

    @classmethod
    def from_prior(cls, model: DefenderModel) -> "JointBelief":
        return cls(model.prior_h.copy(), model.prior_s.copy())

    def copy(self) -> "JointBelief":
        return JointBelief(self.p_h.copy(), self.cond.copy())

    # ---- marginals --------------------------------------------------------
    def source_marginal(self) -> np.ndarray:
        """P(S_q = s | E), shape (K, NS)."""
        return np.einsum("h,hqs->qs", self.p_h, self.cond)

    def reliability(self) -> np.ndarray:
        """r_hat_q = P(S_q = HEALTHY | E) — the estimated reliability used by P3_RHAT*."""
        return self.source_marginal()[:, 0]

    def h_entropy(self) -> float:
        return float(_entropy(self.p_h))

    def joint_entropy(self) -> float:
        """H(H, S) = H(H) + sum_h p(h) sum_q H(S_q | h)."""
        return float(_entropy(self.p_h) + self.p_h @ _entropy(self.cond).sum(-1))

    def decision_value(self, utility: np.ndarray) -> float:
        return float((utility @ self.p_h).max())

    def bayes_decision(self, utility: np.ndarray) -> int:
        """argmax_d E[U(d,H)|E]; ties -> lowest index (CLOSE before responses)."""
        eu = utility @ self.p_h
        return int(np.flatnonzero(eu >= eu.max() - 1e-12)[0])

    # ---- update -----------------------------------------------------------
    def update(self, actions: ActionSpace, a: int, outcome: int) -> None:
        q = int(actions.source[a])
        lik = actions.lik[a, outcome]                    # (M, NS)
        num = self.cond[:, q, :] * lik                   # (M, NS)
        ratio = num.sum(-1)                              # (M,)
        joint = self.p_h * ratio
        z = joint.sum()
        if z <= 0:
            raise ValueError(f"zero-probability outcome {outcome} for action {actions.names[a]}")
        self.p_h = joint / z
        safe = np.where(ratio > 0, ratio, 1.0)
        new_cond = np.where(ratio[:, None] > 0, num / safe[:, None], self.cond[:, q, :])
        self.cond[:, q, :] = new_cond
        self.validate()

    def validate(self) -> None:
        if abs(self.p_h.sum() - 1.0) > 1e-9 or (self.p_h < -1e-12).any():
            raise AssertionError(f"P(H|E) not normalised: {self.p_h}")
        s = self.cond.sum(-1)
        if not np.allclose(s, 1.0, atol=1e-9):
            raise AssertionError("P(S_q|H,E) not normalised")


@dataclass
class Lookahead:
    """One-step predictive quantities for every action and outcome."""
    p_o: np.ndarray       # (A, O)
    post_h: np.ndarray    # (A, O, M)
    h_ent: np.ndarray     # (A, O)   H(H) after
    j_ent: np.ndarray     # (A, O)   H(H,S) after
    d_val: np.ndarray     # (A, O)   max_d E[U] after
    new_cond: np.ndarray  # (A, O, M, NS)  updated cond slice for the touched source


def one_step(belief: JointBelief, actions: ActionSpace, utility: np.ndarray) -> Lookahead:
    cond_a = belief.cond[:, actions.source, :].transpose(1, 0, 2)    # (A, M, NS)
    num = cond_a[:, None, :, :] * actions.lik                         # (A, O, M, NS)
    ratio = num.sum(-1)                                               # (A, O, M)
    joint = belief.p_h[None, None, :] * ratio
    p_o = joint.sum(-1)                                               # (A, O)
    safe_po = np.where(p_o > 0, p_o, 1.0)
    post_h = joint / safe_po[..., None]
    safe_r = np.where(ratio > 0, ratio, 1.0)
    new_cond = num / safe_r[..., None]
    h_ent = _entropy(post_h)
    hs_old = _entropy(belief.cond)                                    # (M, K)
    c_tot = hs_old.sum(-1)                                            # (M,)
    hs_old_a = hs_old[:, actions.source].T                            # (A, M)
    hs_new = _entropy(new_cond)                                       # (A, O, M)
    cond_ent = c_tot[None, None, :] - hs_old_a[:, None, :] + hs_new
    j_ent = h_ent + (post_h * cond_ent).sum(-1)
    d_val = np.einsum("dh,aoh->aod", utility, post_h).max(-1)
    return Lookahead(p_o=p_o, post_h=post_h, h_ent=h_ent, j_ent=j_ent, d_val=d_val, new_cond=new_cond)


def branch(belief: JointBelief, actions: ActionSpace, la: Lookahead, a: int, o: int) -> JointBelief:
    """Belief after hypothetical outcome ``o`` of action ``a`` (uses cached look-ahead)."""
    b = JointBelief(la.post_h[a, o].copy(), belief.cond.copy())
    b.cond[:, int(actions.source[a]), :] = la.new_cond[a, o]
    return b


OBJECTIVES: Dict[str, str] = {
    "h_info": "negative H-entropy  -H(H|E)",
    "joint_info": "negative joint entropy  -H(H,S|E)",
    "decision": "Bayes decision value  max_d E[U(d,H)|E]",
}


def objective_now(belief: JointBelief, objective: str, utility: np.ndarray) -> float:
    if objective == "h_info":
        return -belief.h_entropy()
    if objective == "joint_info":
        return -belief.joint_entropy()
    if objective == "decision":
        return belief.decision_value(utility)
    raise KeyError(objective)


def objective_after(la: Lookahead, objective: str) -> np.ndarray:
    if objective == "h_info":
        return -la.h_ent
    if objective == "joint_info":
        return -la.j_ent
    if objective == "decision":
        return la.d_val
    raise KeyError(objective)
