# Phase 7C-A — Cost Attribution Gates (PREREGISTERED)

All gates are evaluated on `phase7c_cost_attribution_main` at λ = 1.0 unless stated.
Statistics: paired Wilcoxon, paired bootstrap 95% CI (5000 resamples), Cliff's δ.

### CAG-1 — Cost baseline validity
PASS iff all of:
- `tests/test_cost_attribution.py::TestCAG1Validity` passes: equal costs → P3_nom_cost ≡ P3_nom;
  λ = 0 → ≡ P3_nom; every P3_nom_cost choice equals the independent argmax of (nominal EIG − λ·cost).
- Empirically, P3_nom_cost diverges from P3_nom in at least one main-run cell (costs differ in B, C, D).

### CAG-2 — Cost attribution (Scenario C)
PASS iff in C (all σ pooled, λ = 1.0), P3_nom_cost vs P3_nom shows **all** of:
- decision divergence > 0;
- lower mean cost per query (total_cost / n_queries) for P3_nom_cost, 95% CI of the paired difference excluding 0;
- more queries per episode (paired mean Δn_queries > 0, CI excluding 0).
The TPM direction of COST in C is **reported, not required**.

### CAG-3 — Incremental HADES contribution (PRIMARY)
Contrast: HADES_INCREMENT = P5_full − P3_nom_cost. Family: {B, D} × σ ∈ {0.10, 0.20, 0.30} (6 cells).
POSITIVE iff at least one cell has: mean Δ > 0, mean 95% CI > 0, and Holm-adjusted Wilcoxon p < 0.05.
Cliff's δ and Δcost must be reported alongside.
NEGATIVE iff at least one cell has mean 95% CI < 0 and Holm p < 0.05 (Case D), with no POSITIVE cell.
Otherwise NULL.

### CAG-4 — φ attribution
A φ contribution may be claimed only if, in at least one D cell, PHI = P5_full − P5_no_phi has:
decision divergence > 0, and Holm-significant (PHI family, 9 cells) nonzero TPM effect with CI excluding 0.
The sign is reported. A φ claim in HADES's favour also requires CAG-3 POSITIVE (spec Case E).

### CAG-5 — No baseline contamination
PASS iff `tests/test_cost_attribution.py::TestCAG5Contamination` passes (P3_nom / P3_nom_cost invariant to
r̂ and φ̂; their source references no `*_estimated` or `*_true` fields) and `test_existing_p3_is_phi_invariant` passes.
Also: no run-level integrity flag (beliefs_sum_to_one, budget_consistent) is False.

## Interpretation map (spec cases, applied per primary cell)

| Case | COST | HADES_INCREMENT |
|------|------|-----------------|
| A — incremental effect | any | > 0, CI > 0 |
| B — cost explains | ≈ TOTAL | CI ∋ 0 |
| C — no effect | CI ∋ 0 | CI ∋ 0 (and TOTAL CI ∋ 0) |
| D — cost helps, HADES hurts | > 0 | < 0, CI < 0 |
| E — φ-specific | — | A holds and PHI > 0 Holm-significant |
