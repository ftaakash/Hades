# Phase 7C-A — Cost-Matched Attribution Protocol (PREREGISTERED)

**Experiment IDs**: `phase7c_cost_attribution_pilot`, `phase7c_cost_attribution_main`
**Frozen**: before any 7C-A run. Post-run changes need a new experiment ID.
**Code base**: Phase 7C repair `173d864` + this protocol's commit (P5 unchanged).

## 1. Pre-run validation finding (changes the design)

The spec defined `P3 = nominal EIG`. **The existing P3 (`hades/policies/p3_ig.py`) is not nominal.**
It passes the policy-visible `r_hat` into the contaminated likelihood. Its choice flips when only
`r_hat` changes (`tests/test_cost_attribution.py::test_existing_p3_is_rhat_aware`). It is φ-invariant.

Consequences:
- Phase 6D's `P5_no_cost ≡ P3` means "P5 minus cost equals **r̂-aware** EIG". Reliability awareness was
  already in the baseline, so the Phase 6/7B P5−P3 contrasts (including the 7B B/σ=0.30 +0.022)
  measure **cost (+φ after 7C)** on top of r̂-aware EIG. They do not measure reliability awareness.
- The spec's `P3_cost` built on the existing P3 would be `r̂-EIG − λ·Cost`, which is **algebraically identical
  to P5_no_phi** (`test_rhat_cost_identical_to_p5_no_phi`).

Decision (the user was asked twice and skipped both times; the agent's recommended option was taken):
run **both** the true nominal baselines (as the spec intends) and the legacy r̂-aware P3 (continuity with 6/7B).

## 2. Policy arms (5 run; 6 defined)

| Arm | Score | Reads r̂ | Reads φ̂ | Cost | Code |
|-----|-------|---------|---------|------|------|
| `P3_nom` | EIG(r=1, φ=0) | no | no | no | `p3_cost.NominalIGPolicy` |
| `P3_nom_cost` | EIG(r=1, φ=0) − λ·Cost | no | no | yes | `p3_cost.NominalIGCostPolicy` |
| `P3_rhat` | EIG(r̂) — legacy P3 | yes | no | no | `p3_ig.IGPolicy` |
| `P5_no_phi` | EIG(r̂) − λ·Cost (≡ P3_rhat_cost) | yes | no | yes | `run_mechanism_ablation.P5NoPhi` |
| `P5_full` | EIG(r̂, φ̂ mixture) − λ·Cost | yes | yes | yes | `p5_robust_voi.RobustVoIPolicy` (7C-frozen) |

All arms share the menu, the table construction, the affinity default of 0.5, the budget filter and the
alphabetical-max tie-break.

## 3. Contrasts

| Name | Definition | Role |
|------|-----------|------|
| **HADES_INCREMENT** | P5_full − P3_nom_cost | **PRIMARY** (spec's P5 − P3_cost) |
| COST | P3_nom_cost − P3_nom | secondary |
| TOTAL | P5_full − P3_nom | secondary |
| TOTAL_LEGACY | P5_full − P3_rhat | secondary (7B continuity) |
| RELIABILITY | P5_no_phi − P3_nom_cost | secondary (r̂ given cost) |
| PHI | P5_full − P5_no_phi | secondary (φ given r̂ + cost) |

Identity: HADES_INCREMENT = RELIABILITY + PHI (exact for per-pair differences).

## 4. Matrix

| | Pilot | Main |
|---|---|---|
| Scenarios | B, C, D | B, C, D |
| σ (NoisyEstimator) | 0.10, 0.30 | 0.10, 0.20, 0.30 |
| Regimes (as 7B) | R1_missing(0.25), R2_stale(0.33), R3_misleading(0.25), R4a_targeted(0.75) | same |
| λ | 0.5, 1.0, 2.0 | 0.5, 1.0, 2.0 |
| Seeds | 1000–1024 (25, disjoint from main) | 0–99 (100) |
| Budget | 10.0 | 10.0 |

**Pairing**: for each (scenario, σ, regime, λ, seed) all 5 arms use the same true hypothesis
(`Random(seed ^ 0xCAFE)`), env seed, corruptor RNG (`seed ^ 0xBEEF`) and estimator RNG (`seed ^ 0xDEAD`).
Estimator draws don't depend on the chosen source, so the step-k menus are identical across arms.
Corruptors are stateless.

## 5. Analysis unit and primary test

- **Primary cell** = scenario × σ at **λ = 1.0**, pooled over the 4 regimes (n = 400 pairs in main).
- **Primary family (CAG-3)**: HADES_INCREMENT in the 6 cells {B, D} × {0.10, 0.20, 0.30}.
  Holm correction on paired Wilcoxon p across these 6.
  Preregistered direction: **positive**.
- Secondary families: each secondary contrast across the 9 cells (B, C, D × σ) at λ = 1.0, Holm within the family.
- λ = 0.5 and 2.0: reported descriptively with the same statistics, no gate.
- The pilot is diagnostic only and makes no inferential claims.

## 6. Metrics per pair

TPM (primary), mean/median Δ, paired bootstrap 95% CI (mean and median, 5000 resamples), Wilcoxon p,
Cliff's δ, fraction of pairs >0 and <0, ΔCost (total_cost), Δn_queries, correct-hypothesis rate,
high-φ queries, decision divergence (query sequence differs).
Not implemented: queries-to-correct-hypothesis (no belief trajectory is stored). Noted as a limitation.

## 7. Frozen — must not change after the pilot

λ grid, costs, affinities, corruption severities, φ̂ handling, scenario definitions, primary metric,
gates, seed lists. If the pilot exposes an implementation bug: fix it, add a test, make a new commit,
and rerun the pilot.
