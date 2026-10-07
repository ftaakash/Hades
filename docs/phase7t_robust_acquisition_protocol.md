# Phase 7T — Robust Acquisition Pilot Protocol (PRE-REGISTERED)

**Experiment ID**: `phase7t_robust_pilot_v1`
**Config**: `configs/experiments/phase7t_robust_pilot_v1.json` · **Gates**: `docs/phase7t_robust_acquisition_gates.md`
**Code**: `hades/probe_experiment/robust.py` (policies, new attacker), `hades/probe_experiment/robust_eval.py` (gates)
**Literature**: `docs/phase7t_literature_checklist.md` · **Decision deadline**: **2026-11-11** (no verdict → KILL)

Frozen by commit before the calibration and pilot. Nothing is overwritten; changes need a new experiment ID.

## 1. Origin and status of the question

The killed v2 pilot (`docs/hades2_probe_kill_report.md`) contained an **exploratory, not pre-registered** observation:
model-based acquisition lost its edge against attackers its model did not match, and random acquisition beat every
model-based policy against the policy-aware trust-harvest attacker. 7T tests whether a principled robust policy
captures that advantage **against an attacker no policy was designed for**. v2 is not reopened; v2 data are not
reused (new world seeds).

## 2. Question

Does randomised or model-robust acquisition reduce decision regret by ≥ 10% relative to **both** the best v2
model-based comparator (`P_JOINT_EIG_COST`) **and** random acquisition, against a new held-out attacker, at
identical spend, without a material loss on clean worlds and on the attacker families known at design time?

## 3. Candidates (each changes P_JOINT_EIG_COST in exactly one way)

| Candidate | Change | Free parameters |
|---|---|---|
| `P_RAND_JEIG` | samples the next action with probability ∝ its non-negative P_JOINT_EIG_COST score | none |
| `P_MINIMAX_JEIG` | worst-case P_JOINT_EIG_COST score over three compromised-source models known at design time (cover-up, misattribution, noise), each with its own exact posterior | none |

Both use the shared exact posterior and Bayes decision at the end, like every v2 policy; they differ only in
acquisition. Comparators: `P_JOINT_EIG_COST`, `P0_RANDOM_COST_MATCHED`. References (reported, not gated):
`P3_NOM`, `P3_RHAT_COST`, `P_JOINT_HEIG_COST`, `P_PROBE`.

## 4. New held-out attacker `A_DECOY_MIGRATE`

Specified in `robust.py`, written before any 7T run, and used by no policy, test threshold or world parameter:
B controlled sources chosen uniformly at random; each reports one **sticky decoy** class (fixed per episode,
never the true hypothesis) with probability 0.80; probes of a controlled source pass with an extra probability
0.30; when the defender probes a controlled source, the attacker **migrates** to the unprobed, uncontrolled source
the defender has queried most. Under BENIGN it is present with probability κ and its decoy is an intrusion class.
It differs from every known family in target selection (random), forged content (sticky decoy that can be BENIGN
or the wrong intrusion), and policy-awareness (probe-triggered migration).

## 5. Design

- Worlds: the frozen v2 `WorldDistribution`, unchanged. Seeds: calibration 910000–910039; pilot from 2000000.
- 13 conditions: CLEAN; {A_COVER, A_MISATTRIB, A_TRUST_HARVEST} × B ∈ {1,2,3} (known); A_DECOY_MIGRATE × B ∈ {1,2,3}
  (**primary cells**). 12 episodes per (world, condition). Same common-random-number pairing as v2.
- Spend matched exactly (integer costs, budget 12, forced spending). Randomised policies draw from a per-(world,
  episode, policy) generator, so runs are reproducible.

## 6. Statistics

- Endpoint: `RRR = 1 − Σ_w ȳ_w(candidate) / Σ_w ȳ_w(comparator)` on the primary cells (normalised regret).
- Threshold: RRR ≥ 0.10 against each comparator (unchanged from v2).
- Multiplicity: two candidates, Bonferroni → one-sided α = 0.0125 per candidate, i.e. the lower bound of a 97.5%
  paired bootstrap CI (10,000 resamples, seed 20261007) must exceed 0. Within a candidate both comparators must be
  beaten (intersection–union test; no further adjustment).
- Power: n = ⌈1.15·((z_0.9875 + z_0.80)·sd_d / (0.10·μ_X))²⌉ for each of the 4 candidate × comparator pairs;
  the pilot uses the maximum, clamped to [50, 400]. `sd_d` and `μ_X` come from a **blinded** 40-world calibration
  that outputs only the spread of the paired differences and the comparators' mean regret.
- Also reported: Wilcoxon one-sided, Cliff's δ, per-budget and per-half RRR, queries per episode, the full regret
  table by attacker family for all 8 policies.

## 7. Verdict

INVALID if V-1 fails. **PROCEED** if at least one candidate passes RG-1 … RG-4 and RG-7, and RG-5/RG-6 pass;
otherwise **KILL**. A PROCEED makes the passing candidate the constructive section of the paper, subject to the
literature checklist's decision rule. A KILL is reported as a further negative result.

## 8. Order

1. Commit protocol, gates, config, code, tests (this freeze).
2. `py -m pytest tests/test_robust_acquisition.py -q`.
3. `py scripts/run_robust_pilot.py calibration` → commit seed manifest.
4. `py scripts/run_robust_pilot.py pilot` → `py scripts/analyze_robust_pilot.py` → commit raw, statistics, verdict, report.
