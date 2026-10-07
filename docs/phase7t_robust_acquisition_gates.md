# Phase 7T Gates (RG-1 … RG-7) — PRE-REGISTERED

Applies to `phase7t_robust_pilot_v1`. Code: `hades/probe_experiment/robust_eval.py::evaluate_robust_gates`.
Primary cells = A_DECOY_MIGRATE × B ∈ {1,2,3}. Known cells = {A_COVER, A_MISATTRIB, A_TRUST_HARVEST} × B ∈ {1,2,3}.
J = `P_JOINT_EIG_COST`, R = `P0_RANDOM_COST_MATCHED`. CI = paired bootstrap over worlds.

| Gate | Scope | PASS criterion |
|---|---|---|
| **V-1** new attacker matters | validity | P3_NOM regret, A_DECOY_MIGRATE B3 − CLEAN: 95% CI lower > 0. Fail → INVALID |
| **RG-1** beats model-based comparator | per candidate | primary cells: RRR vs J ≥ 0.10 and 97.5% CI lower > 0 |
| **RG-2** beats random | per candidate | primary cells: RRR vs R ≥ 0.10 and 97.5% CI lower > 0 |
| **RG-3** no loss on known attackers | per candidate | known cells: mean ȳ(cand) − ȳ(J) ≤ +0.02 and 95% CI upper ≤ +0.04 |
| **RG-4** clean non-regression | per candidate | CLEAN: mean ȳ(cand) − ȳ(J) ≤ +0.01 and 95% CI upper ≤ +0.02 |
| **RG-5** spend matching | shared | every episode of every policy spends exactly the budget |
| **RG-6** no leakage | shared | `tests/test_robust_acquisition.py -k leak` and `tests/test_probe_experiment.py -k leak` pass |
| **RG-7** replicability | per candidate | RRR > 0 against both J and R in each budget B1–B3 and in both world halves (even/odd seed) |

**PROCEED** if any candidate passes RG-1, RG-2, RG-3, RG-4 and RG-7, with RG-5 and RG-6 passing; else **KILL**.
No gate is redefined after results. Deadline 2026-11-11.
