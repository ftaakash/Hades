"""
hades/probe_experiment/hai_eval.py
----------------------------------
Pre-registered gates for phase7v_hai_replication_v1 (docs/phase7v_hai_replication_gates.md).
Committed with the protocol, before any confirmatory HAI episode was built.

Unit of analysis: the episode (one attack segment or one sampled normal window). Each policy sees every
episode once, so the contrasts are paired by episode.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

from hades.probe_experiment.evaluation import rrr
from hades.probe_experiment.joint_confirm import CANDIDATE, COMPARATORS
from hades.probe_experiment.robust_eval import boot_mean, boot_rrr

THRESHOLD_RRR = 0.10
ALPHA_ONE_SIDED = 0.025
NORMAL_MARGIN_POINT, NORMAL_MARGIN_UPPER = 0.01, 0.02
PRIMARY_VERSION = "hai-21.03"
SECONDARY_VERSION = "hai-22.04"


def prior_only_regret(utility: np.ndarray, prior_h: np.ndarray, h_true: np.ndarray) -> np.ndarray:
    """Normalised regret of the Bayes decision taken on the prior alone (no evidence)."""
    d = int(np.argmax(utility @ prior_h))
    return np.array([(utility[h, h] - utility[d, h]) / -utility.min() for h in h_true], float)


def evaluate_hai_gates(per_ep: Dict[str, np.ndarray], h_true: np.ndarray, compromised_n: np.ndarray,
                       prior_regret: np.ndarray, spend_ok: bool, leakage_ok: bool) -> Dict:
    """per_ep[policy] = normalised regret per episode, all policies in the same episode order."""
    g: Dict = {"n_episodes": int(len(h_true)), "n_attack": int((h_true > 0).sum()),
               "n_spoofed_attack": int(((h_true > 0) & (compromised_n > 0)).sum())}
    v1 = boot_mean(prior_regret - per_ep["P3_NOM"])
    g["V-1"] = {**v1, "pass": v1["ci95"][0] > 0}
    g["HG-4"] = {"pass": bool(spend_ok)}
    g["HG-5"] = {"pass": bool(leakage_ok)}
    c, (R, J) = CANDIDATE, COMPARATORS
    g["contrasts"] = {x: boot_rrr(per_ep[c], per_ep[x], alpha=ALPHA_ONE_SIDED) for x in COMPARATORS}
    for gate, x in (("HG-1", R), ("HG-2", J)):
        k = g["contrasts"][x]
        g[gate] = {"comparator": x, "pass": k["rrr"] >= THRESHOLD_RRR and k["ci_lower"] > 0,
                   "clearly_below_threshold": k["ci_upper"] < THRESHOLD_RRR}
    normal = h_true == 0
    nd = boot_mean(per_ep[c][normal] - per_ep[R][normal])
    g["HG-3"] = {**nd, "pass": nd["mean"] <= NORMAL_MARGIN_POINT and nd["ci95"][1] <= NORMAL_MARGIN_UPPER}
    idx = np.arange(len(h_true))
    rep = {x: {"even": rrr(per_ep[c][idx % 2 == 0], per_ep[x][idx % 2 == 0]),
               "odd": rrr(per_ep[c][idx % 2 == 1], per_ep[x][idx % 2 == 1])} for x in COMPARATORS}
    g["HG-6"] = {"halves": rep, "pass": all(v > 0 for r in rep.values() for v in r.values())}
    subsets = {"all": np.ones_like(normal), "normal": normal, "h1": h_true == 1, "h2": h_true == 2,
               "spoofed_attack": (h_true > 0) & (compromised_n > 0),
               "unspoofed_attack": (h_true > 0) & (compromised_n == 0)}
    g["regret_table"] = {p: {s: float(v[m].mean()) if m.any() else None for s, m in subsets.items()}
                         for p, v in {**per_ep, "PRIOR_ONLY": prior_regret}.items()}
    g["scope_map"] = {s: {x: rrr(per_ep[c][m], per_ep[x][m]) for x in COMPARATORS}
                      for s, m in subsets.items() if m.any()}
    gates = ("HG-1", "HG-2", "HG-3", "HG-4", "HG-5", "HG-6")
    if not g["V-1"]["pass"]:
        verdict = "INVALID"
    elif all(g[k]["pass"] for k in gates):
        verdict = "PROCEED"
    elif (not all(g[k]["pass"] for k in ("HG-3", "HG-4", "HG-5"))
          or any(g[k]["clearly_below_threshold"] for k in ("HG-1", "HG-2"))):
        verdict = "KILL"
    else:
        verdict = "INCONCLUSIVE"
    g["verdict"] = verdict
    return g


def per_episode_arrays(results: List[Dict], policies) -> Dict[str, np.ndarray]:
    return {p: np.array([r["norm_regret"][p] for r in results], float) for p in policies}
