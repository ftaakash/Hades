# Phase 7U — Joint Source-State Belief: Confirmatory Pilot Protocol (PRE-REGISTERED)

**Experiment ID**: `phase7u_joint_belief_v1`
**Config**: `configs/experiments/phase7u_joint_belief_v1.json` · **Gates**: `docs/phase7u_joint_belief_gates.md`
**Code**: `hades/probe_experiment/joint_confirm.py` (policy set, new attacker), `hades/probe_experiment/joint_eval.py` (gates)
**Decision deadline**: **2026-11-11** (no verdict → KILL)

Frozen by commit before the calibration and pilot. Nothing is overwritten; changes need a new experiment ID.

## 1. Origin (exploratory, disclosed)

The hypothesis comes from looking at the two killed pilots after their verdicts, so it is **not** evidence yet:
`P_JOINT_HEIG_COST` had lower normalised regret than reliability-weighted EIG (`P3_RHAT_COST`) by 28% over all v2
attacker cells (better in 71% of 140 worlds) and by 55% on the 7T held-out attacker (87% of 400 worlds), and by 52%
vs `P_JOINT_EIG_COST` on that attacker. The gain was large against cover-up and decoy attackers and near zero against
misattribution and trust-harvest. 7U tests the claim prospectively: fresh world seeds and a new held-out attacker
written before any 7U run. No policy, world parameter, threshold or attacker has been changed after seeing 7U data.

## 2. Claim under test

Under adversarial telemetry, choosing evidence by hypothesis information under a **joint posterior over the
hypothesis and every source's state** reduces decision regret by ≥ 10% relative to (a) reliability-weighted EIG
with the same horizon and cost-awareness and (b) joint (H, S) EIG, at identical spend, against an attacker no
policy was designed for, without a material loss on clean worlds.

## 3. Policies (all unchanged v2 code; no new parameters)

| Role | Policy | Model | Objective | Horizon | Cost-aware |
|---|---|---|---|---|---|
| Candidate | `P_JOINT_HEIG_COST` | joint (H, S) posterior | H entropy reduction | 2 | yes |
| Comparator R | `P3_RHAT_COST_LA2` | reliability-weighted (r̂) likelihood | H entropy reduction | 2 | yes |
| Comparator J | `P_JOINT_EIG_COST` | joint (H, S) posterior | joint entropy reduction | 2 | yes |
| References | `P0_RANDOM_COST_MATCHED`, `P3_NOM`, `P3_RHAT_COST`, `P_PROBE` | | | | |

R is the horizon-matched version of the policy named in the exploratory comparison; it is the stricter comparator.
Candidate and R differ only in the belief model; candidate and J differ only in the objective.

## 4. New held-out attacker `A_COLLUDE_CHEAP`

Specified in `joint_confirm.py` before any 7U run. Controls the B **cheapest** sources (the ones a cost-aware
defender is most likely to read); all controlled sources tell the **same lie**, drawn once per episode (under an
intrusion: BENIGN or the other intrusion class, prob ½ each; under BENIGN: a random intrusion class), with prob
0.85 per answer; probes of a controlled source pass with an extra prob 0.40; no adaptation. Present under BENIGN
with prob κ. It differs from all four earlier families in target selection (cost), content (coordinated across
sources, mixed cover-up and misattribution) and is not policy-aware.

## 5. Design

- Worlds: the frozen v2 `WorldDistribution`. Seeds: calibration 920000–920039; pilot from 3000000.
- 16 conditions: CLEAN; {A_COVER, A_MISATTRIB, A_TRUST_HARVEST, A_DECOY_MIGRATE} × B ∈ {1,2,3} (known, descriptive);
  A_COLLUDE_CHEAP × B ∈ {1,2,3} (**primary cells**). 12 episodes per (world, condition); common random numbers.
- Spend matched exactly (integer costs, budget 12, forced spending).

## 6. Statistics

- Endpoint: `RRR = 1 − Σ_w ȳ_w(candidate) / Σ_w ȳ_w(comparator)` on the primary cells.
- Threshold RRR ≥ 0.10 against **each** comparator; one candidate, both comparators required (intersection–union),
  one-sided α = 0.025 → lower bound of the 95% paired bootstrap CI (10,000 resamples, seed 20261007) > 0.
- Power: n = ⌈1.15·((z_0.975 + z_0.80)·sd_d / (0.10·μ_X))²⌉ per comparator, maximum used, clamped to [50, 400];
  from a **blinded** 40-world calibration that outputs only sd_d and the comparators' mean regret.
- Reported, not gated: the scope map (RRR vs each comparator by attacker family, including the four known
  families), Wilcoxon, Cliff's δ, the full regret table.

## 7. Verdict

INVALID if V-1 fails. **PROCEED** if JG-1 … JG-6 all pass; otherwise **KILL**. A PROCEED supports the scoped claim
in §2 for the attacker types where the scope map shows a gain; failures elsewhere are reported, not hidden.

## 8. Order

1. Commit protocol, gates, config, code, tests (this freeze).
2. `py -m pytest tests/test_joint_belief.py -q`.
3. `py scripts/run_joint_pilot.py calibration` → commit seed manifest.
4. `py scripts/run_joint_pilot.py pilot` → `py scripts/analyze_joint_pilot.py` → commit raw (gzipped), statistics, verdict, report.
