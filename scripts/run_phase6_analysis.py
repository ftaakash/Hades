"""scripts/run_phase6_analysis.py — Phase 6 Statistical Analysis & Verdict.

Reads raw Phase 6 sweep output and produces:
  1. Episode-level paired metrics (P5 vs P3)
  2. Wilcoxon signed-rank test (confirmatory)
  3. Bootstrap CI (95%, 10k resamples)
  4. Cliff's delta effect size
  5. Holm-corrected secondary breakdowns
  6. Kill gate verdicts (G6-1 through G6-5)
  7. Final verdict JSON

USAGE
-----
  py scripts/run_phase6_analysis.py results/raw/phase6_main_*.json
  py scripts/run_phase6_analysis.py results/raw/phase6_pilot_*.json --pilot

OUTPUT
------
  results/phase6_verdict.json
  STDOUT: human-readable verdict table
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from hades.evaluation.metrics import EpisodeMetrics, pair_episodes
from hades.evaluation.statistics import (
    paired_wilcoxon, paired_bootstrap_ci, cliffs_delta,
    holm_correction, evaluate_gates,
)


def load_episodes(path: str) -> List[EpisodeMetrics]:
    """Load episode metrics from raw sweep JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    episodes = []
    for ep in data["episodes"]:
        episodes.append(EpisodeMetrics(**{
            k: v for k, v in ep.items()
            if k in EpisodeMetrics.__dataclass_fields__
        }))
    return episodes


def confirmatory_analysis(pairs: List[Dict]) -> Dict:
    """Run confirmatory P5 vs P3 analysis on contaminated conditions."""
    contaminated = [p for p in pairs if p["corruption_regime"] != "R0_clean"]

    if not contaminated:
        return {"error": "No contaminated episodes found"}

    tpm_a = [p["tpm_a"] for p in contaminated]  # P5
    tpm_b = [p["tpm_b"] for p in contaminated]  # P3

    wilcox = paired_wilcoxon(tpm_a, tpm_b)
    boot = paired_bootstrap_ci(tpm_a, tpm_b)
    cliff = cliffs_delta(tpm_a, tpm_b)

    return {
        "n_pairs": len(contaminated),
        "wilcoxon": wilcox.to_dict(),
        "bootstrap_ci": boot.to_dict(),
        "cliffs_delta": cliff.to_dict(),
        "median_P5_tpm": sorted(tpm_a)[len(tpm_a) // 2],
        "median_P3_tpm": sorted(tpm_b)[len(tpm_b) // 2],
    }


def secondary_analysis(pairs: List[Dict]) -> Dict:
    """Holm-corrected secondary breakdowns by scenario, regime, estimator."""
    contaminated = [p for p in pairs if p["corruption_regime"] != "R0_clean"]
    results = {}

    # By scenario
    p_values = []
    for scenario in sorted(set(p["scenario"] for p in contaminated)):
        sc_pairs = [p for p in contaminated if p["scenario"] == scenario]
        tpm_a = [p["tpm_a"] for p in sc_pairs]
        tpm_b = [p["tpm_b"] for p in sc_pairs]
        w = paired_wilcoxon(tpm_a, tpm_b)
        b = paired_bootstrap_ci(tpm_a, tpm_b, n_resamples=5000, seed=100)
        c = cliffs_delta(tpm_a, tpm_b)
        results[f"scenario_{scenario}"] = {
            "n": len(sc_pairs),
            "wilcoxon_p": w.p_value,
            "median_diff": b.median_diff,
            "ci": [b.ci_low, b.ci_high],
            "cliffs_delta": c.delta,
            "interp": c.interpretation,
        }
        p_values.append((scenario, w.p_value))

    # Holm correction
    corrected = holm_correction(p_values)
    for label, adj_p, sig in corrected:
        results[f"scenario_{label}"]["holm_adj_p"] = adj_p
        results[f"scenario_{label}"]["significant_corrected"] = sig

    # By corruption regime
    for regime in sorted(set(p["corruption_regime"] for p in contaminated)):
        r_pairs = [p for p in contaminated if p["corruption_regime"] == regime]
        tpm_a = [p["tpm_a"] for p in r_pairs]
        tpm_b = [p["tpm_b"] for p in r_pairs]
        b = paired_bootstrap_ci(tpm_a, tpm_b, n_resamples=5000, seed=200)
        results[f"regime_{regime}"] = {
            "n": len(r_pairs),
            "median_diff": b.median_diff,
            "ci": [b.ci_low, b.ci_high],
        }

    # By estimator
    for est in sorted(set(p["estimator_regime"] for p in contaminated)):
        e_pairs = [p for p in contaminated if p["estimator_regime"] == est]
        tpm_a = [p["tpm_a"] for p in e_pairs]
        tpm_b = [p["tpm_b"] for p in e_pairs]
        b = paired_bootstrap_ci(tpm_a, tpm_b, n_resamples=5000, seed=300)
        results[f"estimator_{est}"] = {
            "n": len(e_pairs),
            "median_diff": b.median_diff,
            "ci": [b.ci_low, b.ci_high],
        }

    return results


def print_verdict(verdict: Dict) -> None:
    """Print human-readable verdict to stdout."""
    print("\n" + "=" * 70)
    print("HADES PHASE 6 — VERDICT")
    print("=" * 70)

    conf = verdict.get("confirmatory", {})
    print(f"\n  PRIMARY (P5 vs P3, contaminated conditions):")
    print(f"    Pairs      : {conf.get('n_pairs', 0)}")
    if "wilcoxon" in conf:
        print(f"    Wilcoxon p : {conf['wilcoxon']['p_value']:.6f}")
    if "bootstrap_ci" in conf:
        ci = conf["bootstrap_ci"]
        print(f"    Median diff: {ci['median_diff']:.4f}")
        print(f"    95% CI     : [{ci['ci_low']:.4f}, {ci['ci_high']:.4f}]")
    if "cliffs_delta" in conf:
        cd = conf["cliffs_delta"]
        print(f"    Cliff's δ  : {cd['delta']:.4f} ({cd['interpretation']})")

    print(f"\n  KILL GATES:")
    for gate in verdict.get("gates", []):
        icon = {"PASS": "🟢", "CONDITIONAL": "🟡", "KILL": "🔴"}.get(gate["status"], "❓")
        print(f"    {icon} {gate['gate_id']}: {gate['status']} — {gate['detail'][:80]}")

    overall = verdict.get("overall_verdict", "UNKNOWN")
    icon = "🟢" if overall == "GO" else "🔴" if overall == "KILL" else "🟡"
    print(f"\n  {icon} OVERALL: {overall}")
    print("=" * 70 + "\n")


def build_verdict(
    episodes: List[EpisodeMetrics],
    pilot: bool = False,
) -> Dict:
    """Build the complete Phase 6 verdict."""
    pairs = pair_episodes(episodes, policy_a="P5_robust_voi", policy_b="P3_ig")

    if not pairs:
        return {"error": "No P5-P3 pairs found", "overall_verdict": "ERROR"}

    conf = confirmatory_analysis(pairs)
    secondary = secondary_analysis(pairs)
    gates = evaluate_gates(pairs)

    # Overall verdict
    gate_statuses = [g.status for g in gates]
    if "KILL" in gate_statuses:
        overall = "CONDITIONAL"  # at least one gate killed
        kills = [g.gate_id for g in gates if g.status == "KILL"]
        overall_detail = f"Gates killed: {', '.join(kills)}"
    elif all(s == "PASS" for s in gate_statuses):
        overall = "GO"
        overall_detail = "All gates passed"
    else:
        overall = "CONDITIONAL"
        conditional = [g.gate_id for g in gates if g.status == "CONDITIONAL"]
        overall_detail = f"Conditional gates: {', '.join(conditional)}"

    verdict = {
        "experiment_id": "phase6_main_v2",
        "mode": "pilot" if pilot else "main",
        "overall_verdict": overall,
        "overall_detail": overall_detail,
        "confirmatory": conf,
        "secondary": secondary,
        "gates": [g.to_dict() for g in gates],
        "n_total_episodes": len(episodes),
        "n_pairs": len(pairs),
    }

    return verdict


def main():
    p = argparse.ArgumentParser(description="HADES Phase 6 Analysis")
    p.add_argument("input", help="Path to raw sweep JSON")
    p.add_argument("--pilot", action="store_true",
                   help="Mark as pilot (not inferential)")
    p.add_argument("--output", type=str, default="results/phase6_verdict.json")
    args = p.parse_args()

    print(f"Loading: {args.input}")
    episodes = load_episodes(args.input)
    print(f"  Loaded {len(episodes)} episodes")

    verdict = build_verdict(episodes, pilot=args.pilot)
    print_verdict(verdict)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2)
    print(f"Verdict saved → {out_path}")


if __name__ == "__main__":
    main()
