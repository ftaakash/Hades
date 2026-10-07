"""
scripts/analyze_joint_pilot.py
------------------------------
Applies the frozen 7U gates (docs/phase7u_joint_belief_gates.md) to the pilot raw output.

Usage:  py scripts/analyze_joint_pilot.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hades.probe_experiment.joint_eval import evaluate_joint_gates  # noqa: E402

EXP = "phase7u_joint_belief_v1"
RAW = ROOT / "results" / "raw" / f"{EXP}.json"
STATS = ROOT / "results" / "analysis" / f"{EXP}_statistics.json"
VERDICT = ROOT / "results" / f"{EXP}_verdict.json"


def main():
    if VERDICT.exists():
        raise SystemExit(f"{VERDICT} exists; a verdict is never overwritten")
    data = json.loads(RAW.read_text())
    agg = data["aggregates"]
    spend_ok = all(abs(r["spend_min"] - data["budget"][w]) < 1e-9 and abs(r["spend_max"] - data["budget"][w]) < 1e-9
                   for w in agg for c in agg[w] for r in agg[w][c].values())
    leak = subprocess.run([sys.executable, "-m", "pytest", "tests/test_joint_belief.py", "tests/test_robust_acquisition.py",
                           "tests/test_probe_experiment.py", "-q", "-k", "leak"],
                          cwd=ROOT, capture_output=True, text=True)
    g = evaluate_joint_gates(agg, spend_ok, leak.returncode == 0)
    g["provenance"] = {k: data[k] for k in ("experiment_id", "git_commit", "git_dirty", "config_sha256",
                                             "simulator_version", "attacker_version", "policy_version", "robust_version", "joint_confirm_version")}
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(g, indent=2, default=float))
    summary = {"experiment_id": EXP, "verdict": g["verdict"],
               **{k: g[k]["pass"] for k in ("V-1", "JG-1", "JG-2", "JG-3", "JG-4", "JG-5", "JG-6")},
               "rrr": {x: {k: v[k] for k in ("rrr", "ci_lower", "ci_upper")} for x, v in g["contrasts"].items()},
               "provenance": g["provenance"]}
    VERDICT.write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
