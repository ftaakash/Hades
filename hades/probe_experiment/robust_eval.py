"""
hades/probe_experiment/robust_eval.py
-------------------------------------
Pre-registered gates for phase7t_robust_pilot_v1 (docs/phase7t_robust_acquisition_gates.md).
Committed with the protocol, before any calibration or pilot run.
"""
from __future__ import annotations

import math
from typing import Dict

import numpy as np

from hades.probe_experiment.evaluation import (
    BOOT_SEED, CLEAN, N_BOOT, cliffs_delta, cond_name, rrr, wilcoxon_one_sided, world_means,
)
from hades.probe_experiment.robust import CANDIDATES, COMPARATORS, NEW_FAMILY

BUDGETS = (1, 2, 3)
KNOWN_FAMILIES = ("A_COVER", "A_MISATTRIB", "A_TRUST_HARVEST")
PRIMARY_CELLS = tuple(cond_name(NEW_FAMILY, b) for b in BUDGETS)
KNOWN_CELLS = tuple(cond_name(f, b) for f in KNOWN_FAMILIES for b in BUDGETS)
ALL_CONDITIONS = CLEAN + KNOWN_CELLS + PRIMARY_CELLS
THRESHOLD_RRR = 0.10
ALPHA_ONE_SIDED = 0.0125            # 0.025 Bonferroni-split over the two candidates
KNOWN_MARGIN_POINT, KNOWN_MARGIN_UPPER = 0.02, 0.04
CLEAN_MARGIN_POINT, CLEAN_MARGIN_UPPER = 0.01, 0.02
Z_ALPHA = 2.241402727604947         # one-sided 0.0125
Z_BETA = 0.8416212335729143         # power 0.80


def boot_rrr(y_c: np.ndarray, y_x: np.ndarray, alpha: float = ALPHA_ONE_SIDED) -> Dict:
    rng = np.random.default_rng(BOOT_SEED)
    n = len(y_c)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    sc, sx = y_c[idx].sum(1), y_x[idx].sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        b = np.where(sx > 0, 1 - sc / sx, np.nan)
    b = b[np.isfinite(b)]
    lo, hi = np.percentile(b, [100 * alpha, 100 * (1 - alpha)])
    return {"rrr": rrr(y_c, y_x), "ci_lower": float(lo), "ci_upper": float(hi), "ci_level": 1 - 2 * alpha,
            "p_one_sided": (1 + int((b <= 0).sum())) / (1 + len(b)),
            "wilcoxon_p_one_sided": wilcoxon_one_sided(y_x - y_c), "cliffs_delta": cliffs_delta(y_x, y_c),
            "mean_candidate": float(y_c.mean()), "mean_comparator": float(y_x.mean())}


def boot_mean(d: np.ndarray) -> Dict:
    rng = np.random.default_rng(BOOT_SEED)
    m = d[rng.integers(0, len(d), size=(N_BOOT, len(d)))].mean(1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return {"mean": float(d.mean()), "ci95": [float(lo), float(hi)]}


def required_worlds(pairs: Dict[str, Dict], threshold: float = THRESHOLD_RRR, inflation: float = 1.15,
                    n_min: int = 50, n_max: int = 400) -> Dict:
    """pairs[name] = {'sd_d': .., 'mean_comparator': ..}; n is the max over all candidate x comparator pairs."""
    raw = {}
    for k, v in pairs.items():
        mu = v["mean_comparator"]
        raw[k] = math.inf if mu <= 0 else ((Z_ALPHA + Z_BETA) * v["sd_d"] / (threshold * mu)) ** 2 * inflation
    worst = max(raw.values())
    n = int(min(n_max, max(n_min, math.ceil(worst)))) if math.isfinite(worst) else n_max
    return {"n_required_raw": {k: (None if not math.isfinite(v) else v) for k, v in raw.items()},
            "n_worlds": n, "capped": (not math.isfinite(worst)) or worst > n_max}


def spread(agg: Dict, policy: str, cells) -> float:
    """Mean number of distinct sources queried per episode is not stored; report queries per episode instead."""
    q = sum(agg[w][c][policy]["n_queries"] for w in agg for c in cells)
    n = sum(agg[w][c][policy]["n"] for w in agg for c in cells)
    return q / n


def evaluate_robust_gates(agg: Dict, spend_ok: bool, leakage_ok: bool) -> Dict:
    g: Dict = {}
    nom_b3 = world_means(agg, "P3_NOM", (cond_name(NEW_FAMILY, 3),))
    nom_clean = world_means(agg, "P3_NOM", CLEAN)
    v1 = boot_mean(nom_b3 - nom_clean)
    g["V-1"] = {"decisive": "validity", **v1, "pass": v1["ci95"][0] > 0}
    g["RG-5"] = {"decisive": True, "pass": bool(spend_ok)}
    g["RG-6"] = {"decisive": True, "pass": bool(leakage_ok)}
    ids = sorted(agg, key=int)
    even = np.array([int(w) % 2 == 0 for w in ids])
    J = "P_JOINT_EIG_COST"
    cand_pass = {}
    for c in CANDIDATES:
        yc = world_means(agg, c, PRIMARY_CELLS)
        r: Dict = {"contrasts": {}}
        for x in COMPARATORS:
            r["contrasts"][x] = boot_rrr(yc, world_means(agg, x, PRIMARY_CELLS))
        r["RG-1_vs_joint_eig"] = (r["contrasts"][J]["rrr"] >= THRESHOLD_RRR and r["contrasts"][J]["ci_lower"] > 0)
        rx = r["contrasts"]["P0_RANDOM_COST_MATCHED"]
        r["RG-2_vs_random"] = rx["rrr"] >= THRESHOLD_RRR and rx["ci_lower"] > 0
        kd = boot_mean(world_means(agg, c, KNOWN_CELLS) - world_means(agg, J, KNOWN_CELLS))
        r["known_families_diff_vs_joint_eig"] = kd
        r["RG-3_known_noninferior"] = kd["mean"] <= KNOWN_MARGIN_POINT and kd["ci95"][1] <= KNOWN_MARGIN_UPPER
        cd = boot_mean(world_means(agg, c, CLEAN) - world_means(agg, J, CLEAN))
        r["clean_diff_vs_joint_eig"] = cd
        r["RG-4_clean_noninferior"] = cd["mean"] <= CLEAN_MARGIN_POINT and cd["ci95"][1] <= CLEAN_MARGIN_UPPER
        rep = {}
        for x in COMPARATORS:
            per_b = {b: rrr(world_means(agg, c, (cond_name(NEW_FAMILY, b),)),
                            world_means(agg, x, (cond_name(NEW_FAMILY, b),))) for b in BUDGETS}
            yx = world_means(agg, x, PRIMARY_CELLS)
            halves = {"even": rrr(yc[even], yx[even]), "odd": rrr(yc[~even], yx[~even])}
            rep[x] = {"per_budget": per_b, "halves": halves}
        r["replicability"] = rep
        r["RG-7_replicable"] = all(v > 0 for x in rep.values() for v in list(x["per_budget"].values()) + list(x["halves"].values()))
        r["queries_per_episode_primary"] = spread(agg, c, PRIMARY_CELLS)
        r["pass"] = all(r[k] for k in ("RG-1_vs_joint_eig", "RG-2_vs_random", "RG-3_known_noninferior",
                                       "RG-4_clean_noninferior", "RG-7_replicable"))
        g[c] = r
        cand_pass[c] = r["pass"]
    # Descriptive: every policy's regret by family
    fam = {"CLEAN": CLEAN, NEW_FAMILY: PRIMARY_CELLS,
           **{f: tuple(cond_name(f, b) for b in BUDGETS) for f in KNOWN_FAMILIES}}
    pols = list(next(iter(next(iter(agg.values())).values())).keys())
    g["regret_table"] = {p: {f: float(world_means(agg, p, cells).mean()) for f, cells in fam.items()} for p in pols}
    shared_ok = g["RG-5"]["pass"] and g["RG-6"]["pass"]
    if not g["V-1"]["pass"]:
        verdict = "INVALID"
    elif shared_ok and any(cand_pass.values()):
        verdict = "PROCEED"
    else:
        verdict = "KILL"
    g["verdict"] = verdict
    g["passing_candidates"] = [c for c, ok in cand_pass.items() if ok and shared_ok]
    return g
