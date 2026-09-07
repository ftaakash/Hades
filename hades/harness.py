"""HADES harness: implements CDB's `run(env, model) -> dict` contract
(see cyber_defense_benchmark/README.md, "Swapping your own harness"),
but drives a fixed-menu acquisition Policy instead of an LLM.

Output-compatible with `benchmark.scorer` / `benchmark.make_plots`: the
returned dict carries the same keys `run_benchmark` produces, so hunts
written by this harness score and plot identically to LLM-driven ones.

STATUS (v1): P0 (random) and P1 (fixed_heuristic) only. The candidate-
timestamp extraction is deliberately naive -- every timestamp seen in
any query result is submitted -- which is a real, honest baseline (an
analyst who reads everything but can't distinguish signal from noise)
and gives every future, smarter policy something concrete to beat. The
hypothesis-discrimination logic that would make this selective (P2
relevance onward) is not implemented yet.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, Type

from hades.policies.base import InvestigationState, Policy, QueryRecord
from hades.policies.fixed_heuristic import FixedHeuristicPolicy
from hades.policies.random_policy import RandomPolicy
from hades.query_menu import get_menu

POLICY_REGISTRY: Dict[str, Type[Policy]] = {
    "random": RandomPolicy,
    "fixed_heuristic": FixedHeuristicPolicy,
}

_TS_RE = re.compile(r'"?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)"?')


def _extract_timestamps(observation: str) -> list[str]:
    """Pull ISO-8601 timestamps out of a query's text observation.

    CDB's `TimeCreated` field is always ISO-8601 with a trailing 'Z'
    (see datasets/README.md); the observation is pretty-printed JSON
    embedded in a text block (gym.py `_format_observation`), so a
    regex over the raw text is simpler and just as correct as parsing
    the JSON back out.
    """
    return _TS_RE.findall(observation)


def run(
    env,
    *,
    model: str,
    max_queries: int = 20,
    seed: int = 0,
    rollout_id: int = 0,
    verbose: bool = False,
    **extra: Any,
) -> Dict[str, Any]:
    """`model` names a policy in POLICY_REGISTRY (e.g. "random",
    "fixed_heuristic") -- kept as `model` for drop-in compatibility
    with `benchmark.runner`, which threads that kwarg through
    unmodified regardless of which harness module is loaded.
    """
    policy_cls = POLICY_REGISTRY.get(model)
    if policy_cls is None:
        raise ValueError(f"Unknown HADES policy {model!r}; have {list(POLICY_REGISTRY)}")
    policy: Policy = policy_cls(seed=seed) if model == "random" else policy_cls()

    menu = get_menu()
    obs, info = env.reset(seed=seed)

    state = InvestigationState(remaining_budget=max_queries)
    per_turn: list[Dict[str, Any]] = []
    started = time.time()
    turns = 0

    while True:
        source_name = policy.select_query(state, menu)
        if source_name is None:
            break

        spec = menu[source_name]
        sql = spec.render(limit=env.query_row_limit)
        obs, _reward, terminated, truncated, info = env.step(sql)
        turns += 1
        state.remaining_budget -= 1

        found = _extract_timestamps(obs)
        state.candidate_timestamps.update(found)
        state.history.append(
            QueryRecord(source=source_name, sql=sql, observation=obs, n_candidates_found=len(found))
        )
        state.queried_sources.append(source_name)

        per_turn.append({
            "turn": turns,
            "source": source_name,
            "sql": sql,
            "n_candidates_seen": len(found),
            "cumulative_candidates": len(state.candidate_timestamps),
        })
        if verbose:
            print(f"[{turns}] {source_name}: +{len(found)} candidates "
                  f"(total {len(state.candidate_timestamps)})")

        if terminated or truncated:
            break

    submitted_timestamps = sorted(state.candidate_timestamps)

    return {
        "model": model,
        "outcome": "budget_exhausted",
        "turns": turns,
        "submitted_timestamps": submitted_timestamps,
        "cost_usd": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "elapsed_s": time.time() - started,
        "per_turn": per_turn,
        "error": None,
        "max_queries": max_queries,
        "queries_used": turns,
        "seed": int(getattr(env, "_seed", seed)),
    }
