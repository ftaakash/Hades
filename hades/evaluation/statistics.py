"""hades/evaluation/statistics.py — Statistical analysis for Phase 6.

Implements the pre-registered analysis plan from docs/phase6_protocol.md:

- Paired Wilcoxon signed-rank test (primary)
- Paired bootstrap confidence intervals (10k resamples, 95%)
- Cliff's delta effect size
- Holm correction for secondary family
- Kill gate evaluation (G6-1 through G6-5)

All functions operate on arrays of paired episode-level observations.
The inferential unit is the episode, not the turn.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Paired Wilcoxon signed-rank test
# ---------------------------------------------------------------------------

@dataclass
class WilcoxonResult:
    statistic: float
    p_value: float
    n_pairs: int

    def to_dict(self) -> Dict:
        return asdict(self)


def paired_wilcoxon(
    values_a: List[float],
    values_b: List[float],
) -> WilcoxonResult:
    """Paired Wilcoxon signed-rank test (two-sided).

    Parameters
    ----------
    values_a : P5 TPM values (one per episode)
    values_b : P3 TPM values (one per episode, same order)

    Returns
    -------
    WilcoxonResult with statistic, p-value, n_pairs
    """
    assert len(values_a) == len(values_b), "Unpaired arrays"
    n = len(values_a)

    # Compute differences, exclude zeros
    diffs = [a - b for a, b in zip(values_a, values_b)]
    nonzero = [(abs(d), d) for d in diffs if abs(d) > 1e-12]

    if len(nonzero) < 2:
        # Not enough non-zero differences for a meaningful test
        return WilcoxonResult(statistic=0.0, p_value=1.0, n_pairs=n)

    try:
        from scipy.stats import wilcoxon as _wilcoxon
        stat, p = _wilcoxon(values_a, values_b, alternative='two-sided')
        return WilcoxonResult(statistic=float(stat), p_value=float(p), n_pairs=n)
    except ImportError:
        # Fallback: manual Wilcoxon implementation
        return _manual_wilcoxon(diffs, n)


def _manual_wilcoxon(diffs: List[float], n: int) -> WilcoxonResult:
    """Manual Wilcoxon signed-rank for environments without scipy."""
    nonzero = [(abs(d), 1 if d > 0 else -1) for d in diffs if abs(d) > 1e-12]
    if len(nonzero) < 2:
        return WilcoxonResult(statistic=0.0, p_value=1.0, n_pairs=n)

    # Rank by absolute value
    nonzero.sort(key=lambda x: x[0])
    nr = len(nonzero)

    # Assign ranks (average ties)
    ranks = [0.0] * nr
    i = 0
    while i < nr:
        j = i
        while j < nr and abs(nonzero[j][0] - nonzero[i][0]) < 1e-12:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = avg_rank
        i = j

    # W+ = sum of ranks for positive differences
    w_plus = sum(r for r, (_, sign) in zip(ranks, nonzero) if sign > 0)
    w_minus = sum(r for r, (_, sign) in zip(ranks, nonzero) if sign < 0)
    w = min(w_plus, w_minus)

    # Normal approximation for p-value (n >= 10)
    mean_w = nr * (nr + 1) / 4.0
    std_w = math.sqrt(nr * (nr + 1) * (2 * nr + 1) / 24.0)
    if std_w < 1e-12:
        return WilcoxonResult(statistic=w, p_value=1.0, n_pairs=n)

    z = (w - mean_w) / std_w
    # Two-sided p-value from normal approximation
    p_value = 2.0 * _norm_cdf(-abs(z))

    return WilcoxonResult(statistic=w, p_value=p_value, n_pairs=n)


def _norm_cdf(z: float) -> float:
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Paired bootstrap confidence interval
# ---------------------------------------------------------------------------

@dataclass
class BootstrapResult:
    ci_low: float
    ci_high: float
    median_diff: float
    mean_diff: float
    n_resamples: int

    def to_dict(self) -> Dict:
        return asdict(self)


def paired_bootstrap_ci(
    values_a: List[float],
    values_b: List[float],
    n_resamples: int = 10000,
    alpha: float = 0.05,
    seed: int = 42,
) -> BootstrapResult:
    """Paired bootstrap CI for median difference (P5 - P3).

    Resamples episodes (not turns), preserving the pairing.
    """
    assert len(values_a) == len(values_b), "Unpaired arrays"
    n = len(values_a)
    if n == 0:
        return BootstrapResult(ci_low=0.0, ci_high=0.0, median_diff=0.0,
                               mean_diff=0.0, n_resamples=n_resamples)

    diffs = [a - b for a, b in zip(values_a, values_b)]
    rng = random.Random(seed)

    boot_medians = []
    for _ in range(n_resamples):
        sample = [diffs[rng.randint(0, n - 1)] for _ in range(n)]
        sample.sort()
        mid = len(sample) // 2
        if len(sample) % 2 == 0:
            boot_medians.append((sample[mid - 1] + sample[mid]) / 2.0)
        else:
            boot_medians.append(sample[mid])

    boot_medians.sort()
    lo_idx = int(math.floor(alpha / 2.0 * n_resamples))
    hi_idx = int(math.ceil((1.0 - alpha / 2.0) * n_resamples)) - 1
    lo_idx = max(0, min(lo_idx, n_resamples - 1))
    hi_idx = max(0, min(hi_idx, n_resamples - 1))

    diffs_sorted = sorted(diffs)
    mid = len(diffs_sorted) // 2
    if len(diffs_sorted) % 2 == 0:
        obs_median = (diffs_sorted[mid - 1] + diffs_sorted[mid]) / 2.0
    else:
        obs_median = diffs_sorted[mid]

    return BootstrapResult(
        ci_low=boot_medians[lo_idx],
        ci_high=boot_medians[hi_idx],
        median_diff=obs_median,
        mean_diff=sum(diffs) / n,
        n_resamples=n_resamples,
    )


# ---------------------------------------------------------------------------
# Cliff's delta effect size
# ---------------------------------------------------------------------------

@dataclass
class CliffsResult:
    delta: float
    interpretation: str  # negligible, small, medium, large
    n_a: int
    n_b: int

    def to_dict(self) -> Dict:
        return asdict(self)


def cliffs_delta(
    values_a: List[float],
    values_b: List[float],
) -> CliffsResult:
    """Cliff's delta: nonparametric effect size.

    δ = (#(a > b) - #(a < b)) / (n_a × n_b)

    Interpretation thresholds (Romano et al. 2006):
    |δ| < 0.147 → negligible
    |δ| < 0.33  → small
    |δ| < 0.474 → medium
    |δ| >= 0.474 → large
    """
    na, nb = len(values_a), len(values_b)
    if na == 0 or nb == 0:
        return CliffsResult(delta=0.0, interpretation="negligible", n_a=na, n_b=nb)

    more = 0
    less = 0
    for a in values_a:
        for b in values_b:
            if a > b:
                more += 1
            elif a < b:
                less += 1

    delta = (more - less) / (na * nb)
    abs_d = abs(delta)

    if abs_d < 0.147:
        interp = "negligible"
    elif abs_d < 0.33:
        interp = "small"
    elif abs_d < 0.474:
        interp = "medium"
    else:
        interp = "large"

    return CliffsResult(delta=delta, interpretation=interp, n_a=na, n_b=nb)


# ---------------------------------------------------------------------------
# Holm correction
# ---------------------------------------------------------------------------

def holm_correction(p_values: List[Tuple[str, float]]) -> List[Tuple[str, float, bool]]:
    """Holm-Bonferroni step-down correction for multiple comparisons.

    Parameters
    ----------
    p_values : list of (label, raw_p)

    Returns
    -------
    list of (label, adjusted_p, significant) sorted by adjusted_p
    """
    if not p_values:
        return []

    n = len(p_values)
    sorted_ps = sorted(p_values, key=lambda x: x[1])
    adjusted = []
    prev_adj = 0.0

    for i, (label, raw_p) in enumerate(sorted_ps):
        adj_p = min(1.0, raw_p * (n - i))
        adj_p = max(adj_p, prev_adj)  # enforce monotonicity
        prev_adj = adj_p
        adjusted.append((label, adj_p, adj_p < 0.05))

    return adjusted


# ---------------------------------------------------------------------------
# Kill gate evaluation
# ---------------------------------------------------------------------------

@dataclass
class GateVerdict:
    gate_id: str
    status: str  # PASS, CONDITIONAL, KILL
    detail: str

    def to_dict(self) -> Dict:
        return asdict(self)


def _full_stats(tpm_a: List[float], tpm_b: List[float],
                boot_resamples: int = 5000, boot_seed: int = 42) -> Dict:
    """Compute mean, median, both CIs, Wilcoxon p, Cliff's δ for a paired slice."""
    diffs = [a - b for a, b in zip(tpm_a, tpm_b)]
    n = len(diffs)
    mean_d = sum(diffs) / n if n else 0.0
    sd = sorted(diffs)
    median_d = sd[n // 2] if n % 2 else (sd[n // 2 - 1] + sd[n // 2]) / 2.0 if n else 0.0

    wilcox = paired_wilcoxon(tpm_a, tpm_b)
    boot = paired_bootstrap_ci(tpm_a, tpm_b, n_resamples=boot_resamples, seed=boot_seed)
    cliff = cliffs_delta(tpm_a, tpm_b)

    # Bootstrap CI for the mean (separate from median CI)
    rng = random.Random(boot_seed + 1)
    boot_means = []
    for _ in range(boot_resamples):
        sample = [diffs[rng.randint(0, n - 1)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lo = int(0.025 * boot_resamples)
    hi = int(0.975 * boot_resamples) - 1
    mean_ci_lo = boot_means[max(0, lo)]
    mean_ci_hi = boot_means[min(hi, len(boot_means) - 1)]

    return {
        "n": n,
        "mean_diff": round(mean_d, 6),
        "median_diff": round(median_d, 6),
        "mean_ci": [round(mean_ci_lo, 6), round(mean_ci_hi, 6)],
        "median_ci": [round(boot.ci_low, 6), round(boot.ci_high, 6)],
        "wilcoxon_p": wilcox.p_value,
        "cliffs_delta": round(cliff.delta, 6),
        "cliffs_interp": cliff.interpretation,
    }


def evaluate_gates(
    pairs: List[Dict],
    clean_tolerance: float = 0.05,
    breadth_threshold: int = 3,
) -> Tuple[List[GateVerdict], Dict]:
    """Evaluate G6-1 through G6-5 on paired episode data.

    Returns (verdicts, diagnostics) where diagnostics contains full
    per-scenario and per-estimator statistics for transparency.

    Gate metric policy (v2 — fixed after Phase 6 review):
    - G6-1: statistical significance AND practical magnitude (Cliff's δ)
    - G6-3: mean difference per scenario (explicitly labeled)
    - G6-4: mean difference + Wilcoxon p + Cliff's δ per estimator
    - G6-5: bootstrap CI for median per scenario
    """
    verdicts = []
    diagnostics = {"per_scenario": {}, "per_estimator": {}}

    # Separate contaminated (R1-R4) from clean (R0)
    contaminated = [p for p in pairs if p["corruption_regime"] != "R0_clean"]
    clean = [p for p in pairs if p["corruption_regime"] == "R0_clean"]

    # ── G6-1: Primary utility ────────────────────────────────────────────
    # Checks BOTH statistical significance AND practical magnitude.
    # A tiny but significant effect at huge N is flagged as CONDITIONAL.
    if contaminated:
        tpm_a = [p["tpm_a"] for p in contaminated]
        tpm_b = [p["tpm_b"] for p in contaminated]
        stats = _full_stats(tpm_a, tpm_b, boot_resamples=10000, boot_seed=42)

        sig = stats["wilcoxon_p"] <= 0.05
        practical = abs(stats["cliffs_delta"]) >= 0.147  # "small" threshold

        detail = (f"p={stats['wilcoxon_p']:.2e}, mean_diff={stats['mean_diff']:.4f}, "
                  f"median_diff={stats['median_diff']:.4f}, "
                  f"mean_CI={stats['mean_ci']}, median_CI={stats['median_ci']}, "
                  f"δ={stats['cliffs_delta']:.4f} ({stats['cliffs_interp']})")

        if not sig:
            verdicts.append(GateVerdict("G6-1", "KILL", detail))
        elif sig and not practical:
            verdicts.append(GateVerdict("G6-1", "CONDITIONAL",
                f"Significant but negligible effect size. {detail}"))
        else:
            verdicts.append(GateVerdict("G6-1", "PASS", detail))

        diagnostics["confirmatory"] = stats
    else:
        verdicts.append(GateVerdict("G6-1", "KILL", "No contaminated data"))

    # ── G6-2: Clean non-regression ───────────────────────────────────────
    if clean:
        clean_diffs = [p["tpm_diff"] for p in clean]
        mean_diff = sum(clean_diffs) / len(clean_diffs)
        if mean_diff < -clean_tolerance:
            verdicts.append(GateVerdict("G6-2", "KILL",
                f"Clean mean TPM diff = {mean_diff:.4f} < -{clean_tolerance}"))
        else:
            verdicts.append(GateVerdict("G6-2", "PASS",
                f"Clean mean TPM diff = {mean_diff:.4f} (tolerance ±{clean_tolerance})"))
    else:
        verdicts.append(GateVerdict("G6-2", "PASS", "No clean data to regress on"))

    # ── G6-3: Robustness breadth ─────────────────────────────────────────
    # Uses MEAN difference per scenario (explicitly labeled).
    # Also reports median for transparency.
    if contaminated:
        scenarios = sorted(set(p["scenario"] for p in contaminated))
        positive_scenarios = 0
        scenario_details = []
        for sc in scenarios:
            sc_a = [p["tpm_a"] for p in contaminated if p["scenario"] == sc]
            sc_b = [p["tpm_b"] for p in contaminated if p["scenario"] == sc]
            sc_stats = _full_stats(sc_a, sc_b, boot_resamples=5000,
                                   boot_seed=hash(sc) & 0x7FFFFFFF)
            diagnostics["per_scenario"][sc] = sc_stats

            if sc_stats["mean_diff"] > 0:
                positive_scenarios += 1
            scenario_details.append(
                f"{sc}: mean={sc_stats['mean_diff']:+.4f}, "
                f"median={sc_stats['median_diff']:+.4f}, "
                f"δ={sc_stats['cliffs_delta']:.4f}")

        if positive_scenarios < breadth_threshold:
            verdicts.append(GateVerdict("G6-3", "KILL",
                f"Positive mean in {positive_scenarios}/{len(scenarios)} scenarios "
                f"(need >={breadth_threshold}). {'; '.join(scenario_details)}"))
        else:
            verdicts.append(GateVerdict("G6-3", "PASS",
                f"Positive mean in {positive_scenarios}/{len(scenarios)} scenarios. "
                f"{'; '.join(scenario_details)}"))
    else:
        verdicts.append(GateVerdict("G6-3", "KILL", "No contaminated data"))

    # ── G6-4: Estimator dependence ───────────────────────────────────────
    # Reports FULL stats per estimator: mean, median, Wilcoxon p, Cliff's δ.
    # Survival criterion: positive mean difference with p < 0.10.
    if contaminated:
        estimators = sorted(set(p["estimator_regime"] for p in contaminated))
        non_clean_ests = [e for e in estimators if e != "clean"]
        surviving_ests = 0
        est_details = []
        for est in non_clean_ests:
            est_a = [p["tpm_a"] for p in contaminated if p["estimator_regime"] == est]
            est_b = [p["tpm_b"] for p in contaminated if p["estimator_regime"] == est]
            est_stats = _full_stats(est_a, est_b, boot_resamples=5000,
                                    boot_seed=hash(est) & 0x7FFFFFFF)
            diagnostics["per_estimator"][est] = est_stats

            # Survival: positive mean AND at least marginally significant
            if est_stats["mean_diff"] > 0 and est_stats["wilcoxon_p"] < 0.10:
                surviving_ests += 1
            est_details.append(
                f"{est}: mean={est_stats['mean_diff']:+.4f}, "
                f"median={est_stats['median_diff']:+.4f}, "
                f"p={est_stats['wilcoxon_p']:.2e}, "
                f"δ={est_stats['cliffs_delta']:.4f}")

        if surviving_ests == 0 and len(non_clean_ests) > 0:
            verdicts.append(GateVerdict("G6-4", "KILL",
                f"Benefit gone under all non-clean estimators. "
                f"{'; '.join(est_details)}"))
        elif surviving_ests >= 2:
            verdicts.append(GateVerdict("G6-4", "PASS",
                f"Survives {surviving_ests}/{len(non_clean_ests)} non-clean estimators. "
                f"{'; '.join(est_details)}"))
        else:
            verdicts.append(GateVerdict("G6-4", "CONDITIONAL",
                f"Survives {surviving_ests}/{len(non_clean_ests)} non-clean estimators. "
                f"{'; '.join(est_details)}"))
    else:
        verdicts.append(GateVerdict("G6-4", "KILL", "No contaminated data"))

    # ── G6-5: Seed stability ────────────────────────────────────────────
    # Uses bootstrap CI for median per scenario (consistent with median reporting).
    if contaminated:
        scenarios = sorted(set(p["scenario"] for p in contaminated))
        ci_excludes_zero = 0
        stability_details = []
        for sc in scenarios:
            sc_stats = diagnostics["per_scenario"].get(sc)
            if sc_stats and sc_stats["n"] >= 10:
                ci = sc_stats["median_ci"]
                if ci[0] > 0 or ci[1] < 0:
                    ci_excludes_zero += 1
                stability_details.append(
                    f"{sc}: median_CI=[{ci[0]:.4f},{ci[1]:.4f}]")
            else:
                # Recompute if not already in diagnostics
                sc_pairs = [p for p in contaminated if p["scenario"] == sc]
                if len(sc_pairs) >= 10:
                    boot = paired_bootstrap_ci(
                        [p["tpm_a"] for p in sc_pairs],
                        [p["tpm_b"] for p in sc_pairs],
                        n_resamples=5000, seed=456,
                    )
                    if boot.ci_low > 0 or boot.ci_high < 0:
                        ci_excludes_zero += 1
                    stability_details.append(
                        f"{sc}: median_CI=[{boot.ci_low:.4f},{boot.ci_high:.4f}]")
                else:
                    stability_details.append(f"{sc}: too few pairs")

        n_scenarios = len(scenarios)
        includes_zero_count = n_scenarios - ci_excludes_zero
        if includes_zero_count >= 4:
            verdicts.append(GateVerdict("G6-5", "KILL",
                f"Median CI includes zero in {includes_zero_count}/{n_scenarios} scenarios. "
                f"{'; '.join(stability_details)}"))
        else:
            verdicts.append(GateVerdict("G6-5", "PASS",
                f"Median CI excludes zero in {ci_excludes_zero}/{n_scenarios} scenarios. "
                f"{'; '.join(stability_details)}"))
    else:
        verdicts.append(GateVerdict("G6-5", "KILL", "No contaminated data"))

    return verdicts, diagnostics
