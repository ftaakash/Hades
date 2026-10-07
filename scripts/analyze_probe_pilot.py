"""
scripts/analyze_probe_pilot.py
------------------------------
Applies the frozen gates (docs/hades2_kill_gates.md) to the phase7l_probe_pilot_v2 raw
output. Gate logic lives in hades/probe_experiment/evaluation.py and was committed with
the protocol, before the pilot ran.

Usage:  py scripts/analyze_probe_pilot.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hades.probe_experiment.evaluation import evaluate_gates  # noqa: E402

EXP = "phase7l_probe_pilot_v2"
RAW = ROOT / "results" / "raw" / f"{EXP}.json"
STATS = ROOT / "results" / "analysis" / f"{EXP}_statistics.json"
VERDICT = ROOT / "results" / f"{EXP}_verdict.json"


def main():
    if VERDICT.exists():
        raise SystemExit(f"{VERDICT} exists; a verdict is never overwritten")
    data = json.loads(RAW.read_text())
    agg = data["aggregates"]
    spend_ok = all(
        abs(r["spend_min"] - data["budget"][w]) < 1e-9 and abs(r["spend_max"] - data["budget"][w]) < 1e-9
        for w in agg for c in agg[w] for r in agg[w][c].values()
    )
    leak = subprocess.run([sys.executable, "-m", "pytest", "tests/test_probe_experiment.py", "-q", "-k", "leak"],
                          cwd=ROOT, capture_output=True, text=True)
    gates = evaluate_gates(agg, data["world_params"], spend_ok, leak.returncode == 0)
    fallback = {}
    for p in ("P_PROBE", "P_PROBE_NO_S", "P_PROBE_NO_PROBE"):
        steps = sum(agg[w][c][p]["steps"] for w in agg for c in agg[w])
        fb = sum(agg[w][c][p]["fallback_steps"] for w in agg for c in agg[w])
        fallback[p] = fb / steps if steps else 0.0
    gates["fallback_rate"] = fallback
    gates["provenance"] = {k: data[k] for k in ("experiment_id", "git_commit", "git_dirty", "config_sha256",
                                                 "simulator_version", "attacker_version", "policy_version")}
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(gates, indent=2, default=float))
    summary = {"experiment_id": EXP, "verdict": gates["verdict"], "failed_decisive": gates["failed_decisive"],
               "gates": {k: v["pass"] for k, v in gates.items() if isinstance(v, dict) and "pass" in v},
               "primary_rrr": gates["PF-1"]["rrr"], "primary_ci95": gates["PF-1"]["ci95"],
               "provenance": gates["provenance"]}
    VERDICT.write_text(json.dumps(summary, indent=2, default=float))
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
