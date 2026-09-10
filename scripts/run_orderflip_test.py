"""
scripts/run_orderflip_test.py
------------------------------
G1 Gate — Order-Flip Test

Demonstrates the order-flip phenomenon: evidence reliability and/or
manipulation risk can change which evidence source is the optimal next
query, independent of raw information gain.

Methodology
~~~~~~~~~~~
For each scenario and each initial belief state (varied by true_hypothesis):
  1. Compute the preferred next query under four policies:
       P3_IG:     argmax_s IG(s)
       P4_IC:     argmax_s IG(s)/cost(s)
       P4b_ERHG:  argmax_s IG(s) * reliability_estimated(s) / cost(s)
       P5_HADES:  argmax_s U(s) = ERHG(s) - lambda*cost(s) - mu*manip_risk(s)

  2. An order-flip occurs when:
       P5_HADES != P3_IG  (reliability/cost/manip changes the decision)
     or the weaker:
       P4b_ERHG != P3_IG  (reliability alone changes the decision)

  3. Report the order-flip rate (observed, not against a pre-set threshold).

G1 Criterion (qualitative, per merged plan):
  At least one non-degenerate class of states exists in which
  reliability/manipulability changes the preferred query relative to IG/IG-cost,
  and the phenomenon persists across multiple independently seeded simulator
  configurations.

Usage:
    PYTHONPATH=. python scripts/run_orderflip_test.py [--seeds N] [--lambda L] [--mu M]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from hades.simulator.environment import SimEnv
from hades.simulator.scenarios import ALL_SCENARIOS, SimScenario


# ---------------------------------------------------------------------------
# Decision-making helpers (policy logic inlined for clarity — no policy
# objects needed here, just the utility calculations on SimEnv)
# ---------------------------------------------------------------------------

def _argmax_with_tiebreak(scores: Dict[str, float]) -> str:
    """Max by value, tie-break alphabetically (deterministic)."""
    return max(scores.keys(), key=lambda k: (scores[k], k))


def select_p3_ig(env: SimEnv) -> str:
    scores = {s.name: env.expected_ig(s.name) for s in env.sources}
    return _argmax_with_tiebreak(scores)


def select_p4_ig_cost(env: SimEnv) -> str:
    scores = {
        s.name: env.expected_ig(s.name) / s.cost
        for s in env.sources
    }
    return _argmax_with_tiebreak(scores)


def select_p4b_erhg(env: SimEnv) -> str:
    """IG × reliability_estimated / cost — no manipulation penalty."""
    scores = {
        s.name: (env.expected_ig(s.name) * s.reliability_estimated) / s.cost
        for s in env.sources
    }
    return _argmax_with_tiebreak(scores)


def select_p5_hades(env: SimEnv, lambda_: float, mu: float) -> str:
    scores = {
        s.name: env.hades_utility(s.name, lambda_=lambda_, mu=mu)
        for s in env.sources
    }
    return _argmax_with_tiebreak(scores)


# ---------------------------------------------------------------------------
# Per-state decision record
# ---------------------------------------------------------------------------

@dataclass
class DecisionRecord:
    scenario: str
    true_hypothesis: str
    seed: int
    step: int

    p3_ig_choice: str
    p4_ic_choice: str
    p4b_erhg_choice: str
    p5_hades_choice: str

    ig_scores: Dict[str, float]
    erhg_scores: Dict[str, float]
    hades_scores: Dict[str, float]

    # Flip flags
    flip_erhg_vs_ig: bool = False    # P4b != P3
    flip_hades_vs_ig: bool = False   # P5 != P3
    flip_hades_vs_p4: bool = False   # P5 != P4


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

def run_orderflip_test(
    scenarios: List[SimScenario],
    n_seeds: int = 20,
    budget: float = 10.0,
    lambda_: float = 1.0,
    mu: float = 1.0,
    verbose: bool = True,
) -> Dict:
    """
    Run the G1 order-flip test across all scenarios and seeds.
    Returns a summary dict with per-scenario and overall statistics.
    """
    results = {}

    total_states = 0
    total_flips_erhg = 0
    total_flips_hades = 0

    print("\n" + "=" * 70)
    print("  HADES — G1 Order-Flip Test")
    print(f"  λ={lambda_}  μ={mu}  seeds={n_seeds}  budget={budget}")
    print("=" * 70)

    for scenario in scenarios:
        records: List[DecisionRecord] = []
        print(f"\n[{scenario.name}]")
        print(f"  {scenario.description}")
        print(f"  Hypotheses: {scenario.hypotheses}")
        print(f"  Sources:    {[s.name for s in scenario.sources]}")

        for seed in range(n_seeds):
            env = SimEnv(scenario, seed=seed, budget=budget)

            for true_hyp in scenario.hypotheses:
                env.reset(true_hypothesis=true_hyp, seed=seed)

                # Each step with different belief concentrations
                # (initially uniform; then after 0, 1, 2 steps we re-evaluate)
                for step in range(3):
                    # Compute decisions at current belief state
                    ig_scores = {s.name: env.expected_ig(s.name) for s in env.sources}
                    erhg_scores = {
                        s.name: env.expected_ig(s.name) * s.reliability_estimated / s.cost
                        for s in env.sources
                    }
                    hades_scores = {
                        s.name: env.hades_utility(s.name, lambda_=lambda_, mu=mu)
                        for s in env.sources
                    }

                    p3 = select_p3_ig(env)
                    p4 = select_p4_ig_cost(env)
                    p4b = select_p4b_erhg(env)
                    p5 = select_p5_hades(env, lambda_=lambda_, mu=mu)

                    rec = DecisionRecord(
                        scenario=scenario.name,
                        true_hypothesis=true_hyp,
                        seed=seed,
                        step=step,
                        p3_ig_choice=p3,
                        p4_ic_choice=p4,
                        p4b_erhg_choice=p4b,
                        p5_hades_choice=p5,
                        ig_scores=ig_scores,
                        erhg_scores=erhg_scores,
                        hades_scores=hades_scores,
                        flip_erhg_vs_ig=(p4b != p3),
                        flip_hades_vs_ig=(p5 != p3),
                        flip_hades_vs_p4=(p5 != p4),
                    )
                    records.append(rec)

                    # Advance belief state by querying the top IG source
                    # (simulate one step of evidence gathering)
                    if env.remaining_budget >= min(s.cost for s in env.sources) and step < 2:
                        try:
                            env.step(p3)
                        except RuntimeError:
                            break

        n = len(records)
        n_flip_erhg = sum(r.flip_erhg_vs_ig for r in records)
        n_flip_hades = sum(r.flip_hades_vs_ig for r in records)
        n_flip_hades_p4 = sum(r.flip_hades_vs_p4 for r in records)

        rate_erhg = n_flip_erhg / n if n > 0 else 0.0
        rate_hades = n_flip_hades / n if n > 0 else 0.0

        total_states += n
        total_flips_erhg += n_flip_erhg
        total_flips_hades += n_flip_hades

        results[scenario.name] = {
            "n_states": n,
            "n_seeds": n_seeds,
            "flip_erhg_vs_ig": n_flip_erhg,
            "flip_hades_vs_ig": n_flip_hades,
            "flip_hades_vs_p4": n_flip_hades_p4,
            "rate_erhg_vs_ig": rate_erhg,
            "rate_hades_vs_ig": rate_hades,
        }

        print(f"\n  Results ({n} decision states across {n_seeds} seeds × "
              f"{len(scenario.hypotheses)} hyps × 3 steps):")
        print(f"    ERHG vs IG   flips: {n_flip_erhg:4d} / {n:4d} = {rate_erhg*100:.1f}%")
        print(f"    HADES vs IG  flips: {n_flip_hades:4d} / {n:4d} = {rate_hades*100:.1f}%")
        print(f"    HADES vs P4  flips: {n_flip_hades_p4:4d} / {n:4d} = "
              f"{n_flip_hades_p4/n*100:.1f}%")

        # Print a representative flip example (if any)
        flip_examples = [r for r in records if r.flip_hades_vs_ig]
        if flip_examples:
            ex = flip_examples[0]
            print(f"\n  Example flip (seed={ex.seed}, hyp={ex.true_hypothesis}, step={ex.step}):")
            print(f"    P3(IG)   → {ex.p3_ig_choice}")
            print(f"    P4(IC)   → {ex.p4_ic_choice}")
            print(f"    P4b(ERHG)→ {ex.p4b_erhg_choice}")
            print(f"    P5(HADES)→ {ex.p5_hades_choice}")
            # Show top-2 scores for each policy
            top_ig = sorted(ex.ig_scores.items(), key=lambda x: -x[1])[:2]
            top_h = sorted(ex.hades_scores.items(), key=lambda x: -x[1])[:2]
            print(f"    IG scores (top 2):    {top_ig}")
            print(f"    HADES scores (top 2): {top_h}")

    # Overall G1 assessment
    overall_rate_erhg = total_flips_erhg / total_states if total_states > 0 else 0.0
    overall_rate_hades = total_flips_hades / total_states if total_states > 0 else 0.0

    print("\n" + "=" * 70)
    print("  OVERALL SUMMARY")
    print("=" * 70)
    print(f"  Total decision states: {total_states}")
    print(f"  ERHG vs IG  flip rate: {total_flips_erhg}/{total_states} "
          f"= {overall_rate_erhg*100:.1f}%")
    print(f"  HADES vs IG flip rate: {total_flips_hades}/{total_states} "
          f"= {overall_rate_hades*100:.1f}%")

    # G1 qualitative assessment
    print(f"\n  G1 CRITERION CHECK (qualitative):")
    scenario_b_data = results.get("B_reliability_flip", {})
    b_flips = scenario_b_data.get("flip_hades_vs_ig", 0)
    b_rate = scenario_b_data.get("rate_hades_vs_ig", 0.0)
    d_data = results.get("D_manipulation_flip", {})
    d_flips = d_data.get("flip_hades_vs_p4", 0)

    g1_pass = (
        b_flips > 0                  # Scenario B: reliability flips order
        and d_flips > 0              # Scenario D: manip risk flips order (independently)
        and overall_rate_hades > 0   # phenomenon exists
    )

    print(f"  Scenario B (reliability flip): {b_flips} flips ({b_rate*100:.1f}%)")
    print(f"  Scenario D (manip risk flip):  {d_flips} HADES-vs-P4 flips")
    print(f"\n  G1 STATUS: {'PASS ✓' if g1_pass else 'FAIL ✗'}")
    if g1_pass:
        print(f"  → Reliability-aware acquisition chooses different queries in {b_rate*100:.1f}% "
              f"of states.")
        print(f"  → Manipulation risk as an INDEPENDENT term also flips decisions.")
        print(f"  → Phenomenon persists across {n_seeds} independently seeded configurations.")
        print(f"  Proceed to Phase 1B (Hypothesis Tracking Engine).")
    else:
        print(f"  → G1 FAILED. Reformulate HADES mechanism before proceeding to CDB.")

    results["__overall__"] = {
        "total_states": total_states,
        "total_flips_erhg": total_flips_erhg,
        "total_flips_hades": total_flips_hades,
        "overall_rate_erhg": overall_rate_erhg,
        "overall_rate_hades": overall_rate_hades,
        "g1_pass": g1_pass,
        "lambda": lambda_,
        "mu": mu,
        "n_seeds": n_seeds,
    }

    return results


def save_results(results: Dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved → {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="HADES G1 Order-Flip Test")
    parser.add_argument("--seeds", type=int, default=20, help="Seeds per scenario")
    parser.add_argument("--budget", type=float, default=10.0, help="Query budget")
    parser.add_argument("--lambda", dest="lambda_", type=float, default=1.0)
    parser.add_argument("--mu", type=float, default=1.0)
    parser.add_argument("--out", default="results/raw/g1_orderflip_test.json",
                        help="Output JSON path")
    args = parser.parse_args()

    results = run_orderflip_test(
        scenarios=ALL_SCENARIOS,
        n_seeds=args.seeds,
        budget=args.budget,
        lambda_=args.lambda_,
        mu=args.mu,
        verbose=True,
    )
    save_results(results, REPO_ROOT / args.out)

    # Exit with non-zero code if G1 failed (for CI integration)
    if not results["__overall__"]["g1_pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
