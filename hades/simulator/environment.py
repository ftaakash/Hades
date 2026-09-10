"""
hades/simulator/environment.py
-------------------------------
SimEnv: the minimal synthetic investigation environment.

Design goals
~~~~~~~~~~~~
* Deterministic (given seed) — every simulator run is reproducible.
* Fast (~microseconds per step, not seconds like CDB with its SQLite inserts).
* Transparent — every parameter is explicit and human-readable.
* Provides the cheapest possible falsification point for the HADES mechanism:
  can reliability/manipulability change the rational next query?

State model
~~~~~~~~~~~
* There are K hypotheses.  At most one is the "true" hypothesis.
* There are N evidence sources (SimEvidenceSource instances).
* Each source has:
    - cost:                    query cost in budget units
    - reliability_true:        P(signal is accurate | clean observation)
    - reliability_estimated:   what the policy is allowed to see
    - manipulation_risk_true:  P(attacker can forge this source)
    - manipulation_risk_est:   what the policy is allowed to see
    - hypothesis_affinity:     Dict[hyp_id, float in [0,1]] — how relevant
                               this source is to each hypothesis

Separation of truth and policy-visible information is enforced here:
  * policy_state (what policies may read) is a separate dict that
    contains ONLY estimated values.
  * evaluator_truth is an internal attribute never passed to policies.

Usage
~~~~~
    from hades.simulator.environment import SimEnv
    from hades.simulator.scenarios import SCENARIO_B_RELIABILITY_FLIP

    env = SimEnv(SCENARIO_B_RELIABILITY_FLIP, seed=42)
    state = env.reset()

    # Run each source once and record belief state after each step
    for source in env.sources:
        obs = env.step(source.name)
        # obs contains: obs_class, belief_distribution
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Evidence source specification
# ---------------------------------------------------------------------------

@dataclass
class SimEvidenceSource:
    """
    One evidence source in the synthetic simulator.

    reliability_true and manipulation_risk_true are evaluator-only.
    reliability_estimated and manipulation_risk_estimated are what policies see.
    These four values are intentionally independent.
    """
    name: str
    cost: float                         # budget units consumed per query
    reliability_true: float             # evaluator only — never leaked to policy
    reliability_estimated: float        # policy-visible
    manipulation_risk_true: float       # evaluator only — never leaked
    manipulation_risk_estimated: float  # policy-visible
    hypothesis_affinity: Dict[str, float]  # hyp_id → relevance in [0,1]
    description: str = ""

    def __post_init__(self) -> None:
        assert self.cost > 0, f"{self.name}: cost must be > 0"
        for attr in ("reliability_true", "reliability_estimated",
                     "manipulation_risk_true", "manipulation_risk_estimated"):
            v = getattr(self, attr)
            assert 0.0 <= v <= 1.0, f"{self.name}.{attr}={v} out of [0,1]"
        if self.hypothesis_affinity:
            for hyp, v in self.hypothesis_affinity.items():
                assert 0.0 <= v <= 1.0, f"{self.name}.hypothesis_affinity[{hyp}]={v} out of [0,1]"


# ---------------------------------------------------------------------------
# Simulator scenario (configuration)
# ---------------------------------------------------------------------------

@dataclass
class SimScenario:
    """
    A named simulator configuration: hypotheses + evidence sources.
    The true hypothesis is NOT stored here — it is set at reset() time.
    """
    name: str
    description: str
    hypotheses: List[str]               # hypothesis IDs (e.g., ["H1","H2","H3"])
    sources: List[SimEvidenceSource]
    priors: Optional[Dict[str, float]] = None  # if None → uniform

    def __post_init__(self) -> None:
        assert len(self.hypotheses) >= 2, "Need ≥2 hypotheses"
        assert len(self.sources) >= 2, "Need ≥2 evidence sources"
        if self.priors is not None:
            s = sum(self.priors.values())
            assert abs(s - 1.0) < 1e-6, f"Priors must sum to 1 (got {s})"


# ---------------------------------------------------------------------------
# Observation result
# ---------------------------------------------------------------------------

@dataclass
class SimObservation:
    source_name: str
    obs_class: str                       # from OBS_CLASSES
    belief_before: Dict[str, float]      # prior to this step
    belief_after: Dict[str, float]       # posterior after belief update
    under_targeted_attack: bool
    evaluator_info: Dict                 # evaluator-only — never shown to policies


# ---------------------------------------------------------------------------
# Step result exposed to policies (no evaluator leakage)
# ---------------------------------------------------------------------------

@dataclass
class PolicyObservation:
    source_name: str
    obs_class: str
    belief_distribution: Dict[str, float]   # updated beliefs (policy-visible)
    queries_used: int
    remaining_budget: float


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class SimEnv:
    """
    Minimal synthetic investigation environment.

    Key properties
    ~~~~~~~~~~~~~~
    * sub-millisecond step (no SQLite, no file I/O)
    * belief state maintained by the sim via Bayesian update
    * strict evaluator/policy information separation
    * supports targeted attack regime (R4): attacker manipulates the source
      with highest current affinity to the leading hypothesis
    """

    def __init__(
        self,
        scenario: "SimScenario",
        seed: int = 0,
        budget: float = 10.0,
        corruption_regime: str = "R0_clean",  # R0 / R1_missing / R2_stale / R3_misleading / R4_targeted
        missing_drop_rate: float = 0.25,       # for R1
    ) -> None:
        self.scenario = scenario
        self.seed = seed
        self.initial_budget = budget
        self.corruption_regime = corruption_regime
        self.missing_drop_rate = missing_drop_rate

        self._rng = random.Random(seed)
        self._true_hypothesis: Optional[str] = None
        self._beliefs: Dict[str, float] = {}
        self._budget_remaining: float = 0.0
        self._queries_used: int = 0
        self._history: List[PolicyObservation] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def sources(self) -> List[SimEvidenceSource]:
        return self.scenario.sources

    @property
    def hypotheses(self) -> List[str]:
        return self.scenario.hypotheses

    @property
    def beliefs(self) -> Dict[str, float]:
        """Current (policy-visible) belief distribution (copy)."""
        return dict(self._beliefs)

    @property
    def remaining_budget(self) -> float:
        return self._budget_remaining

    @property
    def queries_used(self) -> int:
        return self._queries_used

    @property
    def history(self) -> List[PolicyObservation]:
        return list(self._history)

    def reset(
        self,
        true_hypothesis: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> PolicyObservation:
        """
        Reset the environment.  Returns the initial (prior) state as a
        PolicyObservation with obs_class='init'.

        true_hypothesis: if None, sampled uniformly from scenario.hypotheses.
        seed: overrides the instance seed for this episode.
        """
        if seed is not None:
            self._rng = random.Random(seed)

        if true_hypothesis is not None:
            assert true_hypothesis in self.hypotheses, \
                f"Unknown hypothesis {true_hypothesis!r}"
            self._true_hypothesis = true_hypothesis
        else:
            self._true_hypothesis = self._rng.choice(self.hypotheses)

        # Initialise beliefs from priors (uniform if not specified)
        if self.scenario.priors:
            self._beliefs = dict(self.scenario.priors)
        else:
            p = 1.0 / len(self.hypotheses)
            self._beliefs = {h: p for h in self.hypotheses}

        self._budget_remaining = self.initial_budget
        self._queries_used = 0
        self._history = []

        return PolicyObservation(
            source_name="__init__",
            obs_class="init",
            belief_distribution=self.beliefs,
            queries_used=0,
            remaining_budget=self._budget_remaining,
        )

    def step(self, source_name: str) -> PolicyObservation:
        """Query one evidence source and update belief state."""
        if self._true_hypothesis is None:
            raise RuntimeError("Call reset() before step()")

        src = self._get_source(source_name)

        if self._budget_remaining < src.cost:
            raise RuntimeError(f"Insufficient budget: {self._budget_remaining:.2f} < {src.cost}")

        # Determine if targeted attack applies to this source
        under_targeted = (
            self.corruption_regime == "R4_targeted"
            and self._is_highest_affinity_source(source_name)
        )

        # Missing corruption: with probability drop_rate, return neutral
        if (self.corruption_regime == "R1_missing"
                and self._rng.random() < self.missing_drop_rate):
            obs_class = "neutral"
        else:
            # Draw observation using BOTH reliability AND manip risk (independent)
            is_relevant = (
                src.hypothesis_affinity.get(self._true_hypothesis, 0.0) >= 0.5
            )
            from hades.simulator.observations import DEFAULT_OBS_MODEL
            obs_class = DEFAULT_OBS_MODEL.sample(
                self._rng,
                is_relevant=is_relevant,
                reliability_true=src.reliability_true,
                manipulation_risk_true=src.manipulation_risk_true,
                under_targeted_attack=under_targeted,
            )

        # Bayesian belief update
        belief_before = self.beliefs
        self._beliefs = self._update_beliefs(src, obs_class)
        self._validate_beliefs()

        self._budget_remaining -= src.cost
        self._queries_used += 1

        pol_obs = PolicyObservation(
            source_name=source_name,
            obs_class=obs_class,
            belief_distribution=self.beliefs,
            queries_used=self._queries_used,
            remaining_budget=self._budget_remaining,
        )
        self._history.append(pol_obs)
        return pol_obs

    def evaluator_truth(self) -> Dict:
        """Return evaluator-only information — NEVER pass this to policies."""
        return {
            "true_hypothesis": self._true_hypothesis,
            "corruption_regime": self.corruption_regime,
            "beliefs_are_correct": bool(
                self._true_hypothesis
                and max(self._beliefs, key=self._beliefs.get) == self._true_hypothesis
            ),
        }

    # ------------------------------------------------------------------
    # Information-theoretic helpers (used by IG-based policies)
    # ------------------------------------------------------------------

    def entropy(self) -> float:
        """Shannon entropy H(beliefs)."""
        h = 0.0
        for p in self._beliefs.values():
            if p > 1e-12:
                h -= p * math.log2(p)
        return h

    def expected_ig(self, source_name: str) -> float:
        """
        Estimate raw Expected Information Gain for querying this source.
        IG(s) ≈ H(beliefs_now) − E[H(beliefs_after | s)]

        p_informative is derived from the source's *nominal discriminating power*:
        the mean affinity across hypotheses that currently have non-trivial
        probability mass.  This is INDEPENDENT of reliability — reliability
        is applied separately in expected_reliable_ig().

        Separating IG from reliability is the key design decision that allows
        IG-only policies (P3) and reliability-aware policies (P4b, P5) to
        produce DIFFERENT query rankings (the G1 order-flip phenomenon).
        """
        src = self._get_source(source_name)
        h_before = self.entropy()

        # p_informative = how likely is this source to return a signal that
        # discriminates between hypotheses — based on affinity structure only,
        # NOT on reliability.  Reliability is a separate multiplicative factor.
        # We use the affinity-weighted average over hypotheses with belief > 0.
        leading_hyp = max(self._beliefs, key=self._beliefs.get)
        p_informative = src.hypothesis_affinity.get(leading_hyp, 0.0)
        # Clamp to reasonable range so we always get a non-trivial IG estimate
        p_informative = max(0.05, min(0.99, p_informative))

        # Informative branch: posterior concentrates on the highest-affinity hyp
        hyp_max_aff = max(self.hypotheses, key=lambda h: src.hypothesis_affinity.get(h, 0.0))
        beliefs_informative = dict(self._beliefs)
        beliefs_informative[hyp_max_aff] = min(
            1.0, beliefs_informative[hyp_max_aff] * 4.0
        )
        beliefs_informative = _normalize(beliefs_informative)
        h_informative = _entropy(beliefs_informative)

        # Neutral branch: beliefs unchanged → entropy stays same
        h_neutral = h_before

        expected_h_after = p_informative * h_informative + (1 - p_informative) * h_neutral
        return max(0.0, h_before - expected_h_after)

    def expected_reliable_ig(self, source_name: str) -> float:
        """
        Expected Reliable Hypothesis Gain (ERHG):
            ERHG(s) = IG(s) × reliability_estimated(s)

        reliability_estimated attenuates raw IG: an unreliable source is
        expected to return less useful signal per query.
        This is the key quantity that can rank sources DIFFERENTLY from
        raw IG, producing the G1 order-flip phenomenon.
        """
        src = self._get_source(source_name)
        return self.expected_ig(source_name) * src.reliability_estimated

    def hades_utility(
        self,
        source_name: str,
        lambda_: float = 1.0,
        mu: float = 1.0,
    ) -> float:
        """U(q) = ERHG(q) - lambda_*cost(q) - mu*manip_risk_est(q)."""
        src = self._get_source(source_name)
        return (
            self.expected_reliable_ig(source_name)
            - lambda_ * src.cost
            - mu * src.manipulation_risk_estimated
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_source(self, name: str) -> SimEvidenceSource:
        for s in self.sources:
            if s.name == name:
                return s
        raise KeyError(f"Unknown source {name!r}")

    def _is_highest_affinity_source(self, source_name: str) -> bool:
        """Is this the source most relevant to the current leading hypothesis?"""
        if not self._beliefs:
            return False
        leading = max(self._beliefs, key=self._beliefs.get)
        best = max(
            self.sources,
            key=lambda s: s.hypothesis_affinity.get(leading, 0.0),
        )
        return best.name == source_name

    def _update_beliefs(
        self, src: SimEvidenceSource, obs_class: str
    ) -> Dict[str, float]:
        """
        Bayesian belief update using observation weight as likelihood.
        P(H | obs) ∝ P(H) × likelihood(obs | H)

        Likelihood is derived from the affinity and the obs_class weight:
          - high-affinity hypothesis → get "positive" weight
          - low-affinity hypothesis  → get "negative" weight (inverted)
        """
        from hades.simulator.observations import OBS_CLASSES
        obs_weight = OBS_CLASSES[obs_class]

        new_beliefs: Dict[str, float] = {}
        for hyp, prior in self._beliefs.items():
            affinity = src.hypothesis_affinity.get(hyp, 0.0)
            # High-affinity hypothesis benefits from positive obs; low affinity hurts
            if affinity >= 0.5:
                likelihood = obs_weight
            else:
                # Invert — a strong support reading for another hypothesis
                # is weak or contrary evidence for this one
                likelihood = 1.0 / obs_weight if obs_weight != 0 else 1e-6
            new_beliefs[hyp] = prior * likelihood

        return _normalize(new_beliefs)

    def _validate_beliefs(self) -> None:
        """Probability invariant: beliefs must sum to 1. Fails loudly."""
        s = sum(self._beliefs.values())
        if abs(s - 1.0) > 1e-3:
            raise RuntimeError(
                f"[SimEnv] Probability invariant violated: beliefs sum to {s:.6f}. "
                f"State: {self._beliefs}"
            )
        for hyp, p in self._beliefs.items():
            if not (0.0 <= p <= 1.0 + 1e-9):
                raise RuntimeError(
                    f"[SimEnv] Belief {hyp}={p:.6f} out of [0,1]"
                )


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _normalize(d: Dict[str, float]) -> Dict[str, float]:
    s = sum(d.values())
    if s < 1e-12:
        # All weights collapsed — reset to uniform
        n = len(d)
        return {k: 1.0 / n for k in d}
    return {k: v / s for k, v in d.items()}


def _entropy(d: Dict[str, float]) -> float:
    h = 0.0
    for p in d.values():
        if p > 1e-12:
            h -= p * math.log2(p)
    return h
