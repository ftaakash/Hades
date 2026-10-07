"""
scripts/analyze_hai_replication.py
----------------------------------
Applies the frozen 7V gates (docs/phase7v_hai_replication_gates.md) to the replication raw output.
The verdict comes from the primary version only; the secondary version is reported with the same code.

Usage:  py scripts/analyze_hai_replication.py
"""
from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hades.probe_experiment.hai_eval import (  # noqa: E402
    PRIMARY_VERSION, SECONDARY_VERSION, evaluate_hai_gates, per_episode_arrays, prior_only_regret,
)
from hades.probe_experiment.joint_confirm import JOINT_POLICY_NAMES  # noqa: E402

EXP = "phase7v_hai_replication_v1"
RAW = ROOT / "results" / "raw" / f"{EXP}.json.gz"
STATS = ROOT / "results" / "analysis" / f"{EXP}_statistics.json"
VERDICT = ROOT / "results" / f"{EXP}_verdict.json"


def evaluate(data, version, leakage_ok):
    rows = data["versions"][version]["results"]
    budget = data["model"]["budget"]
    spend_ok = all(abs(s - budget) < 1e-9 for r in rows for s in r["spend"].values())
    h = np.array([r["h_true"] for r in rows])
    ncomp = np.array([len(r["compromised"]) for r in rows])
    prior = prior_only_regret(np.array(data["model"]["utility"]), np.array(data["model"]["prior_h"]), h)
    g = evaluate_hai_gates(per_episode_arrays(rows, JOINT_POLICY_NAMES), h, ncomp, prior, spend_ok, leakage_ok)
    g["probes_per_episode"] = {p: float(np.mean([r["n_probes"][p] for r in rows])) for p in JOINT_POLICY_NAMES}
    return g


def main():
    if VERDICT.exists():
        raise SystemExit(f"{VERDICT} exists; a verdict is never overwritten")
    with gzip.open(RAW, "rt") as fh:
        data = json.load(fh)
    leak = subprocess.run([sys.executable, "-m", "pytest", "tests/test_hai_replication.py", "tests/test_joint_belief.py",
                           "-q", "-k", "leak"], cwd=ROOT, capture_output=True, text=True)
    stats = {v: evaluate(data, v, leak.returncode == 0) for v in (PRIMARY_VERSION, SECONDARY_VERSION)}
    prov = {k: data[k] for k in ("experiment_id", "git_commit", "git_dirty", "config_sha256", "hai_version",
                                 "hai_model_version", "joint_confirm_version", "dev_episodes_sha256")}
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps({"provenance": prov, **stats}, indent=2, default=float))
    g = stats[PRIMARY_VERSION]
    summary = {"experiment_id": EXP, "verdict": g["verdict"], "primary_version": PRIMARY_VERSION,
               **{k: g[k]["pass"] for k in ("V-1", "HG-1", "HG-2", "HG-3", "HG-4", "HG-5", "HG-6")},
               "rrr": {x: {k: v[k] for k in ("rrr", "ci_lower", "ci_upper")} for x, v in g["contrasts"].items()},
               "secondary": {"version": SECONDARY_VERSION, "verdict_if_primary": stats[SECONDARY_VERSION]["verdict"],
                             "rrr": {x: {k: v[k] for k in ("rrr", "ci_lower", "ci_upper")}
                                     for x, v in stats[SECONDARY_VERSION]["contrasts"].items()}},
               "provenance": prov}
    VERDICT.write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
