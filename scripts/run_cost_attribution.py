"""scripts/run_cost_attribution.py -- Phase 7C-A cost-matched attribution runner.

Protocol: docs/phase7c_cost_attribution_protocol.md (preregistered).
Writes RAW results only. Analysis is in scripts/analyze_cost_attribution.py.

USAGE
-----
  py scripts/run_cost_attribution.py --mode pilot     # seeds 1000-1024, sigma {0.10, 0.30}
  py scripts/run_cost_attribution.py --mode main      # seeds 0-99, sigma {0.10, 0.20, 0.30}
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
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
from hades.reliability.estimator import NoisyEstimator
from hades.integration.runner import IntegrationRunner
from hades.evaluation.metrics import extract_metrics
from hades.policies.p3_ig import IGPolicy
from hades.policies.p3_cost import NominalIGPolicy, NominalIGCostPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy
from scripts.run_mechanism_ablation import P5NoPhi

# ---- Frozen matrix (see protocol section 4) --------------------------------
MODES = {
    "pilot": {"experiment_id": "phase7c_cost_attribution_pilot",
              "sigma": [0.10, 0.30], "seeds": list(range(1000, 1025))},
    "main":  {"experiment_id": "phase7c_cost_attribution_main",
              "sigma": [0.10, 0.20, 0.30], "seeds": list(range(0, 100))},
}
SCENARIO_TAGS = ["B_", "C_", "D_"]
SCENARIOS = [s for s in ALL_SCENARIOS if any(s.name.startswith(t) for t in SCENARIO_TAGS)]
REGIMES = [
    ("R1_missing",    MissingCorruptor(p_drop=0.25)),
    ("R2_stale",      StaleCorruptor(staleness=0.33)),
    ("R3_misleading", MisleadingCorruptor(p_inject=0.25)),
    ("R4a_targeted",  TargetedCorruptor(p_attack=0.75)),
]
LAMBDA_GRID = [0.5, 1.0, 2.0]
BUDGET = 10.0
ARMS = ["P3_nom", "P3_nom_cost", "P3_rhat", "P5_no_phi", "P5_full"]


def make_arms(lam: float) -> Dict:
    return {
        "P3_nom":      NominalIGPolicy(),
        "P3_nom_cost": NominalIGCostPolicy(lam=lam),
        "P3_rhat":     IGPolicy(),
        "P5_no_phi":   P5NoPhi(lam=lam),
        "P5_full":     RobustVoIPolicy(lam=lam, use_robust=False),
    }


def _policy_fingerprint() -> Dict[str, str]:
    """SHA-256 of each arm's class source, to freeze the policy definitions."""
    out = {}
    for name, pol in make_arms(1.0).items():
        src = inspect.getsource(type(pol))
        out[name] = hashlib.sha256(src.encode()).hexdigest()[:16]
    return out


def run_cell(scenario, corruptor, corr_label, estimator, est_label, lam, seed) -> List[Dict]:
    true_hyp = random.Random(seed ^ 0xCAFE).choice(scenario.hypotheses)
    rows = []
    for arm, policy in make_arms(lam).items():
        runner = IntegrationRunner(scenario=scenario, budget=BUDGET, seeds=1,
                                   corruptors=[corruptor], estimators=[estimator],
                                   policies=[policy], lam=lam)
        ep = runner.run_episode(policy=policy, corruptor=corruptor,
                                estimator=estimator, seed=seed, true_hyp=true_hyp)
        ep.policy_name = arm
        d = extract_metrics(ep, lam, corr_label, est_label).to_dict()
        d["sources_queried"] = list(ep.sources_queried)
        rows.append(d)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=list(MODES), required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    cfg = MODES[a.mode]

    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                         cwd=str(Path(__file__).parent.parent),
                                         stderr=subprocess.DEVNULL).decode().strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--", "hades", "scripts"],
                                             cwd=str(Path(__file__).parent.parent)).decode().strip())
    except Exception:
        commit, dirty = "unknown", True

    episodes: List[Dict] = []
    t0 = time.perf_counter()
    for sigma in cfg["sigma"]:
        est, est_label = NoisyEstimator(sigma=sigma), f"noisy_sigma{sigma}"
        for sc in SCENARIOS:
            for corr_label, corr in REGIMES:
                for lam in LAMBDA_GRID:
                    for seed in cfg["seeds"]:
                        for d in run_cell(sc, corr, corr_label, est, est_label, lam, seed):
                            d["sigma"] = sigma
                            episodes.append(d)
            print(f"  sigma={sigma} {sc.name} done ({time.perf_counter() - t0:.1f}s)", flush=True)

    out = {
        "meta": {
            "experiment_id": cfg["experiment_id"],
            "mode": a.mode,
            "protocol": "docs/phase7c_cost_attribution_protocol.md",
            "hades_commit": commit,
            "working_tree_dirty_code": dirty,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "scenarios": [s.name for s in SCENARIOS],
            "sigma_grid": cfg["sigma"],
            "regimes": [{"label": l, "repr": repr(c)} for l, c in REGIMES],
            "lambda_grid": LAMBDA_GRID,
            "seeds": cfg["seeds"],
            "budget": BUDGET,
            "arms": ARMS,
            "policy_source_sha256_16": _policy_fingerprint(),
            "pairing": "true_hyp=Random(seed^0xCAFE); env seed; corruptor seed^0xBEEF; estimator seed^0xDEAD",
            "n_episodes": len(episodes),
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
        },
        "episodes": episodes,
    }
    path = Path(a.out or f"results/raw/phase7c_cost_attribution_{a.mode}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing raw file {path}")
    path.write_text(json.dumps(out), encoding="utf-8")
    print(f"Raw saved -> {path}  ({len(episodes)} episodes, commit {commit[:7]}, dirty={dirty})")


if __name__ == "__main__":
    main()
