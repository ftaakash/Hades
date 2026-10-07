# Phase 7U Joint Source-State Belief Pilot — Verdict: PROCEED

**Experiment**: `phase7u_joint_belief_v1` · **Date**: 2026-10-07 (deadline 2026-11-11) · **Code commit**: `1252b2d` (frozen at `d4f2e75`)
**Config SHA-256**: `e7a5fef7…13a3` · Protocol `docs/phase7u_joint_belief_protocol.md`, gates `docs/phase7u_joint_belief_gates.md`
**Data**: `results/raw/phase7u_joint_belief_v1.json.gz` (gzip; SHA-256 of the uncompressed JSON `197a497d…31785ad1`; `gunzip -k` before
`analyze_joint_pilot.py`; 400 worlds, seeds 3000000–3000399, 16 conditions × 12 episodes × 7 policies = 537,600 episodes)
**Statistics**: `results/analysis/phase7u_joint_belief_v1_statistics.json` · **Verdict file**: `results/phase7u_joint_belief_v1_verdict.json`

## Verdict

**PROCEED.** Every pre-registered gate passed. Calibration asked for 400 worlds (the cap; the binding pair needed 432).

| Gate | Result |
|---|---|
| V-1 new attacker matters | P3_NOM regret B3 − CLEAN = +0.120, 95% CI [0.103, 0.137] PASS |
| JG-1 C vs P3_RHAT_COST_LA2 | **RRR 0.266**, 95% CI [0.229, 0.303]; Cliff's δ 0.23; Wilcoxon p < 1e-4 PASS |
| JG-2 C vs P_JOINT_EIG_COST | **RRR 0.223**, 95% CI [0.186, 0.260]; Cliff's δ 0.22 PASS |
| JG-3 clean non-regression vs R | ȳ(C) − ȳ(R) = −0.019, 95% CI [−0.023, −0.015] PASS |
| JG-4 spend matching | exact in every episode PASS |
| JG-5 leakage tests | pass PASS |
| JG-6 replicability | RRR vs R: B1 0.38, B2 0.28, B3 0.21, halves 0.27 / 0.26; vs J: 0.37, 0.23, 0.15, halves 0.23 / 0.22 PASS |

## Scope map (descriptive, not gated): RRR of P_JOINT_HEIG_COST, 95% CI

| Attacker | vs P3_RHAT_COST_LA2 | vs P_JOINT_EIG_COST |
|---|---|---|
| CLEAN | 0.57 [0.48, 0.66] | 0.69 [0.62, 0.75] |
| **A_COLLUDE_CHEAP (held-out, primary)** | **0.27 [0.23, 0.30]** | **0.22 [0.19, 0.26]** |
| A_COVER (design) | 0.66 [0.63, 0.70] | 0.48 [0.43, 0.52] |
| A_DECOY_MIGRATE (7T held-out) | 0.56 [0.51, 0.60] | 0.53 [0.47, 0.58] |
| A_MISATTRIB | 0.05 [0.01, 0.10] | 0.02 [−0.03, 0.07] |
| A_TRUST_HARVEST | 0.12 [0.07, 0.18] | −0.03 [−0.09, 0.03] |

## Mean normalised regret, all policies

| Policy | CLEAN | COLLUDE_CHEAP | COVER | DECOY_MIGRATE | MISATTRIB | TRUST_HARVEST |
|---|---|---|---|---|---|---|
| P0_RANDOM_COST_MATCHED | 0.100 | 0.170 | 0.183 | 0.156 | 0.185 | **0.126** |
| P3_NOM | 0.051 | **0.132** | 0.319 | 0.137 | 0.280 | 0.259 |
| P3_RHAT_COST | 0.034 | 0.213 | 0.230 | 0.125 | 0.192 | 0.252 |
| P3_RHAT_COST_LA2 | 0.033 | 0.212 | 0.229 | 0.122 | 0.190 | 0.254 |
| **P_JOINT_HEIG_COST** | **0.014** | 0.156 | 0.077 | **0.054** | **0.180** | 0.223 |
| P_JOINT_EIG_COST | 0.046 | 0.200 | 0.146 | 0.114 | 0.184 | 0.217 |
| P_PROBE | 0.017 | 0.143 | **0.076** | 0.063 | 0.195 | 0.205 |

## What the result supports, and what it does not

**Supported (confirmatory):** against an attacker written before the run, choosing evidence by hypothesis information
under a joint (hypothesis, source-state) posterior cut regret by 27% relative to reliability-weighted EIG with the same
horizon and cost-awareness, and by 22% relative to joint (H, S) EIG, at identical spend, in every budget and both world
halves, with lower regret on clean worlds too.

**Not supported / caveats that must travel with the claim:**
1. **Not best overall on the primary attacker.** P3_NOM (nominal EIG, *not* cost-aware) has lower regret (0.132) than the
   candidate (0.156) on A_COLLUDE_CHEAP, and P_PROBE is close (0.143). The attacker targets the cheapest sources, so a
   cost-blind policy avoids them by accident. The pre-registered claim is a comparison among cost-aware policies; it is
   not "the best policy against this attacker". P3_NOM is far worse on every other attacker family (0.26–0.32 on
   cover, misattribution, trust-harvest).
2. **Scope.** The gain is large against cover-up, decoy and coordinated-lie attackers, small against misattribution
   (0.05 vs R) and absent against the policy-aware trust-harvest attacker, where random acquisition remains best (0.126).
3. **Origin.** The hypothesis was formed after looking at the killed 7L and 7T pilots; 7U is the first prospective test.
   One simulator, one world distribution; no real-data evidence yet.
4. **Novelty.** Joint fault-and-hypothesis belief is classical (de Kleer & Williams 1987; Heckerman, Breese & Rommelse
   1995). The contribution is the adversarial-telemetry setting, the held-out-attacker evidence, and the scope map.

## Consequence

The constructive section of the paper is now the scoped joint-belief claim, alongside the two pre-registered negative
results (probe value, robust acquisition). Replication on real data (e.g. an industrial-control dataset with
per-sensor attack labels) is the next external-validity step and needs its own protocol.

## Erratum (2026-10-07, found during paper review)

Scope item 2 says the gain is "absent against the policy-aware trust-harvest attacker". That holds only relative to
P_JOINT_EIG_COST (RRR -0.03, 95% CI [-0.09, 0.03]). Relative to P3_RHAT_COST_LA2 the candidate still reduces
trust-harvest regret (RRR 0.12, 95% CI [0.07, 0.18]; recomputed by `scripts/paper/recompute_headlines.py`). Random
acquisition is still lowest there (0.126). Gate outcomes are unaffected (trust-harvest is not a gated cell).
