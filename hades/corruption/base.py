"""hades/corruption/base.py — Corruptor ABC and ObsContext.

All corruption regimes implement the Corruptor interface:

    corrupt(obs_class: str, ctx: ObsContext, rng: random.Random) -> str

The corruptor may replace the observation class with a different class,
or leave it unchanged. It must NEVER modify the ground-truth hypothesis,
reliability_true, or any evaluator-only fields.

ObsContext carries the minimal information a corruptor needs to act.
The policy_visible fields are intentionally excluded — the corruptor
acts on the observation stream before the policy ever sees it.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple


# Canonical observation classes — imported from the simulator vocabulary.
# Using the simulator's 5-class system as ground truth.
# strong_support / weak_support → informative (increases leading belief)
# neutral                       → uninformative
# weak_contra / strong_contra   → counter-evidence (decreases leading belief)
from hades.simulator.observations import OBS_CLASSES as _OBS_DICT
OBS_CLASSES: Tuple[str, ...] = tuple(_OBS_DICT.keys())

# Semantic categories for corruptor decision logic
SUPPORTING = ("strong_support", "weak_support")
CONTRA      = ("weak_contra",   "strong_contra")
UNINFORMATIVE = "neutral"


@dataclass
class ObsContext:
    """Context passed to every corruptor at corruption time.

    Fields
    ------
    source_name        : Name of the evidence source being queried.
    true_hypothesis    : Evaluator-only ground truth (corruptors may use this
                         for R3/R4 plausibility, but NEVER leak to policy).
    query_history      : Ordered list of sources queried so far (for R4).
    current_beliefs    : Policy-visible beliefs at time of query (for R4 targeting).
    reliability_true   : True operational reliability of this source.
    manipulation_risk_true : True P(attacker can forge this source).
    hypothesis_affinity : {hyp: relevance} for this source.
    """
    source_name: str
    true_hypothesis: str
    query_history: List[str] = field(default_factory=list)
    current_beliefs: Dict[str, float] = field(default_factory=dict)
    reliability_true: float = 1.0
    manipulation_risk_true: float = 0.0
    hypothesis_affinity: Dict[str, float] = field(default_factory=dict)


class Corruptor(ABC):
    """Abstract base class for all corruption regimes.

    Invariants all subclasses must obey
    ------------------------------------
    1. Only the returned obs_class string changes. Never mutate ctx.
    2. Ground truth (true_hypothesis, reliability_true) is read-only.
    3. Deterministic given rng state.
    4. Return an obs_class that is a member of OBS_CLASSES.
    """

    regime: str = "R_unknown"

    @abstractmethod
    def corrupt(
        self,
        obs_class: str,
        ctx: ObsContext,
        rng: random.Random,
    ) -> str:
        """Apply corruption to obs_class. Return (possibly modified) obs_class."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(regime={self.regime})"
