# AGENTS.md — hades-bench-v1 (v3.0, reframed 2026-09-20)

Budgeted evidence acquisition for cyber threat hunting (CDB benchmark).
Researcher: Aakash G.S. Target: IEEE empirical paper. See `README.md` and `docs/REFRAME.md`.

## Commands (Windows PowerShell 5.1, Python 3.14.3)

- `py` is the interpreter (`python` resolves to the Store stub — do not use).
- Tests: `py -m pytest tests/ -q`
- Single file: `py -m pytest tests/test_simulator.py -q`
- F1 kill-gate sweep: `py scripts/run_f1_sweep.py --seeds 20 --noise 0,0.10,0.25,0.50`
- Legacy G1 test (heuristic-era, do not cite): `py scripts/run_orderflip_test.py --seeds 5`
- Baseline vs real CDB: `py scripts/run_baseline_comparison.py` (needs `../cdb` + unpacked dataset, ~28s/reset)
- Dataset hash: `py scripts/hash_dataset.py`
- Smoke test: `py scripts/run_smoke.py`
- HADES 2.0 7K tests: `py -m pytest tests/test_probe_experiment.py -q`
- HADES 2.0 blinded power calibration: `py scripts/run_probe_pilot.py calibration` (writes seed manifest; once)
- HADES 2.0 pilot: `py scripts/run_probe_pilot.py pilot` then `py scripts/analyze_probe_pilot.py`
- Phase 7T robust pilot: `py -m pytest tests/test_robust_acquisition.py -q`; `py scripts/run_robust_pilot.py calibration`, then `pilot`, then `py scripts/analyze_robust_pilot.py`
- Phase 7U joint-belief pilot: `py -m pytest tests/test_joint_belief.py -q`; `py scripts/run_joint_pilot.py calibration`, then `pilot`, then `py scripts/analyze_joint_pilot.py`

Do not use `tail`/`head` (not on Windows) — use `| Select-Object -First/Last N`.
Do not pipe agent long-runs through `Select-Object -First N` — it kills the pipe early. Redirect to file instead.

## Layout

```
hades/
  query_menu.py          — 7-source fixed SQL menu (extend, do not break P0/P1)
  harness.py             — CDB run(env,model) contract; P0/P1 only for now
  policies/
    base.py              — Policy ABC; InvestigationState (being extended)
    random_policy.py     — P0
    fixed_heuristic.py   — P1
    [p2..p7 pending]
  simulator/
    environment.py       — SimEnv A-E; IG/utility internals being replaced
    observations.py      — observation sampling + likelihood (being extended)
    scenarios.py         — 5 canonical test cases
  belief/                — [NEW in v3] contaminated likelihood, EIG, VoI
    likelihood.py        — LikelihoodTable; nominal + contaminated likelihood
    posterior.py         — Bayesian belief update
    value.py             — entropy, eig, terminal_utility, voi, robust_voi
    relevance.py         — expert relevance matrix with provenance
  hypothesis/            — [pending] HypothesisTracker, AttackHypothesis
  corruption/            — [pending] R1-R4 corruptors
  reliability/           — [pending] estimators
  benchmark/             — [pending] fast_db, candidate_extractor
  evaluation/            — [pending] metrics, statistics, ablation
scripts/
  run_orderflip_test.py  — LEGACY heuristic G1 (results/raw/g1_v0_legacy.json; do not cite)
  run_f1_sweep.py        — [pending] reframed kill-gate sweep
  run_smoke.py           — end-to-end pipeline smoke test
  run_baseline_comparison.py
docs/
  REFRAME.md             — explains v0->v3 architectural change
  threat_model.md        — R0-R4 corruption regime definitions
  literature_matrix.csv  — novelty audit table
results/raw/
  g1_v0_legacy.json      — heuristic-era G1 result; historical only, NOT a paper claim
configs/experiments/
  pilot_v1.yaml, main_v1.yaml — frozen before sweeps
data_manifest/
  benchmark_lock.json    — CDB version/checksum provenance (pinned)
STATUS_CDB_SAMPLE_KILLED.md — formal kill record for CDB sample transfer
docs/
  REFRAME.md             — explains v0->v3 architectural change
  threat_model.md        — R0-R4 corruption regime definitions
  literature_matrix.csv  — novelty audit table
  future/
    cdb_full_access_plan.md — future full-CDB evaluation (independent experiment)
../cdb                   — Cyber Defense Benchmark sibling dependency
```

## Conventions (v3.0)

- **Objective**: `V(q) = E_{e~p(e|H,q,r_hat,phi_hat)}[U_terminal(H'(e))] - lam*Cost(q)`.
  Old `U = ERHG - lam*cost - mu*ManipRisk` is **RETIRED**. See `docs/REFRAME.md`.
- **mu is deleted**. Manipulation risk enters through contaminated likelihood, not additive penalty.
- **lam** is the only free parameter (budget-normalized). Default `lam=1.0`.
- Contaminated likelihood: `p(e|H,q) = r_hat*p_nominal(e|H,q) + (1-r_hat)*p_noise`.
- Policies read ONLY `*_estimated` fields. `*_true` is evaluator-only. `TestLeakage` enforces this.
- Probability invariant: beliefs sum to 1.0, validated loudly every step.
- Deterministic tie-break: alphabetical max `(score, name)`.
- Never fabricate results. Never change `benchmark.scorer.score_hunt` semantics. Never rewrite a failed gate as pass.
- Correlation of `reliability` and `manipulation_risk` is empirically measured, never assumed dependent.

## Policy Ladder (all cited in code headers)

| Policy | Rule | Citation |
|--------|------|----------|
| P0 | Random | floor |
| P1 | Fixed heuristic priority | floor+ |
| P2 | argmax relevance[leading_hyp][s] | static adaptive |
| P3 | argmax EIG | Naghshvar & Javidi 2013; ECC-AHT 2026 |
| P4 | argmax EIG/cost | cost-aware |
| P4b | argmax EIG(r_hat-likelihood)/cost | Settles et al. 2008 — NOT novel |
| P7 | Expected error reduction / Thompson | anti-strawman (Settles 2008 §4) |
| P5 | argmax V(q) / robust_voi | HADES under test |
| P6 | LLM frozen reference | optional, deferred |

## HADES 2.0 (probe-value falsification, `hades/probe_experiment/`)

- HADES 1.0 is frozen (tag `hades-1.0-final`); 2.0 code lives only in `hades/probe_experiment/`.
- Protocol `docs/phase7g_probe_value_falsification_protocol.md`, gates `docs/hades2_kill_gates.md`,
  config `configs/experiments/phase7l_probe_pilot_v2.json`. Primary: P_PROBE vs **P_JOINT_EIG_COST**, RRR >= 0.10.
- Worlds are procedurally generated; never hand-tune worlds, attackers or thresholds after a run.
- Seeds: dev/tests 0-99, calibration 900000-900039, pilot from 1000000.
- Pilot kill date **2026-11-11**. **Pilot v2 verdict: KILL** (2026-10-07; PF-3/4/6 fail; `docs/hades2_probe_kill_report.md`).
- Phase 7T follow-up `phase7t_robust_pilot_v1`: P_RAND_JEIG / P_MINIMAX_JEIG vs P_JOINT_EIG_COST and random on held-out
  A_DECOY_MIGRATE (`docs/phase7t_robust_acquisition_protocol.md`, gates `docs/phase7t_robust_acquisition_gates.md`).
  Seeds: calibration 910000-910039, pilot from 2000000. **7T verdict: KILL** (2026-10-07; RG-1 fails for both; `docs/phase7t_robust_kill_report.md`).
- Phase 7U confirmatory `phase7u_joint_belief_v1`: P_JOINT_HEIG_COST vs P3_RHAT_COST_LA2 and P_JOINT_EIG_COST on held-out
  A_COLLUDE_CHEAP (`docs/phase7u_joint_belief_protocol.md`, gates `docs/phase7u_joint_belief_gates.md`).
  Hypothesis is from exploratory 7L/7T data, disclosed. Seeds: calibration 920000-920039, pilot from 3000000.
  **7U verdict: PROCEED** (2026-10-07; RRR 0.27 vs R, 0.22 vs J; scoped, see `docs/phase7u_joint_belief_report.md`).

## Gates

G0 baseline reproducible: PASS. G1 (heuristic-era, legacy): PASS [see g1_v0_legacy.json, not a paper claim].
F1/F5 kill gate (reframed sweep on simulator): PENDING.
Phase 5A CDB sample transfer: KILLED (T2 failed — obs representation degenerate on sample.json).
  Mapper v1 (row count): LIMIT saturation → 647/647 strong_support.
  Mapper v2 (null_rate + EventID variety): query-fixed signal → 654/654 neutral.
  Mapper v3 (computer spread): placeholder values → 654/654 neutral.
  See STATUS_CDB_SAMPLE_KILLED.md for full record.
G2-G6: pending full CDB sweep (deferred pending full-benchmark access).

## Kill / Pivot Protocol

- F1 ~ 0: kill method claim. Artifact/measurement paper or H4 negative-results pivot.
- F1 pass + collapse at 10-25% noise: estimator paper reframe.
- F2/F6/F10 fail: narrow claims to non-adaptive or CDB-specific.
- G6 fails: don't submit as novel-method paper.
- CDB sample obs collapse: kill sample transfer, preserve infrastructure for full-CDB.

## Known Issues

- CDB sample transfer KILLED: sample.json uses placeholder values (Computer="Computer", AccountName=null).
  CDB adapter/infrastructure preserved; full-CDB evaluation is deferred.
- `ThreatHuntEnv.reset()` inserts 155K rows one-at-a-time (~28s). `fast_db.py` patches this.
- `hades/simulator/environment.py` IG methods are still v0 heuristics; v3 belief wrappers pending.
- `run_orderflip_test.py` inline policy logic needs refactor to import policy classes (Phase 2).

## Provenance

Every paper claim must trace: claim -> figure/table -> analysis script -> processed data ->
raw run -> config -> seed -> git commit -> benchmark version. `main_v1.yaml` is frozen before
sweeps; post-run changes need a new experiment ID.
