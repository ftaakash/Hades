# HADES 2.0 Kill Gates (PF-1 … PF-10) — PRE-REGISTERED

Applies to `phase7l_probe_pilot_v2`. Implemented in `hades/probe_experiment/evaluation.py::evaluate_gates`,
committed with the protocol before any run.

Notation: unit = world. **Primary cells** = {A_COVER, A_MISATTRIB, A_TRUST_HARVEST} × B ∈ {1,2,3}.
`ȳ_w(X)` = mean normalised regret of X in world w over the named cells.
`RRR_X = 1 − Σ_w ȳ_w(P_PROBE) / Σ_w ȳ_w(X)`. CI = paired bootstrap 95% over worlds (10,000, seed 20261007).
**J** = `P_JOINT_EIG_COST` (primary comparator).

| Gate | Decisive | PASS criterion |
|------|----------|----------------|
| **V-1** attacker matters | validity | `P3_NOM` regret, B = 3 minus CLEAN: CI lower > 0. Fail → run INVALID |
| **PF-1** Decision-regret separation | yes | Primary cells: `RRR_J ≥ 0.10` **and** CI lower > 0 |
| **PF-2** Cost matching | yes | Every episode of every policy spends exactly the budget |
| **PF-3** Not reliability weighting / not H-information | yes | Primary cells, vs each of `P3_RHAT_COST`, `P3_RHAT_COST_LA2`, `P_JOINT_HEIG_COST`: RRR > 0 and Holm-adjusted (3 tests) one-sided bootstrap p < 0.05 |
| **PF-4** Actual probing | yes | Primary cells: `P_PROBE` probes a suspicious source (P(C\|E) ≥ 0.10) in ≥ 10% of episodes **and** ≥ 50% of its probes target suspicious sources |
| **PF-5** Source-state attribution | yes | Primary cells: `RRR` vs `P_PROBE_NO_S` has CI lower > 0, **and** the regret gap to `P_PROBE_NO_S` is ≥ 50% of the gap to J (with the gap to J > 0). `P_PROBE_NO_PROBE` reported |
| **PF-6** Held-out robustness | yes | `A_MISATTRIB`, B = 1–3: `RRR_J > 0` and CI lower > 0. Adaptive (`A_TRUST_HARVEST`) and design (`A_COVER`) reported, non-decisive |
| **PF-7** No oracle leakage | yes | `tests/test_probe_experiment.py -k leak` passes at analysis time |
| **PF-8** Practical magnitude | report | RRR, CI, ratio to 0.10, Cliff's δ |
| **PF-9** Clean non-regression | yes | CLEAN: mean `ȳ(P_PROBE) − ȳ(J)` ≤ +0.01 and its CI upper ≤ +0.02 (normalised-regret units) |
| **PF-10** Replicability | yes | `RRR_J > 0` in each of B = 1, 2, 3 (families pooled), in both world halves (even / odd seed), and after dropping the 10% of worlds with the largest gain |

**Verdict**: INVALID if V-1 fails; otherwise **PROCEED** only if every decisive gate passes, else **KILL**.
**Deadline**: no verdict by **2026-11-11** → KILL.
No gate is redefined after results. A failed gate is never rewritten as a pass. The phase map (protocol §8)
is descriptive and cannot rescue a failed gate.
