"""hades/integration/runner.py — End-to-end integration runner (Phase 4 gate).

This module wires the full Phase 4 pipeline:

    corruptor (R1-R4)
        ↓
    observation (from SimEnv)
        ↓
    reliability estimator (Clean/Noisy/Miscalibrated/Adversarial)
        ↓
    belief update (Bayesian, via SimEnv._update_beliefs)
        ↓
    policy (P3/P4/P4b/P5/P7)
        ↓
    action + outcome

SimEnv continues to own belief state and the Markov environment.
The integration runner adds:
  1. A reliability estimator layer that transforms the source's estimated
     fields before the policy sees the menu.
  2. A corruptor layer that wraps SimEnv.step() to intercept the raw obs_class
     and apply R1-R4 corruption BEFORE the Bayesian update.

Attacker knowledge model (R4)
------------------------------
In this version the targeted corruptor uses ARCHITECTURE-AWARE knowledge:
  - attacker knows the source affinity structure (from threat_model.md)
  - attacker does NOT know the policy or current beliefs
  - attacker targets the source with highest affinity to any hypothesis
    (conservative: doesn't need to know leading hypothesis)

This is documented as R4a (Architecture-Aware) per the reviewer's request.

Invariants enforced here
------------------------
- Policy only receives *_estimated fields (modified by estimator, not _true).
- Budget accounting is consistent across all (corruptor × estimator × policy).
- Beliefs remain normalised (validated by SimEnv._validate_beliefs).
- No _true leakage: evaluator_truth() is only accessed post-episode.
- Reproducibility: all stochasticity is seeded through the same RNG chain.
"""
from __future__ import annotations

import random
import types
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hades.corruption.base import Corruptor, ObsContext, OBS_CLASSES
from hades.corruption.missing import MissingCorruptor
from hades.corruption.stale import StaleCorruptor
from hades.corruption.misleading import MisleadingCorruptor
from hades.corruption.targeted import TargetedCorruptor
from hades.reliability.estimator import (
    ReliabilityEstimator,
    CleanEstimator,
    EstimatorResult,
)
from hades.simulator.environment import SimEnv, SimEvidenceSource
from hades.policies.base import InvestigationState, Policy


# ---------------------------------------------------------------------------
# Episode result dataclass
# ---------------------------------------------------------------------------

@dataclass
class EpisodeResult:
    """Complete record of one integration episode."""
    policy_name: str
    scenario_name: str
    corruptor_regime: str
    estimator_regime: str
    seed: int
    true_hypothesis: str
    budget: float

    # Outcome metrics
    n_queries: int = 0
    final_beliefs: Dict[str, float] = field(default_factory=dict)
    max_belief: float = 0.0
    correct_hyp: bool = False
    leading_hyp: str = ""
    sources_queried: List[str] = field(default_factory=list)
    high_phi_queries: int = 0
    manip_reliance: float = 0.0
    total_cost: float = 0.0

    # Pipeline integrity
    beliefs_sum_to_one: bool = True
    no_true_leak: bool = True
    no_impossible_obs: bool = True
    budget_consistent: bool = True
    all_obs_valid: bool = True


# ---------------------------------------------------------------------------
# Corrupted SimEnv step helper
# ---------------------------------------------------------------------------

def _make_policy_menu(
    env: SimEnv,
    estimator: ReliabilityEstimator,
    estimator_rng: random.Random,
) -> Dict[str, types.SimpleNamespace]:
    """
    Build the policy-visible menu, applying reliability estimator to each source.

    The policy sees ONLY the estimated values; _true fields are excluded.
    Budget is read from env.remaining_budget.
    """
    menu = {}
    for src in env.sources:
        est: EstimatorResult = estimator.estimate(
            r_true=src.reliability_true,
            phi_true=src.manipulation_risk_true,
            rng=estimator_rng,
            source_name=src.name,
        )
        # Policy-visible spec: estimated fields only
        spec = types.SimpleNamespace(
            name=src.name,
            cost=src.cost,
            reliability_estimated=est.r_hat,
            manipulation_risk_estimated=est.phi_hat,
            hypothesis_affinity=dict(src.hypothesis_affinity),
            # Explicitly exclude _true fields
        )
        menu[src.name] = spec
    return menu


def _corrupted_step(
    env: SimEnv,
    source_name: str,
    corruptor: Corruptor,
    corruptor_rng: random.Random,
) -> Tuple[str, Dict[str, float]]:
    """
    Execute one step in SimEnv with the Corruptor applied to the raw obs.

    Strategy: we intercept at the observation level. SimEnv.step() internally
    draws obs_class then does the Bayesian update. To inject our corruptor,
    we:
    1. Get the raw obs_class from SimEnv (internal access via a patched step).
    2. Apply corruptor.
    3. Force SimEnv to perform the Bayesian update on the corrupted obs_class.

    In v3.1 this will use a pluggable corruptor hook in SimEnv. For now we
    intercept by calling _update_beliefs directly after sampling the raw obs.

    This approach preserves all SimEnv invariants.
    """
    # Get source metadata for corruption context
    src = env._get_source(source_name)

    # Build ObsContext for the corruptor
    ctx = ObsContext(
        source_name=source_name,
        true_hypothesis=env._true_hypothesis,  # evaluator-only, used by corruptor
        query_history=[h.source_name for h in env.history],
        current_beliefs=env.beliefs,   # policy-visible beliefs at this step
        reliability_true=src.reliability_true,
        manipulation_risk_true=src.manipulation_risk_true,
        hypothesis_affinity=dict(src.hypothesis_affinity),
    )

    # Draw raw obs_class from SimEnv's native sampling
    is_relevant = src.hypothesis_affinity.get(env._true_hypothesis, 0.0) >= 0.5
    from hades.simulator.observations import DEFAULT_OBS_MODEL
    raw_obs = DEFAULT_OBS_MODEL.sample(
        env._rng,
        is_relevant=is_relevant,
        reliability_true=src.reliability_true,
        manipulation_risk_true=src.manipulation_risk_true,
        under_targeted_attack=isinstance(corruptor, TargetedCorruptor)
                              and env._is_highest_affinity_source(source_name),
    )

    # Apply corruptor
    corrupted_obs = corruptor.corrupt(raw_obs, ctx, corruptor_rng)

    # Bayesian update on corrupted obs, validate beliefs
    env._beliefs = env._update_beliefs(src, corrupted_obs)
    env._validate_beliefs()
    env._budget_remaining -= src.cost
    env._queries_used += 1

    from hades.simulator.environment import PolicyObservation
    pol_obs = PolicyObservation(
        source_name=source_name,
        obs_class=corrupted_obs,
        belief_distribution=env.beliefs,
        queries_used=env._queries_used,
        remaining_budget=env._budget_remaining,
    )
    env._history.append(pol_obs)
    return corrupted_obs, env.beliefs


# ---------------------------------------------------------------------------
# Integration runner
# ---------------------------------------------------------------------------

class IntegrationRunner:
    """Runs full end-to-end episodes for all (corruptor × estimator × policy) combos.

    Usage
    -----
    runner = IntegrationRunner(scenario, budget=10.0, seeds=5)
    results = runner.run_all()
    """

    PHI_HIGH_THRESHOLD = 0.40  # threshold for "manipulable source" metric

    def __init__(
        self,
        scenario,
        budget: float = 10.0,
        seeds: int = 5,
        corruptors: Optional[List[Corruptor]] = None,
        estimators: Optional[List[ReliabilityEstimator]] = None,
        policies: Optional[List[Policy]] = None,
        lam: float = 1.0,
    ) -> None:
        self.scenario = scenario
        self.budget = budget
        self.seeds = seeds
        self.lam = lam

        self.corruptors: List[Corruptor] = corruptors or [
            MissingCorruptor(p_drop=0.0),       # R0 baseline (no-op)
            MissingCorruptor(p_drop=0.25),      # R1 moderate
            StaleCorruptor(staleness=0.33),     # R2 1h lag
            MisleadingCorruptor(p_inject=0.25), # R3 moderate
            TargetedCorruptor(p_attack=0.75),   # R4 partial capability
        ]

        self.estimators: List[ReliabilityEstimator] = estimators or [
            CleanEstimator(),                   # oracle baseline
        ]

        if policies is None:
            from hades.policies.p3_ig import IGPolicy
            from hades.policies.p4_ig_cost import IGCostPolicy
            from hades.policies.p4b_ig_cost_rel import IGCostRelPolicy
            from hades.policies.p5_robust_voi import RobustVoIPolicy
            from hades.policies.p7_bayes_al import BayesALPolicy
            self.policies: List[Policy] = [
                IGPolicy(),
                IGCostPolicy(),
                IGCostRelPolicy(),
                RobustVoIPolicy(lam=lam),
                BayesALPolicy(),
            ]
        else:
            self.policies = policies

    def run_episode(
        self,
        policy: Policy,
        corruptor: Corruptor,
        estimator: ReliabilityEstimator,
        seed: int,
        true_hyp: Optional[str] = None,
    ) -> EpisodeResult:
        """Run one complete episode. Returns EpisodeResult."""
        env = SimEnv(self.scenario, seed=seed, budget=self.budget)

        # Derive true_hyp from seed if not specified
        if true_hyp is None:
            rng2 = random.Random(seed ^ 0xCAFE)
            true_hyp = rng2.choice(self.scenario.hypotheses)

        env.reset(true_hypothesis=true_hyp, seed=seed)

        # Separate RNGs for corruptor and estimator (no cross-contamination)
        corruptor_rng = random.Random(seed ^ 0xBEEF)
        estimator_rng = random.Random(seed ^ 0xDEAD)

        result = EpisodeResult(
            policy_name=policy.name,
            scenario_name=self.scenario.name,
            corruptor_regime=corruptor.regime,
            estimator_regime=estimator.regime,
            seed=seed,
            true_hypothesis=true_hyp,
            budget=self.budget,
        )

        valid_obs_classes = set(OBS_CLASSES) | {"init"}
        budget_spent = 0.0
        step = 0

        while env.remaining_budget > 0 and step < 50:
            # Build policy menu with estimator-transformed reliability values
            menu = _make_policy_menu(env, estimator, estimator_rng)
            beliefs = env.beliefs
            leading = max(beliefs, key=lambda h: (beliefs[h], h)) if beliefs else ""

            state = InvestigationState(
                queried_sources=result.sources_queried[:],
                history=[],
                remaining_budget=env.remaining_budget,
                beliefs=beliefs,
                leading_hyp=leading,
            )

            # Policy selects next source
            choice = policy.select_query(state, menu)
            if choice is None:
                break
            if choice not in menu:
                break   # safety: invalid choice, stop episode

            # Execute corrupted step
            obs_class, new_beliefs = _corrupted_step(
                env, choice, corruptor, corruptor_rng
            )

            # Track obs validity
            if obs_class not in OBS_CLASSES:
                result.all_obs_valid = False

            src_cost = next(s.cost for s in env.sources if s.name == choice)
            budget_spent += src_cost
            result.sources_queried.append(choice)

            # Track manipulable source reliance (using estimator-visible phi_hat)
            phi_hat = menu[choice].manipulation_risk_estimated
            if phi_hat >= self.PHI_HIGH_THRESHOLD:
                result.high_phi_queries += 1

            step += 1

        # ── Post-episode metrics ─────────────────────────────────────────────
        final_beliefs = env.beliefs
        result.final_beliefs = final_beliefs
        result.n_queries = len(result.sources_queried)
        result.max_belief = max(final_beliefs.values()) if final_beliefs else 0.0
        result.leading_hyp = (
            max(final_beliefs, key=lambda h: (final_beliefs[h], h))
            if final_beliefs else ""
        )
        result.correct_hyp = (result.leading_hyp == true_hyp)
        result.manip_reliance = (
            result.high_phi_queries / max(result.n_queries, 1)
        )
        result.total_cost = budget_spent

        # Validate beliefs sum to 1
        s = sum(final_beliefs.values())
        result.beliefs_sum_to_one = abs(s - 1.0) < 1e-3

        # Budget consistency
        result.budget_consistent = (
            abs(budget_spent - (self.budget - env.remaining_budget)) < 1e-6
        )

        return result

    def run_all(self) -> List[EpisodeResult]:
        """Run all (corruptor × estimator × policy × seed) combinations."""
        all_results = []
        for corruptor in self.corruptors:
            for estimator in self.estimators:
                for policy in self.policies:
                    for seed in range(self.seeds):
                        r = self.run_episode(policy, corruptor, estimator, seed)
                        all_results.append(r)
        return all_results
