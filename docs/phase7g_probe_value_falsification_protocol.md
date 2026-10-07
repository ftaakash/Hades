# Phase 7G — Probe-Value Falsification Protocol (PRE-REGISTERED)

**Experiment ID**: `phase7l_probe_pilot_v2`
**Config**: `configs/experiments/phase7l_probe_pilot_v2.json` (SHA-256 recorded in every raw output)
**Problem spec**: `docs/phase7f_probe_value_problem.md` · **Gates**: `docs/hades2_kill_gates.md`
**Analysis code**: `hades/probe_experiment/evaluation.py` (gate logic is code, committed with this document)
**Pilot decision deadline**: **2026-11-11**. No verdict by then → KILL by default.

Frozen by commit before any calibration or pilot run. Any change after a run needs a new experiment ID; nothing
is overwritten (the runner and analysis scripts refuse to).

## 1. Lineage of this protocol

`phase7l_probe_pilot_v1` was a local, uncommitted draft (two hand-designed environments, `P3_RHAT_COST` as the
primary comparator, absolute threshold 0.05). It was never run. It is superseded by v2 for three reasons
recorded in the 2026-10-07 review: the primary comparator was structurally blind to probe value, the scenarios
favoured probing by design, and the threshold had no power analysis behind it.

## 2. Primary comparison

`P_PROBE` vs **`P_JOINT_EIG_COST`** (cost-aware information gain over the joint `(H, S)`, two-step).
Secondary comparators that must also be beaten (PF-3): `P3_RHAT_COST`, `P3_RHAT_COST_LA2`, `P_JOINT_HEIG_COST`.

## 3. Conditions and pairing

- 10 conditions per world: `CLEAN`, and {`A_COVER`, `A_MISATTRIB`, `A_TRUST_HARVEST`} × B ∈ {1, 2, 3}.
- 12 episodes per (world, condition). Every policy faces the same `H_true`, degraded sources, adversary
  presence and per-(source, k-th use) random numbers (common random numbers). The truth draw does not depend
  on the condition, so conditions are paired too.
- 12 policies (spec §8), all run on every episode.
- Cost matching by design: integer costs (min 1), fixed budget 12, forced spending → identical spend.

## 4. World distribution (frozen; `WorldDistribution` in `hades/probe_experiment/world.py`)

| Parameter | Distribution | Level |
|---|---|---|
| sources K | U{5..8} | world |
| P(BENIGN) | U(0.30, 0.80); rest split evenly | world |
| accuracy acc_q (informativeness) | U(0.45, 0.95) (chance = 0.33) | source |
| evidence cost c_q | U{1..4}, one source forced to 1 | source |
| probe-cost ratio r | log-U(0.25, 2.0); probe cost = max(1, round(r·c_q)) | world |
| compromise prior π | U(0.02, 0.40); per source π·U(0.5, 1.5), capped 0.60 | world / source |
| benign coupling κ | U(0, 1) | world |
| degradation prior | U(0, 0.15) | source |
| probe accuracy P(FAIL\|COMPROMISED) | U(0.50, 0.99) | world |
| probe false-fail P(FAIL\|HEALTHY) | U(0, 0.10) | world |
| P(FAIL\|DEGRADED) | U(0.60, 0.99) | world |
| loss asymmetry L_miss / L_fa | log-U(1, 20) | world |
| assumed forge rate (defender model) | 0.90 | fixed |
| budget | 12 | fixed |

Seed ranges are disjoint: development and tests 0–99 (and hand-built models); calibration 900000–900039;
pilot from 1000000.

## 5. Attacker regimes (frozen; `hades/probe_experiment/attacker.py`)

Budget B = number of controlled sources (A0 = clean, A1–A3 = 1–3). `A_COVER` is the design family (the
defender's model of a compromised source matches it). `A_MISATTRIB` is held out: no policy, test threshold or
world parameter was chosen with it. `A_TRUST_HARVEST` is adaptive and observes the defender's queries and probes.
Under BENIGN an adversary is present with probability κ.

## 6. Endpoint

World-level mean normalised regret `ȳ_w(X)` over the 9 attacked cells × 12 episodes = 108 episodes.
`RRR = 1 − Σ_w ȳ_w(P_PROBE) / Σ_w ȳ_w(P_JOINT_EIG_COST)`.

## 7. Statistics

### 7.1 Threshold (frozen)
**RRR ≥ 0.10** — a 10% relative cut in decision regret at identical spend. Rationale: smaller than this, an
analyst would not change tooling for it; HADES 1.0 showed that a highly significant but practically null
difference (p = 2e-55, median difference 0) is possible at this scale, so significance alone never passes.

### 7.2 Power analysis → number of worlds
- Test: one-sided paired bootstrap of RRR over worlds, α = 0.025 (equivalent to a two-sided 95% CI excluding 0).
- Target: power 0.80 to reject RRR ≤ 0 when the true RRR = 0.10.
- Delta method: `SE(RRR) ≈ sd_d / (√n · μ_J)`, with `d_w = ȳ_w(J) − ȳ_w(P)` and `μ_J` the comparator's mean regret.
  `n = ⌈1.15 · ((z_0.975 + z_0.80) · sd_d / (0.10 · μ_J))²⌉`, clamped to [50, 400]. The 1.15 factor covers the
  denominator's variance and bootstrap slack.
- `sd_d` and `μ_J` come from a **blinded internal calibration** on 40 calibration worlds (seeds 900000–900039),
  running only `P_PROBE` and `P_JOINT_EIG_COST` on the primary cells. The script writes only `sd_d`, `μ_J` and `n`
  to `results/raw/phase7l_probe_pilot_v2_seed_manifest.json`; the mean difference and the candidate's mean are
  never output. Calibration worlds are not reused in the pilot.
- If `n` hits the cap of 400, the pilot runs 400 worlds and reports the achieved power.
- Honest note on the pass rule: PF-1 needs *both* significance and a point estimate ≥ 0.10. At a true RRR of
  exactly 0.10 the pass probability is about 50%; it reaches about 80% at a true RRR of about 0.13. The study is
  sized to detect the threshold effect, and the pass rule is deliberately stricter than detection.

### 7.3 Reported alongside every contrast
RRR, bootstrap 95% CI (10,000 resamples, seed 20261007), one-sided bootstrap p, one-sided Wilcoxon signed-rank
on `d_w`, Cliff's δ, mean regret of both arms. Holm correction within each multi-comparison gate. Behavioural
statistics: probes per episode, fraction of episodes probing a suspicious source (`P(S_q = C | E) ≥ 0.10` at
the time of the probe), share of probes on suspicious sources, attack exposure (queries answered by a
controlled source), forged answers received, state resolution (controlled sources ending with
`P(C) > 0.5`), false flags, decision accuracy, and the VoI-plateau fallback rate of the decision-objective policies.

## 8. Phase map (secondary, descriptive, pre-registered)

Per world, `d_w` for two contrasts: `P_PROBE` vs `P_PROBE_NO_PROBE` ("does probing beat avoidance?") and
`P_PROBE` vs `P_JOINT_EIG_COST`. Reported: fraction of worlds where `P_PROBE` is better / worse / tied; a logistic
regression of `1[d_w > 0]` on the five standardised axes (compromise prior, log probe-cost ratio, probe accuracy,
informativeness, log loss asymmetry); a 3 × 3 tertile grid of compromise prior × log probe-cost ratio with mean
`d_w` and fraction better per cell. This analysis is what supports a claim of the form "probing beats avoidance
when the compromise prior is in X and probe cost is below Y". It is descriptive and cannot rescue a failed gate.

## 9. Validity check (not a gate)

V-1 "the attacker must matter": `P3_NOM` regret at B = 3 exceeds CLEAN, 95% CI lower bound > 0. If V-1 fails
the run is INVALID (the simulator cannot test an adversarial claim); a corrected run needs a new experiment ID
and the 2026-11-11 deadline still applies.

## 10. Order of operations

1. Commit this protocol, the gates, the config and the analysis code. (7G freeze)
2. 7K deterministic tests pass (`py -m pytest tests/test_probe_experiment.py -q`).
3. `py scripts/run_probe_pilot.py calibration` → commit the seed manifest.
4. `py scripts/run_probe_pilot.py pilot` (refuses a dirty tree, a changed config or an existing raw file).
5. `py scripts/analyze_probe_pilot.py` → statistics + verdict; write `docs/hades2_probe_kill_report.md` or the
   proceed report. Commit everything, whatever the outcome.

## 11. Interpretation constraints

Only the gates decide. Nothing beyond the narrow mechanism may be claimed; the substrate is not novel
(`docs/hades2_novelty_audit_record.md`). A KILL is recorded as a valid negative result and the mechanism is
not rescued by redesigning the world distribution.
