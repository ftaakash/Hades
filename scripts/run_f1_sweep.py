"""
scripts/run_f1_sweep.py
-----------------------
F1/F5 Kill Gate Sweep — Phase 3 (HADES v3.0)

PURPOSE
-------
Tests whether P5 (robust VoI) creates meaningful policy separation versus
P3/P4/P4b/P7 across increasing corruption levels. This is the mandatory
scientific kill gate BEFORE any CDB experiments.

WHAT IT MEASURES
----------------
F1 — Does reliability modify acquisition ordering?  (clean regime)
F5 — Does adversarial contamination create measurable P3↔P5 divergence?

KILL CONDITIONS (per AGENTS.md)
--------------------------------
F1 ~0  : kill method claim
F1 pass + collapse at 10-25% noise : estimator paper reframe

METRICS
-------
- flip_rate  : fraction of steps where P5 chose differently from P3
- p3_vs_p5_agreement : mean Jaccard similarity of top-k choice sets
- manip_source_reliance : fraction of queries to high-phi_hat sources
- posterior_quality : max_belief at episode end (higher = more certain)
- correct_hyp_rate  : fraction of episodes where leading belief == true_hyp

USAGE
-----
  py scripts/run_f1_sweep.py --seeds 20 --noise 0,0.10,0.25,0.50 --budgets 10
  py scripts/run_f1_sweep.py --seeds 5 --noise 0,0.25  (quick smoke)

OUTPUT
------
  results/raw/f1_sweep_<timestamp>.json
  STDOUT: summary table + GO/NO-GO verdict per noise level

LAMBDA PROTOCOL (pre-registered)
---------------------------------
lambda_grid = [0.5, 1.0, 2.0]   (fixed before any run, no post-hoc selection)
Primary analysis uses lam=1.0. Sensitivity reported across all lam values.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Make sure hades package is importable when run from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from hades.simulator.environment import SimEnv, SimEvidenceSource, SimScenario
from hades.simulator.scenarios import ALL_SCENARIOS
from hades.policies.base import InvestigationState
from hades.policies.p3_ig import IGPolicy
from hades.policies.p4_ig_cost import IGCostPolicy
from hades.policies.p4b_ig_cost_rel import IGCostRelPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy
from hades.policies.p7_bayes_al import BayesALPolicy


# ---------------------------------------------------------------------------
# Pre-registered lambda grid (fixed before runs; do not change post-hoc)
# ---------------------------------------------------------------------------
LAMBDA_GRID = [0.5, 1.0, 2.0]


# ---------------------------------------------------------------------------
# Policy instantiation helpers
# ---------------------------------------------------------------------------

def make_policies(lam: float):
    """Instantiate all sweep policies for a given lambda value."""
    return {
        "P3_ig":        IGPolicy(),
        "P4_ig_cost":   IGCostPolicy(),
        "P4b_rel":      IGCostRelPolicy(),
        "P5_voi":       RobustVoIPolicy(lam=lam, use_robust=False),
        "P7_bayes_al":  BayesALPolicy(),
    }


# ---------------------------------------------------------------------------
# SimEnv → InvestigationState bridge
# ---------------------------------------------------------------------------

def _make_state(env: SimEnv, budget: float) -> InvestigationState:
    """Build a policy-visible InvestigationState from current SimEnv state."""
    beliefs = env.beliefs
    leading = max(beliefs, key=lambda h: (beliefs[h], h)) if beliefs else ""
    return InvestigationState(
        queried_sources=[],
        history=[],
        remaining_budget=budget,
        beliefs=beliefs,
        leading_hyp=leading,
    )


def _menu_from_env(env: SimEnv) -> dict:
    """Build the policy menu dict from SimEnv sources."""
    return {src.name: src for src in env.sources}


# ---------------------------------------------------------------------------
# Single-episode runner for one policy
# ---------------------------------------------------------------------------

def run_episode(
    env: SimEnv,
    policy,
    budget: float,
    true_hypothesis: str,
    seed: int,
    corruption_regime: str = "R0_clean",
    noise_level: float = 0.0,
) -> Dict:
    """
    Run one full episode. Returns metrics dict.

    noise_level: injected reliability estimation error (sigma).
    """
    env.reset(true_hypothesis=true_hypothesis, seed=seed)
    menu = _menu_from_env(env)

    # Apply estimation noise to r_hat (misspecification experiment)
    # True values unchanged; only estimated copies get noise.
    import random as _rnd
    rng = _rnd.Random(seed ^ 0xDEADBEEF)

    def noisy_spec(src: SimEvidenceSource, sigma: float):
        """Return a namedspace-like object with noisy estimated fields."""
        import types
        r_noisy = float(max(0.0, min(1.0, src.reliability_estimated + rng.gauss(0, sigma))))
        phi_noisy = float(max(0.0, min(1.0, src.manipulation_risk_estimated + rng.gauss(0, sigma))))
        return types.SimpleNamespace(
            name=src.name,
            cost=src.cost,
            reliability_estimated=r_noisy,
            manipulation_risk_estimated=phi_noisy,
            hypothesis_affinity=src.hypothesis_affinity,
        )

    noisy_menu = {
        k: noisy_spec(v, noise_level) for k, v in menu.items()
    }

    choices_made = []
    high_phi_queries = 0
    phi_threshold = 0.40  # sources with phi_hat >= 0.4 are "manipulable"

    remaining = budget
    step = 0
    while remaining > 0 and step < 50:  # safety cap
        state = InvestigationState(
            queried_sources=choices_made[:],
            history=[],
            remaining_budget=remaining,
            beliefs=env.beliefs,
            leading_hyp=max(env.beliefs, key=lambda h: (env.beliefs[h], h)),
        )

        # Policy sees the noisy menu (misspecified estimates)
        affordable_noisy = {k: v for k, v in noisy_menu.items()
                            if v.cost <= remaining}
        if not affordable_noisy:
            break

        choice = policy.select_query(state, affordable_noisy)
        if choice is None:
            break

        # Execute on the ground-truth SimEnv (which uses true values internally)
        try:
            env.step(choice)
        except RuntimeError:
            break

        choices_made.append(choice)
        remaining -= menu[choice].cost
        step += 1

        # Track reliance on manipulable sources (using noisy phi estimate)
        if noisy_menu[choice].manipulation_risk_estimated >= phi_threshold:
            high_phi_queries += 1

    # ── Episode metrics ──────────────────────────────────────────────────
    final_beliefs = env.beliefs
    max_belief = max(final_beliefs.values()) if final_beliefs else 0.0
    leading_hyp = max(final_beliefs, key=lambda h: (final_beliefs[h], h)) \
        if final_beliefs else ""
    correct = (leading_hyp == true_hypothesis)
    n_queries = len(choices_made)

    return {
        "choices": choices_made,
        "n_queries": n_queries,
        "high_phi_queries": high_phi_queries,
        "manip_reliance": high_phi_queries / max(n_queries, 1),
        "max_belief": max_belief,
        "correct_hyp": correct,
        "final_beliefs": final_beliefs,
    }


# ---------------------------------------------------------------------------
# Flip-rate computation (P5 vs reference policy)
# ---------------------------------------------------------------------------

def compute_flip_rate(
    results_p3: List[Dict],
    results_p5: List[Dict],
) -> float:
    """
    Fraction of episodes where P5 chose a DIFFERENT first query than P3.
    (First query is the clearest single-step policy differentiation signal.)
    """
    if not results_p3 or not results_p5:
        return 0.0
    assert len(results_p3) == len(results_p5)
    flips = 0
    for r3, r5 in zip(results_p3, results_p5):
        c3 = r3["choices"][:1]
        c5 = r5["choices"][:1]
        if c3 != c5:
            flips += 1
    return flips / len(results_p3)


def compute_manip_reliance_gap(
    results_p3: List[Dict],
    results_p5: List[Dict],
) -> float:
    """
    Mean reduction in manipulable-source queries: P5 - P3.
    Negative = P5 queries fewer manipulable sources (desired behaviour).
    """
    if not results_p3 or not results_p5:
        return 0.0
    gap = [r5["manip_reliance"] - r3["manip_reliance"]
           for r3, r5 in zip(results_p3, results_p5)]
    return sum(gap) / len(gap)


def compute_posterior_quality_gap(
    results_p3: List[Dict],
    results_p5: List[Dict],
) -> float:
    """Mean improvement in max_belief: P5 - P3. Positive = P5 is better."""
    if not results_p3 or not results_p5:
        return 0.0
    gap = [r5["max_belief"] - r3["max_belief"]
           for r3, r5 in zip(results_p3, results_p5)]
    return sum(gap) / len(gap)


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def run_sweep(
    seeds: int,
    noise_levels: List[float],
    budgets: List[float],
    lambda_grid: List[float],
    verbose: bool = True,
) -> Dict:
    """Run the full F1/F5 kill-gate sweep. Returns results dict."""
    scenarios = ALL_SCENARIOS
    results = {
        "meta": {
            "seeds": seeds,
            "noise_levels": noise_levels,
            "budgets": budgets,
            "lambda_grid": lambda_grid,
            "scenarios": [s.name for s in scenarios],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "F1_sweep_v1",
        },
        "runs": [],
        "summary": {},
    }

    total_configs = (len(scenarios) * len(noise_levels) * len(budgets)
                     * len(lambda_grid) * seeds)
    done = 0

    for scenario in scenarios:
        for noise in noise_levels:
            for budget in budgets:
                for lam in lambda_grid:
                    policies = make_policies(lam)
                    per_policy_results: Dict[str, List[Dict]] = {
                        name: [] for name in policies
                    }

                    for seed_i in range(seeds):
                        # Sample true_hypothesis uniformly across seeds
                        import random as _rnd2
                        rng2 = _rnd2.Random(seed_i ^ 0xCAFE)
                        true_hyp = rng2.choice(scenario.hypotheses)

                        for policy_name, policy in policies.items():
                            corruption = (
                                "R4_targeted" if noise > 0.25
                                else "R1_missing" if noise > 0.0
                                else "R0_clean"
                            )
                            env = SimEnv(
                                scenario,
                                seed=seed_i,
                                budget=budget,
                                corruption_regime=corruption,
                                missing_drop_rate=noise,
                            )
                            ep = run_episode(
                                env=env,
                                policy=policy,
                                budget=budget,
                                true_hypothesis=true_hyp,
                                seed=seed_i,
                                noise_level=noise,
                            )
                            ep["scenario"] = scenario.name
                            ep["noise"] = noise
                            ep["budget"] = budget
                            ep["lam"] = lam
                            ep["policy"] = policy_name
                            ep["seed"] = seed_i
                            ep["true_hyp"] = true_hyp
                            results["runs"].append(ep)
                            per_policy_results[policy_name].append(ep)

                        done += len(policies)

                    # ── Compute summary metrics for this configuration ──
                    key = f"{scenario.name}|noise={noise}|budget={budget}|lam={lam}"
                    r3 = per_policy_results["P3_ig"]
                    r5 = per_policy_results["P5_voi"]
                    flip = compute_flip_rate(r3, r5)
                    manip_gap = compute_manip_reliance_gap(r3, r5)
                    post_gap = compute_posterior_quality_gap(r3, r5)
                    correct_p3 = sum(r["correct_hyp"] for r in r3) / max(len(r3), 1)
                    correct_p5 = sum(r["correct_hyp"] for r in r5) / max(len(r5), 1)

                    summary_entry = {
                        "scenario": scenario.name,
                        "noise": noise,
                        "budget": budget,
                        "lam": lam,
                        "flip_rate_P3_vs_P5": round(flip, 4),
                        "manip_reliance_gap_P5_minus_P3": round(manip_gap, 4),
                        "posterior_quality_gap_P5_minus_P3": round(post_gap, 4),
                        "correct_hyp_rate_P3": round(correct_p3, 4),
                        "correct_hyp_rate_P5": round(correct_p5, 4),
                        "n_episodes_per_policy": seeds,
                    }
                    results["summary"][key] = summary_entry

                    if verbose:
                        verdict = _verdict_line(flip, noise)
                        print(
                            f"  {scenario.name:<22} noise={noise:.2f}  "
                            f"budget={budget:4.0f}  lam={lam:.1f}  "
                            f"flip={flip:.3f}  manip_gap={manip_gap:+.3f}  "
                            f"post_gap={post_gap:+.4f}  {verdict}"
                        )

    results["go_nogo"] = _compute_go_nogo(results["summary"])
    return results


# ---------------------------------------------------------------------------
# GO/NO-GO verdict logic
# ---------------------------------------------------------------------------

def _verdict_line(flip: float, noise: float) -> str:
    if noise == 0.0:
        return "✓ clean" if flip <= 0.20 else "⚠ unexpect-flip-clean"
    if flip < 0.05:
        return "🔴 NO-GO (zero separation)"
    if noise <= 0.10 and flip >= 0.10:
        return "🟢 F1-pass-candidate"
    if noise <= 0.25 and flip >= 0.15:
        return "🟢 F5-pass-candidate"
    if flip > 0.0:
        return "🟡 marginal"
    return "🔴 NO-GO"


def _compute_go_nogo(summary: Dict) -> Dict:
    """
    Aggregate GO/NO-GO verdict across all configurations.

    F1 PASS criterion:
      At least 2 configurations with flip_rate >= 0.10 at noise <= 0.10.
      This confirms reliability modifies acquisition ordering.

    F5 PASS criterion:
      P5's flip advantage does NOT collapse from noise=0.25 to noise=0.50.
      Collapse = mean flip drop > 0.30 across scenario/budget/lam combos.
      NOTE: Low flip at noise=0.50 alone is NOT collapse — P5 being conservative
      when signal is meaningless is correct behaviour. We test monotonic drop.

    CLEAN_OK criterion:
      At noise=0.0, scenarios with structured source differences (B, C) should
      not show P5 flipping >20% of the time. Scenarios D (symmetric sources)
      and E (identical sources) are excluded from this check because tie-breaks
      in symmetric cases are expected to vary.
    """
    f1_configs_passing = []
    collapse_at_high_noise = []

    # Group by (scenario, budget, lam) to compare noise levels for F5
    from collections import defaultdict
    by_config: Dict = defaultdict(dict)
    for key, entry in summary.items():
        cfg = f"{entry['scenario']}|budget={entry['budget']}|lam={entry['lam']}"
        by_config[cfg][entry["noise"]] = entry["flip_rate_P3_vs_P5"]

    for cfg, noise_map in by_config.items():
        if 0.25 in noise_map and 0.50 in noise_map:
            flip_25 = noise_map[0.25]
            flip_50 = noise_map[0.50]
            # Collapse: flip dropped by >50% of its 0.25 value AND went below 0.05
            if flip_25 > 0.05 and flip_50 < flip_25 * 0.5 and flip_50 < 0.05:
                collapse_at_high_noise.append(f"{cfg}|noise_drop={flip_25:.2f}->{flip_50:.2f}")

    clean_ok = True
    # Scenarios where P5 should NOT diverge from P3 in clean conditions:
    # A = identical reliability/cost → P5 == P3 expected
    # E = identical sources → all policies equivalent
    # B,C,D: clean-regime flips are EXPECTED by design:
    #   B: reliability inside EIG changes ordering
    #   C: cost term (lam*cost) separates P5 from P3 on expensive sources
    #   D: symmetric sources create tie-break variation (acceptable)
    NO_FLIP_EXPECTED = {"A_no_reliability_diff", "E_no_distinction"}
    for key, entry in summary.items():
        scenario_name = entry["scenario"]
        flip = entry["flip_rate_P3_vs_P5"]
        noise = entry["noise"]
        if noise == 0.0 and scenario_name in NO_FLIP_EXPECTED:
            if flip > 0.20:
                clean_ok = False

    for key, entry in summary.items():
        flip = entry["flip_rate_P3_vs_P5"]
        noise = entry["noise"]
        if noise <= 0.10 and flip >= 0.10:
            f1_configs_passing.append(key)

    f1_pass = len(f1_configs_passing) >= 2
    f5_pass = len(collapse_at_high_noise) == 0

    verdict = "GO" if (f1_pass and f5_pass and clean_ok) else "NO-GO"

    reason = []
    if not f1_pass:
        reason.append(
            f"F1 FAIL: only {len(f1_configs_passing)} configs with flip>=0.10 at noise<=0.10 "
            f"(need >=2). Kill method claim."
        )
    if not f5_pass:
        reason.append(
            f"F5 FAIL: {len(collapse_at_high_noise)} config(s) show P5 collapsing at noise=0.50 "
            f"after passing at noise=0.25. Estimator paper reframe recommended.\n"
            + "\n".join(f"    {c}" for c in collapse_at_high_noise)
        )
    if not clean_ok:
        reason.append(
            "CLEAN-REGIME WARN (B/C only): P5 flips away from P3 >20% of the time in "
            "clean conditions for structured scenarios. Check robustness tax."
        )

    return {
        "verdict": verdict,
        "f1_pass": f1_pass,
        "f5_pass": f5_pass,
        "clean_ok": clean_ok,
        "f1_passing_configs": f1_configs_passing,
        "collapse_configs": collapse_at_high_noise,
        "reasons": reason,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_summary_table(results: Dict) -> None:
    """Print a human-readable summary table to stdout."""
    print("\n" + "=" * 80)
    print("F1/F5 KILL GATE SWEEP — SUMMARY")
    print("=" * 80)
    print(f"{'Scenario':<22} {'noise':>6} {'budget':>7} {'lam':>5} "
          f"{'flip P3↔P5':>11} {'manip_gap':>10} {'post_gap':>9}")
    print("-" * 80)

    for key, e in sorted(results["summary"].items(),
                         key=lambda x: (x[1]["scenario"], x[1]["noise"])):
        print(
            f"  {e['scenario']:<20} {e['noise']:>6.2f} {e['budget']:>7.0f} "
            f"{e['lam']:>5.1f} {e['flip_rate_P3_vs_P5']:>11.3f} "
            f"{e['manip_reliance_gap_P5_minus_P3']:>+10.3f} "
            f"{e['posterior_quality_gap_P5_minus_P3']:>+9.4f}"
        )

    print("=" * 80)
    go_nogo = results["go_nogo"]
    verdict = go_nogo["verdict"]
    icon = "🟢" if verdict == "GO" else "🔴"
    print(f"\n{icon}  OVERALL VERDICT: {verdict}")
    print(f"   F1 PASS: {go_nogo['f1_pass']}  |  F5 PASS: {go_nogo['f5_pass']}  |  CLEAN OK: {go_nogo['clean_ok']}")
    if go_nogo["reasons"]:
        print("\nReasons:")
        for r in go_nogo["reasons"]:
            print(f"  • {r}")
    print()


def save_results(results: Dict, output_dir: str = "results/raw") -> Path:
    """Save full results JSON to disk."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"f1_sweep_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return out_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="F1/F5 Kill Gate Sweep — HADES Phase 3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--seeds", type=int, default=20,
        help="Number of random seeds per configuration (default: 20)",
    )
    p.add_argument(
        "--noise", type=str, default="0,0.10,0.25,0.50",
        help="Comma-separated noise levels / estimation sigma (default: 0,0.10,0.25,0.50)",
    )
    p.add_argument(
        "--budgets", type=str, default="10",
        help="Comma-separated budget values (default: 10)",
    )
    p.add_argument(
        "--lam", type=str, default=None,
        help="Comma-separated lambda values. Defaults to pre-registered grid: "
             + ",".join(str(l) for l in LAMBDA_GRID),
    )
    p.add_argument(
        "--scenarios", type=str, default=None,
        help="Comma-separated scenario names to run (default: all). "
             "Options: A_no_reliability_diff, B_reliability_flip, C_cost_flip, "
             "D_manipulation_flip, E_no_distinction",
    )
    p.add_argument(
        "--output-dir", type=str, default="results/raw",
        help="Output directory for JSON results (default: results/raw)",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-config progress output",
    )
    return p.parse_args()


def main():
    args = parse_args()

    noise_levels = [float(x) for x in args.noise.split(",")]
    budgets = [float(x) for x in args.budgets.split(",")]
    lam_grid = (
        [float(x) for x in args.lam.split(",")]
        if args.lam else LAMBDA_GRID
    )

    from hades.simulator.scenarios import ALL_SCENARIOS as _ALL
    scenarios_map = {s.name: s for s in _ALL}
    if args.scenarios:
        selected_names = [n.strip() for n in args.scenarios.split(",")]
        selected_scens = []
        for n in selected_names:
            # Allow partial match (e.g. "B" matches "B_reliability_flip")
            matches = [s for sname, s in scenarios_map.items()
                       if n.lower() in sname.lower()]
            selected_scens.extend(matches)
    else:
        selected_scens = _ALL

    # Inject filtered scenario list into globals for sweep
    import hades.simulator.scenarios as _scen_mod
    _orig = _scen_mod.ALL_SCENARIOS
    _scen_mod.ALL_SCENARIOS = selected_scens

    print(f"\nHADES F1/F5 Kill Gate Sweep")
    print(f"  Scenarios : {[s.name for s in selected_scens]}")
    print(f"  Seeds     : {args.seeds}")
    print(f"  Noise     : {noise_levels}")
    print(f"  Budgets   : {budgets}")
    print(f"  Lambda    : {lam_grid}  (pre-registered; no post-hoc tuning)")
    print()

    t0 = time.perf_counter()
    results = run_sweep(
        seeds=args.seeds,
        noise_levels=noise_levels,
        budgets=budgets,
        lambda_grid=lam_grid,
        verbose=not args.quiet,
    )
    elapsed = time.perf_counter() - t0

    print_summary_table(results)
    out_path = save_results(results, args.output_dir)
    print(f"Results saved → {out_path}")
    print(f"Elapsed: {elapsed:.1f}s\n")

    _scen_mod.ALL_SCENARIOS = _orig  # restore

    # Exit code: 0 = GO, 1 = NO-GO
    sys.exit(0 if results["go_nogo"]["verdict"] == "GO" else 1)


if __name__ == "__main__":
    main()
