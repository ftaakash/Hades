"""
scripts/run_hai_replication.py
------------------------------
Phase 7V runner for phase7v_hai_replication_v1 (docs/phase7v_hai_replication_protocol.md).

  1. builds the development episodes (HAI 20.07) and fits the defender model on them only;
  2. builds the confirmatory episodes (HAI 21.03 primary, HAI 22.04 secondary) with detectors fit on each
     version's own attack-free train files;
  3. runs every 7U policy on every episode at equal spend and writes one raw file.

Refuses a dirty tree, a config that differs from the code, or an existing raw file.

Usage:  py scripts/run_hai_replication.py
"""
from __future__ import annotations

import gzip
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from run_probe_pilot import git_state  # noqa: E402
from hades.probe_experiment import hai  # noqa: E402
from hades.probe_experiment.belief import action_space  # noqa: E402
from hades.probe_experiment.hai_model import HAI_MODEL_VERSION, fit_model, run_hai_episode  # noqa: E402
from hades.probe_experiment.joint_confirm import JOINT_CONFIRM_VERSION, JOINT_POLICY_NAMES, make_joint_policies  # noqa: E402

CONFIG = ROOT / "configs" / "experiments" / "phase7v_hai_replication_v1.json"
RAW = ROOT / "results" / "raw"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def episodes_digest(eps) -> str:
    h = hashlib.sha256()
    for e in eps:
        h.update(json.dumps([e.file, e.onset, e.h_true, e.attack_index, e.compromised,
                             e.query_obs.tolist(), e.probe_obs.tolist()]).encode())
    return h.hexdigest()


def build(version):
    t = time.time()
    det = hai.fit_detectors(version)
    eps = hai.build_episodes(version, det)
    print(f"  {version}: {len(eps)} episodes in {time.time() - t:.0f}s", flush=True)
    return det, eps


def main():
    text = CONFIG.read_bytes()
    cfg = json.loads(text)
    sha = hashlib.sha256(text).hexdigest()
    if cfg["dev_version"] != "hai-20.07" or tuple(cfg["policies"]) != JOINT_POLICY_NAMES:
        raise SystemExit("config differs from code; refusing to run")
    commit, dirty = git_state()
    if dirty:
        raise SystemExit("working tree dirty; commit the frozen protocol first")
    raw = RAW / f"{cfg['experiment_id']}.json.gz"
    if raw.exists():
        raise SystemExit(f"{raw} exists; never overwrite")

    files = {}
    for v in (cfg["dev_version"], *cfg["confirm_versions"]):
        for f in hai.VERSIONS[v]["train"] + hai.VERSIONS[v]["test"]:
            files[f"{v}/{f}"] = sha256_file(hai.DATA_ROOT / v / f)

    _, dev = build(cfg["dev_version"])
    model = fit_model(dev)
    acts = action_space(model)
    pols = make_joint_policies()
    out = {"experiment_id": cfg["experiment_id"], "git_commit": commit, "git_dirty": dirty, "config_sha256": sha,
           "hai_version": hai.HAI_VERSION, "hai_model_version": HAI_MODEL_VERSION,
           "joint_confirm_version": JOINT_CONFIRM_VERSION, "python": platform.python_version(),
           "numpy": np.__version__, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "dataset_sha256": files, "dev_episodes_sha256": episodes_digest(dev), "n_dev": len(dev),
           "model": {"prior_h": model.prior_h.tolist(), "prior_s": model.prior_s.tolist(),
                     "lik_query": model.lik_query.tolist(), "lik_probe": model.lik_probe.tolist(),
                     "utility": model.utility.tolist(), "budget": model.budget, "params": model.params},
           "versions": {}}
    for v in cfg["confirm_versions"]:
        det, eps = build(v)
        rows = []
        for i, e in enumerate(eps):
            row = {"file": e.file, "onset": e.onset, "h_true": e.h_true, "attack_index": e.attack_index,
                   "compromised": e.compromised, "norm_regret": {}, "decision": {}, "spend": {}, "n_probes": {},
                   "n_compromised_read": {}, "actions": {}}
            for p in JOINT_POLICY_NAMES:
                r = run_hai_episode(pols[p], model, e, i, acts)
                row["norm_regret"][p] = r.norm_regret
                row["decision"][p] = r.decision
                row["spend"][p] = r.spend
                row["n_probes"][p] = r.n_probes
                row["n_compromised_read"][p] = r.n_compromised_read
                row["actions"][p] = r.actions
            rows.append(row)
        out["versions"][v] = {"episodes_sha256": episodes_digest(eps), "n_episodes": len(eps),
                              "detectors": {"q_thresh": det.q_thresh.tolist(), "p_thresh": det.p_thresh.tolist()},
                              "results": rows}
    RAW.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(out).encode()
    with gzip.open(raw, "wb") as fh:
        fh.write(payload)
    print(f"raw -> {raw}  sha256(json)={hashlib.sha256(payload).hexdigest()}")


if __name__ == "__main__":
    main()
