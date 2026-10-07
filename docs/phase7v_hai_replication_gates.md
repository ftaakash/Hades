# Phase 7V Gates (HG-1 … HG-6) — PRE-REGISTERED

Applies to `phase7v_hai_replication_v1`. Code: `hades/probe_experiment/hai_eval.py::evaluate_hai_gates`.
Candidate C = `P_JOINT_HEIG_COST`; R = `P3_RHAT_COST_LA2`; J = `P_JOINT_EIG_COST`.
Decision data = every HAI 21.03 episode (attack segments plus an equal number of sampled normal windows).
Unit = episode; CI = paired bootstrap over episodes (10,000 resamples, seed 20261007).
Regret is normalised by the largest loss (L_MISS = 5).

| Gate | PASS criterion |
|---|---|
| **V-1** evidence matters | mean regret of the prior-only decision − P3_NOM: 95% CI lower > 0. Fail → INVALID |
| **HG-1** joint belief beats reliability weighting | RRR(C vs R) ≥ 0.10 and 95% CI lower > 0 |
| **HG-2** hypothesis objective beats joint objective | RRR(C vs J) ≥ 0.10 and 95% CI lower > 0 |
| **HG-3** normal non-regression | normal episodes: mean regret(C) − regret(R) ≤ +0.01 and 95% CI upper ≤ +0.02 |
| **HG-4** spend matching | every episode of every policy spends exactly the budget (6) |
| **HG-5** no leakage | `-k leak` in tests/test_hai_replication.py and tests/test_joint_belief.py pass |
| **HG-6** replicability | RRR > 0 vs both R and J in both halves of the episode list (even / odd index) |

Verdict, on HAI 21.03 only:
- **PROCEED** iff V-1 and all of HG-1 … HG-6 pass.
- **KILL** iff HG-3, HG-4 or HG-5 fails, or the 95% CI upper bound of RRR vs R or vs J is below 0.10
  (the effect is shown to be smaller than the practical threshold).
- **INCONCLUSIVE** otherwise (in practice: the CI is too wide for the available episodes).

HAI 22.04 is evaluated with the same function and reported as secondary; it cannot change the verdict.
No gate is redefined after results. Deadline 2026-11-11.
