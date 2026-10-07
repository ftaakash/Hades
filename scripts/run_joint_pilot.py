"""
scripts/run_joint_pilot.py
--------------------------
Phase 7U runner for phase7u_joint_belief_v1 (docs/phase7u_joint_belief_protocol.md).

  calibration  blinded power calibration (outputs only spreads and comparator means) -> seed manifest
  pilot        the pre-registered pilot; refuses a dirty tree, a changed config, or an existing raw file

Usage:  py scripts/run_joint_pilot.py calibration | pilot [--workers 4]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_probe_pilot import METRICS, git_state  # noqa: E402
from hades.probe_experiment import SIMULATOR_VERSION  # noqa: E402
from hades.probe_experiment.attacker import ATTACKER_VERSION  # noqa: E402
from hades.probe_experiment.belief import action_space  # noqa: E402
from hades.probe_experiment.policies import POLICY_VERSION  # noqa: E402
from hades.probe_experiment.joint_confirm import (  # noqa: E402
    CANDIDATE, COMPARATORS, JOINT_CONFIRM_VERSION, make_joint_policies,
)
from hades.probe_experiment.joint_eval import PRIMARY_CELLS, required_worlds  # noqa: E402
from hades.probe_experiment.robust import ROBUST_VERSION  # noqa: E402
from hades.probe_experiment.simulator import Condition, run_episode  # noqa: E402
from hades.probe_experiment.world import WorldDistribution, distribution_as_dict, generate_world  # noqa: E402

CONFIG = ROOT / "configs" / "experiments" / "phase7u_joint_belief_v1.json"
RAW = ROOT / "results" / "raw"


def load_config():
    text = CONFIG.read_bytes()
    cfg = json.loads(text)
    if cfg["world_distribution"] != distribution_as_dict(WorldDistribution()):
        raise SystemExit("config world_distribution differs from code defaults; refusing to run")
    return cfg, hashlib.sha256(text).hexdigest()


def run_world(args):
    world_seed, conditions, n_ep, policy_names = args
    model = generate_world(world_seed)
    acts = action_space(model)
    pols = make_joint_policies()
    out = {}
    for cname, c in conditions.items():
        cond = Condition(cname, c["family"], c["budget"])
        out[cname] = {}
        for pname in policy_names:
            pol = pols[pname]
            agg = {m: 0.0 for m in METRICS}
            agg.update(n=0, correct=0, spend_min=1e9, spend_max=-1e9)
            for e in range(n_ep):
                r = run_episode(pol, model, cond, world_seed, e, actions=acts)
                for m in METRICS:
                    agg[m] += getattr(r, m)
                agg["n"] += 1
                agg["correct"] += int(r.regret == 0)
                agg["spend_min"] = min(agg["spend_min"], r.spend)
                agg["spend_max"] = max(agg["spend_max"], r.spend)
            out[cname][pname] = agg
    return world_seed, out, model.params, float(model.budget)


def sweep(seeds, conditions, n_ep, policies, workers):
    jobs = [(s, conditions, n_ep, policies) for s in seeds]
    res, t0 = {}, time.time()
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
            "policy_version": POLICY_VERSION, "robust_version": ROBUST_VERSION, "joint_confirm_version": JOINT_CONFIRM_VERSION,
            "python": platform.python_version(), "numpy": np.__version__,
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def world_mean(out, policy, cells):
    return sum(out[c][policy]["norm_regret"] for c in cells) / sum(out[c][policy]["n"] for c in cells)


def calibration(cfg, sha, workers):
    manifest = RAW / f"{cfg['experiment_id']}_seed_manifest.json"
    if manifest.exists():
        raise SystemExit(f"{manifest} exists; never overwrite")
    prov = provenance(cfg, sha)
    if prov["git_dirty"]:
        raise SystemExit("working tree dirty; commit the frozen protocol first")
    lo, hi = cfg["power"]["calibration_world_seeds"]
    conds = {c: cfg["conditions"][c] for c in PRIMARY_CELLS}
    res = sweep(range(lo, hi), conds, cfg["episodes_per_world_condition"], [CANDIDATE, *COMPARATORS], workers)
    pairs = {}
    for c in (CANDIDATE,):
        for x in COMPARATORS:
            yc = np.array([world_mean(res[s][0], c, conds) for s in sorted(res)])
            yx = np.array([world_mean(res[s][0], x, conds) for s in sorted(res)])
            pairs[f"{c}_vs_{x}"] = {"sd_d": float((yx - yc).std(ddof=1)), "mean_comparator": float(yx.mean())}
    pw = cfg["power"]
    n = required_worlds(pairs, cfg["practical_threshold_rrr"], pw["inflation"], pw["n_min"], pw["n_max"])
    start = cfg["pilot_world_seed_start"]
    out = {**prov, "blinded": True, "calibration_worlds": [lo, hi], "pairs": pairs, **n,
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
