"""scripts/run_transfer_gate.py — Phase 5A: CDB semantic transfer gate.

Runs a small (~15 episodes) experiment to verify that HADES abstractions
transfer correctly to real CDB data before authorizing the full sweep.

Transfer gate criteria
----------------------
T1: Candidate extraction  — >=1 candidate timestamp per episode
T2: Obs-class variety     — >=2 distinct obs_classes over all episodes per policy
T3: Budget consistency    — queries_used <= max_queries every episode
T4: Belief normalization  — beliefs sum to 1.0 at episode end
T5: No true leakage       — policy menu contains no *_true fields
T6: Policy divergence     — P5 and P3 make at least 1 different first choice
                            across all shared episodes
T7: Baseline coverage     — P3 (EIG, the established baseline) achieves
                            coverage > 0 in >= 3 of N episodes.
                            Rationale: coverage > 0 once could be a single lucky
                            timestamp match. Repeated coverage establishes that
                            HADES's candidate extraction is semantically valid.
T8: No lucky episode      — No single episode accounts for >50% of the total
                            detected flag count across all P3 episodes.
                            Rationale: prevents a single fluke from masking a
                            degenerate mapper.

Hard kill: if T7 fails, the obs_mapper row-yield thresholds need recalibration
before Phase 5B. Do not proceed to full sweep.

Frozen configuration (Phase 5A)
--------------------------------
Budget:        12 queries (sub-budget; CDB nominal = 50; Phase 5B will sweep)
Policies:      P3, P4, P5, P7 (primary comparison; P0/P1/P2/P4b are ablations)
Estimator:     noisy (sigma=0.10; realistic estimation error)
Lambda:        1.0 (pre-registered)
CDB snapshot:  git commit hash + sample.json sha256 recorded in output JSON

Usage
-----
# Standard run (15 episodes)
py scripts/run_transfer_gate.py --episodes 15 --budget 12 --verbose

# Quick smoke (5 episodes)
py scripts/run_transfer_gate.py --episodes 5 --budget 8

# Ablation: uniform affinity prior (required for Phase 5B)
py scripts/run_transfer_gate.py --episodes 15 --budget 12 --uniform-affinity

# Save raw artifact
py scripts/run_transfer_gate.py --episodes 15 --budget 12 --out results/raw/5a_transfer_gate_v1.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_CDB  = _ROOT.parent / "cdb"
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_CDB))

# ── Apply fast_db patch BEFORE importing ThreatHuntEnv ───────────────────────
from hades.benchmark.fast_db import patch_db
_patched = patch_db(cdb_path=_CDB)

from hades.harness import run as hades_run

# ── Gate constants (frozen) ───────────────────────────────────────────────────
DEFAULT_DATA_PATH  = _CDB / "datasets" / "sample.json"
DEFAULT_FLAGS_PATH = _CDB / "datasets" / "sample_flags.json"
DEFAULT_POLICIES   = ["p3_ig", "p4_ig_cost", "p5_robust_voi", "p7_bayes_al"]
DEFAULT_EPISODES   = 15
DEFAULT_BUDGET     = 12
DEFAULT_ESTIMATOR  = "noisy"
T7_MIN_EPISODES    = 3     # P3 must achieve coverage>0 in >=this many episodes
T8_MAX_SINGLE_FRAC = 0.50  # no single episode may account for >50% of total flags


# ── CDB snapshot provenance ───────────────────────────────────────────────────

def _cdb_git_hash(cdb_path: Path) -> str:
    """Record the CDB repo commit (not HADES). Uses git -C <cdb_path>."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cdb_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _hades_git_hash(hades_path: Path) -> str:
    """Record the HADES repo commit (separate from CDB)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(hades_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _sha256_file(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "unknown"


# ── Episode runner ─────────────────────────────────────────────────────────────

def _run_episodes(
    data_path: Path,
    policies: List[str],
    n_episodes: int,
    budget: int,
    estimator: str,
    uniform_affinity: bool,
    verbose: bool,
) -> List[Dict]:
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
                uniform_affinity=uniform_affinity,
            )
            env.close()
            result["_episode"] = ep
            result["_wall_s"]  = time.time() - t0
            results.append(result)
            if verbose:
                print(
                    f"  [{policy_name} ep={ep:02d}] "
                    f"turns={result['turns']:<3}  "
                    f"candidates={result['n_candidates']:<4}  "
                    f"leading={result['leading_hyp']}  "
                    f"({result['_wall_s']:.1f}s)"
                )
    return results


# ── Scorer ────────────────────────────────────────────────────────────────────

def _score_all(results: List[Dict], flags_path: Path) -> List[Dict]:
    from benchmark.scorer import score_hunt
    flags = json.loads(flags_path.read_text(encoding="utf-8"))
    scored = []
    for r in results:
        score = score_hunt(r, flags)
        score["model"]   = r["model"]
        score["seed"]    = r["seed"]
        score["_episode"] = r["_episode"]
        scored.append(score)
    return scored


# ── Gate evaluation ───────────────────────────────────────────────────────────

def _evaluate_gates(results: List[Dict], scored: List[Dict]) -> Dict[str, Any]:
    gates: Dict[str, Any] = {}

    # T1: >=1 candidate per episode
    gates["T1_candidates"] = all(r["n_candidates"] >= 1 for r in results)

    # T2: >=2 distinct obs_classes per policy
    for pol in {r["model"] for r in results}:
        obs_classes = set()
        for r in results:
            if r["model"] == pol:
                for turn in r.get("per_turn", []):
                    obs_classes.add(turn.get("obs_class"))
        gates[f"T2_obs_variety_{pol}"] = len(obs_classes) >= 2

    # T3: budget not exceeded
    gates["T3_budget_ok"] = all(r["queries_used"] <= r["max_queries"] for r in results)

    # T4: beliefs sum to 1.0
    gates["T4_beliefs_normalized"] = all(
        abs(sum(r["final_beliefs"].values()) - 1.0) < 1e-3
        for r in results
    )

    # T5: no *_true fields in first-turn policy menu
    # (checked structurally: per_turn must not contain r_true)
    gates["T5_no_leakage"] = all(
        "r_true" not in turn and "phi_true" not in turn
        for r in results
        for turn in r.get("per_turn", [])
    )

    # T6: P3 and P5 make at least 1 different first choice across episodes
    p3_first: Dict[int, str] = {}
    p5_first: Dict[int, str] = {}
    for r in results:
        ep = r["_episode"]
        turns = r.get("per_turn", [])
        if turns:
            fc = turns[0]["source"]
            if r["model"] == "p3_ig":
                p3_first[ep] = fc
            elif r["model"] == "p5_robust_voi":
                p5_first[ep] = fc
    shared = set(p3_first) & set(p5_first)
    n_different = sum(p3_first[e] != p5_first[e] for e in shared)
    gates["T6_policy_divergence"] = (n_different >= 1) if shared else None

    # T7: P3 achieves coverage>0 in >=T7_MIN_EPISODES
    p3_scored = [s for s in scored if s["model"] == "p3_ig"]
    p3_nonzero = [
        s for s in p3_scored
        if (s.get("coverage_score_per_run") or 0.0) > 0.0
    ]
    gates["T7_baseline_coverage"] = len(p3_nonzero) >= T7_MIN_EPISODES
    gates["_T7_detail"] = f"{len(p3_nonzero)}/{len(p3_scored)} P3 episodes with coverage>0 (need >={T7_MIN_EPISODES})"

    # T8: no single P3 episode dominates (anti-lucky-episode).
    # Diagnostic gate: if total_flags <= 2, T8 is N/A (sparse transfer
    # behaviour; a single correct timestamp would fail this gate falsely).
    # We report the raw quantities regardless so they can be inspected blind.
    p3_flags = [s.get("n_flags_detected", 0) or 0 for s in p3_scored]
    total_p3_flags = sum(p3_flags)
    max_single = max(p3_flags) if p3_flags else 0
    fraction = (max_single / total_p3_flags) if total_p3_flags > 0 else None
    n_p3_zero = sum(1 for f in p3_flags if f == 0)

    if total_p3_flags <= 2:
        # Too sparse to apply the >50% rule meaningfully. Mark N/A (diagnostic).
        gates["T8_no_lucky_episode"] = None
    elif fraction is not None:
        gates["T8_no_lucky_episode"] = fraction <= T8_MAX_SINGLE_FRAC
    else:
        gates["T8_no_lucky_episode"] = False

    gates["_T8_detail"] = (
        f"total_detected_flags={total_p3_flags}  "
        f"max_episode_detected={max_single}  "
        f"max_episode_fraction={fraction:.3f}  "
        f"n_zero_coverage_episodes={n_p3_zero}"
        if fraction is not None else
        f"total_detected_flags={total_p3_flags}  too_sparse_for_T8"
    )

    return gates


def _coverage_stats(scored: List[Dict], policy: str) -> Dict:
    pol_s = [s for s in scored if s["model"] == policy]
    if not pol_s:
        return {}
    covs = [(s.get("coverage_score_per_run") or 0.0) for s in pol_s]
    n_nonzero = sum(1 for c in covs if c > 0)
    return {
        "n_episodes": len(covs),
        "mean": sum(covs) / len(covs),
        "min": min(covs),
        "max": max(covs),
        "n_zero_coverage": len(covs) - n_nonzero,
        "n_nonzero_coverage": n_nonzero,
    }


# ── Summary printer ───────────────────────────────────────────────────────────

def _print_summary(
    results: List[Dict],
    scored: List[Dict],
    gates: Dict[str, Any],
    meta: Dict,
) -> None:
    print("\n" + "=" * 72)
    print("PHASE 5A TRANSFER GATE — RESULTS")
    print("=" * 72)
    print(f"  CDB commit:   {meta['cdb_commit']}")
    print(f"  Data hash:    {meta['data_hash'][:16]}...")
    print(f"  Affinity:     {'uniform (ablation)' if meta['uniform_affinity'] else 'MITRE-grounded'}")

    print(f"\n{'Policy':<20} {'N':>4} {'AvgCov':>8} {'NonZeroCov':>12} {'AvgCand':>10}")
    print("-" * 58)
    for pol in sorted({r["model"] for r in results}):
        pol_rs = [r for r in results if r["model"] == pol]
        cst = _coverage_stats(scored, pol)
        avg_cands = sum(r["n_candidates"] for r in pol_rs) / max(len(pol_rs), 1)
        print(
            f"  {pol:<18} {cst.get('n_episodes',0):>4}"
            f" {cst.get('mean', 0):>8.3f}"
            f" {cst.get('n_nonzero_coverage',0):>5}/{cst.get('n_episodes',0):<5}"
            f" {avg_cands:>9.1f}"
        )

    print(f"\n{'Gate':<40} {'Status':>8}")
    print("-" * 50)
    hard_fail = []
    for gate, result in gates.items():
        if gate.startswith("_"):
            continue  # detail fields
        if result is None:
            symbol, status = "─", "N/A"
        elif result:
            symbol, status = "✅", "PASS"
        else:
            symbol, status = "🔴", "FAIL"
            hard_fail.append(gate)
        detail = gates.get(f"_{gate}_detail", "")
        row = f"  {symbol}  {gate:<38} {status:>6}"
        if detail:
            row += f"\n       └─ {detail}"
        print(row)

    print("\n" + "=" * 72)
    if not hard_fail:
        print("🟢 PHASE 5A TRANSFER GATE: PASS — Phase 5B authorized")
        print("   Next: freeze config, run full CDB sweep per main_v1.yaml")
    else:
        print(f"🔴 PHASE 5A TRANSFER GATE: FAIL — address: {', '.join(hard_fail)}")
        if "T7_baseline_coverage" in hard_fail:
            print("   ► T7 FAIL: Recalibrate obs_mapper.py thresholds before Phase 5B.")
    print("=" * 72 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5A CDB transfer gate (frozen config)")
    parser.add_argument("--episodes",        type=int,  default=DEFAULT_EPISODES)
    parser.add_argument("--budget",          type=int,  default=DEFAULT_BUDGET)
    parser.add_argument("--policies",        type=str,  default=",".join(DEFAULT_POLICIES))
    parser.add_argument("--estimator",       type=str,  default=DEFAULT_ESTIMATOR)
    parser.add_argument("--data",            type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--flags",           type=Path, default=DEFAULT_FLAGS_PATH)
    parser.add_argument("--out",             type=Path, default=None)
    parser.add_argument("--uniform-affinity", action="store_true",
                        help="Ablation: replace MITRE priors with uniform 0.5")
    parser.add_argument("--verbose",         action="store_true")
    args = parser.parse_args()

    policies = [p.strip() for p in args.policies.split(",")]

    if not args.data.exists():
        print(f"ERROR: CDB data not found: {args.data}")
        print("  git clone https://github.com/simbianai/cyber_defense_benchmark ../cdb")
        sys.exit(1)

    # Snapshot provenance (frozen before run, recorded in every artifact)
    cdb_commit   = _cdb_git_hash(_CDB)     # CDB repo HEAD, not HADES
    hades_commit = _hades_git_hash(_ROOT)  # HADES repo HEAD
    data_hash    = _sha256_file(args.data)
    meta = {
        "phase": "5A_transfer_gate",
        "config_frozen": True,
        "policies": policies,
        "n_episodes": args.episodes,
        "budget": args.budget,
        "estimator": args.estimator,
        "uniform_affinity": args.uniform_affinity,
        "hades_commit": hades_commit,   # HADES implementation freeze
        "cdb_commit": cdb_commit,       # CDB benchmark snapshot
        "data_hash": data_hash,         # sample.json sha256 (strongest provenance)
        "t7_min_episodes": T7_MIN_EPISODES,
        "t8_max_single_frac": T8_MAX_SINGLE_FRAC,
    }

    print("Phase 5A CDB Transfer Gate")
    print(f"  policies:         {policies}")
    print(f"  episodes:         {args.episodes} × each policy")
    print(f"  budget:           {args.budget} queries (CDB nominal=50; Phase 5B will sweep)")
    print(f"  estimator:        {args.estimator}")
    print(f"  affinity prior:   {'uniform (ablation)' if args.uniform_affinity else 'MITRE-grounded'}")
    print(f"  fast_db:          {'patched' if _patched else 'unpatched'}")
    print(f"  HADES commit:     {hades_commit}")
    print(f"  CDB commit:       {cdb_commit}")
    print(f"  data sha256:      {data_hash[:16]}...")
    print()

    t0 = time.time()
    n_total = len(policies) * args.episodes
    print(f"Running {n_total} episodes...")
    results = _run_episodes(
        args.data, policies, args.episodes, args.budget,
        args.estimator, args.uniform_affinity, args.verbose,
    )
    print(f"  Completed in {time.time() - t0:.1f}s\n")

    scored = _score_all(results, args.flags)
    gates  = _evaluate_gates(results, scored)
    _print_summary(results, scored, gates, meta)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            **meta,
            "gates": {k: (str(v) if not isinstance(v, (bool, type(None))) else v)
                      for k, v in gates.items()},
            "results": results,
            "scored": scored,
        }
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Raw artifact written to {args.out}")

    all_pass = all(v is None or v is True for k, v in gates.items() if not k.startswith("_"))
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
