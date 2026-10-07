# Phase 7U Gates (JG-1 … JG-6) — PRE-REGISTERED

Applies to `phase7u_joint_belief_v1`. Code: `hades/probe_experiment/joint_eval.py::evaluate_joint_gates`.
Candidate C = `P_JOINT_HEIG_COST`; R = `P3_RHAT_COST_LA2`; J = `P_JOINT_EIG_COST`.
Primary cells = A_COLLUDE_CHEAP × B ∈ {1,2,3}. CI = paired bootstrap over worlds.

| Gate | PASS criterion |
|---|---|
| **V-1** new attacker matters | P3_NOM regret, A_COLLUDE_CHEAP B3 − CLEAN: 95% CI lower > 0. Fail → INVALID |
| **JG-1** joint belief beats reliability weighting | primary cells: RRR(C vs R) ≥ 0.10 and 95% CI lower > 0 |
| **JG-2** hypothesis objective beats joint objective | primary cells: RRR(C vs J) ≥ 0.10 and 95% CI lower > 0 |
| **JG-3** clean non-regression | CLEAN: mean ȳ(C) − ȳ(R) ≤ +0.01 and 95% CI upper ≤ +0.02 |
| **JG-4** spend matching | every episode of every policy spends exactly the budget |
| **JG-5** no leakage | `-k leak` in tests/test_joint_belief.py, test_robust_acquisition.py, test_probe_experiment.py pass |
| **JG-6** replicability | RRR > 0 vs both R and J in each budget B1–B3 and both world halves (even/odd seed) |

**PROCEED** iff all of JG-1 … JG-6 pass (and V-1). Else **KILL**. No gate is redefined after results.
Deadline 2026-11-11.
