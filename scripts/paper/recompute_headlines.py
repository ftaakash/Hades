"""
scripts/paper/recompute_headlines.py
------------------------------------
Recomputes every number the HADES 2.0 paper reports directly from the raw run files, without importing the
gate code, and checks each against the committed statistics JSON. Writes results/processed/paper_numbers.json.
Exits non-zero if any headline differs from the committed statistics.

Usage:  py scripts/paper/recompute_headlines.py
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "results" / "raw"
STATS = ROOT / "results" / "analysis"
OUT = ROOT / "results" / "processed" / "paper_numbers.json"
N_BOOT, SEED = 10_000, 20261007
B = (1, 2, 3)


def load(name):
    p = RAW / name
    if p.suffix == ".gz":
        with gzip.open(p, "rt") as fh:
            return json.load(fh)
    return json.loads(p.read_text())


def cells(fam):
    return ("CLEAN",) if fam == "CLEAN" else tuple(f"{fam}_B{b}" for b in B)


def ybar(agg, pol, cs):
    ws = sorted(agg, key=int)
    return np.array([sum(agg[w][c][pol]["norm_regret"] for c in cs) / sum(agg[w][c][pol]["n"] for c in cs) for w in ws])


def rrr_ci(yc, yx, alpha):
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, len(yc), size=(N_BOOT, len(yc)))
    sc, sx = yc[idx].sum(1), yx[idx].sum(1)
    b = 1 - sc[sx > 0] / sx[sx > 0]
    lo, hi = np.percentile(b, [100 * alpha, 100 * (1 - alpha)])
    return {"rrr": float(1 - yc.sum() / yx.sum()), "lo": float(lo), "hi": float(hi)}


def sim_block(name, families, pols, contrasts, alpha):
    d = load(name)
    agg = d["aggregates"]
    out = {"n_worlds": len(agg), "seeds": d["pilot_world_seeds"], "git_commit": d["git_commit"],
           "config_sha256": d["config_sha256"],
           "n_episodes": int(sum(r["n"] for w in agg.values() for c in w.values() for r in c.values())),
           "regret": {p: {f: float(ybar(agg, p, cells(f)).mean()) for f in families} for p in pols},
           "contrasts": {}}
    for (cand, comp, fams) in contrasts:
        cs = tuple(c for f in fams for c in cells(f))
        out["contrasts"][f"{cand}|{comp}|{'+'.join(fams)}"] = rrr_ci(ybar(agg, cand, cs), ybar(agg, comp, cs), alpha)
    return out


def main():
    nums, checks = {}, []

    # 7L (probe value): primary cells = 3 known families, alpha 0.025
    F7L = ("CLEAN", "A_COVER", "A_MISATTRIB", "A_TRUST_HARVEST")
    P7L = ("P0_RANDOM_COST_MATCHED", "P3_NOM", "P3_RHAT_COST", "P3_RHAT_COST_LA2", "P_JOINT_HEIG_COST",
           "P_JOINT_EIG_COST", "P_PROBE", "P_PROBE_NO_S", "P_PROBE_NO_PROBE")
    prim = ("A_COVER", "A_MISATTRIB", "A_TRUST_HARVEST")
    nums["7L"] = sim_block("phase7l_probe_pilot_v2.json", F7L, P7L, [
        ("P_PROBE", "P_JOINT_EIG_COST", prim), ("P_PROBE", "P_JOINT_HEIG_COST", prim),
        ("P_PROBE", "P3_RHAT_COST_LA2", prim), ("P_PROBE", "P_PROBE_NO_S", prim),
        ("P_PROBE", "P_JOINT_EIG_COST", ("A_MISATTRIB",)), ("P_PROBE", "P_JOINT_EIG_COST", ("A_COVER",)),
        ("P_PROBE", "P_JOINT_EIG_COST", ("A_TRUST_HARVEST",))], 0.025)
    s = json.loads((STATS / "phase7l_probe_pilot_v2_statistics.json").read_text())
    checks.append(("7L PF-1 RRR", nums["7L"]["contrasts"]["P_PROBE|P_JOINT_EIG_COST|A_COVER+A_MISATTRIB+A_TRUST_HARVEST"]["rrr"],
                   s["PF-1"]["rrr"]))
    checks.append(("7L PF-1 CI lower", nums["7L"]["contrasts"]["P_PROBE|P_JOINT_EIG_COST|A_COVER+A_MISATTRIB+A_TRUST_HARVEST"]["lo"],
                   s["PF-1"]["ci95"][0]))

    # 7T (robust): primary = A_DECOY_MIGRATE, alpha 0.0125
    F7T = ("CLEAN", "A_DECOY_MIGRATE", "A_COVER", "A_MISATTRIB", "A_TRUST_HARVEST")
    P7T = ("P0_RANDOM_COST_MATCHED", "P3_NOM", "P3_RHAT_COST", "P_JOINT_HEIG_COST", "P_JOINT_EIG_COST", "P_PROBE",
           "P_RAND_JEIG", "P_MINIMAX_JEIG")
    nums["7T"] = sim_block("phase7t_robust_pilot_v1.json.gz", F7T, P7T, [
        (c, x, ("A_DECOY_MIGRATE",)) for c in ("P_RAND_JEIG", "P_MINIMAX_JEIG")
        for x in ("P_JOINT_EIG_COST", "P0_RANDOM_COST_MATCHED")], 0.0125)
    s = json.loads((STATS / "phase7t_robust_pilot_v1_statistics.json").read_text())
    checks.append(("7T RG-1 P_RAND_JEIG", nums["7T"]["contrasts"]["P_RAND_JEIG|P_JOINT_EIG_COST|A_DECOY_MIGRATE"]["rrr"],
                   s["P_RAND_JEIG"]["contrasts"]["P_JOINT_EIG_COST"]["rrr"]))
    checks.append(("7T RG-1 P_MINIMAX_JEIG", nums["7T"]["contrasts"]["P_MINIMAX_JEIG|P_JOINT_EIG_COST|A_DECOY_MIGRATE"]["rrr"],
                   s["P_MINIMAX_JEIG"]["contrasts"]["P_JOINT_EIG_COST"]["rrr"]))

    # 7U (joint belief): primary = A_COLLUDE_CHEAP, alpha 0.025
    F7U = ("CLEAN", "A_COLLUDE_CHEAP", "A_COVER", "A_DECOY_MIGRATE", "A_MISATTRIB", "A_TRUST_HARVEST")
    P7U = ("P0_RANDOM_COST_MATCHED", "P3_NOM", "P3_RHAT_COST", "P3_RHAT_COST_LA2", "P_JOINT_HEIG_COST",
           "P_JOINT_EIG_COST", "P_PROBE")
    nums["7U"] = sim_block("phase7u_joint_belief_v1.json.gz", F7U, P7U, [
        ("P_JOINT_HEIG_COST", x, (f,)) for x in ("P3_RHAT_COST_LA2", "P_JOINT_EIG_COST") for f in F7U], 0.025)
    s = json.loads((STATS / "phase7u_joint_belief_v1_statistics.json").read_text())
    for x in ("P3_RHAT_COST_LA2", "P_JOINT_EIG_COST"):
        checks.append((f"7U vs {x}", nums["7U"]["contrasts"][f"P_JOINT_HEIG_COST|{x}|A_COLLUDE_CHEAP"]["rrr"],
                       s["contrasts"][x]["rrr"]))
        checks.append((f"7U vs {x} CI lower", nums["7U"]["contrasts"][f"P_JOINT_HEIG_COST|{x}|A_COLLUDE_CHEAP"]["lo"],
                       s["contrasts"][x]["ci_lower"]))

    # 7V (HAI): per-episode, alpha 0.025
    d = load("phase7v_hai_replication_v1.json.gz")
    s = json.loads((STATS / "phase7v_hai_replication_v1_statistics.json").read_text())
    U, ph = np.array(d["model"]["utility"]), np.array(d["model"]["prior_h"])
    dprior = int(np.argmax(U @ ph))
    nums["7V"] = {"git_commit": d["git_commit"], "n_dev": d["n_dev"], "model_params": d["model"]["params"],
                  "prior_h": d["model"]["prior_h"]}
    for v, rows in ((v, d["versions"][v]["results"]) for v in d["versions"]):
        h = np.array([r["h_true"] for r in rows])
        y = {p: np.array([r["norm_regret"][p] for r in rows]) for p in rows[0]["norm_regret"]}
        prior = np.array([(U[k, k] - U[dprior, k]) / -U.min() for k in h])
        diff = prior - y["P3_NOM"]
        rng = np.random.default_rng(SEED)
        m = diff[rng.integers(0, len(diff), size=(N_BOOT, len(diff)))].mean(1)
        nums["7V"][v] = {"n": len(rows), "n_attack": int((h > 0).sum()),
                         "n_spoofed": int(sum(1 for r in rows if r["h_true"] > 0 and r["compromised"])),
                         "v1": {"mean": float(diff.mean()), "lo": float(np.percentile(m, 2.5)), "hi": float(np.percentile(m, 97.5))},
                         "regret": {**{p: float(a.mean()) for p, a in y.items()}, "PRIOR_ONLY": float(prior.mean())},
                         "probes": {p: float(np.mean([r["n_probes"][p] for r in rows])) for p in y},
                         "contrasts": {x: rrr_ci(y["P_JOINT_HEIG_COST"], y[x], 0.025)
                                       for x in ("P3_RHAT_COST_LA2", "P_JOINT_EIG_COST")}}
        checks.append((f"7V {v} V-1 mean", nums["7V"][v]["v1"]["mean"], s[v]["V-1"]["mean"]))
        for x in ("P3_RHAT_COST_LA2", "P_JOINT_EIG_COST"):
            checks.append((f"7V {v} vs {x}", nums["7V"][v]["contrasts"][x]["rrr"], s[v]["contrasts"][x]["rrr"]))
            checks.append((f"7V {v} vs {x} CI lower", nums["7V"][v]["contrasts"][x]["lo"], s[v]["contrasts"][x]["ci_lower"]))

    # Quoted alongside the recomputed numbers (read, not recomputed): calibration requirement and Cliff's delta
    for blk, name in (("7L", "phase7l_probe_pilot_v2"), ("7T", "phase7t_robust_pilot_v1"), ("7U", "phase7u_joint_belief_v1")):
        man = json.loads((RAW / f"{name}_seed_manifest.json").read_text())
        req = man["n_required_raw"]
        nums[blk]["calibration_required"] = max(req.values()) if isinstance(req, dict) else req
    s = json.loads((STATS / "phase7u_joint_belief_v1_statistics.json").read_text())
    nums["7U"]["cliffs_delta"] = {x: s["contrasts"][x]["cliffs_delta"] for x in s["contrasts"]}

    bad = [(k, a, b) for k, a, b in checks if abs(a - b) > 1e-9]
    nums["checks"] = [{"name": k, "recomputed": a, "committed": b, "match": abs(a - b) <= 1e-9} for k, a, b in checks]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(nums, indent=1))
    for k, a, b in checks:
        print(f"{'OK ' if abs(a - b) <= 1e-9 else 'BAD'} {k}: {a:.6f} vs {b:.6f}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
