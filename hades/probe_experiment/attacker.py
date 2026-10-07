"""
hades/probe_experiment/attacker.py
----------------------------------
Strategic, budgeted attacker (plan §7I, protocol §5). Isolated from policies:
policies never import this module and never see its state (tests enforce this).

The attacker knows the public world description (which sources exist, how
informative and how expensive they are) and, for the adaptive family, observes
which actions the defender takes. Its budget is the number of sources it may
control.

Families
~~~~~~~~
A_COVER (design family; the defender's compromised-source model matches it)
    Targets the B most informative sources. A controlled source reports BENIGN
    with prob 0.90 under intrusion (cover-up) and a random intrusion indicator
    with prob 0.90 under benign (false flag); otherwise it reports honestly.
    Probes detect it with the world's probe accuracy.

A_MISATTRIB (held-out family; never used to design or tune any policy)
    Targets the B most *trusted* informative sources (max accuracy x (1 - prior
    compromise probability)), i.e. the sources a defender is least likely to probe.
    Under intrusion it reports the *other* intrusion class with prob 0.70
    (misattribution: pushes the wrong response); under benign it reports a
    random intrusion indicator with prob 0.70. Probes detect it normally.

A_TRUST_HARVEST (adaptive, policy-aware)
    Holds its budget in reserve. When the defender first queries a source, that
    answer is honest (trust is built); the attacker then takes the source over,
    up to B sources, and forges like A_COVER from the next query on. It is
    canary-aware and probe-aware: a probe of a controlled source passes with an
    extra prob 0.50 (it lets synthetic canary events through untouched), and the
    first query after the defender probes a source is answered honestly (it lies
    low while being watched).

Under H = BENIGN an adversary (an unrelated tamperer) is present with the
world's benign-coupling probability kappa; under intrusion it is present
whenever B > 0.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

import numpy as np

from hades.probe_experiment.world import DefenderModel

ATTACKER_VERSION = "probe-attacker-1.0"

FAMILIES = ("A_COVER", "A_MISATTRIB", "A_TRUST_HARVEST")
DESIGN_FAMILY = "A_COVER"
HELDOUT_FAMILY = "A_MISATTRIB"
ADAPTIVE_FAMILY = "A_TRUST_HARVEST"

FORGE_RATE = {"A_COVER": 0.90, "A_MISATTRIB": 0.70, "A_TRUST_HARVEST": 0.90}
PROBE_EVASION = {"A_COVER": 0.0, "A_MISATTRIB": 0.0, "A_TRUST_HARVEST": 0.50}


@dataclass
class Attacker:
    family: str
    budget: int
    present: bool
    compromised: Set[int] = field(default_factory=set)
    lying_low: Set[int] = field(default_factory=set)
    log: List[str] = field(default_factory=list)

    @classmethod
    def create(cls, family: str, budget: int, model: DefenderModel, h_true: int,
               kappa: float, u_present: float) -> "Attacker":
        if family not in FAMILIES and budget > 0:
            raise ValueError(family)
        present = budget > 0 and (h_true != 0 or u_present < kappa)
        att = cls(family=family, budget=budget, present=present)
        if present and family != ADAPTIVE_FAMILY:
            if family == DESIGN_FAMILY:
                order = sorted(range(model.n_sources), key=lambda q: (-model.accuracy[q], q))
            else:
                trust = model.accuracy * (1.0 - model.prior_s[1, :, 2])
                order = sorted(range(model.n_sources), key=lambda q: (-trust[q], q))
            att.compromised = set(order[:budget])
        return att

    # -- adaptive hook: called by the simulator AFTER the defender's query is answered
    def observe_query(self, q: int) -> None:
        if self.present and self.family == ADAPTIVE_FAMILY:
            if q not in self.compromised and len(self.compromised) < self.budget:
                self.compromised.add(q)
                self.log.append(f"take_over:{q}")

    def observe_probe(self, q: int) -> None:
        if self.present and self.family == ADAPTIVE_FAMILY and q in self.compromised:
            self.lying_low.add(q)

    def forge(self, q: int, h_true: int, u_forge: float, u_pick: float) -> int | None:
        """Forged outcome for a query of controlled source q, or None if this answer is honest."""
        if q in self.lying_low:
            self.lying_low.discard(q)
            return None
        if u_forge >= FORGE_RATE[self.family]:
            return None
        if h_true == 0:
            return 1 + int(u_pick * 2)            # false flag
        if self.family == HELDOUT_FAMILY:
            return 3 - h_true                     # misattribution (1 <-> 2)
        return 0                                  # cover-up

    @property
    def probe_evasion(self) -> float:
        return PROBE_EVASION.get(self.family, 0.0)
