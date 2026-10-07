# Phase 7V Report — HAI real-data replication of 7U (2026-10-07)

**Verdict: INVALID** (pre-registered rule: V-1 failed, so the HG gates cannot decide anything).
Experiment `phase7v_hai_replication_v1`; protocol frozen at dd8d008; run at 84acf18 (a file-path fix to the
dataset hashing, made after a crash that happened before any data was read). Raw
`results/raw/phase7v_hai_replication_v1.json.gz` (sha256 of the JSON 63464949…a0fb). Statistics
`results/analysis/phase7v_hai_replication_v1_statistics.json`; verdict `results/phase7v_hai_replication_v1_verdict.json`.

## 1. What failed

V-1 asks whether the HAI evidence, as mapped, helps the decision at all: the regret of the prior-only decision
minus P3_NOM's regret must have a 95% CI above 0.

| Version | Episodes (attack / spoofed) | Prior-only − P3_NOM | 95% CI | V-1 |
|---|---|---|---|---|
| 21.03 (primary) | 100 (50 / 19) | +0.040 | [−0.041, +0.119] | fail |
| 22.04 (secondary) | 98 (49 / 15) | −0.083 | [−0.172, +0.004] | fail |

With 6 reads of 30 s change alarms, the evidence does not reliably beat guessing from the prior. On 22.04 every
deterministic policy did worse than the prior-only decision. The comparison of belief models is therefore not
tested by this experiment, and no claim, positive or negative, about 7U follows from it.

## 2. Gate table (21.03, reported for completeness; not a verdict)

| Gate | Result |
|---|---|
| HG-1 C vs R (P3_RHAT_COST_LA2) | RRR +0.09, 95% CI [−0.18, +0.30]: fail |
| HG-2 C vs J (P_JOINT_EIG_COST) | RRR **−0.56**, 95% CI [−1.44, −0.12]: fail, J clearly better |
| HG-3 normal non-regression | pass (−0.004) |
| HG-4 spend | pass |
| HG-5 leakage | pass |
| HG-6 halves | fail |

22.04: RRR +0.01 vs R [−0.16, +0.15], −0.03 vs J [−0.20, +0.11].

## 3. Mean normalised regret (21.03)

| Policy | All | Normal | h1 (P1) | h2 (P2/P3) | Spoofed attacks | Unspoofed attacks |
|---|---|---|---|---|---|---|
| PRIOR_ONLY | 0.215 | 0.200 | 0.500 | 0.000 | 0.263 | 0.210 |
| P0_RANDOM | 0.223 | 0.176 | 0.435 | 0.130 | 0.421 | 0.177 |
| P3_NOM | 0.175 | 0.000 | 0.304 | 0.389 | 0.447 | 0.290 |
| P3_RHAT_COST(_LA2) | 0.232 | 0.004 | 0.696 | 0.259 | 0.605 | 0.371 |
| **P_JOINT_HEIG_COST** | 0.210 | 0.000 | 0.522 | 0.333 | 0.447 | 0.403 |
| P_JOINT_EIG_COST | 0.135 | 0.000 | 0.304 | 0.241 | 0.395 | 0.194 |
| P_PROBE | 0.105 | 0.000 | 0.174 | 0.241 | 0.211 | 0.210 |

## 4. Exploratory observations (not claims)

1. No deterministic policy ever probed (mean probes 0.0 on both versions); only random did. The dev-fitted
   probe was weak (FAIL 0.355 healthy vs 0.674 spoofed) at twice the cost of a query.
2. On 21.03 the ordering is the reverse of 7U: J and P_PROBE have the lowest regret, C is behind both. Had
   V-1 passed, HG-2 would have produced KILL. This was foreshadowed by the disclosed development look
   (protocol §6), where C and J were level.
3. The joint-belief policies help most on spoofed attacks versus R (RRR +0.26 on 21.03, +0.16 on 22.04),
   the cell 7U predicts, but the counts (19 and 15 episodes) are far too small for any claim.
4. Missed P1 attacks dominate the regret; the change-alarm sensor model is the bottleneck, not acquisition.

## 5. What this means

- The 7U PROCEED stands as a **simulator-only** result. It has no real-data support yet, and the one real-data
  look we have points the other way on the J contrast.
- A new real-data attempt needs evidence that passes V-1 *before* any acquisition contrast: a stronger
  per-source detector (longer windows or a learned residual), more reads per budget, or a dataset with more
  attacks per class. Any such change is a new experiment ID with a new frozen protocol; 7V is not re-run.
- For the paper: report 7V as a pre-registered real-data attempt that was invalid by its own validity gate.
