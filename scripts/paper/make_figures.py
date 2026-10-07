"""
scripts/paper/make_figures.py
-----------------------------
Builds every figure and table of the HADES 2.0 paper from results/processed/paper_numbers.json
(written by recompute_headlines.py from the raw run files). No number in the paper is typed by hand.

Usage:  py scripts/paper/recompute_headlines.py && py scripts/paper/make_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
NUM = json.loads((ROOT / "results" / "processed" / "paper_numbers.json").read_text())
FIG = ROOT / "paper" / "manuscript" / "figures"
TAB = ROOT / "paper" / "manuscript" / "tables"
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1f1f1e", "#6b6b68", "#e4e4e1"
SEQ = ["#ffffff", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
THR = 0.10

plt.rcParams.update({"font.family": "serif", "font.size": 7.5, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": INK, "axes.linewidth": 0.6, "pdf.fonttype": 42})

SHORT = {"P0_RANDOM_COST_MATCHED": "Random", "P3_NOM": "EIG (nominal)", "P3_RHAT_COST": r"EIG-$\hat r$/cost",
         "P3_RHAT_COST_LA2": r"EIG-$\hat r$/cost LA2 (R)", "P_JOINT_HEIG_COST": "Joint H-EIG/cost (C)",
         "P_JOINT_EIG_COST": "Joint (H,S)-EIG/cost (J)", "P_PROBE": "Decision-value probe",
         "P_RAND_JEIG": "Randomised J", "P_MINIMAX_JEIG": "Minimax J", "P_PROBE_NO_S": "Probe, no S model",
         "P_PROBE_NO_PROBE": "Probe objective, no probes"}
TEX = {k: v.replace("(R)", "($R$)").replace("(C)", "($C$)").replace("(J)", "($J$)") for k, v in SHORT.items()}
FAM = {"CLEAN": "Clean", "A_COVER": "Cover-up", "A_MISATTRIB": "Misattrib.", "A_TRUST_HARVEST": "Trust-harvest",
       "A_DECOY_MIGRATE": "Decoy-migrate", "A_COLLUDE_CHEAP": "Collude-cheap"}


def c(block, key):
    return NUM[block]["contrasts"][key]


def forest():
    """Fig. 1: every pre-registered primary contrast, RRR with its pre-registered CI, against the 0.10 threshold."""
    P = "A_COVER+A_MISATTRIB+A_TRUST_HARVEST"
    rows = [
        ("E1  probe value vs J (PF-1)", c("7L", f"P_PROBE|P_JOINT_EIG_COST|{P}"), "PASS"),
        ("E1  probe value vs C (PF-3)", c("7L", f"P_PROBE|P_JOINT_HEIG_COST|{P}"), "FAIL"),
        ("E1  probe value vs J, held-out (PF-6)", c("7L", "P_PROBE|P_JOINT_EIG_COST|A_MISATTRIB"), "FAIL"),
        ("E2  randomised J vs J (RG-1)", c("7T", "P_RAND_JEIG|P_JOINT_EIG_COST|A_DECOY_MIGRATE"), "FAIL"),
        ("E2  minimax J vs J (RG-1)", c("7T", "P_MINIMAX_JEIG|P_JOINT_EIG_COST|A_DECOY_MIGRATE"), "FAIL"),
        ("E3  C vs R (JG-1)", c("7U", "P_JOINT_HEIG_COST|P3_RHAT_COST_LA2|A_COLLUDE_CHEAP"), "PASS"),
        ("E3  C vs J (JG-2)", c("7U", "P_JOINT_HEIG_COST|P_JOINT_EIG_COST|A_COLLUDE_CHEAP"), "PASS"),
        ("E4  HAI 21.03: C vs R", NUM["7V"]["hai-21.03"]["contrasts"]["P3_RHAT_COST_LA2"], "INVALID"),
        ("E4  HAI 21.03: C vs J", NUM["7V"]["hai-21.03"]["contrasts"]["P_JOINT_EIG_COST"], "INVALID"),
    ]
    fig, ax = plt.subplots(figsize=(3.45, 2.75))
    y = np.arange(len(rows))[::-1]
    for yi, (lab, k, verdict) in zip(y, rows):
        col = {"PASS": BLUE, "FAIL": ORANGE, "INVALID": MUTED}[verdict]
        mk = {"PASS": "o", "FAIL": "s", "INVALID": "D"}[verdict]
        lo, hi = max(k["lo"], -0.65), k["hi"]
        ax.plot([lo, hi], [yi, yi], color=col, lw=1.6, solid_capstyle="round")
        if k["lo"] < -0.65:
            ax.annotate("", xy=(-0.66, yi), xytext=(-0.6, yi), arrowprops=dict(arrowstyle="-|>", color=col, lw=1))
        x = max(k["rrr"], -0.64)
        ax.plot(x, yi, mk, color=col, ms=4.5, mec="white", mew=0.6, zorder=3)
        ax.text(0.6, yi, verdict, color=INK if verdict != "INVALID" else MUTED, va="center", fontsize=6)
    ax.axvline(0, color=MUTED, lw=0.6)
    ax.axvline(THR, color=INK, lw=0.8, ls=(0, (3, 2)))
    ax.text(THR + 0.01, len(rows) - 0.35, "threshold 0.10", fontsize=6, color=INK)
    ax.set_yticks(y, [r[0] for r in rows], fontsize=6.5)
    ax.set_xlim(-0.68, 1.12)
    ax.set_xlabel("RRR with pre-registered CI")
    ax.grid(axis="x", color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout(pad=0.3)
    fig.savefig(FIG / "fig_forest.pdf")
    fig.savefig(FIG / "fig_forest.png", dpi=200)  # README
    plt.close(fig)


def scope():
    """Fig. 2: 7U scope map, RRR of C vs R and vs J by attacker family."""
    fams = ["CLEAN", "A_COVER", "A_DECOY_MIGRATE", "A_COLLUDE_CHEAP", "A_MISATTRIB", "A_TRUST_HARVEST"]
    fig, ax = plt.subplots(figsize=(3.45, 2.0))
    y = np.arange(len(fams))[::-1]
    for off, comp, col, mk, lab in ((0.14, "P3_RHAT_COST_LA2", BLUE, "o", "vs R (reliability-weighted)"),
                                    (-0.14, "P_JOINT_EIG_COST", ORANGE, "s", "vs J (joint-state objective)")):
        for yi, f in zip(y, fams):
            k = c("7U", f"P_JOINT_HEIG_COST|{comp}|{f}")
            ax.plot([k["lo"], k["hi"]], [yi + off] * 2, color=col, lw=1.6, solid_capstyle="round")
            ax.plot(k["rrr"], yi + off, mk, color=col, ms=4, mec="white", mew=0.6, zorder=3,
                    label=lab if f == "CLEAN" else None)
    ax.axvline(0, color=MUTED, lw=0.6)
    ax.axvline(THR, color=INK, lw=0.8, ls=(0, (3, 2)))
    ax.set_yticks(y, [FAM[f] + (" (held-out)" if f == "A_COLLUDE_CHEAP" else "") for f in fams], fontsize=6.5)
    ax.set_xlabel("RRR of joint H-EIG/cost (C), 95% CI")
    ax.grid(axis="x", color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=6, loc="lower right", handlelength=1)
    fig.tight_layout(pad=0.3)
    fig.savefig(FIG / "fig_scope.pdf")
    fig.savefig(FIG / "fig_scope.png", dpi=200)  # README
    plt.close(fig)


def heat():
    """Fig. 3: mean normalised regret, 7U, policy x attacker family (sequential, one hue)."""
    fams = ["CLEAN", "A_COVER", "A_DECOY_MIGRATE", "A_COLLUDE_CHEAP", "A_MISATTRIB", "A_TRUST_HARVEST"]
    pols = ["P0_RANDOM_COST_MATCHED", "P3_NOM", "P3_RHAT_COST", "P3_RHAT_COST_LA2", "P_JOINT_EIG_COST",
            "P_JOINT_HEIG_COST", "P_PROBE"]
    M = np.array([[NUM["7U"]["regret"][p][f] for f in fams] for p in pols])
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", SEQ[1:])
    fig, ax = plt.subplots(figsize=(3.45, 2.2))
    ax.imshow(M, cmap=cmap, vmin=0, vmax=0.32, aspect="auto")
    for i in range(M.shape[0]):
        best = M[:, :].argmin(0)
        for j in range(M.shape[1]):
            v = M[i, j]
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", fontsize=5.8,
                    color="white" if v > 0.17 else INK, fontweight="bold" if best[j] == i else "normal")
    ax.set_xticks(range(len(fams)), [FAM[f] for f in fams], fontsize=6, rotation=25, ha="right")
    ax.set_yticks(range(len(pols)), [SHORT[p] for p in pols], fontsize=6)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout(pad=0.3)
    fig.savefig(FIG / "fig_regret_heat.pdf")
    plt.close(fig)


def f3(x):
    return f"{x:.3f}"


def ci(k):
    return f"${k['rrr']:.3f}$ [${k['lo']:.3f}$, ${k['hi']:.3f}$]"


def tables():
    P = "A_COVER+A_MISATTRIB+A_TRUST_HARVEST"
    n = NUM
    rows = [
        (r"E1 & $P$ vs $J$, pooled families & PF-1 & " + ci(c("7L", f"P_PROBE|P_JOINT_EIG_COST|{P}")) + r" & pass \\"),
        (r" & $P$ vs $C$, pooled families & PF-3 & " + ci(c("7L", f"P_PROBE|P_JOINT_HEIG_COST|{P}")) + r" & \textbf{fail} \\"),
        (r" & $P$ vs $J$, held-out misattrib. & PF-6 & " + ci(c("7L", "P_PROBE|P_JOINT_EIG_COST|A_MISATTRIB")) + r" & \textbf{fail} \\"),
        (r"E2 & Rand. $J$ vs $J$, held-out & RG-1 & " + ci(c("7T", "P_RAND_JEIG|P_JOINT_EIG_COST|A_DECOY_MIGRATE")) + r" & \textbf{fail} \\"),
        (r" & Minimax $J$ vs $J$, held-out & RG-1 & " + ci(c("7T", "P_MINIMAX_JEIG|P_JOINT_EIG_COST|A_DECOY_MIGRATE")) + r" & \textbf{fail} \\"),
        (r"E3 & $C$ vs $R$, held-out & JG-1 & " + ci(c("7U", "P_JOINT_HEIG_COST|P3_RHAT_COST_LA2|A_COLLUDE_CHEAP")) + r" & pass \\"),
        (r" & $C$ vs $J$, held-out & JG-2 & " + ci(c("7U", "P_JOINT_HEIG_COST|P_JOINT_EIG_COST|A_COLLUDE_CHEAP")) + r" & pass \\"),
        (r"E4 & $C$ vs $R$, HAI 21.03 & HG-1 & " + ci(n["7V"]["hai-21.03"]["contrasts"]["P3_RHAT_COST_LA2"]) + r" & n/a \\"),
        (r" & $C$ vs $J$, HAI 21.03 & HG-2 & " + ci(n["7V"]["hai-21.03"]["contrasts"]["P_JOINT_EIG_COST"]) + r" & n/a \\"),
    ]
    (TAB / "tab_primary.tex").write_text("\n".join(rows) + "\n")

    fams = ["CLEAN", "A_COVER", "A_DECOY_MIGRATE", "A_COLLUDE_CHEAP", "A_MISATTRIB", "A_TRUST_HARVEST"]
    pols = ["P0_RANDOM_COST_MATCHED", "P3_NOM", "P3_RHAT_COST_LA2", "P_JOINT_EIG_COST", "P_JOINT_HEIG_COST", "P_PROBE"]
    R = n["7U"]["regret"]
    out = []
    for p in pols:
        cells = []
        for f in fams:
            v = R[p][f]
            best = min(R[q][f] for q in R)
            cells.append(r"\textbf{" + f3(v) + "}" if abs(v - best) < 1e-12 else f3(v))
        out.append(TEX[p] + " & " + " & ".join(cells) + r" \\")
    (TAB / "tab_regret7u.tex").write_text("\n".join(out) + "\n")

    hv = []
    for p in ("PRIOR_ONLY", "P0_RANDOM_COST_MATCHED", "P3_NOM", "P3_RHAT_COST_LA2", "P_JOINT_EIG_COST",
              "P_JOINT_HEIG_COST", "P_PROBE"):
        name = "Prior only (no evidence)" if p == "PRIOR_ONLY" else TEX[p]
        hv.append(name + " & " + f3(n["7V"]["hai-21.03"]["regret"][p]) + " & " + f3(n["7V"]["hai-22.04"]["regret"][p]) + r" \\")
    (TAB / "tab_hai.tex").write_text("\n".join(hv) + "\n")

    # Macros for numbers quoted in the running text
    m = {}
    def put(name, val, fmt="{:.3f}"):
        m[name] = fmt.format(val)
    for blk, key, nm in (("7U", "P_JOINT_HEIG_COST|P3_RHAT_COST_LA2|A_COLLUDE_CHEAP", "UR"),
                         ("7U", "P_JOINT_HEIG_COST|P_JOINT_EIG_COST|A_COLLUDE_CHEAP", "UJ"),
                         ("7U", "P_JOINT_HEIG_COST|P3_RHAT_COST_LA2|A_MISATTRIB", "URmis"),
                         ("7U", "P_JOINT_HEIG_COST|P_JOINT_EIG_COST|A_TRUST_HARVEST", "UJth"),
                         ("7U", "P_JOINT_HEIG_COST|P3_RHAT_COST_LA2|A_TRUST_HARVEST", "URth"),
                         ("7U", "P_JOINT_HEIG_COST|P_JOINT_EIG_COST|CLEAN", "UJclean"),
                         ("7L", f"P_PROBE|P_JOINT_EIG_COST|{P}", "LJ"), ("7L", f"P_PROBE|P_JOINT_HEIG_COST|{P}", "LC"),
                         ("7L", "P_PROBE|P_JOINT_EIG_COST|A_MISATTRIB", "LJmis"),
                         ("7L", "P_PROBE|P_JOINT_EIG_COST|A_COVER", "LJcov"),
                         ("7T", "P_RAND_JEIG|P_JOINT_EIG_COST|A_DECOY_MIGRATE", "TR"),
                         ("7T", "P_MINIMAX_JEIG|P_JOINT_EIG_COST|A_DECOY_MIGRATE", "TM")):
        k = c(blk, key)
        put(nm, k["rrr"], "{:.2f}")
        put(nm + "lo", k["lo"], "{:.2f}")
        put(nm + "hi", k["hi"], "{:.2f}")
    for v, tag in (("hai-21.03", "A"), ("hai-22.04", "B")):
        d = n["7V"][v]
        put("Vn" + tag, d["n"], "{}")
        put("Vatt" + tag, d["n_attack"], "{}")
        put("Vsp" + tag, d["n_spoofed"], "{}")
        put("Vone" + tag, d["v1"]["mean"], "{:.3f}")
        put("Vonelo" + tag, d["v1"]["lo"], "{:.3f}")
        put("Vonehi" + tag, d["v1"]["hi"], "{:.3f}")
        for x, s in (("P3_RHAT_COST_LA2", "R"), ("P_JOINT_EIG_COST", "J")):
            put("V" + s + tag, d["contrasts"][x]["rrr"], "{:.2f}")
            put("V" + s + "lo" + tag, d["contrasts"][x]["lo"], "{:.2f}")
            put("V" + s + "hi" + tag, d["contrasts"][x]["hi"], "{:.2f}")
    put("Vndev", n["7V"]["n_dev"], "{}")
    put("VPA", n["7V"]["hai-21.03"]["regret"]["P_PROBE"])
    put("VJregA", n["7V"]["hai-21.03"]["regret"]["P_JOINT_EIG_COST"])
    put("VCregA", n["7V"]["hai-21.03"]["regret"]["P_JOINT_HEIG_COST"])
    put("VprA", n["7V"]["hai-21.03"]["regret"]["PRIOR_ONLY"])
    put("cdR", n["7U"]["cliffs_delta"]["P3_RHAT_COST_LA2"], "{:.2f}")
    put("cdJ", n["7U"]["cliffs_delta"]["P_JOINT_EIG_COST"], "{:.2f}")
    for blk, tag in (("7L", "L"), ("7T", "T"), ("7U", "U")):
        put("calib" + tag, n[blk]["calibration_required"], "{:.0f}")
        th = {p: v["A_TRUST_HARVEST"] for p, v in n[blk]["regret"].items()}
        put("thRand" + tag, th["P0_RANDOM_COST_MATCHED"])
    put("thRandJT", n["7T"]["regret"]["P_RAND_JEIG"]["A_TRUST_HARVEST"])
    put("Vfailh", n["7V"]["model_params"]["p_fail_healthy"], "{:.3f}")
    put("Vfails", n["7V"]["model_params"]["p_fail_spoofed"], "{:.3f}")
    for blk, tag in (("7L", "L"), ("7T", "T"), ("7U", "U")):
        put("nW" + tag, n[blk]["n_worlds"], "{}")
        put("nE" + tag, n[blk]["n_episodes"], "{:,}")
    letters = str.maketrans("0123456789", "abcdefghij")
    lines = [r"\newcommand{\num" + k.translate(letters) + "}{" + v.replace(",", "{,}") + "}" for k, v in m.items()]
    (TAB / "numbers.tex").write_text("% generated by scripts/paper/make_figures.py; do not edit\n" + "\n".join(lines) + "\n")


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    forest()
    scope()
    heat()
    tables()
    print("figures ->", FIG, "\ntables  ->", TAB)


if __name__ == "__main__":
    main()
