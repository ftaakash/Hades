"""scripts/run_reliability_stress.py — Phase 7B σ Sweep.

PURPOSE
-------
Test whether stronger reliability estimation noise makes the reliability
mechanism increasingly valuable. Focused on B (reliability-flip) and D
(manipulation-flip) scenarios.

MATRIX
------
  σ = {0, 0.05, 0.10, 0.20, 0.30}
  Scenarios: B, D
  Policies: P3, P5_full, P5_no_reliability, P5_no_cost, P5_no_phi
  Corruption regimes: R1-R4a (contaminated only)
  Lambda: {0.5, 1.0, 2.0}
  Seeds: 100

PRIMARY QUESTIONS
-----------------
  B: Does σ↑ make P5_full - P3 less negative / eventually positive?
  D: Does σ↑ make the φ channel matter?

USAGE
-----
  py scripts/run_reliability_stress.py --seeds 100
  py scripts/run_reliability_stress.py --seeds 5 --pilot
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from hades.simulator.scenarios import ALL_SCENARIOS
from hades.corruption.missing import MissingCorruptor
from hades.corruption.stale import StaleCorruptor
from hades.corruption.misleading import MisleadingCorruptor
from hades.corruption.targeted import TargetedCorruptor
from hades.reliability.estimator import (
    NoisyEstimator, CleanEstimator, AdversarialEstimator,
)
from hades.integration.runner import IntegrationRunner
from hades.evaluation.metrics import extract_metrics, EpisodeMetrics
from hades.evaluation.statistics import _full_stats
from hades.policies.p3_ig import IGPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy

# Import ablation variants from Phase 6D
from scripts.run_mechanism_ablation import (
    P5NoCost, P5NoReliability, P5NoPhi,
)


# ---------------------------------------------------------------------------
# Experimental matrix
# ---------------------------------------------------------------------------

SIGMA_GRID = [0.0, 0.05, 0.10, 0.20, 0.30]

FOCUS_SCENARIOS = [s for s in ALL_SCENARIOS
                   if any(tag in s.name for tag in ["B_", "D_"])]

CORRUPTION_REGIMES = [
    ("R1_missing",         MissingCorruptor(p_drop=0.25)),
    ("R2_stale",           StaleCorruptor(staleness=0.33)),
    ("R3_misleading",      MisleadingCorruptor(p_inject=0.25)),
    ("R4a_targeted",       TargetedCorruptor(p_attack=0.75)),
]

LAMBDA_GRID = [0.5, 1.0, 2.0]


def make_policies(lam: float) -> Dict:
    return {
        "P3_ig":            IGPolicy(),
        "P5_full":          RobustVoIPolicy(lam=lam, use_robust=False),
        "P5_no_cost":       P5NoCost(),
        "P5_no_reliability": P5NoReliability(lam=lam),
        "P5_no_phi":        P5NoPhi(lam=lam),
    }


# ---------------------------------------------------------------------------
# Episode runner
# ---------------------------------------------------------------------------

def run_cell(scenario, corruptor, corr_label, estimator, est_label,
             lam, seed, budget, policies):
    rng = random.Random(seed ^ 0xCAFE)
    true_hyp = rng.choice(scenario.hypotheses)

    results = []
    for policy_name, policy in policies.items():
        runner = IntegrationRunner(
            scenario=scenario, budget=budget, seeds=1,
            corruptors=[corruptor], estimators=[estimator],
            policies=[policy], lam=lam,
        )
        ep = runner.run_episode(
            policy=policy, corruptor=corruptor,
            estimator=estimator, seed=seed, true_hyp=true_hyp,
        )
        ep.policy_name = policy_name
        metrics = extract_metrics(ep, lam, corr_label, est_label)
        results.append(metrics)
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_sigma_sweep(seeds: int = 100, budget: float = 10.0,
                    pilot: bool = False, verbose: bool = True) -> Dict:
    all_metrics: List[Dict] = []

    total = (len(SIGMA_GRID) * len(FOCUS_SCENARIOS) * len(CORRUPTION_REGIMES) *
             len(LAMBDA_GRID) * seeds)

    if verbose:
        mode = "PILOT" if pilot else "SIGMA SWEEP"
        print(f"\n{'='*70}")
        print(f"HADES Phase 7B — {mode}")
        print(f"{'='*70}")
        print(f"  Sigma    : {SIGMA_GRID}")
        print(f"  Scenarios: {[s.name for s in FOCUS_SCENARIOS]}")
        print(f"  Regimes  : {len(CORRUPTION_REGIMES)}")
        print(f"  Lambda   : {LAMBDA_GRID}")
        print(f"  Seeds    : {seeds}")
        print(f"  Total    : {total} cells × 5 policies = {total*5} episodes")
        print(f"{'='*70}\n")

    t0 = time.perf_counter()
    done = 0

    for sigma in SIGMA_GRID:
        # Create estimator for this sigma
        if sigma == 0.0:
            estimator = CleanEstimator()
            est_label = "clean"
        else:
            estimator = NoisyEstimator(sigma=sigma)
            est_label = f"noisy_sigma{sigma}"

        for scenario in FOCUS_SCENARIOS:
            for corr_label, corruptor in CORRUPTION_REGIMES:
                for lam in LAMBDA_GRID:
                    policies = make_policies(lam)
                    for seed in range(seeds):
                        cell_metrics = run_cell(
                            scenario, corruptor, corr_label,
                            estimator, est_label, lam, seed, budget, policies,
                        )
                        for m in cell_metrics:
                            d = m.to_dict()
                            d["sigma"] = sigma
                            all_metrics.append(d)

                    done += seeds
                    if verbose and done % (seeds * 4) == 0:
                        elapsed = time.perf_counter() - t0
                        pct = done / total * 100
                        print(f"  [{pct:5.1f}%] σ={sigma} {scenario.name} "
                              f"× {corr_label} ({elapsed:.1f}s)")

    elapsed = time.perf_counter() - t0

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).parent.parent),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        commit = "unknown"

    return {
        "meta": {
            "experiment_id": "phase7b_sigma_sweep",
            "mode": "pilot" if pilot else "stress",
            "hades_commit": commit,
            "sigma_grid": SIGMA_GRID,
            "n_episodes": len(all_metrics),
            "n_seeds": seeds,
            "elapsed_seconds": round(elapsed, 2),
        },
        "episodes": all_metrics,
    }


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_sigma_sweep(all_metrics: List[Dict]) -> Dict:
    """Per-σ, per-scenario comparison table."""
    episodes = [EpisodeMetrics(**{k: v for k, v in m.items()
                if k in EpisodeMetrics.__dataclass_fields__}) for m in all_metrics]

    # Index by sigma
    sigma_values = sorted(set(m.get("sigma", 0.0) for m in all_metrics))
    variants = ["P5_full", "P5_no_cost", "P5_no_reliability", "P5_no_phi"]
    scenarios = sorted(set(m["scenario"] for m in all_metrics))

    results = {}
    for sigma in sigma_values:
        sigma_eps = [EpisodeMetrics(**{k: v for k, v in m.items()
                     if k in EpisodeMetrics.__dataclass_fields__})
                     for m in all_metrics if m.get("sigma") == sigma]

        sigma_key = f"sigma_{sigma}"
        results[sigma_key] = {}

        for variant in variants:
            from hades.evaluation.metrics import pair_episodes
            pairs = pair_episodes(sigma_eps, policy_a=variant, policy_b="P3_ig")
            if not pairs:
                results[sigma_key][variant] = {"error": "No pairs"}
                continue

            variant_res = {"aggregate": {}, "per_scenario": {}}
            tpm_a = [p["tpm_a"] for p in pairs]
            tpm_b = [p["tpm_b"] for p in pairs]
            variant_res["aggregate"] = _full_stats(tpm_a, tpm_b,
                                                    boot_resamples=5000, boot_seed=42)

            for sc in scenarios:
                sc_pairs = [p for p in pairs if p["scenario"] == sc]
                if sc_pairs:
                    sc_a = [p["tpm_a"] for p in sc_pairs]
                    sc_b = [p["tpm_b"] for p in sc_pairs]
                    variant_res["per_scenario"][sc] = _full_stats(
                        sc_a, sc_b, boot_resamples=5000,
                        boot_seed=hash(f"{sigma}_{variant}_{sc}") & 0x7FFFFFFF)

            results[sigma_key][variant] = variant_res

    return results


def print_sigma_table(analysis: Dict) -> None:
    """Print the sigma stress table."""
    print("\n" + "=" * 90)
    print("HADES PHASE 7B — RELIABILITY σ STRESS TEST")
    print("=" * 90)

    # Column: sigma, Variant, Scenario, mean, mean_CI, δ
    print(f"\n  {'σ':>5} | {'Variant':<20} | {'Scenario':<20} | "
          f"{'mean':>8} | {'mean_CI':>20} | {'δ':>7} | {'p':>10}")
    print("  " + "-" * 100)

    for sigma_key in sorted(analysis.keys()):
        sigma = sigma_key.replace("sigma_", "")
        for variant in ["P5_full", "P5_no_cost", "P5_no_reliability", "P5_no_phi"]:
            vdata = analysis[sigma_key].get(variant, {})
            if "error" in vdata:
                continue

            for sc, stats in sorted(vdata.get("per_scenario", {}).items()):
                print(f"  {sigma:>5} | {variant:<20} | {sc:<20} | "
                      f"{stats['mean_diff']:>+8.4f} | "
                      f"{str(stats['mean_ci']):>20} | "
                      f"{stats['cliffs_delta']:>7.4f} | "
                      f"{stats['wilcoxon_p']:>10.2e}")

        print("  " + "-" * 100)

    # Summary: P5_full vs P3 per sigma per scenario
    print(f"\n  SUMMARY: P5_full vs P3 (mean diff by σ)")
    print(f"  {'σ':>5} | {'B_reliability_flip':>20} | {'D_manipulation_flip':>20}")
    print("  " + "-" * 50)
    for sigma_key in sorted(analysis.keys()):
        sigma = sigma_key.replace("sigma_", "")
        p5 = analysis[sigma_key].get("P5_full", {}).get("per_scenario", {})
        b_val = p5.get("B_reliability_flip", {}).get("mean_diff", "N/A")
        d_val = p5.get("D_manipulation_flip", {}).get("mean_diff", "N/A")
        b_str = f"{b_val:+.4f}" if isinstance(b_val, float) else b_val
        d_str = f"{d_val:+.4f}" if isinstance(d_val, float) else d_val
        print(f"  {sigma:>5} | {b_str:>20} | {d_str:>20}")

    print("=" * 90 + "\n")


def main():
    p = argparse.ArgumentParser(description="HADES Phase 7B σ Stress Test")
    p.add_argument("--seeds", type=int, default=100)
    p.add_argument("--budget", type=float, default=10.0)
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--output-dir", type=str, default="results/raw")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    results = run_sigma_sweep(
        seeds=args.seeds, budget=args.budget,
        pilot=args.pilot, verbose=not args.quiet,
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = results["meta"]["mode"]
    out_path = out_dir / f"phase7b_{mode}_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw saved → {out_path}")

    analysis = analyze_sigma_sweep(results["episodes"])
    print_sigma_table(analysis)

    analysis_path = Path("results") / "phase7b_sigma_analysis.json"
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)
    print(f"Analysis saved → {analysis_path}")


if __name__ == "__main__":
    main()
