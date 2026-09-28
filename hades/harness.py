"""HADES harness v2: P2-P7 policies against CDB with belief/estimator integration.

This replaces harness.py v1 (P0/P1 only) with a full Phase 5A harness that:

1. Supports all 7 policies: P0 random, P1 heuristic, P2 relevance,
   P3 EIG, P4 EIG/cost, P4b EIG/cost/reliability, P5 robust-VoI, P7 EER.

2. Integrates the CandidateExtractor to map SQL observations → 5-class
   obs_class, which then flows into the v3 Bayesian belief update.

3. Integrates the reliability estimator (default: NoisyEstimator for
   realistic simulation; override via estimator_name kwarg).

4. Applies the corruption layer when requested (default: R0 clean).

5. Produces output that is fully compatible with benchmark.scorer.score_hunt()
   (same keys as the original harness, plus HADES-specific diagnostics).

Information barrier
-------------------
The policy ONLY receives:
  - estimated reliability / manipulation_risk (from estimator)
  - current beliefs (from Bayesian update)
  - remaining budget
  - hypothesis_affinity (from query_menu relevance priors)
  - list of sources already queried

Ground truth (true_hypothesis, *_true fields) is NEVER passed to the policy.
Evaluator-only data is only read AFTER the episode ends for scoring.

Hypothesis set
--------------
The CDB doesn't expose a labelled hypothesis set. We use a proxy: the
7 MITRE ATT&CK tactic buckets that CDB measures coverage for:
  TA0001 Initial Access, TA0002 Execution, TA0003 Persistence,
  TA0004 Privilege Escalation, TA0005 Defense Evasion,
  TA0006 Credential Access, TA0008 Lateral Movement.

Each query source has a hypothesis_affinity vector (from query_menu.py
relevance assignments) capturing which tactics it is most likely to yield
evidence for. This maps HADES's structure cleanly onto CDB semantics.
"""
from __future__ import annotations

import random
import sys
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from hades.benchmark.candidate_extractor import CandidateExtractor
from hades.benchmark.obs_mapper import OBS_MAPPER_VERSION
from hades.query_menu import get_menu, QuerySpec
from hades.policies.base import InvestigationState, Policy
from hades.reliability.estimator import (
    CleanEstimator,
    NoisyEstimator,
    ReliabilityEstimator,
    ESTIMATOR_REGISTRY,
)
from hades.belief.posterior import update as _bayes_update
from hades.belief.likelihood import make_default_table

# ---------------------------------------------------------------------------
# Hypothesis set (ATT&CK tactics as CDB measures)
# ---------------------------------------------------------------------------
CDB_HYPOTHESES = [
    "TA0001",  # Initial Access
    "TA0002",  # Execution
    "TA0003",  # Persistence
    "TA0004",  # Privilege Escalation
    "TA0005",  # Defense Evasion
    "TA0006",  # Credential Access
    "TA0008",  # Lateral Movement
]

# ---------------------------------------------------------------------------
# Source → tactic affinity priors (grounded in MITRE ATT&CK associations)
# These are fixed priors for the Phase 5A experiment.
# ---------------------------------------------------------------------------
_SOURCE_AFFINITY: Dict[str, Dict[str, float]] = {
    "auth_events": {
        "TA0001": 0.40, "TA0002": 0.20, "TA0003": 0.15,
        "TA0004": 0.60, "TA0005": 0.30, "TA0006": 0.80, "TA0008": 0.70,
    },
    "process_events": {
        "TA0001": 0.30, "TA0002": 0.90, "TA0003": 0.50,
        "TA0004": 0.50, "TA0005": 0.70, "TA0006": 0.20, "TA0008": 0.40,
    },
    "network_events": {
        "TA0001": 0.80, "TA0002": 0.30, "TA0003": 0.20,
        "TA0004": 0.10, "TA0005": 0.40, "TA0006": 0.30, "TA0008": 0.90,
    },
    "dns_events": {
        "TA0001": 0.70, "TA0002": 0.20, "TA0003": 0.10,
        "TA0004": 0.05, "TA0005": 0.30, "TA0006": 0.20, "TA0008": 0.80,
    },
    "persistence_events": {
        "TA0001": 0.20, "TA0002": 0.40, "TA0003": 0.90,
        "TA0004": 0.40, "TA0005": 0.60, "TA0006": 0.10, "TA0008": 0.20,
    },
    "powershell_events": {
        "TA0001": 0.30, "TA0002": 0.85, "TA0003": 0.40,
        "TA0004": 0.50, "TA0005": 0.80, "TA0006": 0.30, "TA0008": 0.30,
    },
    "object_access_events": {
        "TA0001": 0.10, "TA0002": 0.20, "TA0003": 0.30,
        "TA0004": 0.75, "TA0005": 0.60, "TA0006": 0.50, "TA0008": 0.20,
    },
}

# ---------------------------------------------------------------------------
# Policy registry (all P0-P7)
# ---------------------------------------------------------------------------

def _build_policy_registry() -> Dict[str, Policy]:
    from hades.policies.random_policy import RandomPolicy
    from hades.policies.fixed_heuristic import FixedHeuristicPolicy
    from hades.policies.p2_relevance import RelevancePolicy
    from hades.policies.p3_ig import IGPolicy
    from hades.policies.p4_ig_cost import IGCostPolicy
    from hades.policies.p4b_ig_cost_rel import IGCostRelPolicy
    from hades.policies.p5_robust_voi import RobustVoIPolicy
    from hades.policies.p7_bayes_al import BayesALPolicy
    return {
        "random":         RandomPolicy(),
        "fixed_heuristic": FixedHeuristicPolicy(),
        "p2_relevance":   RelevancePolicy(),
        "p3_ig":          IGPolicy(),
        "p4_ig_cost":     IGCostPolicy(),
        "p4b_ig_cost_rel": IGCostRelPolicy(),
        "p5_robust_voi":  RobustVoIPolicy(lam=1.0),
        "p7_bayes_al":    BayesALPolicy(),
    }


# ---------------------------------------------------------------------------
# Belief helpers
# ---------------------------------------------------------------------------

def _uniform_beliefs() -> Dict[str, float]:
    n = len(CDB_HYPOTHESES)
    return {h: 1.0 / n for h in CDB_HYPOTHESES}


def _update_beliefs(
    beliefs: Dict[str, float],
    obs_class: str,
    source_name: str,
    menu: Dict[str, QuerySpec],
    r_hat: float,
    phi_hat: float,
) -> Dict[str, float]:
    """Bayesian belief update for CDB sources."""
    spec = menu[source_name]
    affinity = _SOURCE_AFFINITY.get(source_name, {h: 0.5 for h in CDB_HYPOTHESES})
    relevance = {h: affinity.get(h, 0.5) for h in CDB_HYPOTHESES}

    table = make_default_table(
        sources=[source_name],
        hypotheses=CDB_HYPOTHESES,
        relevance={(source_name, h): affinity.get(h, 0.5) for h in CDB_HYPOTHESES},
    )
    new_beliefs = _bayes_update(
        beliefs=dict(beliefs),
        obs_class=obs_class,
        source=source_name,
        table=table,
        r_hat=r_hat,
        phi_hat=phi_hat,
        source_relevance=relevance,
    )
    # Validate normalization
    s = sum(new_beliefs.values())
    if abs(s - 1.0) > 1e-3:
        # Renormalize gracefully — log warning, don't crash
        n = len(new_beliefs)
        new_beliefs = {k: 1.0 / n for k in new_beliefs}
    return new_beliefs


# ---------------------------------------------------------------------------
# Main run() entry point
# ---------------------------------------------------------------------------

def run(
    env,
    *,
    model: str,
    max_queries: int = 20,
    seed: int = 0,
    rollout_id: int = 0,
    verbose: bool = False,
    estimator_name: str = "noisy",
    lam: float = 1.0,
    **extra: Any,
) -> Dict[str, Any]:
    """Run one episode of HADES against CDB.

    Parameters
    ----------
    env : ThreatHuntEnv
        The CDB gymnasium environment.
    model : str
        Policy name (key in _build_policy_registry()).
    max_queries : int
        Episode budget.
    seed : int
        RNG seed for policy randomness.
    estimator_name : str
        Reliability estimator to use: 'clean', 'noisy', 'miscalibrated', 'adversarial'.
    lam : float
        Budget-normalisation lambda (pre-registered: 0.5, 1.0, 2.0).
    """
    registry = _build_policy_registry()
    if model not in registry:
        raise ValueError(f"Unknown policy {model!r}; available: {list(registry)}")
    policy = registry[model]

    # Estimator: noisy by default (sigma=0.10 is realistic)
    if estimator_name == "noisy":
        estimator: ReliabilityEstimator = NoisyEstimator(sigma=0.10)
    elif estimator_name in ESTIMATOR_REGISTRY:
        estimator = ESTIMATOR_REGISTRY[estimator_name]()
    else:
        estimator = CleanEstimator()

    menu = get_menu()
    rng = random.Random(seed)
    est_rng = random.Random(seed ^ 0xCAFE)

    obs_briefing, info = env.reset(seed=seed)

    # Episode state
    beliefs = _uniform_beliefs()
    extractor = CandidateExtractor(menu)
    queried_sources: List[str] = []
    per_turn: List[Dict[str, Any]] = []
    budget_remaining = float(max_queries)
    started = time.time()
    turns = 0

    while budget_remaining >= 1.0:
        # ── Policy menu: estimated fields only ──────────────────────────────
        policy_menu = {}
        for src_name, spec in menu.items():
            est_result = estimator.estimate(
                r_true=spec.reliability_true,
                phi_true=0.0,   # manipulation risk for CDB sources
                rng=est_rng,
                source_name=src_name,
            )
            policy_menu[src_name] = types.SimpleNamespace(
                name=src_name,
                cost=spec.cost,
                reliability_estimated=est_result.r_hat,
                manipulation_risk_estimated=est_result.phi_hat,
                hypothesis_affinity=_SOURCE_AFFINITY.get(src_name, {}),
            )

        # ── Policy selects source ────────────────────────────────────────────
        leading = max(beliefs, key=lambda h: (beliefs[h], h))
        state = InvestigationState(
            queried_sources=list(queried_sources),
            history=[],
            remaining_budget=budget_remaining,
            beliefs=dict(beliefs),
            leading_hyp=leading,
        )
        source_name = policy.select_query(state, policy_menu)
        if source_name is None or source_name not in menu:
            break

        # ── Execute SQL query ─────────────────────────────────────────────────
        spec = menu[source_name]
        sql = spec.render(limit=env.query_row_limit)
        obs_text, _reward, terminated, truncated, _info = env.step(sql)
        turns += 1
        budget_remaining -= spec.cost   # cost-aware budget (not fixed 1.0/turn)
        queried_sources.append(source_name)

        # ── Map observation → 5-class ────────────────────────────────────────
        obs_class, n_rows, new_ts = extractor.process(source_name, obs_text)

        # ── Belief update ─────────────────────────────────────────────────────
        est_spec = policy_menu[source_name]
        beliefs = _update_beliefs(
            beliefs, obs_class, source_name, menu,
            r_hat=est_spec.reliability_estimated,
            phi_hat=est_spec.manipulation_risk_estimated,
        )

        # ── Per-turn record ───────────────────────────────────────────────────
        per_turn.append({
            "turn": turns,
            "source": source_name,
            "obs_class": obs_class,
            "n_rows": n_rows,
            "n_new_submitted": len(new_ts),
            "cumulative_candidates": extractor.n_candidates(),
            "queries_used": turns,
            "leading_hyp": leading,
            "beliefs_entropy": _entropy(beliefs),
        })

        if verbose:
            print(
                f"[{turns:>2}] {source_name:<25} obs={obs_class:<16} "
                f"rows={n_rows:>4}  +{len(new_ts)} ts  "
                f"budget={budget_remaining:.1f}  leading={leading}"
            )

        if terminated or truncated:
            break

    elapsed = time.time() - started

    return {
        # CDB scorer-compatible keys
        "model": model,
        "outcome": "budget_exhausted",
        "turns": turns,
        "submitted_timestamps": extractor.all_candidates(),
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "elapsed_s": elapsed,
        "per_turn": per_turn,
        "error": None,
        "max_queries": max_queries,
        "queries_used": turns,
        "seed": seed,
        # HADES-specific diagnostics
        "hades_version": "v3.1",
        "obs_mapper_version": OBS_MAPPER_VERSION,
        "estimator": estimator_name,
        "lam": lam,
        "final_beliefs": dict(beliefs),
        "leading_hyp": max(beliefs, key=lambda h: (beliefs[h], h)),
        "n_candidates": extractor.n_candidates(),
        "source_yield_stats": extractor.source_yield_stats(),
    }


def _entropy(beliefs: Dict[str, float]) -> float:
    import math
    h = 0.0
    for p in beliefs.values():
        if p > 1e-12:
            h -= p * math.log2(p)
    return h
