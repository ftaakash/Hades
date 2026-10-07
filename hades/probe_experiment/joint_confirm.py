"""
hades/probe_experiment/joint_confirm.py
---------------------------------------
Phase 7U: confirmatory test of joint source-state belief (docs/phase7u_joint_belief_protocol.md).

Origin (exploratory, stated as such): in both killed pilots, P_JOINT_HEIG_COST (two-step hypothesis
information per unit cost under the joint (H, S) posterior) had lower regret than reliability-weighted
EIG (P3_RHAT_COST): 28% over all v2 attacker cells, 55% on the 7T held-out attacker. 7U tests that
claim prospectively, on fresh worlds and against a new held-out attacker written before any 7U run.

Candidate  P_JOINT_HEIG_COST (unchanged v2 policy; no new parameters)
Comparators P3_RHAT_COST_LA2 (reliability-weighted EIG, horizon and cost matched to the candidate)
            P_JOINT_EIG_COST (the v2 primary comparator)

New held-out attacker A_COLLUDE_CHEAP (never used to design, tune or test a policy):
controls the B cheapest sources (ties: lowest index), i.e. the sources a cost-aware defender is most
likely to read; every controlled source tells the SAME lie, drawn once per episode (under an intrusion:
BENIGN or the other intrusion class with prob 1/2 each; under BENIGN: a random intrusion class), with
prob 0.85 per answer; probes of a controlled source pass with an extra prob 0.40; no adaptation.
Under BENIGN it is present with prob kappa, like every other family.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set

import numpy as np

from hades.probe_experiment import robust  # noqa: F401  (registers A_DECOY_MIGRATE)
from hades.probe_experiment.policies import Policy, make_policies
from hades.probe_experiment.simulator import EXTRA_ATTACKERS, Condition, EpisodeTruth
from hades.probe_experiment.world import M, DefenderModel

JOINT_CONFIRM_VERSION = "probe-joint-confirm-1.0"
NEW_FAMILY = "A_COLLUDE_CHEAP"
COLLUDE_FORGE_RATE = 0.85
COLLUDE_PROBE_EVASION = 0.40


@dataclass
class ColludeCheapAttacker:
    family: str
    budget: int
    present: bool
    lie: int
    compromised: Set[int] = field(default_factory=set)
    log: List[str] = field(default_factory=list)
    probe_evasion: float = COLLUDE_PROBE_EVASION

    def observe_query(self, q: int) -> None:
        pass

    def observe_probe(self, q: int) -> None:
        pass

    def forge(self, q: int, h_true: int, u_forge: float, u_pick: float):
        return self.lie if u_forge < COLLUDE_FORGE_RATE else None


def _make_collude_cheap(cond: Condition, model: DefenderModel, truth: EpisodeTruth, world_seed: int, episode: int):
    rng = np.random.default_rng([7_7_4_0, world_seed, episode])
    kappa = model.params.get("benign_coupling", 0.0)
    present = cond.budget > 0 and (truth.h_true != 0 or truth.u_present < kappa)
    others = [h for h in range(M) if h != truth.h_true and (truth.h_true != 0 or h != 0)]
    lie = int(rng.choice(others))
    order = sorted(range(model.n_sources), key=lambda q: (model.evidence_cost[q], q))
    targets = set(order[:cond.budget]) if present else set()
    return ColludeCheapAttacker(family=NEW_FAMILY, budget=cond.budget, present=present, lie=lie,
                                compromised=targets)


EXTRA_ATTACKERS[NEW_FAMILY] = _make_collude_cheap

JOINT_POLICY_NAMES = ("P0_RANDOM_COST_MATCHED", "P3_NOM", "P3_RHAT_COST", "P3_RHAT_COST_LA2",
                      "P_JOINT_HEIG_COST", "P_JOINT_EIG_COST", "P_PROBE")
CANDIDATE = "P_JOINT_HEIG_COST"
COMPARATORS = ("P3_RHAT_COST_LA2", "P_JOINT_EIG_COST")


def make_joint_policies() -> Dict[str, Policy]:
    base = make_policies()
    return {n: base[n] for n in JOINT_POLICY_NAMES}
