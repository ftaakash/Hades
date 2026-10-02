"""scripts/run_mechanism_ablation.py — Phase 6D Mechanism Attribution.

PURPOSE
-------
Decompose the P5 effect into its component contributions:

  P5_full     — full V(q) = EIG(r_hat, phi_hat) - lam*cost   (baseline)
  P5_no_cost  — V(q) = EIG(r_hat, phi_hat)  (lam=0)          (A3)
  P5_no_rel   — V(q) = EIG(1.0, 0.0) - lam*cost              (A1: neutralise reliability)
  P5_no_phi   — V(q) = EIG(r_hat, 0.0) - lam*cost             (A2: neutralise manipulation)
  P3          — argmax EIG(1.0, 0.0)                          (reference)

Focus on scenarios B (reliability-flip), C (cost-flip), D (manipulation-flip).
100 seeds, contaminated regimes only, lam grid from main_v2.yaml.

USAGE
-----
  py scripts/run_mechanism_ablation.py --seeds 100
  py scripts/run_mechanism_ablation.py --seeds 5 --pilot

OUTPUT
------
  results/raw/phase6d_ablation_<timestamp>.json
  STDOUT: ablation table
"""
from __future__ import annotations

import argparse
import copy
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

sys.path.insert(0, str(Path(__file__).parent.parent))

from hades.simulator.environment import SimEnv
from hades.simulator.scenarios import ALL_SCENARIOS
from hades.policies.base import InvestigationState, Policy, _argmax_tiebreak
from hades.policies.p3_ig import IGPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy
from hades.query_menu import QuerySpec
from hades.belief.likelihood import LikelihoodTable, make_default_table
from hades.belief.value import voi as _voi_func, eig as _eig_func
from hades.corruption.base import Corruptor
from hades.corruption.missing import MissingCorruptor
from hades.corruption.stale import StaleCorruptor
from hades.corruption.misleading import MisleadingCorruptor
from hades.corruption.targeted import TargetedCorruptor
from hades.reliability.estimator import (
    CleanEstimator, NoisyEstimator, MiscalibratedEstimator,
    AdversarialEstimator, ReliabilityEstimator,
)
from hades.integration.runner import IntegrationRunner, EpisodeResult
from hades.evaluation.metrics import extract_metrics, EpisodeMetrics
from hades.evaluation.statistics import _full_stats


# ---------------------------------------------------------------------------
# Ablated P5 variants
# ---------------------------------------------------------------------------

class P5NoCost(RobustVoIPolicy):
    """A3: P5 with lam=0 (cost component removed)."""
    name = "P5_no_cost"

    def __init__(self):
        super().__init__(lam=0.0, use_robust=False)


class P5NoReliability(Policy):
    """A1: P5 with r_hat=1.0, phi_hat=0.0 (reliability info neutralised).

    This forces EIG to use the nominal likelihood (no contamination),
    isolating the cost component.
    """
    name = "P5_no_reliability"

    def __init__(self, lam: float = 1.0):
        self.lam = lam

    def select_query(self, state, menu, likelihood_table=None, estimators=None):
        available = self._available(state, menu)
        if not available or state.remaining_budget <= 0:
            return None
        if not state.beliefs:
            return min(available)

        scores = {}
        for src_name, spec in available.items():
            cost = getattr(spec, "cost", 1.0)
            affinity = getattr(spec, "hypothesis_affinity", {})
            table = likelihood_table or make_default_table(
                sources=[src_name],
                hypotheses=list(state.beliefs.keys()),
                relevance={(src_name, h): affinity.get(h, 0.5)
                           for h in state.beliefs},
            )
            source_rel = {h: affinity.get(h, 0.5) for h in state.beliefs}

            # Neutralise: r_hat=1.0, phi_hat=0.0
            scores[src_name] = _voi_func(
                source=src_name, beliefs=state.beliefs, table=table,
                cost=cost, lam=self.lam, r_hat=1.0, phi_hat=0.0,
                source_relevance=source_rel, under_targeted_attack=False,
            )
        return _argmax_tiebreak(scores)


class P5NoPhi(Policy):
    """A2: P5 with phi_hat=0 (manipulation risk neutralised, reliability kept).

    Uses r_hat from the estimator but zeroes phi_hat.
    """
    name = "P5_no_phi"

    def __init__(self, lam: float = 1.0):
        self.lam = lam

    def select_query(self, state, menu, likelihood_table=None, estimators=None):
        available = self._available(state, menu)
        if not available or state.remaining_budget <= 0:
            return None
        if not state.beliefs:
            return min(available)

        scores = {}
        for src_name, spec in available.items():
            r_hat = getattr(spec, "reliability_estimated", 1.0)
            cost = getattr(spec, "cost", 1.0)
            affinity = getattr(spec, "hypothesis_affinity", {})
            table = likelihood_table or make_default_table(
                sources=[src_name],
                hypotheses=list(state.beliefs.keys()),
                relevance={(src_name, h): affinity.get(h, 0.5)
                           for h in state.beliefs},
            )
            source_rel = {h: affinity.get(h, 0.5) for h in state.beliefs}

            # Keep r_hat, neutralise phi_hat=0.0
            scores[src_name] = _voi_func(
                source=src_name, beliefs=state.beliefs, table=table,
                cost=cost, lam=self.lam, r_hat=r_hat, phi_hat=0.0,
                source_relevance=source_rel, under_targeted_attack=False,
            )
        return _argmax_tiebreak(scores)


# ---------------------------------------------------------------------------
# Experimental matrix
# ---------------------------------------------------------------------------

# Focus scenarios: B, C, D
FOCUS_SCENARIOS = [s for s in ALL_SCENARIOS
                   if any(tag in s.name for tag in ["B_", "C_", "D_"])]

# Contaminated regimes only (R0 excluded)
CORRUPTION_REGIMES = [
    ("R1_missing",         MissingCorruptor(p_drop=0.25)),
    ("R2_stale",           StaleCorruptor(staleness=0.33)),
    ("R3_misleading",      MisleadingCorruptor(p_inject=0.25)),
    ("R4a_targeted",       TargetedCorruptor(p_attack=0.75)),
    ("R4a_adversarial_est", TargetedCorruptor(p_attack=0.75)),
]

# Same estimators as main sweep
ESTIMATOR_REGIMES = [
    ("clean",              CleanEstimator()),
    ("noisy",              NoisyEstimator(sigma=0.10)),
    ("miscalibrated_under", MiscalibratedEstimator(phi_scale=0.286, phi_bias=0.0)),
    ("miscalibrated_over", MiscalibratedEstimator(phi_scale=1.286, phi_bias=0.0)),
    ("adversarial",        AdversarialEstimator()),
]

LAMBDA_GRID = [0.5, 1.0, 2.0]


def make_ablation_policies(lam: float) -> Dict[str, Policy]:
    """Instantiate the ablation policy set for a given lambda."""
    return {
        "P3_ig":            IGPolicy(),
        "P5_full":          RobustVoIPolicy(lam=lam, use_robust=False),
        "P5_no_cost":       P5NoCost(),           # lam=0 always
        "P5_no_reliability": P5NoReliability(lam=lam),
        "P5_no_phi":        P5NoPhi(lam=lam),
    }


# ---------------------------------------------------------------------------
# Episode runner (paired)
# ---------------------------------------------------------------------------

def run_ablation_cell(
    scenario, corruptor, corr_label, estimator, est_label,
    lam, seed, budget, policies,
):
    """Run all ablation policies on the same seed/true_hyp."""
    rng = random.Random(seed ^ 0xCAFE)
    true_hyp = rng.choice(scenario.hypotheses)

    actual_estimator = estimator
    if corr_label == "R4a_adversarial_est" and est_label != "adversarial":
        actual_estimator = AdversarialEstimator()

    results = []
    for policy_name, policy in policies.items():
        runner = IntegrationRunner(
            scenario=scenario, budget=budget, seeds=1,
            corruptors=[corruptor], estimators=[actual_estimator],
            policies=[policy], lam=lam,
        )
        ep = runner.run_episode(
            policy=policy, corruptor=corruptor,
            estimator=actual_estimator, seed=seed, true_hyp=true_hyp,
        )
        ep.policy_name = policy_name
        metrics = extract_metrics(ep, lam, corr_label, est_label)
        results.append(metrics)
    return results


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_ablation(all_metrics: List[Dict]) -> Dict:
    """Produce the ablation attribution table."""
    from hades.evaluation.metrics import EpisodeMetrics, pair_episodes

    episodes = [EpisodeMetrics(**{k: v for k, v in m.items()
                if k in EpisodeMetrics.__dataclass_fields__}) for m in all_metrics]

    # For each ablation variant vs P3, compute full stats per scenario
    variants = ["P5_full", "P5_no_cost", "P5_no_reliability", "P5_no_phi"]
    results = {}

    for variant in variants:
        pairs = pair_episodes(episodes, policy_a=variant, policy_b="P3_ig")
        if not pairs:
            results[variant] = {"error": "No pairs found"}
            continue

        variant_results = {"aggregate": {}, "per_scenario": {}}

        # Aggregate
        tpm_a = [p["tpm_a"] for p in pairs]
        tpm_b = [p["tpm_b"] for p in pairs]
        variant_results["aggregate"] = _full_stats(tpm_a, tpm_b,
                                                    boot_resamples=10000, boot_seed=42)

        # Per scenario
        for sc in sorted(set(p["scenario"] for p in pairs)):
            sc_pairs = [p for p in pairs if p["scenario"] == sc]
            sc_a = [p["tpm_a"] for p in sc_pairs]
            sc_b = [p["tpm_b"] for p in sc_pairs]
            variant_results["per_scenario"][sc] = _full_stats(
                sc_a, sc_b, boot_resamples=5000,
                boot_seed=hash(f"{variant}_{sc}") & 0x7FFFFFFF)

        results[variant] = variant_results

    return results


def print_ablation_table(analysis: Dict) -> None:
    """Print the mechanism-attribution table."""
    print("\n" + "=" * 80)
    print("HADES PHASE 6D — MECHANISM ATTRIBUTION")
    print("=" * 80)

    variants = ["P5_full", "P5_no_cost", "P5_no_reliability", "P5_no_phi"]
    scenarios = set()
    for v in variants:
        if "per_scenario" in analysis.get(v, {}):
            scenarios.update(analysis[v]["per_scenario"].keys())
    scenarios = sorted(scenarios)

    # Header
    print(f"\n  {'Variant':<22} | {'Scenario':<25} | {'mean':>8} | {'median':>8} | "
          f"{'mean_CI':>20} | {'δ':>7} | {'p':>10}")
    print("  " + "-" * 110)

    for variant in variants:
        vdata = analysis.get(variant, {})
        if "error" in vdata:
            print(f"  {variant:<22} | {'ERROR':>25} | {vdata['error']}")
            continue

        # Aggregate
        agg = vdata.get("aggregate", {})
        print(f"  {variant:<22} | {'AGGREGATE':<25} | {agg.get('mean_diff',0):>+8.4f} | "
              f"{agg.get('median_diff',0):>8.4f} | "
              f"{str(agg.get('mean_ci',[])):>20} | "
              f"{agg.get('cliffs_delta',0):>7.4f} | "
              f"{agg.get('wilcoxon_p',1):>10.2e}")

        # Per scenario
        for sc in scenarios:
            sc_data = vdata.get("per_scenario", {}).get(sc, {})
            if sc_data:
                print(f"  {'':22} | {sc:<25} | {sc_data.get('mean_diff',0):>+8.4f} | "
                      f"{sc_data.get('median_diff',0):>8.4f} | "
                      f"{str(sc_data.get('mean_ci',[])):>20} | "
                      f"{sc_data.get('cliffs_delta',0):>7.4f} | "
                      f"{sc_data.get('wilcoxon_p',1):>10.2e}")

        print("  " + "-" * 110)

    # Interpretation
    print("\n  INTERPRETATION KEY:")
    print("    P5_full  vs P3 = total effect")
    print("    P5_no_cost (λ=0) vs P3 = effect WITHOUT cost component")
    print("    P5_no_reliability (r=1,φ=0) vs P3 = effect WITHOUT reliability info (cost only)")
    print("    P5_no_phi (φ=0) vs P3 = effect WITHOUT manipulation risk (reliability + cost)")
    print()
    print("    If P5_full >> P3 but P5_no_cost ≈ P3 → effect is cost-driven")
    print("    If P5_no_reliability ≈ P5_full → reliability info adds nothing")
    print("    If P5_no_phi ≈ P5_full → manipulation risk adds nothing")
    print("=" * 80 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_ablation(seeds: int = 100, budget: float = 10.0,
                 pilot: bool = False, verbose: bool = True) -> Dict:
    """Run the mechanism-attribution ablation sweep."""
    all_metrics: List[Dict] = []
    total_cells = (len(FOCUS_SCENARIOS) * len(CORRUPTION_REGIMES) *
                   len(ESTIMATOR_REGIMES) * len(LAMBDA_GRID) * seeds)
    done = 0

    if verbose:
        mode = "PILOT" if pilot else "ABLATION"
        print(f"\n{'='*70}")
        print(f"HADES Phase 6D — {mode}")
        print(f"{'='*70}")
        print(f"  Scenarios  : {[s.name for s in FOCUS_SCENARIOS]}")
        print(f"  Regimes    : {len(CORRUPTION_REGIMES)} (contaminated only)")
        print(f"  Estimators : {len(ESTIMATOR_REGIMES)}")
        print(f"  Lambda     : {LAMBDA_GRID}")
        print(f"  Seeds      : {seeds}")
        print(f"  Policies   : P3, P5_full, P5_no_cost, P5_no_reliability, P5_no_phi")
        print(f"  Total cells: {total_cells}")
        print(f"  Total eps  : {total_cells * 5}")
        print(f"{'='*70}\n")

    t0 = time.perf_counter()

    for scenario in FOCUS_SCENARIOS:
        for corr_label, corruptor in CORRUPTION_REGIMES:
            for est_label, estimator in ESTIMATOR_REGIMES:
                for lam in LAMBDA_GRID:
                    policies = make_ablation_policies(lam)
                    for seed in range(seeds):
                        cell_metrics = run_ablation_cell(
                            scenario, corruptor, corr_label,
                            estimator, est_label, lam, seed, budget, policies,
                        )
                        for m in cell_metrics:
                            all_metrics.append(m.to_dict())

                    done += seeds
                    if verbose and done % (seeds * 3) == 0:
                        elapsed = time.perf_counter() - t0
                        pct = done / total_cells * 100
                        print(f"  [{pct:5.1f}%] {done}/{total_cells}  "
                              f"{elapsed:.1f}s  {scenario.name} × {corr_label}")

    elapsed = time.perf_counter() - t0

    # Provenance
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).parent.parent),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        commit = "unknown"

    result = {
        "meta": {
            "experiment_id": "phase6d_mechanism_ablation",
            "mode": "pilot" if pilot else "ablation",
            "hades_commit": commit,
            "n_episodes": len(all_metrics),
            "n_seeds": seeds,
            "focus_scenarios": [s.name for s in FOCUS_SCENARIOS],
            "elapsed_seconds": round(elapsed, 2),
        },
        "episodes": all_metrics,
    }

    if verbose:
        print(f"\n  Completed: {len(all_metrics)} episodes in {elapsed:.1f}s")

    return result


def main():
    p = argparse.ArgumentParser(description="HADES Phase 6D Mechanism Ablation")
    p.add_argument("--seeds", type=int, default=100)
    p.add_argument("--budget", type=float, default=10.0)
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--output-dir", type=str, default="results/raw")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    results = run_ablation(
        seeds=args.seeds, budget=args.budget,
        pilot=args.pilot, verbose=not args.quiet,
    )

    # Save raw
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = results["meta"]["mode"]
    out_path = out_dir / f"phase6d_{mode}_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw saved → {out_path}")

    # Analyze
    analysis = analyze_ablation(results["episodes"])
    print_ablation_table(analysis)

    # Save analysis
    analysis_path = Path("results") / "phase6d_ablation_analysis.json"
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)
    print(f"Analysis saved → {analysis_path}")


if __name__ == "__main__":
    main()
