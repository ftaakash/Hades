# Phase 6 — Experimental Protocol

**Status:** FROZEN before main sweep  
**Config:** `configs/experiments/main_v2.yaml`  
**Gates:** `docs/phase6_gates.md`

---

## Research Question

> Does reliability-aware robust VoI acquisition (P5) produce better evidence-acquisition outcomes than nominal EIG (P3) when telemetry is contaminated and telemetry-source reliability is uncertain or manipulated?

## Primary Comparison

**P5** (reliability-aware robust VoI) vs **P3** (nominal EIG)

## Primary Metric

**TPM** — Final posterior mass on the true hypothesis: `P(H_true | E_1:T)`

## Experimental Matrix

| Dimension | Values | Count |
|-----------|--------|-------|
| Scenarios | A, B, C, D, E | 5 |
| Corruption regimes | R0, R1, R2, R3, R4a, R4a+AdvEst | 6 |
| Estimators | Clean, Noisy(σ=0.10), Miscal-under, Miscal-over, Adversarial | 5 |
| Lambda | 0.5, 1.0, 2.0 | 3 |
| Seeds | 0–99, paired across policies | 100 |
| Policies | P0, P1, P2, P3, P4, P4b, P5, P7 | 8 |
| **Total episodes** | | **360,000** |

## Pairing Protocol

For every experimental cell `(scenario, regime, estimator, lambda, seed)`:
- Same seed produces same `true_hypothesis` across all 8 policies
- Same RNG chain for corruptor/estimator noise
- This enables paired statistical comparison: `diff = P5_metric - P3_metric`

## Statistical Analysis

| Component | Method |
|-----------|--------|
| Primary test | Paired Wilcoxon signed-rank, two-sided, α=0.05 |
| Confidence interval | Paired bootstrap, 10,000 resamples, 95% CI |
| Effect size | Cliff's δ |
| Multiple comparison | Holm correction (secondary family) |
| Inferential unit | Episode (not turn) |

## Analysis Hierarchy

1. **Confirmatory**: One aggregate P5-vs-P3 test across contaminated conditions (R1–R4a)
2. **Secondary**: Breakdown by scenario, regime, estimator (Holm-corrected)
3. **Exploratory**: Any post-hoc analysis not defined here

## Clean-Regime Guardrail (R0)

- Non-regression test, NOT superiority
- Tolerance: P5 may degrade TPM by at most **0.05** vs P3 under R0
- R0 episodes excluded from confirmatory analysis

## Secondary Metrics

1. Correct hypothesis rate
2. Posterior quality gap (P5.tpm − P3.tpm)
3. Manipulation-reliance gap
4. Acquisition cost
5. Flip rate (behavioral diagnostic only)

## Pilot Validation

- 5-seed pilot allowed for execution validation ONLY
- Pilot results must NOT enter the inferential dataset
- Pilot verifies: output schema, pairing correctness, runtime, provenance

## Kill Protocol

If any gate G6-1 through G6-5 fires, the corresponding claim is killed or narrowed. See `docs/phase6_gates.md` for exact conditions and actions.

## Provenance

Every result JSON carries: `hades_commit`, Python version, OS, config hash, seed, scenario, corruption regime, estimator regime, lambda, budget, timestamp.
