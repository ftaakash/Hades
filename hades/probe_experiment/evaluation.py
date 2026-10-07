"""
hades/probe_experiment/evaluation.py
------------------------------------
Pre-registered analysis for phase7l_probe_pilot_v2 (protocol §7-§9, gates in
docs/hades2_kill_gates.md). Written and committed before any pilot run.

Unit of analysis: the world. For policy X and a set of cells (conditions),
y_w(X) = mean normalised regret of X over the episodes of world w in those cells.

Relative regret reduction of P_PROBE against comparator X:
    RRR_X = 1 - sum_w y_w(P_PROBE) / sum_w y_w(X)
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Sequence

import numpy as np

CLEAN = ("CLEAN",)
BUDGETS = (1, 2, 3)
FAMILIES = ("A_COVER", "A_MISATTRIB", "A_TRUST_HARVEST")


def cond_name(family: str, budget: int) -> str:
    return f"{family}_B{budget}"


ALL_CONDITIONS = CLEAN + tuple(cond_name(f, b) for f in FAMILIES for b in BUDGETS)
PRIMARY_CELLS = tuple(cond_name(f, b) for f in FAMILIES for b in BUDGETS)
FAMILY_CELLS = {f: tuple(cond_name(f, b) for b in BUDGETS) for f in FAMILIES}
BUDGET_CELLS = {b: tuple(cond_name(f, b) for f in FAMILIES) for b in BUDGETS}

THRESHOLD_RRR = 0.10          # frozen practical threshold (protocol §7.1)
CLEAN_MARGIN_POINT = 0.01     # PF-9, normalised-regret units
CLEAN_MARGIN_UPPER = 0.02
N_BOOT = 10_000
BOOT_SEED = 20261007
PHASE_AXES = ("compromise_prior", "probe_cost_ratio", "probe_accuracy", "informativeness", "loss_asymmetry")
LOG_AXES = ("probe_cost_ratio", "loss_asymmetry")


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def world_means(agg: Dict, policy: str, cells: Sequence[str], metric: str = "norm_regret") -> np.ndarray:
    """agg[world_id][condition][policy] = {metric_sum..., 'n': episodes}. Returns y_w in world order."""
    out = []
    for w in sorted(agg, key=int):
        s = sum(agg[w][c][policy][metric] for c in cells)
        n = sum(agg[w][c][policy]["n"] for c in cells)
        out.append(s / n)
    return np.asarray(out)


def rrr(y_p: np.ndarray, y_x: np.ndarray) -> float:
    den = float(y_x.sum())
    return float("nan") if den <= 0 else 1.0 - float(y_p.sum()) / den


def bootstrap_rrr(y_p: np.ndarray, y_x: np.ndarray, n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> Dict:
    rng = np.random.default_rng(seed)
    n = len(y_p)
    idx = rng.integers(0, n, size=(n_boot, n))
    sp, sx = y_p[idx].sum(1), y_x[idx].sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        boots = np.where(sx > 0, 1.0 - sp / sx, np.nan)
    boots = boots[np.isfinite(boots)]
    point = rrr(y_p, y_x)
    lo, hi = (np.percentile(boots, [2.5, 97.5]) if len(boots) else (float("nan"),) * 2)
    p_one_sided = (1 + int((boots <= 0).sum())) / (1 + len(boots))
    return {"rrr": point, "ci95": [float(lo), float(hi)], "p_one_sided": p_one_sided,
            "n_worlds": n, "mean_regret_candidate": float(y_p.mean()), "mean_regret_comparator": float(y_x.mean())}


def bootstrap_mean_diff(d: np.ndarray, n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> Dict:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    m = d[idx].mean(1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return {"mean": float(d.mean()), "ci95": [float(lo), float(hi)]}


def wilcoxon_one_sided(d: np.ndarray) -> float:
    """Paired Wilcoxon signed-rank, H1: d > 0 (normal approximation, zeros dropped, tie-corrected)."""
    d = d[np.abs(d) > 1e-12]
    n = len(d)
    if n == 0:
        return 1.0
    ranks = _rankdata(np.abs(d))
    w_plus = ranks[d > 0].sum()
    mu = n * (n + 1) / 4
    _, counts = np.unique(np.abs(d), return_counts=True)
    var = n * (n + 1) * (2 * n + 1) / 24 - (counts ** 3 - counts).sum() / 48
    if var <= 0:
        return 1.0
    z = (w_plus - mu - 0.5) / math.sqrt(var)
    return 0.5 * math.erfc(z / math.sqrt(2))


def _rankdata(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x))
    xs = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    gt = (a[:, None] > b[None, :]).sum()
    lt = (a[:, None] < b[None, :]).sum()
    return float((gt - lt) / (len(a) * len(b)))


def holm(pvals: Dict[str, float]) -> Dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


# ---------------------------------------------------------------------------
# Power analysis (protocol §7.2)
# ---------------------------------------------------------------------------
Z_ALPHA = 1.959963984540054    # one-sided alpha = 0.025
Z_BETA = 0.8416212335729143    # power = 0.80


def required_worlds(sd_d: float, mean_comparator: float, threshold: float = THRESHOLD_RRR,
                    inflation: float = 1.15, n_min: int = 50, n_max: int = 400) -> Dict:
    """
    Worlds needed to detect RRR = threshold with one-sided alpha 0.025 and power 0.80.
    Delta method: SE(RRR) ~ sd_d / (sqrt(n) * mean_comparator); the 1.15 inflation covers the
    variance of the denominator and the bootstrap. Clamped to [n_min, n_max].
    """
    if mean_comparator <= 0 or not np.isfinite(sd_d):
        return {"n_required_raw": None, "n_worlds": n_max, "capped": True}
    effect = threshold * mean_comparator
    raw = ((Z_ALPHA + Z_BETA) * sd_d / effect) ** 2 * inflation
    n = int(min(n_max, max(n_min, math.ceil(raw))))
    return {"n_required_raw": raw, "n_worlds": n, "capped": raw > n_max}


# ---------------------------------------------------------------------------
# Phase map (secondary, descriptive; protocol §8)
# ---------------------------------------------------------------------------
def logistic_irls(X: np.ndarray, y: np.ndarray, iters: int = 50, ridge: float = 1e-6) -> Dict:
    Xb = np.column_stack([np.ones(len(X)), X])
    beta = np.zeros(Xb.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xb @ beta))
        W = p * (1 - p)
        H = Xb.T @ (Xb * W[:, None]) + ridge * np.eye(len(beta))
        step = np.linalg.solve(H, Xb.T @ (y - p) - ridge * beta)
        beta += step
        if np.abs(step).max() < 1e-8:
            break
    p = 1 / (1 + np.exp(-Xb @ beta))
    H = Xb.T @ (Xb * (p * (1 - p))[:, None]) + ridge * np.eye(len(beta))
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    return {"coef": beta.tolist(), "se": se.tolist()}


def phase_map(d: np.ndarray, params: List[Dict]) -> Dict:
    X = np.array([[math.log(p[a]) if a in LOG_AXES else p[a] for a in PHASE_AXES] for p in params])
    Xs = (X - X.mean(0)) / X.std(0)
    pos = (d > 1e-12).astype(float)
    out = {
        "fraction_better": float((d > 1e-12).mean()),
        "fraction_worse": float((d < -1e-12).mean()),
        "fraction_tied": float((np.abs(d) <= 1e-12).mean()),
        "axes": list(PHASE_AXES), "log_axes": list(LOG_AXES),
        "logistic_standardised": logistic_irls(Xs, pos) if 0 < pos.sum() < len(pos) else None,
    }
    cp, pc = X[:, 0], X[:, 1]
    cp_t = np.quantile(cp, [1 / 3, 2 / 3])
    pc_t = np.quantile(pc, [1 / 3, 2 / 3])
    grid = []
    for i in range(3):
        for j in range(3):
            m = (np.digitize(cp, cp_t) == i) & (np.digitize(pc, pc_t) == j)
            grid.append({"compromise_prior_tertile": i, "log_probe_cost_ratio_tertile": j,
                         "n": int(m.sum()),
                         "mean_d": float(d[m].mean()) if m.any() else None,
                         "fraction_better": float((d[m] > 1e-12).mean()) if m.any() else None})
    out["grid_compromise_x_probe_cost"] = grid
    out["tertile_edges"] = {"compromise_prior": cp_t.tolist(), "log_probe_cost_ratio": pc_t.tolist()}
    return out


# ---------------------------------------------------------------------------
# Gates (docs/hades2_kill_gates.md). Code frozen with the protocol.
# ---------------------------------------------------------------------------
def evaluate_gates(agg: Dict, world_params: Dict, spend_ok: bool, leakage_tests_ok: bool) -> Dict:
    P, J = "P_PROBE", "P_JOINT_EIG_COST"
    yP = world_means(agg, P, PRIMARY_CELLS)
    yJ = world_means(agg, J, PRIMARY_CELLS)
    g: Dict[str, Dict] = {}

    # Validity V-1: the attacker must matter
    nom_b3 = world_means(agg, "P3_NOM", BUDGET_CELLS[3])
    nom_clean = world_means(agg, "P3_NOM", CLEAN)
    v1 = bootstrap_mean_diff(nom_b3 - nom_clean)
    g["V-1"] = {"decisive": "validity", **v1, "pass": v1["ci95"][0] > 0}

    prim = bootstrap_rrr(yP, yJ)
    prim["wilcoxon_p_one_sided"] = wilcoxon_one_sided(yJ - yP)
    prim["cliffs_delta"] = cliffs_delta(yJ, yP)
    g["PF-1"] = {"decisive": True, **prim,
                 "pass": prim["rrr"] >= THRESHOLD_RRR and prim["ci95"][0] > 0}

    g["PF-2"] = {"decisive": True, "pass": bool(spend_ok)}

    comps = ("P3_RHAT_COST", "P3_RHAT_COST_LA2", "P_JOINT_HEIG_COST")
    res = {c: bootstrap_rrr(yP, world_means(agg, c, PRIMARY_CELLS)) for c in comps}
    adj = holm({c: r["p_one_sided"] for c, r in res.items()})
    for c in comps:
        res[c]["p_holm"] = adj[c]
    g["PF-3"] = {"decisive": True, "contrasts": res,
                 "pass": all(r["rrr"] > 0 and r["p_holm"] < 0.05 for r in res.values())}

    n_ep = sum(agg[w][c][P]["n"] for w in agg for c in PRIMARY_CELLS)
    ep_susp = sum(agg[w][c][P]["episodes_probing_suspicious"] for w in agg for c in PRIMARY_CELLS)
    n_probe = sum(agg[w][c][P]["n_probes"] for w in agg for c in PRIMARY_CELLS)
    n_probe_susp = sum(agg[w][c][P]["n_probes_suspicious"] for w in agg for c in PRIMARY_CELLS)
    rate = ep_susp / n_ep
    share = n_probe_susp / n_probe if n_probe else 0.0
    g["PF-4"] = {"decisive": True, "suspicious_probe_episode_rate": rate, "suspicious_share_of_probes": share,
                 "pass": rate >= 0.10 and share >= 0.50}

    yN = world_means(agg, "P_PROBE_NO_S", PRIMARY_CELLS)
    abl = bootstrap_rrr(yP, yN)
    gain_main = float(yJ.sum() - yP.sum())
    gain_abl = float(yN.sum() - yP.sum())
    g["PF-5"] = {"decisive": True, "vs_no_s": abl, "gain_vs_primary": gain_main, "gain_vs_ablation": gain_abl,
                 "pass": abl["ci95"][0] > 0 and gain_main > 0 and gain_abl >= 0.5 * gain_main}
    g["PF-5"]["no_probe_action_reference"] = bootstrap_rrr(yP, world_means(agg, "P_PROBE_NO_PROBE", PRIMARY_CELLS))

    ho = bootstrap_rrr(world_means(agg, P, FAMILY_CELLS["A_MISATTRIB"]), world_means(agg, J, FAMILY_CELLS["A_MISATTRIB"]))
    ad = bootstrap_rrr(world_means(agg, P, FAMILY_CELLS["A_TRUST_HARVEST"]), world_means(agg, J, FAMILY_CELLS["A_TRUST_HARVEST"]))
    de = bootstrap_rrr(world_means(agg, P, FAMILY_CELLS["A_COVER"]), world_means(agg, J, FAMILY_CELLS["A_COVER"]))
    g["PF-6"] = {"decisive": True, "heldout": ho, "adaptive_reported": ad, "design_reported": de,
                 "pass": ho["rrr"] > 0 and ho["ci95"][0] > 0}

    g["PF-7"] = {"decisive": True, "pass": bool(leakage_tests_ok)}

    g["PF-8"] = {"decisive": False, "rrr": prim["rrr"], "ci95": prim["ci95"], "threshold": THRESHOLD_RRR,
                 "ratio_to_threshold": prim["rrr"] / THRESHOLD_RRR, "cliffs_delta": prim["cliffs_delta"]}

    cd = bootstrap_mean_diff(world_means(agg, P, CLEAN) - world_means(agg, J, CLEAN))
    g["PF-9"] = {"decisive": True, "clean_regret_diff_P_minus_J": cd,
                 "pass": cd["mean"] <= CLEAN_MARGIN_POINT and cd["ci95"][1] <= CLEAN_MARGIN_UPPER}

    per_b = {b: rrr(world_means(agg, P, BUDGET_CELLS[b]), world_means(agg, J, BUDGET_CELLS[b])) for b in BUDGETS}
    ids = sorted(agg, key=int)
    even = np.array([int(w) % 2 == 0 for w in ids])
    halves = {"even": rrr(yP[even], yJ[even]), "odd": rrr(yP[~even], yJ[~even])}
    d = yJ - yP
    keep = d < np.quantile(d, 0.9) if len(d) >= 10 else np.ones(len(d), bool)
    trimmed = rrr(yP[keep], yJ[keep])
    g["PF-10"] = {"decisive": True, "per_budget": per_b, "halves": halves, "drop_top_decile": trimmed,
                  "pass": all(v > 0 for v in per_b.values()) and all(v > 0 for v in halves.values()) and trimmed > 0}

    params = [world_params[w] for w in ids]
    g["phase_map"] = {
        "probe_vs_no_probe": phase_map(world_means(agg, "P_PROBE_NO_PROBE", PRIMARY_CELLS) - yP, params),
        "probe_vs_joint_eig": phase_map(d, params),
    }
    decisive = [k for k, v in g.items() if isinstance(v, dict) and v.get("decisive") is True]
    valid = g["V-1"]["pass"]
    if not valid:
        verdict = "INVALID"
    elif all(g[k]["pass"] for k in decisive):
        verdict = "PROCEED"
    else:
        verdict = "KILL"
    g["verdict"] = verdict
    g["failed_decisive"] = [k for k in decisive if not g[k]["pass"]]
    return g
