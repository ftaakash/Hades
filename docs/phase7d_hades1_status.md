# Phase 7D — HADES 1.0 Final Status (FROZEN)

**Frozen at**: commit `3c236b6` · tag `hades-1.0-final` · 2026-10-07
**Rule**: HADES 1.0 code and results are historical. Nothing in `hades/` (except the new
`hades/probe_experiment/` package) or `results/` from Phases 0–7C is modified by HADES 2.0.

## Scientific record

| Claim | Status | Evidence |
|-------|--------|----------|
| P5 broad superiority under contaminated telemetry | **KILLED** | Phase 6 verdict (Cliff's δ = 0.05, negligible); `results/phase6_verdict.json` |
| Cost-aware acquisition effect | **SUPPORTED** | 7C-A COST contrast; CAG-2 PASS (`docs/phase7c_cost_attribution_verdict.md`) |
| Reliability (r̂) increment over cost-aware nominal EIG | **NARROW / SMALL** | 7C-A CAG-3: B σ=0.10 only, +0.067 [0.029, 0.104], δ = 0.095; r̂-weighting is prior art |
| φ (manipulation-risk) channel | **ACTIVE BUT NOT SUPPORTIVE** | 7C pilot + 7C-A CAG-4: φ changes decisions, PHI ≤ 0 in D |
| Public CDB sample transfer | **KILLED** | `STATUS_CDB_SAMPLE_KILLED.md` |
| Full CDB evaluation | **DEFERRED** | `docs/future/cdb_full_access_plan.md` |

## Important methodological finding (7C-A)
The legacy P3 baseline is r̂-aware EIG, not nominal EIG. So Phase 6/7B "P5 − P3" contrasts had reliability
awareness on both sides. The Phase 7B B/σ=0.30 effect (+0.022) reproduces exactly as `P5_no_phi − P3_rhat`,
i.e. as a cost effect.

## 7C-B status
The D-only φ confirmatory run (7C-B) was not run as a separate experiment. The 7C-A main run includes
D × σ{0.10, 0.20, 0.30} × 100 paired seeds × 4 regimes × 3 λ, with all 7C-B contrasts
(P5−P3_rhat, P5−P3_nom_cost, P5−P5_no_phi). **Recorded as covered by 7C-A main.**
This decision was made because the researcher did not choose an option when asked.

## Lineage
| Phase | Commit |
|-------|--------|
| 5A freeze | `99ea4ea` |
| 6 main | `c82a88f` |
| 6D ablation | `bba40a6` |
| 7B σ stress | `60c9a25` |
| 7C φ repair | `173d864` |
| 7C φ pilot | `fa43454` |
| 7C-A prereg / pilot / main | `d400437` / `0fafa44` / `3c236b6` |
