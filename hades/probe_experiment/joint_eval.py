"""
hades/probe_experiment/joint_eval.py
------------------------------------
Pre-registered gates for phase7u_joint_belief_v1 (docs/phase7u_joint_belief_gates.md).
Committed with the protocol, before any calibration or pilot run.
"""
from __future__ import annotations

import math
from typing import Dict

import numpy as np

from hades.probe_experiment.evaluation import CLEAN, cond_name, rrr, world_means
from hades.probe_experiment.joint_confirm import CANDIDATE, COMPARATORS, NEW_FAMILY
from hades.probe_experiment.robust import NEW_FAMILY as DECOY_FAMILY
from hades.probe_experiment.robust_eval import boot_mean, boot_rrr

BUDGETS = (1, 2, 3)
KNOWN_FAMILIES = ("A_COVER", "A_MISATTRIB", "A_TRUST_HARVEST", DECOY_FAMILY)
PRIMARY_CELLS = tuple(cond_name(NEW_FAMILY, b) for b in BUDGETS)
KNOWN_CELLS = tuple(cond_name(f, b) for f in KNOWN_FAMILIES for b in BUDGETS)
ALL_CONDITIONS = CLEAN + KNOWN_CELLS + PRIMARY_CELLS
THRESHOLD_RRR = 0.10
ALPHA_ONE_SIDED = 0.025              # one candidate; both comparators must be beaten (intersection-union)
CLEAN_MARGIN_POINT, CLEAN_MARGIN_UPPER = 0.01, 0.02
Z_ALPHA = 1.959963984540054
Z_BETA = 0.8416212335729143


def required_worlds(pairs: Dict[str, Dict], threshold: float = THRESHOLD_RRR, inflation: float = 1.15,
                    n_min: int = 50, n_max: int = 400) -> Dict:
    raw = {}
    for k, v in pairs.items():
        mu = v["mean_comparator"]
        raw[k] = math.inf if mu <= 0 else ((Z_ALPHA + Z_BETA) * v["sd_d"] / (threshold * mu)) ** 2 * inflation
    worst = max(raw.values())
    n = int(min(n_max, max(n_min, math.ceil(worst)))) if math.isfinite(worst) else n_max
    return {"n_required_raw": {k: (None if not math.isfinite(v) else v) for k, v in raw.items()},
            "n_worlds": n, "capped": (not math.isfinite(worst)) or worst > n_max}


def evaluate_joint_gates(agg: Dict, spend_ok: bool, leakage_ok: bool) -> Dict:
    g: Dict = {}
    v1 = boot_mean(world_means(agg, "P3_NOM", (cond_name(NEW_FAMILY, 3),)) - world_means(agg, "P3_NOM", CLEAN))
    g["V-1"] = {**v1, "pass": v1["ci95"][0] > 0}
    g["JG-4"] = {"pass": bool(spend_ok)}
    g["JG-5"] = {"pass": bool(leakage_ok)}
    c, (R, J) = CANDIDATE, COMPARATORS
    yc = world_means(agg, c, PRIMARY_CELLS)
    g["contrasts"] = {x: boot_rrr(yc, world_means(agg, x, PRIMARY_CELLS), alpha=ALPHA_ONE_SIDED) for x in COMPARATORS}
    for gate, x in (("JG-1", R), ("JG-2", J)):
        k = g["contrasts"][x]
        g[gate] = {"comparator": x, "pass": k["rrr"] >= THRESHOLD_RRR and k["ci_lower"] > 0}
    cd = boot_mean(world_means(agg, c, CLEAN) - world_means(agg, R, CLEAN))
    g["JG-3"] = {**cd, "pass": cd["mean"] <= CLEAN_MARGIN_POINT and cd["ci95"][1] <= CLEAN_MARGIN_UPPER}
    ids = sorted(agg, key=int)
    even = np.array([int(w) % 2 == 0 for w in ids])
    rep = {}
    for x in COMPARATORS:
        yx = world_means(agg, x, PRIMARY_CELLS)
        rep[x] = {"per_budget": {b: rrr(world_means(agg, c, (cond_name(NEW_FAMILY, b),)),
                                        world_means(agg, x, (cond_name(NEW_FAMILY, b),))) for b in BUDGETS},
                  "halves": {"even": rrr(yc[even], yx[even]), "odd": rrr(yc[~even], yx[~even])}}
    g["JG-6"] = {"replicability": rep,
                 "pass": all(v > 0 for r in rep.values() for v in list(r["per_budget"].values()) + list(r["halves"].values()))}
    # Descriptive scope map (not gated): candidate vs each comparator, by attacker family
    fam = {"CLEAN": CLEAN, NEW_FAMILY: PRIMARY_CELLS,
           **{f: tuple(cond_name(f, b) for b in BUDGETS) for f in KNOWN_FAMILIES}}
    g["scope_map"] = {f: {x: boot_rrr(world_means(agg, c, cells), world_means(agg, x, cells), alpha=ALPHA_ONE_SIDED)
                          for x in COMPARATORS}
                      for f, cells in fam.items()}
    pols = list(next(iter(next(iter(agg.values())).values())).keys())
    g["regret_table"] = {p: {f: float(world_means(agg, p, cells).mean()) for f, cells in fam.items()} for p in pols}
    gates = ("JG-1", "JG-2", "JG-3", "JG-4", "JG-5", "JG-6")
    g["verdict"] = "INVALID" if not g["V-1"]["pass"] else ("PROCEED" if all(g[k]["pass"] for k in gates) else "KILL")
    return g
