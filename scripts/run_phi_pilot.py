"""scripts/run_phi_pilot.py -- Phase 7C.6 micro-pilot (phi-channel repair).

PURPOSE
-------
After the 7C.4 repair (P5 models phi_hat via the normalized forged-evidence
mixture), check whether the phi channel is decision-relevant in practice.

MATRIX (frozen in docs/phase7c_protocol.md)
-------------------------------------------
  Scenarios : B_reliability_flip, D_manipulation_flip
  Policies  : P3_ig, P5_full, P5_no_phi
  sigma     : {0.10, 0.30}  (NoisyEstimator)
  Regimes   : R1_missing, R2_stale, R3_misleading, R4a_targeted
  Lambda    : {0.5, 1.0, 2.0}
  Seeds     : 50 (default)

QUESTIONS
---------
  Q1: Do P5_full and P5_no_phi choose different queries (decision divergence)?
  Q2: Does P5_full use fewer high-phi sources than P5_no_phi?
  Q3: What is P5_full - P5_no_phi on TPM, per scenario x regime?
  Q4: What is P5_full - P3 on TPM in D (direction only -- pilot is not confirmatory)?

The pilot is exploratory. It evaluates PHI-4 only and makes no performance claim.

USAGE
-----
  py scripts/run_phi_pilot.py --seeds 50
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from hades.simulator.scenarios import ALL_SCENARIOS
from hades.corruption.missing import MissingCorruptor
from hades.corruption.stale import StaleCorruptor
from hades.corruption.misleading import MisleadingCorruptor
from hades.corruption.targeted import TargetedCorruptor
from hades.reliability.estimator import NoisyEstimator
from hades.integration.runner import IntegrationRunner
from hades.evaluation.metrics import extract_metrics
from hades.evaluation.statistics import _full_stats
from hades.policies.p3_ig import IGPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy
from scripts.run_mechanism_ablation import P5NoPhi


SIGMA_GRID = [0.10, 0.30]
FOCUS_SCENARIOS = [s for s in ALL_SCENARIOS
                   if any(tag in s.name for tag in ["B_", "D_"])]
CORRUPTION_REGIMES = [
    ("R1_missing",    MissingCorruptor(p_drop=0.25)),
    ("R2_stale",      StaleCorruptor(staleness=0.33)),
    ("R3_misleading", MisleadingCorruptor(p_inject=0.25)),
    ("R4a_targeted",  TargetedCorruptor(p_attack=0.75)),
]
LAMBDA_GRID = [0.5, 1.0, 2.0]


def make_policies(lam: float) -> Dict:
    return {
        "P3_ig":     IGPolicy(),
        "P5_full":   RobustVoIPolicy(lam=lam, use_robust=False),
        "P5_no_phi": P5NoPhi(lam=lam),
    }


def run_cell(scenario, corruptor, corr_label, estimator, est_label,
             lam, seed, budget):
    rng = random.Random(seed ^ 0xCAFE)
    true_hyp = rng.choice(scenario.hypotheses)
    out = {}
    for name, policy in make_policies(lam).items():
        runner = IntegrationRunner(
            scenario=scenario, budget=budget, seeds=1,
            corruptors=[corruptor], estimators=[estimator],
            policies=[policy], lam=lam,
        )
        ep = runner.run_episode(policy=policy, corruptor=corruptor,
                                estimator=estimator, seed=seed, true_hyp=true_hyp)
        ep.policy_name = name
        d = extract_metrics(ep, lam, corr_label, est_label).to_dict()
        d["sources_queried"] = list(ep.sources_queried)
        out[name] = d
    return out


def run(seeds: int, budget: float, verbose: bool) -> Dict:
    episodes: List[Dict] = []
    t0 = time.perf_counter()
    for sigma in SIGMA_GRID:
        est = NoisyEstimator(sigma=sigma)
        est_label = f"noisy_sigma{sigma}"
        for sc in FOCUS_SCENARIOS:
            for corr_label, corr in CORRUPTION_REGIMES:
                for lam in LAMBDA_GRID:
                    for seed in range(seeds):
                        cell = run_cell(sc, corr, corr_label, est, est_label,
                                        lam, seed, budget)
                        for d in cell.values():
                            d["sigma"] = sigma
                            episodes.append(d)
                if verbose:
                    print(f"  sigma={sigma} {sc.name} done "
                          f"({time.perf_counter() - t0:.1f}s)")
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(Path(__file__).parent.parent),
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        commit = "unknown"
    return {
        "meta": {
            "experiment_id": "phase7c_phi_pilot",
            "hades_commit": commit,
            "sigma_grid": SIGMA_GRID,
            "scenarios": [s.name for s in FOCUS_SCENARIOS],
            "regimes": [r for r, _ in CORRUPTION_REGIMES],
            "lambda_grid": LAMBDA_GRID,
            "n_seeds": seeds,
            "budget": budget,
            "n_episodes": len(episodes),
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
        },
        "episodes": episodes,
    }


def _key(d):
    return (d["sigma"], d["scenario"], d["corruption_regime"], d["lam"], d["seed"])


def analyze(episodes: List[Dict]) -> Dict:
    by = defaultdict(dict)
    for d in episodes:
        by[_key(d)][d["policy"]] = d

    groups = defaultdict(lambda: {"div": 0, "n": 0,
                                  "full": [], "nophi": [], "p3": [],
                                  "hphi_full": [], "hphi_nophi": []})
    for k, pol in by.items():
        if not all(p in pol for p in ("P3_ig", "P5_full", "P5_no_phi")):
            continue
        sigma, sc, reg, _lam, _seed = k
        for gk in [("ALL", sc, "ALL"), (sigma, sc, reg), ("ALL", sc, reg)]:
            g = groups[gk]
            g["n"] += 1
            g["div"] += int(pol["P5_full"]["sources_queried"]
                            != pol["P5_no_phi"]["sources_queried"])
            g["full"].append(pol["P5_full"]["tpm"])
            g["nophi"].append(pol["P5_no_phi"]["tpm"])
            g["p3"].append(pol["P3_ig"]["tpm"])
            g["hphi_full"].append(pol["P5_full"]["high_phi_queries"])
            g["hphi_nophi"].append(pol["P5_no_phi"]["high_phi_queries"])

    result = {}
    for (sigma, sc, reg), g in sorted(groups.items(), key=lambda x: str(x[0])):
        n = g["n"]
        result[f"{sigma}|{sc}|{reg}"] = {
            "n_pairs": n,
            "Q1_decision_divergence_rate": g["div"] / n if n else 0.0,
            "Q2_mean_high_phi_full": sum(g["hphi_full"]) / n,
            "Q2_mean_high_phi_no_phi": sum(g["hphi_nophi"]) / n,
            "Q3_full_vs_no_phi": _full_stats(g["full"], g["nophi"],
                                             boot_resamples=2000, boot_seed=7),
            "Q4_full_vs_p3": _full_stats(g["full"], g["p3"],
                                         boot_resamples=2000, boot_seed=11),
        }
    return result


def print_table(analysis: Dict) -> None:
    print("\n" + "=" * 118)
    print("PHASE 7C.6 -- PHI MICRO-PILOT (exploratory)")
    print("=" * 118)
    print(f"  {'cell':<44} {'n':>5} {'div%':>6} {'hphi F':>7} {'hphi N':>7} "
          f"{'F-N mean':>9} {'F-N CI':>20} {'F-P3 mean':>10} {'F-P3 CI':>20}")
    for k, v in analysis.items():
        q3, q4 = v["Q3_full_vs_no_phi"], v["Q4_full_vs_p3"]
        print(f"  {k:<44} {v['n_pairs']:>5} "
              f"{100 * v['Q1_decision_divergence_rate']:>5.1f}% "
              f"{v['Q2_mean_high_phi_full']:>7.2f} {v['Q2_mean_high_phi_no_phi']:>7.2f} "
              f"{q3['mean_diff']:>+9.4f} {str(q3['mean_ci']):>20} "
              f"{q4['mean_diff']:>+10.4f} {str(q4['mean_ci']):>20}")
    print("=" * 118)


def main():
    p = argparse.ArgumentParser(description="Phase 7C.6 phi micro-pilot")
    p.add_argument("--seeds", type=int, default=50)
    p.add_argument("--budget", type=float, default=10.0)
    p.add_argument("--output-dir", type=str, default="results/raw")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args()

    res = run(a.seeds, a.budget, not a.quiet)
    out_dir = Path(a.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = out_dir / f"phase7c_pilot_{ts}.json"
    raw_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"Raw saved -> {raw_path}")

    analysis = analyze(res["episodes"])
    analysis_out = {"meta": res["meta"], "raw_file": str(raw_path), "cells": analysis}
    Path("results/phase7c_pilot_analysis.json").write_text(
        json.dumps(analysis_out, indent=2), encoding="utf-8")
    print_table(analysis)
    print("Analysis saved -> results/phase7c_pilot_analysis.json")


if __name__ == "__main__":
    main()
