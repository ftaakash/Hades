"""scripts/run_phase6_sweep.py — Phase 6 Main Scientific Sweep.

PURPOSE
-------
Run the full confirmatory sweep: 8 policies × 5 scenarios × 6 corruption
regimes × 5 estimators × 3 λ × 100 seeds = 360,000 paired episodes.

PROTOCOL
--------
- Config: configs/experiments/main_v2.yaml (FROZEN)
- Primary comparison: P5 vs P3
- Primary metric: TPM (final posterior mass on true hypothesis)
- Pairing: same seed/true_hyp across all policies per cell
- Pilot: --pilot --seeds 5 for execution validation only

USAGE
-----
  py scripts/run_phase6_sweep.py --seeds 100
  py scripts/run_phase6_sweep.py --pilot --seeds 5
  py scripts/run_phase6_sweep.py --seeds 100 --lam 1.0

OUTPUT
------
  results/raw/phase6_main_<timestamp>.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Ensure hades package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from hades.simulator.environment import SimEnv
from hades.simulator.scenarios import ALL_SCENARIOS
from hades.policies.base import InvestigationState, Policy
from hades.policies.random_policy import RandomPolicy
from hades.policies.fixed_heuristic import FixedHeuristicPolicy
from hades.policies.p2_relevance import RelevancePolicy
from hades.policies.p3_ig import IGPolicy
from hades.policies.p4_ig_cost import IGCostPolicy
from hades.policies.p4b_ig_cost_rel import IGCostRelPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy
from hades.policies.p7_bayes_al import BayesALPolicy
from hades.corruption.base import Corruptor, OBS_CLASSES
from hades.corruption.missing import MissingCorruptor
from hades.corruption.stale import StaleCorruptor
from hades.corruption.misleading import MisleadingCorruptor
from hades.corruption.targeted import TargetedCorruptor
from hades.reliability.estimator import (
    ReliabilityEstimator, CleanEstimator, NoisyEstimator,
    MiscalibratedEstimator, AdversarialEstimator, EstimatorResult,
)
from hades.integration.runner import (
    IntegrationRunner, EpisodeResult, _make_policy_menu, _corrupted_step,
)
from hades.evaluation.metrics import extract_metrics, EpisodeMetrics


# ---------------------------------------------------------------------------
# Experimental matrix from main_v2.yaml
# ---------------------------------------------------------------------------

CORRUPTION_REGIMES = [
    ("R0_clean",           MissingCorruptor(p_drop=0.0)),
    ("R1_missing",         MissingCorruptor(p_drop=0.25)),
    ("R2_stale",           StaleCorruptor(staleness=0.33)),
    ("R3_misleading",      MisleadingCorruptor(p_inject=0.25)),
    ("R4a_targeted",       TargetedCorruptor(p_attack=0.75)),
    ("R4a_adversarial_est", TargetedCorruptor(p_attack=0.75)),  # compound
]

ESTIMATOR_REGIMES = [
    ("clean",              CleanEstimator()),
    ("noisy",              NoisyEstimator(sigma=0.10)),
    ("miscalibrated_under", MiscalibratedEstimator(phi_scale=0.286, phi_bias=0.0)),
    ("miscalibrated_over", MiscalibratedEstimator(phi_scale=1.286, phi_bias=0.0)),
    ("adversarial",        AdversarialEstimator()),
]

LAMBDA_GRID = [0.5, 1.0, 2.0]


def make_policies(lam: float) -> Dict[str, Policy]:
    """Instantiate all 8 policies for a given lambda."""
    return {
        "P0_random":        RandomPolicy(seed=0),
        "P1_fixed":         FixedHeuristicPolicy(),
        "P2_relevance":     RelevancePolicy(),
        "P3_ig":            IGPolicy(),
        "P4_ig_cost":       IGCostPolicy(),
        "P4b_rel":          IGCostRelPolicy(),
        "P5_robust_voi":    RobustVoIPolicy(lam=lam, use_robust=False),
        "P7_bayes_al":      BayesALPolicy(),
    }


# ---------------------------------------------------------------------------
# Single paired cell runner
# ---------------------------------------------------------------------------

def run_cell(
    scenario,
    corruptor: Corruptor,
    corruptor_label: str,
    estimator: ReliabilityEstimator,
    estimator_label: str,
    lam: float,
    seed: int,
    budget: float,
    policies: Dict[str, Policy],
) -> List[EpisodeMetrics]:
    """Run all policies on the same (scenario, regime, estimator, lam, seed).

    Pairing: same true_hyp derived from seed for all policies.
    """
    # Derive true_hyp from seed (deterministic, same across policies)
    rng = random.Random(seed ^ 0xCAFE)
    true_hyp = rng.choice(scenario.hypotheses)

    # For compound R4a+adversarial, override estimator
    actual_estimator = estimator
    if corruptor_label == "R4a_adversarial_est" and estimator_label != "adversarial":
        actual_estimator = AdversarialEstimator()

    results = []
    for policy_name, policy in policies.items():
        # Fresh env per policy (same seed → same RNG state)
        runner = IntegrationRunner(
            scenario=scenario,
            budget=budget,
            seeds=1,
            corruptors=[corruptor],
            estimators=[actual_estimator],
            policies=[policy],
            lam=lam,
        )
        ep = runner.run_episode(
            policy=policy,
            corruptor=corruptor,
            estimator=actual_estimator,
            seed=seed,
            true_hyp=true_hyp,
        )
        # Override policy name to our canonical names
        ep.policy_name = policy_name

        metrics = extract_metrics(
            result=ep,
            lam=lam,
            corruption_regime=corruptor_label,
            estimator_regime=estimator_label,
        )
        results.append(metrics)

    return results


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def get_provenance(config_path: str = "configs/experiments/main_v2.yaml") -> Dict:
    """Collect provenance fields for the run."""
    # Git commit
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).parent.parent),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        commit = "unknown"

    # Config hash
    config_hash = "unknown"
    cfg_path = Path(__file__).parent.parent / config_path
    if cfg_path.exists():
        config_hash = hashlib.sha256(cfg_path.read_bytes()).hexdigest()[:16]

    return {
        "hades_commit": commit,
        "python_version": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "config_hash": config_hash,
        "config_file": config_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def run_sweep(
    seeds: int = 100,
    lambda_grid: Optional[List[float]] = None,
    budget: float = 10.0,
    pilot: bool = False,
    verbose: bool = True,
) -> Dict:
    """Run the full Phase 6 sweep."""
    if lambda_grid is None:
        lambda_grid = LAMBDA_GRID

    scenarios = ALL_SCENARIOS
    provenance = get_provenance()

    all_metrics: List[Dict] = []
    total_cells = (len(scenarios) * len(CORRUPTION_REGIMES) *
                   len(ESTIMATOR_REGIMES) * len(lambda_grid) * seeds)
    total_episodes = total_cells * 8  # 8 policies per cell
    done_cells = 0

    if verbose:
        mode = "PILOT" if pilot else "MAIN SWEEP"
        print(f"\n{'='*70}")
        print(f"HADES Phase 6 — {mode}")
        print(f"{'='*70}")
        print(f"  Scenarios   : {len(scenarios)}")
        print(f"  Corruption  : {len(CORRUPTION_REGIMES)}")
        print(f"  Estimators  : {len(ESTIMATOR_REGIMES)}")
        print(f"  Lambda      : {lambda_grid}")
        print(f"  Seeds       : {seeds}")
        print(f"  Budget      : {budget}")
        print(f"  Total cells : {total_cells}")
        print(f"  Total eps   : {total_episodes}")
        print(f"  Commit      : {provenance['hades_commit'][:8]}")
        print(f"{'='*70}\n")

    t0 = time.perf_counter()

    for si, scenario in enumerate(scenarios):
        for ci, (corr_label, corruptor) in enumerate(CORRUPTION_REGIMES):
            for ei, (est_label, estimator) in enumerate(ESTIMATOR_REGIMES):
                for li, lam in enumerate(lambda_grid):
                    policies = make_policies(lam)

                    for seed in range(seeds):
                        cell_metrics = run_cell(
                            scenario=scenario,
                            corruptor=corruptor,
                            corruptor_label=corr_label,
                            estimator=estimator,
                            estimator_label=est_label,
                            lam=lam,
                            seed=seed,
                            budget=budget,
                            policies=policies,
                        )
                        for m in cell_metrics:
                            all_metrics.append(m.to_dict())

                    done_cells += seeds
                    if verbose and done_cells % (seeds * 5) == 0:
                        elapsed = time.perf_counter() - t0
                        pct = done_cells / total_cells * 100
                        eps = done_cells * 8 / max(elapsed, 0.01)
                        print(f"  [{pct:5.1f}%] {done_cells}/{total_cells} cells  "
                              f"{elapsed:.1f}s  {eps:.0f} ep/s  "
                              f"{scenario.name} × {corr_label} × {est_label}")

    elapsed = time.perf_counter() - t0

    result = {
        "meta": {
            "experiment_id": "phase6_main_v2",
            "mode": "pilot" if pilot else "main",
            "provenance": provenance,
            "n_episodes": len(all_metrics),
            "n_seeds": seeds,
            "lambda_grid": lambda_grid,
            "budget": budget,
            "elapsed_seconds": round(elapsed, 2),
        },
        "episodes": all_metrics,
    }

    if verbose:
        print(f"\n  Completed: {len(all_metrics)} episodes in {elapsed:.1f}s")

    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_results(results: Dict, output_dir: str = "results/raw") -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = results["meta"]["mode"]
    out_path = out_dir / f"phase6_{mode}_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="HADES Phase 6 Scientific Sweep")
    p.add_argument("--seeds", type=int, default=100)
    p.add_argument("--lam", type=str, default=None,
                   help="Comma-separated lambda values (default: 0.5,1.0,2.0)")
    p.add_argument("--budget", type=float, default=10.0)
    p.add_argument("--pilot", action="store_true",
                   help="Pilot mode (execution validation only, not inferential)")
    p.add_argument("--output-dir", type=str, default="results/raw")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    lam_grid = [float(x) for x in args.lam.split(",")] if args.lam else None

    results = run_sweep(
        seeds=args.seeds,
        lambda_grid=lam_grid,
        budget=args.budget,
        pilot=args.pilot,
        verbose=not args.quiet,
    )

    out_path = save_results(results, args.output_dir)
    print(f"\nResults saved → {out_path}")
    print(f"Episodes: {results['meta']['n_episodes']}")


if __name__ == "__main__":
    main()
