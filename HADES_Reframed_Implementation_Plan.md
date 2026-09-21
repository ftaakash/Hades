# HADES Reframed — AI-Executable Implementation Plan (v3.0)

> **Goal:** Build the reframed HADES: a controlled study + open corruption engine + robust-VoI policy for budgeted evidence acquisition under corrupted telemetry on CDB.
> **Non-claim:** No "new general utility formula". P3/P4/P4b are baselines (Settles 2008, Naghshvar & Javidi 2013, ECC-AHT 2026). Contribution = study + artifact + boundary conditions (F1-F10).
> **Repo:** `https://github.com/ftaakash/Hades` / local `hades-bench-v1`
> **Rules:** Never fabricate results. Never change `benchmark.scorer.score_hunt` semantics. Never turn a failed gate into pass by changing protocol post-hoc. Never leak `*_true` to policies.

---

## 1. Environment and Commands

* Interpreter: `py` (do NOT use `python` — Store stub). PowerShell 5.1. No `head`/`tail`; use `| Select-Object -First/Last N`.
* Tests: `py -m pytest tests/ -q`
* Single: `py -m pytest tests/test_simulator.py -q`
* Order-flip: `py scripts/run_orderflip_test.py --seeds 5`
* Smoke: `py scripts/run_smoke.py`
* Baseline: `PYTHONPATH=.;../cdb py scripts/run_baseline_comparison.py` (CDB sibling required; ~28s/reset).
* Provenance chain for every claim: `claim -> figure/table -> analysis script -> processed -> raw -> config -> seed -> git commit -> benchmark version`.

---

## 2. Current State (verified)

### 2.1 DONE

* `data_manifest/benchmark_lock.json` — CDB commit `e8b86d0`, sample 155350 events, sha256 present.
* `configs/experiments/pilot_v1.yaml`, `main_v1.yaml` — exist, need reframing edits (see 4.6).
* `baseline_results.json` — P0 0.0761 +/- 0.006 (n=3), P1 0.0839 (n=1), budget 20. Infrastructure noise, not a result.
* `hades/query_menu.py` — 7-source fixed menu (auth, process, network, dns, persistence, powershell, object_access). Isolates acquisition policy from SQL skill. GOOD — keep.
* `hades/harness.py` — CDB `run(env,model)` contract, P0/P1 only. GOOD scaffold — extend.
* `hades/simulator/environment.py|observations.py|scenarios.py` — synthetic SimEnv A-E, 35 tests pass, G1 synthetic PASS (B 90/90, C 76/90, D 13/90). Mechanism exists synthetically.
* `docs/threat_model.md` R0-R4 definitions. GOOD.

### 2.2 MISSING

P2-P5 as `Policy` objects, hypothesis tracker, relevance matrix, CDB corruption engine, estimators, metrics/stats, `fast_db.py`, sweep runners, figures/tables, manuscript.

### 2.3 KNOWN DEFECTS (must fix, not build on)

1. `hades/simulator/environment.py: expected_ig / expected_reliable_ig / hades_utility / _update_beliefs` — heuristic (`affinity*4.0` boost, `IG*rel`, `U=ERHG-lam*cost-mu*risk`, weight-inversion update). Dimensionally inconsistent, double-counts. REPLACE (see Phase 1).
2. `hades/simulator/observations.py` — no `likelihood(e|H,q)` accessor. ADD.
3. `scripts/run_orderflip_test.py` — inline policy logic duplicates future classes; `print` with unicode arrow crashes on cp1252; D-scenario mu sensitivity undocumented. FIX.
4. `hades/query_menu.py: QuerySpec` — no `*_estimated` fields, no affinity, placeholder `reliability_true` unlabeled. EXTEND.
5. `hades/policies/base.py: InvestigationState` — no beliefs/tracker, `remaining_budget:int` vs SimEnv `float`. EXTEND.
6. `hades/harness.py: _extract_timestamps` — submit-everything baseline. GATE behind flag for P2+.
7. `docs/literature_matrix.csv` — 9 rows, missing Settles08/09, Naghshvar13, ECC-AHT26, OpenSec26, SecRespond26. ADD.
8. `pyproject.toml: build-backend legacy:build` — breaks `pip install -e .`. FIX to `setuptools.build_meta`.

---

## 3. Target Architecture (reframed)

```text
Campaign/Scenario
  -> Hidden hypotheses H_t (evaluator-only truth)
  -> Candidate evidence Q_t (7-source menu)
  -> Observation/Corruption model p(e|H,q,r,phi) (reliability+manipulation INSIDE likelihood)
  -> Acquisition policies: P0 P1 P2 P3 P4 P4b P7 P5-robustVoI (+P6 LLM ref only)
  -> Next query -> CDB / SimEnv
  -> Bayesian posterior update -> repeat until budget exhausted or stop rule fires
  -> CDB scorer (coverage) + hypothesis-correctness scorer + cost/degradation metrics
```

Objective (replaces old U):

```text
V(q) = E_{e ~ p(e|H_t,q,phi_hat)}[ U_terminal(H_{t+1}(e)) ] - lam * Cost(q)
P5 = argmax_q V(q); robust variant = max_q min_{phi in budget} V(q;phi)
```

* `U_terminal` = expected utility of optimal terminal decision (e.g. -entropy or max-belief / coverage-weighted loss). IG is a diagnostic, not the objective.
* `lam` = single free param by budget normalization. `mu` DELETED (manipulation lives in likelihood).
* `r_hat/phi_hat` = policy-side estimates. `r_true/phi_true` = evaluator-only.

Policy ladder (all cited in code headers):

```text
P0 random (floor) | P1 fixed heuristic (floor+) | P2 relevance (static adaptive)
P3 IG [Naghshvar13; ECC-AHT26] | P4 IG/cost | P4b IG/cost+rel [Settles08 — NOT novel]
P7 Bayes-AL expected-error-reduction/Thompson (anti-strawman)
P5 robust-VoI HADES (contribution = study of this under corruption, not formula novelty)
P6 LLM frozen reference only (optional)
```

Ablation V0-V4: V0 IG | V1 +cost | V2 +r_hat in likelihood | V3 +phi_hat non-adaptive | V4 robust minimax | V5 oracle (diagnostic only, never a claim).

---

## 4. Phase 0 — Freeze + Repair (2-3 days)

### Tasks

* [ ] `git tag hades-v0-baseline`; move `results/raw/g1_orderflip_test.json` -> `results/raw/g1_v0_legacy.json` (heuristic-era record; do not cite as reframed evidence).
* [ ] Fix `scripts/run_orderflip_test.py`: replace unicode `->` arrows with ASCII, document tie-break (`alphabetical max (score,name)`), add `--mu` sweep support.
* [ ] Fix `pyproject.toml`: `build-backend = "setuptools.build_meta"`.
* [ ] Re-verify CDB pin: `git -C ../cdb rev-parse HEAD` -> update `benchmark_lock.json`.
* [ ] Add `docs/REFRAME.md` (1 page: old U retired, new V, baselines cited).

### Acceptance

```powershell
py scripts/run_smoke.py
py -m pytest tests/ -q
```

Both green on clean clone. No new science in this phase.

---

## 5. Phase 1 — Belief + Contaminated-Observation Model (1-1.5 wks) — DO FIRST

> Agent-2 constraint: do NOT write more policy code on the old log-score/softmax heuristic. Reframe foundation first or you rewrite twice.

### 5.1 New: `hades/belief/likelihood.py`

```python
@dataclass LikelihoodTable:
    p_obs: Dict[Tuple[str,str,str], float]  # (source,hyp,obs_class) -> prob, sums to 1 per (source,hyp)

def nominal_likelihood(source, hyp, obs_class, relevance) -> float
def contaminated_likelihood(e, hyp, source, r_hat: float, phi_hat: float, forged_dist) -> float:
    # p(e|H,q) = r_hat * p_nominal(e|H,q) + (1-r_hat) * p_noise(e) mixed with phi_hat * p_forged
def make_default_table(sources, hypotheses, relevance, obs_classes) -> LikelihoodTable
```

### 5.2 New: `hades/belief/posterior.py`

```python
def update(beliefs: Dict[str,float], e: str, source: str, table: LikelihoodTable, r_hat, phi_hat) -> Dict[str,float]
# Bayes: posterior[h] propto prior[h] * likelihood(e|h,source). Validate sum==1.0, fail loudly.
```

### 5.3 New: `hades/belief/value.py`

```python
def entropy(beliefs) -> float
def eig(source, beliefs, table, r_hat, phi_hat) -> float  # H(now) - E_e[H(after)]
def terminal_utility(beliefs) -> float  # v1: max_belief or -entropy; document choice, freeze
def voi(source, beliefs, table, cost, lam, r_hat, phi_hat) -> float
def robust_voi(source, beliefs, table, cost, lam, phi_budget) -> float  # Stage C only
```

### 5.4 New: `hades/belief/relevance.py`

```python
RELEVANCE: Dict[Tuple[str,str], float]  # (attack_type, source) -> [0,1]
RELEVANCE_PROVENANCE: Dict[...] -> {"source": "attck|sigma|expert-v0", "version": "v0", "note": str}
# v0 = explicit expert heuristic. NEVER derive from held-out CDB flags. Empirical calibration later on calibration split only.
```

### 5.5 Edit: `hades/simulator/environment.py`

* KEEP: `SimEvidenceSource`, `SimScenario`, `reset/step/budget/history`, `_validate_beliefs`, R1/R4 hooks.
* REPLACE `expected_ig`, `expected_reliable_ig`, `hades_utility`, `_update_beliefs` with thin wrappers calling `hades/belief/*`. Keep old scalarized versions as `legacy_scalarized_utility()` clearly labeled `# LEGACY diagnostic only`.
* `step()` sampling stays, but belief update routes via `posterior.update`.

### 5.6 Edit: `hades/simulator/observations.py`

* KEEP `sample()` dynamics. ADD `likelihood()` + `as_matrix()` accessors. Document independence of `reliability` and `manipulation_risk`.

### 5.7 Tests: `tests/test_belief.py` (new) + update `test_simulator.py` helpers

* EIG ~= 0 when uninformative; EIG high when perfectly discriminating; symmetric queries tie; certain posterior -> EIG -> 0; sum-to-1 invariant; policy path uses only `*_estimated`.

---

## 6. Phase 2 — Policy Ladder as Cited Baselines (1 wk)

Create in `hades/policies/` — common signature:

```python
def select_query(state: InvestigationState, menu: Dict[str,QuerySpec], beliefs, likelihood, estimators) -> Optional[str]
# deterministic tie-break: alphabetical max (score,name). Log full score dict as JSON per step.
```

| File | Rule | Header citation |
|---|---|---|
| `p2_relevance.py` | `argmax relevance[leading_hyp][s]` + cooldown | static baseline |
| `p3_ig.py` | `argmax EIG` | Naghshvar & Javidi 2013; ECC-AHT 2026 |
| `p4_ig_cost.py` | `argmax EIG/cost` (+zero-cost guard) | cost-aware baseline |
| `p4b_ig_cost_rel.py` | `argmax EIG(r_hat-likelihood)/cost` | Settles et al. 2008 — NOT novel |
| `p7_bayes_al.py` | expected error reduction / Thompson sampling | anti-strawman, Settles s4 |
| `p5_robust_voi.py` | `argmax V(q)` / `robust_voi` | HADES under test; Stage A phi=0, Stage B fixed phi, Stage C minimax |

Edit `hades/policies/base.py`: add `beliefs`, `hypothesis_tracker`, `remaining_budget: float`. Keep old fields for compat.
Edit `hades/query_menu.py`: add `reliability_estimated`, `manipulation_risk_estimated`, `hypothesis_affinity`, `cost_units="budget"`, `provenance` fields (defaults keep P0/P1 working).
Edit `hades/harness.py`: add `submission_mode: naive|hypothesis_gated`; P0/P1 use naive, P2+ use `tracker.get_submission_timestamps()`; make `POLICY_REGISTRY` extensible.
New `tests/test_policies.py`: valid keys, budget respect, deterministic ties, `*_true` inaccessible (AST + runtime proxy test), `mu`-free reduction checks.

Do NOT build P6 LLM, ExCyTIn adapter, or R4 adaptive attacker yet.

---

## 7. Phase 3 — F1/F5 Kill Gate on Simulator (3-5 days, NO CDB)

New `scripts/run_f1_sweep.py` (refactor `run_orderflip_test.py` to import policies, not inline):

```powershell
py scripts/run_f1_sweep.py --seeds 20 --noise 0,0.10,0.25,0.50 --budgets 10
```

* Sweep reliability perturbations + estimator noise on scenarios A-E.
* Report: flip rate P5-vs-P4/P4b/P7, simulator coverage-AUC, F5 degradation curve.
* Figure: "next-query ranking under increasing corruption" heatmap. Table: regimes x policies.
* GO: flips in >=2 independent configs + flip->outcome lift + non-inferior at 25% noise. NO-GO: ~0 flips -> kill method claim (artifact/measurement or H4 negative-results pivot); collapse at 10-25% noise -> estimator paper reframe.
* Do NOT proceed to CDB engine until GO.

---

## 8. Phase 4 — Corruption Engine + Estimators (2-3 wks, gated on F1 PASS)

```text
hades/corruption/base.py       — Corruptor.corrupt(obs,ctx)->obs, threat_budget, independent seed
  missing.py    R1 drop {0.1,0.25,0.5}
  stale.py      R2 skew {0,1h,24h}, schema-preserving
  misleading.py R3 plausible decoys supporting wrong hyp (ATT&CK-grounded)
  targeted.py   R4 observes query history, suppresses predicted-best source (document worst-case assumption)
hades/reliability/estimator.py — Clean / Noisy(sigma) / Miscalibrated / Adversarial; r_hat per source, trained on calibration only
```

Invariants: corruption changes observations only, never ground-truth labels; corruption seed != campaign seed; policy never sees regime/`r_true`.
`tests/test_corruption.py`: truth preserved, obs modified, determinism, leakage-free.
Red-team F4: second corruption family by someone not building policies; effect must survive both.

---

## 9. Phase 5 — CDB Transfer (2-3 wks)

1. `hades/benchmark/fast_db.py` — `executemany` batch 5000; before/after benchmark; byte-equivalence on obs + `score_hunt`.
2. `hades/benchmark/candidate_extractor.py` — `EvidenceItem(timestamp,event_id,computer,source,metadata)`; hypothesis-gated submission.
3. `hades/hypothesis/` — campaign->hypothesis map from ATT&CK data-components + Sigma + CDB docs (never held-out flags); priors from public tactic freqs; freeze 14-calibration / 12-heldout split in `main_v1.yaml`.
4. Leakage audit script + doc: policy cannot import `evaluator_truth|reliability_true|manipulation_risk_true|flags`; Sigma-truth circularity mitigated by holding out entire procedures.
5. Pilot per `pilot_v1.yaml` (R0, 2 budgets x 3 seeds): all-terminate, valid probs, non-degenerate, reproducible.

---

## 10. Phase 6 — Main Sweep + Statistics (2-3 wks)

Matrix: `{P0,P1,P2,P3,P4,P4b,P7,P5} x budgets {10,20,35,50} x regimes {R0-R4} x intensities {0,0.1,0.25,0.5} x 30 paired seeds`.
`scripts/run_full_sweep.py` with checkpointing -> `results/raw/main_v1/` (immutable). Pre-commit results-table template BEFORE held-out runs.
`hades/evaluation/metrics.py`: coverage (CDB-native), coverage/query, cost-to-25/50/75%, wrong-hypothesis rate (campaign-graph scorer — coverage != correctness), order-flip rate, targeted degradation (abs+rel), premature-stop.
`hades/evaluation/statistics.py`: paired Wilcoxon + Holm on pre-registered contrasts (P5-vs-P4, P5-vs-P4b, P5-vs-P7), bootstrap 95% CI on coverage-AUC, Cliff delta. `ablation.py` V0-V4. `failure_analysis.py` traces.

---

## 11. Phase 7 — Hardening (gated, deferred)

R4 minimax + F6 policy-aware attacker; conformal stopping + ECE/pass^k (STOP-CAL import) as RQ5; sensitivity `lam/tau/priors/corruption`; F7 campaign generalization, F8 budgets 5-75, F9 |H| {4,8,16,32} on simulator, F10 ExCyTIn only if CDB held-out replicates. P6 LLM frozen reference only.

---

## 12. Phase 8 — Artifact + IEEE Paper + Deployment

Repro: `Dockerfile`, `docker-compose.yml`, `requirements-lock.txt`:

```powershell
py scripts/run_smoke.py
py scripts/run_full_sweep.py --config configs/experiments/main_v1.yaml
py scripts/run_statistics.py
py scripts/make_figures.py
```

Publish: GitHub + Zenodo DOI, CDB hash + seeds + commit per run, `results/raw|processed|publication` chain. Target artifact badges.
Paper (10 secs): I Intro (bounded claims) | II Related (AL/ASHT/BED FIRST + OpenSec/SecRespond + benchmarks + anti-forensics) | III Threat model | IV Method (contaminated likelihood + robust-VoI, estimators policy-side) | V Corruption engine | VI Setup (split + prereg appendix) | VII Results F1-F10 with CIs | VIII Failure/limits | IX Artifact | X Conclusion + ethics (acquisition aids attacker evidence-destruction — defensive framing).
Claim exactly 3: controlled study; open engine+harness+sim; boundary conditions F5/F6. NEVER: new general method / new benchmark / LLM system / "first IG hunting". Venue: IEEE S&P / USENIX / DSN empirical or TIFS. Submit <=4 months (scooping clock). G6 final novelty re-sweep; use "to best of our knowledge" until then.

### Kill/pivot

F1~=0 -> kill method, artifact/measurement or H4 negative-results paper. F2/F6/F10 fail -> narrow to non-adaptive or CDB-specific with limits. Estimator-bound -> estimator paper.
