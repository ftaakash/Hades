"""
scripts/run_probe_pilot.py
--------------------------
Phase 7L runner for phase7l_probe_pilot_v2 (docs/phase7g_probe_value_falsification_protocol.md).

Two modes, in this order:

  calibration  Blinded power calibration (protocol §7.2). Runs P_PROBE and
               P_JOINT_EIG_COST on the calibration worlds only, computes the SD of the
               paired world-level difference and the comparator's mean regret, and writes
               the seed manifest with the required number of pilot worlds. The mean
               difference and the candidate's mean regret are never computed into output
               or printed.

  pilot        The pre-registered pilot. Refuses to run without the seed manifest, if the
               config hash changed, if the working tree is dirty, or if the raw output exists.

Usage:
  py scripts/run_probe_pilot.py calibration
  py scripts/run_probe_pilot.py pilot
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hades.probe_experiment import SIMULATOR_VERSION  # noqa: E402
from hades.probe_experiment.attacker import ATTACKER_VERSION  # noqa: E402
from hades.probe_experiment.belief import action_space  # noqa: E402
from hades.probe_experiment.evaluation import PRIMARY_CELLS, required_worlds  # noqa: E402
from hades.probe_experiment.policies import POLICY_VERSION, make_policies  # noqa: E402
from hades.probe_experiment.simulator import Condition, run_episode  # noqa: E402
from hades.probe_experiment.world import WorldDistribution, distribution_as_dict, generate_world  # noqa: E402

CONFIG = ROOT / "configs" / "experiments" / "phase7l_probe_pilot_v2.json"
RAW = ROOT / "results" / "raw"
METRICS = ("norm_regret", "regret", "n_queries", "n_probes", "n_probes_suspicious", "exposure", "n_forged",
           "n_compromised", "n_resolved", "n_false_flags", "spend")


def load_config():
    text = CONFIG.read_bytes()
    cfg = json.loads(text)
    if cfg["world_distribution"] != distribution_as_dict(WorldDistribution()):
        raise SystemExit("config world_distribution differs from code defaults; refusing to run")
    return cfg, hashlib.sha256(text).hexdigest()


def git_state():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--", "hades", "scripts", "configs", "docs"], cwd=ROOT, text=True).strip())
    except Exception:
        commit, dirty = "unknown", True
    return commit, dirty


def run_world(args):
    world_seed, conditions, n_ep, policy_names = args
    model = generate_world(world_seed)
    acts = action_space(model)
    out = {}
    pols = make_policies()
    for cname, c in conditions.items():
        cond = Condition(cname, c["family"], c["budget"])
        out[cname] = {}
        for pname in policy_names:
            pol = pols[pname]
            pol.steps = pol.fallback_steps = 0
            agg = {m: 0.0 for m in METRICS}
            agg.update(n=0, correct=0, episodes_probing_suspicious=0, spend_min=1e9, spend_max=-1e9)
            for e in range(n_ep):
                r = run_episode(pol, model, cond, world_seed, e, actions=acts)
                for m in METRICS:
                    agg[m] += getattr(r, m)
                agg["n"] += 1
                agg["correct"] += int(r.regret == 0)
                agg["episodes_probing_suspicious"] += int(r.n_probes_suspicious > 0)
                agg["spend_min"] = min(agg["spend_min"], r.spend)
                agg["spend_max"] = max(agg["spend_max"], r.spend)
            agg["steps"], agg["fallback_steps"] = pol.steps, pol.fallback_steps
            out[cname][pname] = agg
    return world_seed, out, model.params, float(model.budget)


def sweep(seeds, conditions, n_ep, policies, workers):
    jobs = [(s, conditions, n_ep, policies) for s in seeds]
    res = {}
    t0 = time.time()
    with Pool(workers) as pool:
        for i, (s, out, params, budget) in enumerate(pool.imap_unordered(run_world, jobs), 1):
            res[s] = (out, params, budget)
            if i % 10 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} worlds  {time.time() - t0:.0f}s", flush=True)
    return res


def provenance(cfg, sha):
    commit, dirty = git_state()
    return {"experiment_id": cfg["experiment_id"], "git_commit": commit, "git_dirty": dirty, "config_sha256": sha,
            "simulator_version": SIMULATOR_VERSION, "attacker_version": ATTACKER_VERSION,
            "policy_version": POLICY_VERSION, "python": platform.python_version(), "numpy": np.__version__,
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def calibration(cfg, sha, workers):
    manifest = RAW / f"{cfg['experiment_id']}_seed_manifest.json"
    if manifest.exists():
        raise SystemExit(f"{manifest} exists; calibration already done (never overwrite)")
    lo, hi = cfg["power"]["calibration_world_seeds"]
    conds = {c: cfg["conditions"][c] for c in PRIMARY_CELLS}
    P, J = cfg["primary_candidate"], cfg["primary_comparator"]
    res = sweep(range(lo, hi), conds, cfg["episodes_per_world_condition"], [P, J], workers)
    yP, yJ = [], []
    for s in sorted(res):
        out = res[s][0]
        yP.append(sum(out[c][P]["norm_regret"] for c in conds) / sum(out[c][P]["n"] for c in conds))
        yJ.append(sum(out[c][J]["norm_regret"] for c in conds) / sum(out[c][J]["n"] for c in conds))
    d = np.asarray(yJ) - np.asarray(yP)
    sd_d = float(d.std(ddof=1))                 # only the spread leaves this function
    mu_j = float(np.mean(yJ))
    pw = cfg["power"]
    n = required_worlds(sd_d, mu_j, cfg["practical_threshold_rrr"], pw["inflation"], pw["n_min"], pw["n_max"])
    start = cfg["pilot_world_seed_start"]
    out = {**provenance(cfg, sha), "blinded": True, "calibration_worlds": [lo, hi],
           "sd_world_diff": sd_d, "mean_regret_comparator": mu_j, **n,
           "pilot_world_seeds": [start, start + n["n_worlds"]]}
    RAW.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


def pilot(cfg, sha, workers):
    manifest = json.loads((RAW / f"{cfg['experiment_id']}_seed_manifest.json").read_text())
    if manifest["config_sha256"] != sha:
        raise SystemExit("config changed since calibration; new experiment ID required")
    prov = provenance(cfg, sha)
    if prov["git_dirty"]:
        raise SystemExit("working tree dirty; commit before running the pilot")
    raw = RAW / f"{cfg['experiment_id']}.json"
    if raw.exists():
        raise SystemExit(f"{raw} exists; never overwrite")
    lo, hi = manifest["pilot_world_seeds"]
    res = sweep(range(lo, hi), cfg["conditions"], cfg["episodes_per_world_condition"], cfg["policies"], workers)
    data = {**prov, "seed_manifest": manifest, "pilot_world_seeds": [lo, hi],
            "aggregates": {str(s): res[s][0] for s in sorted(res)},
            "world_params": {str(s): res[s][1] for s in sorted(res)},
            "budget": {str(s): res[s][2] for s in sorted(res)}}
    raw.write_text(json.dumps(data))
    print(f"raw -> {raw}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["calibration", "pilot"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    cfg, sha = load_config()
    {"calibration": calibration, "pilot": pilot}[a.mode](cfg, sha, a.workers)


if __name__ == "__main__":
    main()
