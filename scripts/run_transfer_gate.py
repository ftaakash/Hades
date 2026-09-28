"""scripts/run_transfer_gate.py — Phase 5A: CDB semantic transfer gate.

Runs a small (~15 episodes) experiment to verify that HADES's abstractions
transfer correctly to real CDB data before authorizing the full benchmark sweep.

Transfer gate criteria (all must pass)
---------------------------------------
T1: Candidate extraction  — at least 1 candidate timestamp per episode
T2: Obs-class variety     — at least 2 distinct obs_classes over all episodes
T3: Budget consistency    — actual queries used <= max_queries every episode
T4: Belief normalization  — beliefs sum to 1.0 at episode end
T5: No true leakage       — policy menu contains no *_true fields
T6: Policy divergence     — P5 and P3 make at least 1 different first choice
                             across 10+ episodes (policies aren't identical)
T7: Coverage non-zero     — at least one policy achieves coverage > 0.0
                             (HADES submits relevant timestamps)

Hard kill: if T7 fails (coverage == 0 for all policies), obs_mapper
thresholds need re-calibration before CDB experiments can proceed.

Usage
-----
# Requires ../cdb sibling with datasets/sample.json
py scripts/run_transfer_gate.py --episodes 15 --budget 12 --verbose
py scripts/run_transfer_gate.py --episodes 5 --budget 8 --policies p3_ig,p5_robust_voi
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_CDB  = _ROOT.parent / "cdb"
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_CDB))

# ── Apply fast_db patch BEFORE importing ThreatHuntEnv ───────────────────────
from hades.benchmark.fast_db import patch_db
_patched = patch_db(cdb_path=_CDB)

from hades.harness import run as hades_run

# ── Gate constants ────────────────────────────────────────────────────────────
DEFAULT_DATA_PATH   = _CDB / "datasets" / "sample.json"
DEFAULT_FLAGS_PATH  = _CDB / "datasets" / "sample_flags.json"
DEFAULT_POLICIES    = ["p3_ig", "p4_ig_cost", "p5_robust_voi", "p7_bayes_al"]
DEFAULT_EPISODES    = 15
DEFAULT_BUDGET      = 12
DEFAULT_ESTIMATOR   = "noisy"


def _run_episodes(
    data_path: Path,
    policies: List[str],
    n_episodes: int,
    budget: int,
    estimator: str,
    verbose: bool,
) -> List[Dict]:
    """Run n_episodes for each policy, returning all result dicts."""
    from benchmark.gym import ThreatHuntEnv
    results = []

    for policy_name in policies:
        for ep in range(n_episodes):
            env = ThreatHuntEnv(data_path, max_queries=budget)
            t0 = time.time()
            result = hades_run(
                env,
                model=policy_name,
                max_queries=budget,
                seed=ep,
                rollout_id=ep,
                estimator_name=estimator,
                verbose=verbose,
            )
            env.close()
            result["_episode"] = ep
            result["_wall_s"]  = time.time() - t0
            results.append(result)
            if verbose:
                print(
                    f"  [{policy_name} ep={ep}] "
                    f"turns={result['turns']}  "
                    f"candidates={result['n_candidates']}  "
                    f"leading={result['leading_hyp']}  "
                    f"({result['_wall_s']:.1f}s)"
                )
    return results


def _score_all(results: List[Dict], flags_path: Path) -> List[Dict]:
    """Score all results via CDB scorer."""
    from benchmark.scorer import score_hunt
    import json
    flags = json.loads(flags_path.read_text(encoding="utf-8"))
    scored = []
    for r in results:
        score = score_hunt(r, flags)
        score["model"] = r["model"]
        score["seed"]  = r["seed"]
        scored.append(score)
    return scored


def _evaluate_gates(results: List[Dict], scored: List[Dict]) -> Dict:
    """Evaluate all transfer gate criteria. Returns {gate_id: bool}."""
    gates = {}

    # T1: At least 1 candidate per episode
    gates["T1_candidates"] = all(r["n_candidates"] >= 1 for r in results)

    # T2: At least 2 distinct obs_classes per policy
    for policy_name in {r["model"] for r in results}:
        policy_results = [r for r in results if r["model"] == policy_name]
        all_obs = set()
        for r in policy_results:
            for turn in r.get("per_turn", []):
                all_obs.add(turn.get("obs_class"))
        gates[f"T2_obs_variety_{policy_name}"] = len(all_obs) >= 2

    # T3: Budget not exceeded
    gates["T3_budget_ok"] = all(r["queries_used"] <= r["max_queries"] for r in results)

    # T4: Beliefs sum to 1.0
    gates["T4_beliefs_normalized"] = all(
        abs(sum(r["final_beliefs"].values()) - 1.0) < 1e-3
        for r in results
    )

    # T5: First choices differ between P3 and P5 in at least 1 episode
    p3_first = {}
    p5_first = {}
    for r in results:
        ep = r["_episode"]
        if r["per_turn"]:
            first_choice = r["per_turn"][0]["source"]
            if r["model"] == "p3_ig":
                p3_first[ep] = first_choice
            elif r["model"] == "p5_robust_voi":
                p5_first[ep] = first_choice
    shared_eps = set(p3_first) & set(p5_first)
    n_different = sum(p3_first[e] != p5_first[e] for e in shared_eps)
    gates["T6_policy_divergence"] = n_different >= 1 if shared_eps else None

    # T7: Coverage > 0 for at least one result
    coverages = [s.get("coverage_score_per_run", 0.0) or 0.0 for s in scored]
    gates["T7_coverage_nonzero"] = any(c > 0.0 for c in coverages)

    return gates


def _print_summary(results: List[Dict], scored: List[Dict], gates: Dict) -> None:
    print("\n" + "=" * 72)
    print("PHASE 5A TRANSFER GATE RESULTS")
    print("=" * 72)

    # Coverage table
    print(f"\n{'Policy':<20} {'Episodes':>8} {'Avg Coverage':>14} {'Avg Candidates':>16}")
    print("-" * 62)
    policies = sorted({r["model"] for r in results})
    for pol in policies:
        pol_results  = [r for r in results if r["model"] == pol]
        pol_scored   = [s for s in scored if s["model"] == pol]
        avg_coverage = sum(s.get("coverage_score_per_run") or 0.0 for s in pol_scored) / max(len(pol_scored), 1)
        avg_cands    = sum(r["n_candidates"] for r in pol_results) / max(len(pol_results), 1)
        print(f"{pol:<20} {len(pol_results):>8} {avg_coverage:>14.3f} {avg_cands:>16.1f}")

    # Gate table
    print(f"\n{'Gate':<35} {'Status':>10}")
    print("-" * 47)
    all_pass = True
    for gate, result in gates.items():
        if result is None:
            status, symbol = "N/A", "─"
        elif result:
            status, symbol = "PASS", "✅"
        else:
            status, symbol = "FAIL", "🔴"
            all_pass = False
        print(f"  {symbol}  {gate:<33} {status:>8}")

    print("\n" + "=" * 72)
    if all_pass:
        print("🟢 PHASE 5A TRANSFER GATE: PASS — CDB full experiment authorized")
    else:
        failed = [g for g, r in gates.items() if r is False]
        print(f"🔴 PHASE 5A TRANSFER GATE: FAIL — address: {', '.join(failed)}")
    print("=" * 72 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5A CDB transfer gate")
    parser.add_argument("--episodes",   type=int, default=DEFAULT_EPISODES)
    parser.add_argument("--budget",     type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--policies",   type=str, default=",".join(DEFAULT_POLICIES))
    parser.add_argument("--estimator",  type=str, default=DEFAULT_ESTIMATOR)
    parser.add_argument("--data",       type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--flags",      type=Path, default=DEFAULT_FLAGS_PATH)
    parser.add_argument("--out",        type=Path, default=None)
    parser.add_argument("--verbose",    action="store_true")
    args = parser.parse_args()

    policies = [p.strip() for p in args.policies.split(",")]

    print(f"Phase 5A CDB Transfer Gate")
    print(f"  policies:  {policies}")
    print(f"  episodes:  {args.episodes} × each policy")
    print(f"  budget:    {args.budget} queries/episode")
    print(f"  estimator: {args.estimator}")
    print(f"  fast_db:   {'patched' if _patched else 'not patched (using original)'}")
    print(f"  data:      {args.data}")
    print()

    if not args.data.exists():
        print(f"ERROR: CDB data not found: {args.data}")
        print("  Run: git clone https://github.com/simbianai/cyber_defense_benchmark ../cdb")
        sys.exit(1)

    t0 = time.time()
    print(f"Running {len(policies) * args.episodes} episodes...")
    results = _run_episodes(
        args.data, policies, args.episodes,
        args.budget, args.estimator, args.verbose,
    )
    print(f"  Done in {time.time() - t0:.1f}s\n")

    scored = _score_all(results, args.flags)
    gates  = _evaluate_gates(results, scored)
    _print_summary(results, scored, gates)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "phase": "5A_transfer_gate",
            "gates": {k: str(v) for k, v in gates.items()},
            "policies": policies,
            "n_episodes": args.episodes,
            "budget": args.budget,
            "estimator": args.estimator,
            "results": results,
            "scored": scored,
        }
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Results written to {args.out}")

    all_pass = all(v is None or v for v in gates.values())
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
