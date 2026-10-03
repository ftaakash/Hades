"""scripts/analyze_cost_attribution.py -- Phase 7C-A analysis + CAG gates.

Reads a RAW file written by run_cost_attribution.py and never modifies it.

USAGE
-----
  py scripts/analyze_cost_attribution.py --raw results/raw/phase7c_cost_attribution_pilot.json
  py scripts/analyze_cost_attribution.py --raw results/raw/phase7c_cost_attribution_main.json

Pilot mode -> results/analysis/phase7c_cost_attribution_pilot_diagnostics.json (no gates)
Main mode  -> results/analysis/phase7c_cost_attribution_statistics.json
              results/phase7c_cost_attribution_verdict.json
              results/figures/{cost_decomposition,incremental_hades_effect,phi_incremental_effect}.png
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows cp1252 consoles
except Exception:
    pass

from hades.evaluation.statistics import _full_stats, holm_correction

ARMS = ["P3_nom", "P3_nom_cost", "P3_rhat", "P5_no_phi", "P5_full"]
CONTRASTS = {  # name: (a, b)  ->  a - b
    "HADES_INCREMENT": ("P5_full", "P3_nom_cost"),
    "COST":            ("P3_nom_cost", "P3_nom"),
    "TOTAL":           ("P5_full", "P3_nom"),
    "TOTAL_LEGACY":    ("P5_full", "P3_rhat"),
    "RELIABILITY":     ("P5_no_phi", "P3_nom_cost"),
    "PHI":             ("P5_full", "P5_no_phi"),
}
PRIMARY = "HADES_INCREMENT"
PRIMARY_LAM = 1.0
BOOT = 5000


# ---------------------------------------------------------------------------
def _mean_ci(diffs: List[float], seed: int, n_boot: int = BOOT) -> List[float]:
    n = len(diffs)
    if n == 0:
        return [0.0, 0.0]
    rng = random.Random(seed)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return [round(means[int(0.025 * n_boot)], 6), round(means[int(0.975 * n_boot) - 1], 6)]


def _seed_for(*parts) -> int:
    # Deterministic across runs (no PYTHONHASHSEED dependence)
    s = "|".join(str(p) for p in parts)
    h = 0
    for ch in s:
        h = (h * 131 + ord(ch)) & 0x7FFFFFFF
    return h


def index_pairs(episodes: List[Dict]) -> Tuple[Dict, Dict]:
    by = defaultdict(dict)
    for e in episodes:
        k = (e["scenario"], e["sigma"], e["corruption_regime"], e["lam"], e["seed"])
        by[k][e["policy"]] = e
    integrity = {"n_keys": len(by), "incomplete_keys": 0, "true_hyp_mismatch": 0,
                 "beliefs_not_normalized": 0, "budget_inconsistent": 0}
    for k, arms in by.items():
        if set(arms) != set(ARMS):
            integrity["incomplete_keys"] += 1
            continue
        if len({a["true_hypothesis"] for a in arms.values()}) != 1:
            integrity["true_hyp_mismatch"] += 1
        integrity["beliefs_not_normalized"] += sum(not a["beliefs_sum_to_one"] for a in arms.values())
        integrity["budget_inconsistent"] += sum(not a["budget_consistent"] for a in arms.values())
    integrity["pairing_ok"] = (integrity["incomplete_keys"] == 0
                               and integrity["true_hyp_mismatch"] == 0)
    return by, integrity


def contrast_stats(rows: List[Dict], a: str, b: str, seed: int) -> Dict:
    ta = [r[a]["tpm"] for r in rows]
    tb = [r[b]["tpm"] for r in rows]
    d = [x - y for x, y in zip(ta, tb)]
    n = len(d)
    st = _full_stats(ta, tb, boot_resamples=BOOT, boot_seed=seed)
    dc = [r[a]["total_cost"] - r[b]["total_cost"] for r in rows]
    dq = [r[a]["n_queries"] - r[b]["n_queries"] for r in rows]
    cpq = [(r[a]["total_cost"] / max(1, r[a]["n_queries"]))
           - (r[b]["total_cost"] / max(1, r[b]["n_queries"])) for r in rows]
    st.update({
        "frac_pos": round(sum(x > 0 for x in d) / n, 4),
        "frac_neg": round(sum(x < 0 for x in d) / n, 4),
        "frac_zero": round(sum(x == 0 for x in d) / n, 4),
        "decision_divergence": round(sum(r[a]["sources_queried"] != r[b]["sources_queried"]
                                         for r in rows) / n, 4),
        "delta_cost_mean": round(sum(dc) / n, 4),
        "delta_cost_ci": _mean_ci(dc, seed + 2),
        "delta_n_queries_mean": round(sum(dq) / n, 4),
        "delta_n_queries_ci": _mean_ci(dq, seed + 3),
        "delta_cost_per_query_mean": round(sum(cpq) / n, 4),
        "delta_cost_per_query_ci": _mean_ci(cpq, seed + 4),
        "correct_rate_a": round(sum(r[a]["correct_hyp"] for r in rows) / n, 4),
        "correct_rate_b": round(sum(r[b]["correct_hyp"] for r in rows) / n, 4),
        "high_phi_queries_a": round(sum(r[a]["high_phi_queries"] for r in rows) / n, 4),
        "high_phi_queries_b": round(sum(r[b]["high_phi_queries"] for r in rows) / n, 4),
    })
    return st


def analyze(raw: Dict) -> Dict:
    by, integrity = index_pairs(raw["episodes"])
    complete = {k: v for k, v in by.items() if set(v) == set(ARMS)}
    scenarios = sorted({k[0] for k in complete})
    sigmas = sorted({k[1] for k in complete})
    lams = sorted({k[3] for k in complete})
    regimes = sorted({k[2] for k in complete})

    cells: Dict[str, Dict] = {}
    for lam in lams:
        for sc in scenarios:
            for sg in sigmas:
                rows = [v for k, v in complete.items() if k[0] == sc and k[1] == sg and k[3] == lam]
                key = f"lam={lam}|{sc}|sigma={sg}"
                cells[key] = {"n_pairs": len(rows),
                              "arm_mean_tpm": {a: round(sum(r[a]["tpm"] for r in rows) / len(rows), 6)
                                               for a in ARMS},
                              "arm_mean_cost": {a: round(sum(r[a]["total_cost"] for r in rows) / len(rows), 4)
                                                for a in ARMS},
                              "contrasts": {c: contrast_stats(rows, a, b, _seed_for(key, c))
                                            for c, (a, b) in CONTRASTS.items()}}
    # Per-regime breakdown at the primary lambda (primary contrast + PHI only; descriptive)
    per_regime = {}
    for sc in scenarios:
        for sg in sigmas:
            for rg in regimes:
                rows = [v for k, v in complete.items()
                        if k[0] == sc and k[1] == sg and k[2] == rg and k[3] == PRIMARY_LAM]
                if rows:
                    key = f"{sc}|sigma={sg}|{rg}"
                    per_regime[key] = {c: contrast_stats(rows, *CONTRASTS[c], _seed_for(key, c))
                                       for c in (PRIMARY, "PHI", "COST")}

    # Holm families at the primary lambda
    families = {}
    for c in CONTRASTS:
        if c == PRIMARY:
            members = [f"lam={PRIMARY_LAM}|{sc}|sigma={sg}" for sc in scenarios
                       if sc.startswith(("B_", "D_")) for sg in sigmas]
        else:
            members = [f"lam={PRIMARY_LAM}|{sc}|sigma={sg}" for sc in scenarios for sg in sigmas]
        members = [m for m in members if m in cells]
        adj = holm_correction([(m, cells[m]["contrasts"][c]["wilcoxon_p"]) for m in members])
        families[c] = {m: {"holm_p": p, "holm_sig": s} for m, p, s in adj}
        for m, p, s in adj:
            cells[m]["contrasts"][c]["holm_p"] = p
            cells[m]["contrasts"][c]["holm_sig"] = s

    return {"integrity": integrity, "scenarios": scenarios, "sigmas": sigmas,
            "lambdas": lams, "regimes": regimes, "cells": cells,
            "per_regime_primary_lam": per_regime, "holm_families": families}


# ---------------------------------------------------------------------------
def _ci_pos(ci): return ci[0] > 0
def _ci_neg(ci): return ci[1] < 0


def classify_case(cell: Dict) -> str:
    c = cell["contrasts"]
    inc, cost, tot, phi = c["HADES_INCREMENT"], c["COST"], c["TOTAL"], c["PHI"]
    if _ci_pos(inc["mean_ci"]):
        return "E" if (_ci_pos(phi["mean_ci"]) and phi.get("holm_sig")) else "A"
    if _ci_neg(inc["mean_ci"]):
        return "D" if _ci_pos(cost["mean_ci"]) else "D*"  # D*: HADES hurts, cost not helping
    if not _ci_pos(tot["mean_ci"]) and not _ci_neg(tot["mean_ci"]) \
            and not _ci_pos(cost["mean_ci"]) and not _ci_neg(cost["mean_ci"]):
        return "C"
    return "B"


def gates(an: Dict) -> Dict:
    cells = an["cells"]
    L = PRIMARY_LAM
    prim = {k: v for k, v in cells.items() if k.startswith(f"lam={L}|")}
    out = {}

    # CAG-1 (tests run separately; empirical part here)
    div = {k: v["contrasts"]["COST"]["decision_divergence"] for k, v in prim.items()}
    out["CAG-1"] = {"status": "PASS" if any(x > 0 for x in div.values()) else "FAIL",
                    "detail": "Unit tests TestCAG1Validity must also pass (recorded separately).",
                    "cost_decision_divergence_by_cell": div}

    # CAG-2: C pooled over sigma at primary lambda
    c_cells = [v for k, v in prim.items() if "|C_" in k]
    # recompute pooled from per-cell means is invalid for CIs -> pool raw via weighted check:
    # require every C cell to satisfy the conditions (stricter than pooled)
    ok = []
    for v in c_cells:
        s = v["contrasts"]["COST"]
        ok.append(s["decision_divergence"] > 0
                  and _ci_neg(s["delta_cost_per_query_ci"])
                  and _ci_pos(s["delta_n_queries_ci"]))
    out["CAG-2"] = {"status": "PASS" if c_cells and all(ok) else "FAIL",
                    "detail": "Every C cell: divergence>0, cost/query CI<0, n_queries CI>0 "
                              "(per-sigma; stricter than pooled).",
                    "per_cell": {k: {kk: v["contrasts"]["COST"][kk] for kk in
                                     ("decision_divergence", "delta_cost_per_query_mean",
                                      "delta_cost_per_query_ci", "delta_n_queries_mean",
                                      "delta_n_queries_ci", "mean_diff", "mean_ci", "cliffs_delta")}
                                 for k, v in prim.items() if "|C_" in k}}

    # CAG-3 primary
    fam = an["holm_families"][PRIMARY]
    pos = [m for m in fam if cells[m]["contrasts"][PRIMARY]["mean_diff"] > 0
           and _ci_pos(cells[m]["contrasts"][PRIMARY]["mean_ci"]) and fam[m]["holm_sig"]]
    neg = [m for m in fam if _ci_neg(cells[m]["contrasts"][PRIMARY]["mean_ci"]) and fam[m]["holm_sig"]]
    status = "POSITIVE" if pos else ("NEGATIVE" if neg else "NULL")
    out["CAG-3"] = {"status": status, "positive_cells": pos, "negative_cells": neg,
                    "family": {m: {k: cells[m]["contrasts"][PRIMARY][k] for k in
                                   ("n", "mean_diff", "mean_ci", "median_diff", "wilcoxon_p",
                                    "holm_p", "cliffs_delta", "cliffs_interp", "frac_pos",
                                    "frac_neg", "delta_cost_mean", "decision_divergence")}
                               for m in fam}}

    # CAG-4
    pfam = an["holm_families"]["PHI"]
    d_cells = [m for m in pfam if "|D_" in m]
    phi_sig = [m for m in d_cells if pfam[m]["holm_sig"]
               and cells[m]["contrasts"]["PHI"]["decision_divergence"] > 0
               and (_ci_pos(cells[m]["contrasts"]["PHI"]["mean_ci"])
                    or _ci_neg(cells[m]["contrasts"]["PHI"]["mean_ci"]))]
    signs = {m: ("+" if cells[m]["contrasts"]["PHI"]["mean_diff"] > 0 else "-") for m in phi_sig}
    claim_ok = any(s == "+" for s in signs.values()) and status == "POSITIVE"
    out["CAG-4"] = {"status": ("PHI_CONTRIBUTION_POSITIVE" if claim_ok else
                               "PHI_EFFECT_NONZERO_NOT_FAVOURABLE" if phi_sig else "NO_PHI_EFFECT"),
                    "significant_D_cells": signs,
                    "D_cells": {m: {k: cells[m]["contrasts"]["PHI"][k] for k in
                                    ("mean_diff", "mean_ci", "holm_p", "cliffs_delta",
                                     "decision_divergence", "high_phi_queries_a", "high_phi_queries_b")}
                                for m in d_cells}}

    # CAG-5 (runtime part)
    integ = an["integrity"]
    out["CAG-5"] = {"status": "PASS" if (integ["pairing_ok"] and integ["beliefs_not_normalized"] == 0
                                          and integ["budget_inconsistent"] == 0) else "FAIL",
                    "detail": "Unit tests TestCAG5Contamination must also pass (recorded separately).",
                    "integrity": integ}

    out["cases_by_cell"] = {k: classify_case(v) for k, v in prim.items()}
    return out


# ---------------------------------------------------------------------------
def figures(an: Dict, outdir: Path) -> List[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    outdir.mkdir(parents=True, exist_ok=True)
    L = PRIMARY_LAM
    keys = [f"lam={L}|{sc}|sigma={sg}" for sc in an["scenarios"] for sg in an["sigmas"]]
    labels = [k.split("|", 1)[1].replace("_reliability_flip", "").replace("_cost_flip", "")
              .replace("_manipulation_flip", "").replace("sigma=", "σ=") for k in keys]
    paths = []

    def bar(ax, comps, colors):
        w = 0.8 / len(comps)
        for i, (c, col) in enumerate(zip(comps, colors)):
            m = [an["cells"][k]["contrasts"][c]["mean_diff"] for k in keys]
            lo = [m[j] - an["cells"][k]["contrasts"][c]["mean_ci"][0] for j, k in enumerate(keys)]
            hi = [an["cells"][k]["contrasts"][c]["mean_ci"][1] - m[j] for j, k in enumerate(keys)]
            xs = [j + (i - (len(comps) - 1) / 2) * w for j in range(len(keys))]
            ax.bar(xs, m, w, yerr=[lo, hi], capsize=2, label=c, color=col)
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xticks(range(len(keys)))
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.set_ylabel("Δ TPM (paired mean, 95% bootstrap CI)")
        ax.legend(fontsize=8)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    bar(ax, ["COST", "RELIABILITY", "PHI", "TOTAL"], ["#8c8c8c", "#4c72b0", "#dd8452", "#2a2a2a"])
    ax.set_title(f"Phase 7C-A decomposition (λ={L}): TOTAL = COST + RELIABILITY + PHI")
    fig.tight_layout(); p = outdir / "cost_decomposition.png"; fig.savefig(p, dpi=150); plt.close(fig)
    paths.append(str(p))

    fig, ax = plt.subplots(figsize=(11, 4.5))
    bar(ax, ["HADES_INCREMENT", "TOTAL_LEGACY"], ["#55a868", "#c44e52"])
    ax.set_title(f"Incremental HADES effect: P5 − P3_nom_cost (primary) vs legacy P5 − P3_rhat (λ={L})")
    fig.tight_layout(); p = outdir / "incremental_hades_effect.png"; fig.savefig(p, dpi=150); plt.close(fig)
    paths.append(str(p))

    fig, ax = plt.subplots(figsize=(11, 4.5))
    bar(ax, ["PHI"], ["#dd8452"])
    ax.set_title(f"φ-specific effect: P5_full − P5_no_phi (λ={L})")
    fig.tight_layout(); p = outdir / "phi_incremental_effect.png"; fig.savefig(p, dpi=150); plt.close(fig)
    paths.append(str(p))
    return paths


def print_summary(an: Dict) -> None:
    L = PRIMARY_LAM
    print(f"\nIntegrity: {an['integrity']}")
    hdr = f"{'cell (λ=%s)' % L:<34}" + "".join(f"{c:>22}" for c in CONTRASTS)
    print(hdr)
    for k, v in an["cells"].items():
        if not k.startswith(f"lam={L}|"):
            continue
        row = f"{k.split('|',1)[1]:<34}"
        for c in CONTRASTS:
            s = v["contrasts"][c]
            flag = "*" if s.get("holm_sig") else " "
            row += f"{s['mean_diff']:>+9.4f} [{s['mean_ci'][0]:+.3f},{s['mean_ci'][1]:+.3f}]{flag}"
        print(row)
    print("(* = Holm-significant within contrast family)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    a = ap.parse_args()
    raw = json.loads(Path(a.raw).read_text(encoding="utf-8"))
    mode = raw["meta"]["mode"]
    an = analyze(raw)
    print_summary(an)

    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        commit = "unknown"
    meta = {"raw_file": a.raw, "raw_meta": raw["meta"], "analysis_commit": commit,
            "protocol": "docs/phase7c_cost_attribution_protocol.md",
            "gates_doc": "docs/phase7c_cost_attribution_gates.md"}

    Path("results/analysis").mkdir(parents=True, exist_ok=True)
    if mode == "pilot":
        out = Path("results/analysis/phase7c_cost_attribution_pilot_diagnostics.json")
        out.write_text(json.dumps({"meta": meta, "note": "DIAGNOSTIC ONLY - no inferential claims",
                                   **an}, indent=2), encoding="utf-8")
        print(f"\nPilot diagnostics -> {out}")
        return

    stats_path = Path("results/analysis/phase7c_cost_attribution_statistics.json")
    stats_path.write_text(json.dumps({"meta": meta, **an}, indent=2), encoding="utf-8")
    g = gates(an)
    figs = figures(an, Path("results/figures"))
    verdict = {"meta": meta, "gates": g, "figures": figs}
    Path("results/phase7c_cost_attribution_verdict.json").write_text(
        json.dumps(verdict, indent=2), encoding="utf-8")
    print("\nGATES:")
    for gid in ("CAG-1", "CAG-2", "CAG-3", "CAG-4", "CAG-5"):
        print(f"  {gid}: {g[gid]['status']}")
    print(f"  cases: {g['cases_by_cell']}")
    print(f"\nStatistics -> {stats_path}\nVerdict -> results/phase7c_cost_attribution_verdict.json\nFigures -> {figs}")


if __name__ == "__main__":
    main()
