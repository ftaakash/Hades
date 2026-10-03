# STATUS: Phase 7B Evidence Frozen

**Date**: 2026-10-03
**Commit**: `60c9a25`
**Test count**: 357 passed, 0 failed

## Phase 7B Results (DO NOT MODIFY)

- Raw data: `results/raw/phase7b_stress_20261002T190156Z.json`
- Analysis: `results/phase7b_sigma_analysis.json`
- Ablation: `results/phase6d_ablation_analysis.json`

## Key Findings (Historical Record)

| σ | P5 vs P3 (B) | P5_no_rel vs P3 (B) |
|---|---|---|
| 0.00 | −0.023 | −0.111 |
| 0.10 | +0.010 | −0.065 |
| 0.30 | +0.022 | −0.035 |

- P5_no_cost ≡ P3 across all σ
- P5_no_phi ≡ P5_full across all σ
- φ channel: INACTIVE (root cause: `under_targeted_attack=False`)

## Constraint

Phase 7C is a NEW experiment. It must not retroactively modify any Phase 7B result files.
