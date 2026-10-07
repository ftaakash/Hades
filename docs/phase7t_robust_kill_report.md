# Phase 7T Robust Acquisition Pilot — Verdict: KILL

**Experiment**: `phase7t_robust_pilot_v1` · **Date**: 2026-10-07 (deadline 2026-11-11) · **Code commit**: `0a2754c`
**Config SHA-256**: `a6727b05…b5da` · Protocol `docs/phase7t_robust_acquisition_protocol.md`, gates `docs/phase7t_robust_acquisition_gates.md`
**Data**: `results/raw/phase7t_robust_pilot_v1.json.gz` (gzip of the 13.4 MB raw file, SHA-256 of the uncompressed JSON `f398e31b…7d65b`; `gunzip -k` before `analyze_robust_pilot.py`; 400 worlds, seeds 2000000–2000399, 13 conditions × 12 episodes × 8 policies = 499,200 episodes)
**Statistics**: `results/analysis/phase7t_robust_pilot_v1_statistics.json` · **Verdict file**: `results/phase7t_robust_pilot_v1_verdict.json`

## Verdict

**KILL.** Neither candidate passed. Validity checks passed: V-1 (the held-out attacker raises P3_NOM regret by
0.118, 95% CI [0.109, 0.128]), RG-5 (spend exactly matched in every episode), RG-6 (leak tests pass).
Calibration asked for 400 worlds (the pre-registered cap; the binding pair needed 531).

| Gate | P_RAND_JEIG | P_MINIMAX_JEIG |
|---|---|---|
| RG-1 RRR vs P_JOINT_EIG_COST (≥ 0.10, 97.5% CI lower > 0) | **−0.186** [−0.281, −0.097] FAIL | **−0.017** [−0.081, 0.044] FAIL |
| RG-2 RRR vs random (≥ 0.10, 97.5% CI lower > 0) | 0.084 [0.027, 0.138] FAIL | **0.214** [0.145, 0.280] PASS |
| RG-3 known families, ȳ(cand) − ȳ(J) | −0.022 [−0.029, −0.014] PASS | +0.023 [0.017, 0.029] FAIL |
| RG-4 clean, ȳ(cand) − ȳ(J) | +0.034 [0.027, 0.041] FAIL | +0.007 [0.003, 0.010] PASS |
| RG-7 RRR > 0 vs both, each budget and half | FAIL (all negative vs J) | FAIL (B1, B2, odd half negative vs J) |

Neither robust policy beats the non-robust comparator on the attacker it was not designed for. Randomisation
pays for robustness with a clear loss on the held-out and clean worlds; the minimax policy matches
P_JOINT_EIG_COST on the held-out attacker but is worse on the known attacker families.

## Mean normalised regret by attacker family (descriptive, all 8 policies)

| Policy | CLEAN | A_DECOY_MIGRATE (held-out) | A_COVER | A_MISATTRIB | A_TRUST_HARVEST |
|---|---|---|---|---|---|
| P0_RANDOM_COST_MATCHED | 0.091 | 0.139 | 0.178 | 0.175 | **0.120** |
| P3_NOM | 0.049 | 0.130 | 0.290 | 0.253 | 0.236 |
| P3_RHAT_COST | 0.032 | 0.114 | 0.225 | 0.177 | 0.242 |
| P_JOINT_HEIG_COST | **0.016** | **0.051** | 0.080 | 0.168 | 0.217 |
| P_JOINT_EIG_COST | 0.043 | 0.108 | 0.147 | 0.177 | 0.199 |
| P_PROBE | 0.018 | 0.061 | **0.078** | 0.183 | 0.191 |
| P_RAND_JEIG | 0.077 | 0.128 | 0.168 | 0.174 | 0.115 |
| P_MINIMAX_JEIG | 0.050 | 0.109 | 0.204 | **0.166** | 0.220 |

## Exploratory observations (not pre-registered; not claims)

1. Two reference policies, P_JOINT_HEIG_COST (hypothesis-only information per cost under the joint model) and
   P_PROBE, have roughly half the held-out-attacker regret of P_JOINT_EIG_COST (0.051 and 0.061 vs 0.108). The
   choice of the v2 primary comparator, not robustness machinery, is the larger lever here; it would need its own
   pre-registered test before any claim.
2. The v2 observation replicates on new worlds: random acquisition (0.120) and P_RAND_JEIG (0.115) beat every
   deterministic model-based policy against the policy-aware trust-harvest attacker. Randomisation helps exactly
   where the attacker conditions on the defender's choices, and costs elsewhere.
3. No single policy is best on every family; the ranking is attacker-dependent.

## Consequence

Per protocol §7 this is reported as a further negative result. The robust-acquisition method claim is not pursued.
HADES 2.0 now has two pre-registered negative results (v2 probe value, 7T robustness), which support a
negative-results / benchmark-artifact framing rather than a novel-method paper. The HADES 1.0 write-up remains the
guaranteed output.
