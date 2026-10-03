# Phase 7C.6–7C.7 — φ Micro-Pilot Verdict

**Experiment**: `phase7c_phi_pilot` (exploratory, not confirmatory)
**Commit under test**: `173d864`
**Raw**: `results/raw/phase7c_pilot_20261003T173025Z.json` (7,200 episodes)
**Analysis**: `results/phase7c_pilot_analysis.json` · script `scripts/run_phi_pilot.py`
**Matrix**: B, D × {R1, R2, R3, R4a} × σ∈{0.10, 0.30} × λ∈{0.5, 1, 2} × 50 seeds × {P3, P5_full, P5_no_phi}

## Answers

| Q | Result |
|---|--------|
| Q1 decision divergence (P5_full ≠ P5_no_phi query sequence) | **95–97%** of paired episodes, every cell |
| Q2 high-φ queries / episode (full vs no_phi) | D: **0.61 vs 2.80**; B: 0.45 vs 1.84 |
| Q3 TPM, P5_full − P5_no_phi | D: −0.0090 [−0.0175, −0.0010], δ=0.002; B: −0.0262 [−0.0407, −0.0108], δ=−0.042 |
| Q3 under R4a_targeted (D) | −0.0059 [−0.0244, +0.0116], p=0.65 — **no benefit even under targeted attack** |
| Q4 TPM, P5_full − P3 (D) | mean −0.0242 [−0.0354, −0.0130]; but Wilcoxon p=0.97, δ=+0.052 (skewed: median/rank not negative) |

## PHI Gates

| Gate | Status | Evidence |
|------|--------|----------|
| PHI-1 integration | PASS | `test_eig_decreases_monotonically_with_phi`, normalization test |
| PHI-2 value sensitivity | PASS | `test_voi_changes_with_phi_under_attack` |
| PHI-3 ranking sensitivity | PASS | `test_p5_selection_changes_with_phi` |
| PHI-4 D decision relevance | **PASS** | 95.4% divergence in D |
| PHI-5 no oracle leakage | PASS | `test_p5_reads_no_oracle_fields`; flag derived from φ̂ only |

## Interpretation (frozen before any confirmatory run)

1. The φ channel is now **live**. It strongly changes behaviour: P5 avoids high-φ sources about 4.6× more than P5_no_phi.
2. That behaviour change does **not** improve hypothesis identification. On TPM, φ-awareness is neutral to slightly harmful in every aggregate, and neutral under R4a targeted attack.
3. Likely mechanism (hypothesis, not tested here): high-φ sources in D are also the informative ones. The evaluator's belief update does not model forgery, so avoiding those sources costs information without a matching robustness gain.
4. The PHI gates check mechanics, not performance. PHI-4 passing does not predict that G7C-3 (P5_full − P3 > 0 in D) will pass. The pilot points against it.

## Recommendation

The confirmatory D run (7C.9–7C.12) is technically unlocked. Its expected outcome, given this pilot, is a **negative or null G7C-3**. Running it would turn that into a preregistered result. Do not retune φ, thresholds, or the forged distribution to rescue the effect: that would be post-hoc. Any redesign needs a new experiment ID.
