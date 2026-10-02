# Phase 6 — Kill Gates

**Status:** FROZEN before main sweep  
**Thresholds defined here are immutable after the first sweep episode runs.**

---

## G6-1 — Primary Utility

**Question:** Does P5 produce a meaningful aggregate improvement over P3?

**Condition to KILL:**
- Paired Wilcoxon p-value > 0.05 (two-sided)
- AND 95% bootstrap CI of median paired difference includes ≤ 0

**Action:** Kill the broad "P5 is superior" claim. Retain only supported behavioral or condition-specific findings.

---

## G6-2 — Clean Non-Regression

**Question:** Does P5 degrade performance when telemetry is clean (R0)?

**Frozen tolerance:** 0.05 TPM

**Condition to KILL:**
- Mean `TPM(P5) - TPM(P3) < -0.05` under R0 (aggregated across scenarios, estimators, seeds)

**Action:** Reject a broad robust-method claim. Narrow or reframe.

**Note:** This is a non-regression test, NOT a superiority test. Do not claim P5 superiority under R0 unless separately justified.

---

## G6-3 — Robustness Breadth

**Question:** Does the positive effect occur broadly or only in cherry-picked conditions?

**Condition to KILL:**
- Positive mean paired TPM difference in fewer than **3 out of 5** scenarios (across contaminated conditions R1–R4a)

**Action:** Do not claim general robustness. Describe the result as condition-specific.

---

## G6-4 — Estimator Dependence

**Question:** Does the benefit survive reliability misspecification?

**Condition to KILL:**
- The P5 advantage (positive median paired TPM difference) disappears under ALL non-clean estimator conditions (Noisy, Miscal-under, Miscal-over, Adversarial)

**Action:** Do not claim broad reliability-aware robustness. Report estimator sensitivity as a limitation/finding.

---

## G6-5 — Seed Stability

**Question:** Is the effect stable across seeds?

**Condition to KILL:**
- 95% bootstrap CI of median paired TPM difference includes zero in **4 or more** of the 5 scenarios

**Action:** Do not rely on pooled averages. Downgrade the claim.

---

## Interpretation Rules

1. Gate verdicts are **PASS**, **CONDITIONAL**, or **KILL**
2. CONDITIONAL = partial failure that narrows but does not eliminate the claim
3. A single KILL does not invalidate the entire study — it narrows the supported claim
4. Negative results remain valid results (Rule 7)
5. Do not change thresholds after observing data (Rule 1)
