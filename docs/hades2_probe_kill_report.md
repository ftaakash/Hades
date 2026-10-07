# HADES 2.0 Probe-Value Pilot — KILL Report

**Experiment**: `phase7l_probe_pilot_v2` · **Verdict**: **KILL** (2026-10-07, before the 2026-11-11 deadline)
**Run**: commit `eb586c6`, clean tree, config SHA-256 `e13220f8…0fb7`, 140 worlds (seeds 1000000–1000139),
10 conditions × 12 episodes × 12 policies = 201,600 episodes. Every policy spent exactly the budget in every episode.
**Files**: `results/raw/phase7l_probe_pilot_v2.json`, `results/analysis/phase7l_probe_pilot_v2_statistics.json`,
`results/phase7l_probe_pilot_v2_verdict.json`. Gates were applied by the frozen code, unchanged.

## Gate outcomes

| Gate | Result | Numbers (RRR = relative regret reduction of P_PROBE; 95% bootstrap CI) |
|---|---|---|
| V-1 attacker matters | valid | P3_NOM regret B3 − CLEAN = +0.241 [0.214, 0.269] |
| PF-1 vs P_JOINT_EIG_COST | PASS | RRR 0.114 [0.056, 0.166]; Cliff's δ 0.14 |
| PF-2 spend matching | PASS | exact |
| **PF-3** not reliability weighting / not H-information | **FAIL** | vs P3_RHAT_COST 0.285 [0.234, 0.334]; vs P3_RHAT_COST_LA2 0.281 [0.230, 0.330]; **vs P_JOINT_HEIG_COST 0.018 [−0.025, 0.061], Holm p = 0.20** |
| **PF-4** actual probing | **FAIL** | 57.5% of episodes probe a suspicious source (≥ 10% needed), but only 34.6% of probes target suspicious sources (≥ 50% needed) |
| PF-5 source-state attribution | PASS | vs P_PROBE_NO_S 0.269 [0.218, 0.318]; ablation gap 2.9× the primary gap |
| **PF-6** held-out attacker | **FAIL** | A_MISATTRIB: RRR −0.046 [−0.127, 0.025]. Adaptive (reported): −0.029 [−0.152, 0.083]. Design (reported): 0.494 [0.414, 0.564] |
| PF-7 leakage | PASS | |
| PF-8 magnitude | report | 1.14 × threshold, carried entirely by the design attacker |
| PF-9 clean non-regression | PASS | P − J = −0.022 [−0.032, −0.013] |
| PF-10 replicability | PASS | B1 0.273, B2 0.091, B3 0.045; halves 0.117 / 0.111; drop top decile 0.049 |

## What the pilot shows

1. **The primary effect is a model-match effect.** The whole PF-1 gain comes from the design attacker, whose
   behaviour matches the defender's compromised-source model (RRR 0.49). Against the held-out and the adaptive
   attackers, P_PROBE is no better than joint-state EIG (point estimates slightly worse).
2. **Decision-relevance adds nothing over H-information under the same joint model** (PF-3: 0.018, CI spans 0).
   The large gains over P3_RHAT_COST / LA2 come from exact joint inference with persistent source state. That is
   the substrate the audit already rules out as novel, not the probe-value mechanism.
3. **Probing is not targeted.** P_PROBE probes often, but about two thirds of its probes go to sources that
   are not suspicious at the time of the probe.
4. The no-source-state ablation does lose (PF-5), so the joint source-state model matters. It just does not
   matter *through decision-valued probing*.

Pre-registered answer: **decision-relevance of source-state information adds nothing robust over joint-state
information gain** in this world family. That is the informative negative the 7G protocol anticipated.

## Phase map (descriptive, pre-registered; cannot rescue a gate)

- P_PROBE vs P_PROBE_NO_PROBE (same objective, no probe action): P_PROBE better in 73.6% of worlds, worse in
  22.1%. Logistic on standardised axes: probe-cost ratio −0.50 (SE 0.21; probing helps more when probes are
  cheap); compromise prior −0.23, probe accuracy +0.12, informativeness −0.31, loss asymmetry −0.08 (all within ~1.5 SE).
- P_PROBE vs P_JOINT_EIG_COST: better in 64.3% of worlds; no axis is clearly predictive.
- Both maps pool all three attacker families, so the design attacker inflates them (point 1).

## Exploratory observation (not pre-registered; hypothesis-generating only)

Mean normalised regret by attacker family:

| Policy | CLEAN | A_COVER (design) | A_MISATTRIB (held-out) | A_TRUST_HARVEST (adaptive) |
|---|---|---|---|---|
| P0_RANDOM_COST_MATCHED | 0.098 | 0.180 | 0.181 | **0.125** |
| P3_RHAT_COST | 0.036 | 0.232 | 0.176 | 0.250 |
| P_JOINT_HEIG_COST | **0.018** | 0.079 | **0.172** | 0.229 |
| P_JOINT_EIG_COST | 0.043 | 0.151 | 0.173 | 0.207 |
| P_PROBE | 0.020 | **0.076** | 0.181 | 0.213 |

Against the held-out attacker every policy is within about 0.01 of random. Against the trust-harvesting attacker,
random acquisition beats every model-based policy: the attacker exploits whichever source a policy relies on, and
spreading queries denies it that leverage. This suggests that robustness to a model-mismatched or policy-aware
adversary, rather than probe valuation, is the open problem. Any follow-up needs a new experiment ID, a new
protocol and its own kill date. It does not reopen this one.

## Actions (plan §12, Outcome A)

1. All pilot artifacts are frozen and committed; nothing is overwritten.
2. The probe-value mechanism is **not** scaled; there is no 7O confirmatory study.
3. The world distribution is not redesigned to obtain a pass.
4. The null result is recorded as a valid negative finding and is not converted into a software contribution.
