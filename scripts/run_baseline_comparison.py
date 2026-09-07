"""Run P0 (random) and P1 (fixed_heuristic) against CDB's real public
sample and score them with CDB's own `benchmark.scorer`.

This is the "reproduce a CDB baseline with our own harness" gate (G1
in the design notes) -- it proves the harness/query-menu/scorer
pipeline actually works end to end against real data, before any of
the smarter policies (P2-P5) get built.

Usage (from hades-bench/, with cyber_defense_benchmark cloned as a
sibling directory and its sample dataset unpacked):

    PYTHONPATH=.:../cdb python scripts/run_baseline_comparison.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

CDB_ROOT = Path(__file__).resolve().parents[2] / "cdb"
sys.path.insert(0, str(CDB_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark.gym import ThreatHuntEnv  # noqa: E402
from benchmark.scorer import score_hunt  # noqa: E402
from hades.harness import run  # noqa: E402

DATA_PATH = CDB_ROOT / "datasets" / "sample.json"
FLAGS_PATH = CDB_ROOT / "datasets" / "sample_flags.json"


def main() -> None:
    with FLAGS_PATH.open() as f:
        sample_flags = json.load(f)

    # NOTE: ThreatHuntEnv.reset() inserts all 155,350 sample rows one at a
    # time (benchmark/db.py LogDatabase.insert uses a Python loop of
    # individual conn.execute() calls, not executemany) -- ~28s per
    # reset(). That's fine for a handful of runs but will need batching
    # before this scales to many policies x many budgets x the full
    # (much larger) gated dataset. Scoped down here to fit a reasonable
    # wall-clock budget for a first end-to-end smoke test.
    budgets = (20,)
    n_random_rollouts = 3

    print(f"{'policy':<16} {'budget':>6} {'queries_used':>13} "
          f"{'n_submitted':>12} {'coverage':>9}")
    print("-" * 62)

    results: dict[str, dict[int, list[float]]] = {"random": {}, "fixed_heuristic": {}}

    for budget in budgets:
        # --- fixed_heuristic: deterministic, one run is enough ---
        env = ThreatHuntEnv(DATA_PATH, max_queries=budget)
        hunt = run(env, model="fixed_heuristic", max_queries=budget, seed=0)
        env.close()
        score = score_hunt(hunt, sample_flags)
        coverage = score["coverage_score_per_run"]
        results["fixed_heuristic"][budget] = [coverage]
        print(f"{'fixed_heuristic':<16} {budget:>6} {hunt['queries_used']:>13} "
              f"{len(hunt['submitted_timestamps']):>12} {coverage:>9.4f}")

        # --- random: stochastic, run several seeds ---
        covs = []
        for s in range(n_random_rollouts):
            env = ThreatHuntEnv(DATA_PATH, max_queries=budget)
            hunt = run(env, model="random", max_queries=budget, seed=s)
            env.close()
            score = score_hunt(hunt, sample_flags)
            covs.append(score["coverage_score_per_run"])
        results["random"][budget] = covs
        mean_cov = statistics.mean(covs)
        print(f"{'random':<16} {budget:>6} {'(x' + str(n_random_rollouts) + ' seeds)':>13} "
              f"{'-':>12} {mean_cov:>9.4f}  (stdev {statistics.pstdev(covs):.4f})")

    out_path = Path(__file__).resolve().parents[1] / "baseline_results.json"
    with out_path.open("w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote raw results to {out_path}")


if __name__ == "__main__":
    main()
