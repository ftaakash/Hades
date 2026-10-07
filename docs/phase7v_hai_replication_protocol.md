# Phase 7V Protocol — Real-data replication of 7U on HAI (PRE-REGISTERED)

Experiment `phase7v_hai_replication_v1`. Config `configs/experiments/phase7v_hai_replication_v1.json`.
Gates `docs/phase7v_hai_replication_gates.md`. Decision deadline 2026-11-11.

## 1. Question

7U (simulator, PROCEED) found that at equal spend `P_JOINT_HEIG_COST` (hypothesis EIG under the joint posterior
over hypothesis and source compromise) has lower decision regret than reliability-weighted EIG
(`P3_RHAT_COST_LA2`) and joint (H, S) EIG (`P_JOINT_EIG_COST`). 7V asks whether that holds when the evidence,
the compromise and the cover-up come from a real industrial control testbed instead of the simulator.

## 2. Data

HAI (HIL-based Augmented ICS) security dataset, icsdataset/hai, CC BY-SA 4.0. Three versions, three roles:

| Role | Version | Use |
|---|---|---|
| Development | HAI 20.07 | adapter design, detector design, defender-model fitting. Looked at freely. |
| **Primary confirmation** | **HAI 21.03** | the verdict. No episode built before this protocol was committed. |
| Secondary confirmation | HAI 22.04 | same analysis, reported, cannot change the verdict. Attacks 41–49 (A407–A415) excluded: the manual's target layout for them is ambiguous. |

Ground truth comes from the dataset's own labels (`attack`, `attack_P1/P2/P3`) and the technical-details
manual (`configs/data/hai_attack_metadata.json`, transcribed before any replication run).

## 3. Mapping (code: `hades/probe_experiment/hai.py`, version `probe-hai-1.0`)

- **Episode**: one contiguous attack segment, or one normal window sampled ≥ 900 s from any attack row.
  Normal windows: as many as attack segments, allocated across test files by eligible length, RNG `[7751, code]`.
- **Hypotheses**: 0 NORMAL; 1 attack confined to process P1 (boiler); 2 attack touching P2 or P3.
- **Sources** (9): P1_PIT01, P1_FT03, P1_LIT01, P1_PCV01D, P1_FCV03D, P1_LCV01D, P2_SIT01, P3_LEVEL, P3_LCV01D.
- **Query** of a source = its own change alarm on the k-th 30 s sub-window after onset versus a −300…−60 s
  reference window; threshold = 99th percentile of the same statistic on attack-free train data.
  An alarm reports the source's process class (1 or 2), no alarm reports 0.
- **Compromise** = real stale-value spoofing: the manual's "maintain/repeat previous sensor value" targets.
  A spoofed PV stays quiet while the process moves, which is a real cover-up; nothing is simulated.
- **Probe** of a source = ridge-regression consistency check against the other points of the same process;
  FAIL when the sub-window mean absolute residual exceeds the train 99th percentile.
- The k-th read of a source returns sub-window k (max 6 reads, 180 s). Detectors per version are fitted on that
  version's attack-free train files only.

## 4. Defender model (code: `hades/probe_experiment/hai_model.py`, version `probe-hai-model-1.0`)

Fitted on the 20.07 development episodes only and applied unchanged to 21.03 and 22.04:
prior over H from development class frequencies; P(spoofed | h) per source from development frequencies
(Beta(0.5, 0.5) smoothing, zero for control outputs and under NORMAL); healthy query likelihoods from
development frequencies (Dirichlet(1)); compromised = 0.9 cover-up + 0.1 healthy; degraded uniform
(prior 0.01); probe FAIL rates from development (healthy vs spoofed). Utility: miss 5, false alarm 1,
misattribution 2.5. Costs: query 1, probe 2, budget 6. These numbers were fixed by design, not tuned.

## 5. Policies and contrast

The seven frozen 7U policies (`JOINT_POLICY_NAMES`), unchanged. Candidate `P_JOINT_HEIG_COST`; comparators
`P3_RHAT_COST_LA2` and `P_JOINT_EIG_COST`, both must be beaten (intersection–union, one-sided α = 0.025).
Endpoint: relative regret reduction RRR = 1 − Σ regret(C) / Σ regret(X) over all 21.03 episodes, paired by
episode. Practical threshold 0.10. Every policy spends exactly the budget.

## 6. Disclosed development look

Before freezing, every policy was run in-sample on the 20.07 development episodes (76 episodes, model fitted on
the same episodes). Mean normalised regret: P3_NOM 0.114, P_PROBE 0.126, P_JOINT_HEIG_COST 0.150,
P_JOINT_EIG_COST 0.157, P0_RANDOM 0.199, P3_RHAT_COST and P3_RHAT_COST_LA2 0.216. No deterministic policy
probed. Development probe FAIL rates were 0.355 healthy vs 0.674 spoofed. Nothing was changed after this look.
The in-sample ordering (candidate ahead of R, roughly level with J, behind P3_NOM) is a reason to expect HG-2
may fail; it is disclosed here rather than designed around.

## 7. Power

The number of episodes is fixed by the dataset (21.03 has about 50 attack segments, so about 100 episodes).
There is no calibration run: an under-powered result is reported as INCONCLUSIVE, not re-run on more data.

## 8. Running

```
py -m pytest tests/test_hai_replication.py -q
py scripts/run_hai_replication.py          # once; refuses a dirty tree or an existing raw file
py scripts/analyze_hai_replication.py      # once; refuses an existing verdict
```

Raw: `results/raw/phase7v_hai_replication_v1.json.gz` (per-episode, per-policy regret, decisions and action
logs, dataset SHA-256s, the fitted model). Verdict: `results/phase7v_hai_replication_v1_verdict.json`.
