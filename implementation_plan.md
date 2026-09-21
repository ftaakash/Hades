# HADES — Definitive Merged Implementation Plan

> [!NOTE]
> **Merged from**: Our implementation plan (engineering backbone) + [HADES_End_to_End_Development_and_Publication_Plan.md](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/HADES_End_to_End_Development_and_Publication_Plan.md) (research/publication governance). Gap analysis: [alignment_analysis.md](file:///C:/Users/Administrator/.gemini/antigravity/brain/f1dc7211-70d0-45b4-a647-c9c478c1a2c5/alignment_analysis.md).
>
> **Goal**: A scientifically defensible HADES result whose implementation, data, statistics and claims can survive IEEE peer review.

---

## Research Contract

**Core question**: Can a budget-aware investigation policy select the next telemetry acquisition action that maximizes reliable discrimination among competing cyberattack hypotheses, while accounting for acquisition cost and adversarial evidence risk?

**Load-bearing proposition**: When evidence sources differ in reliability/manipulability, reliability-aware evidence acquisition can choose a different next query than IG-only or IG/cost policies, and those different choices can produce better investigation outcomes under a finite query budget.

**Non-negotiable**: Never fabricate results, never silently change scoring semantics, never turn a failed gate into a success by changing the protocol post hoc.

---

## Go/No-Go Gates

| Gate | Requirement | Failure Action |
|---|---|---|
| G0 | Baseline reproducible | Fix environment |
| G1 | Order-flip phenomenon exists | Reformulate or abandon |
| G2 | HADES choices improve outcomes | Downgrade to measurement study |
| G3 | No major clean-regime penalty | Tune λ/μ or reject method |
| G4 | Robustness advantage exists | Drop manipulation-risk term |
| G5 | Effect generalizes | Narrow claims |
| G6 | Literature gap survives final audit | Don't submit as novel-method paper |

---

## Execution Plan

### Phase 0 — Lock Environment & Provenance (Week 1–2)

**Gate**: G0

#### Git + Dependencies

##### [NEW] [.gitignore](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/.gitignore)
##### [NEW] [requirements.txt](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/requirements.txt)
##### [NEW] [Dockerfile](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/Dockerfile)
##### [NEW] [docker-compose.yml](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/docker-compose.yml)

#### Provenance

##### [NEW] [data_manifest/benchmark_lock.json](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/data_manifest/benchmark_lock.json)
CDB version/commit, dataset checksum, Python version, OS, event count, scorer version.

##### [MODIFY] [baseline_results.json](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/baseline_results.json)
Add `run_metadata` block: `git_commit`, `cdb_version`, `dataset_checksum`, `seed`, `timestamp_utc`.

##### [NEW] [docs/threat_model.md](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/docs/threat_model.md)
##### [NEW] [docs/literature_matrix.csv](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/docs/literature_matrix.csv)

---

### Phase 1A — Minimal Simulator + Order-Flip Gate G1 (Week 2–4)

> [!IMPORTANT]
> Build the cheapest possible falsification of the core mechanism BEFORE expensive CDB work.

##### [NEW] [hades/simulator/environment.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/simulator/environment.py)
- 5–10 attack hypotheses, 10–20 evidence sources
- Each source: [(cost, latency, reliability_true, reliability_estimated, manipulation_risk_true, manipulation_risk_estimated, relevance_per_hypothesis)](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/harness.py#48-125)
- `SimEnv.step(source)` → synthetic observation based on true hypothesis + reliability
- `SimEnv.reset(true_hypothesis, seed)` → deterministic, ~instant

> [!WARNING]
> **Reliability and manipulation risk are conceptually independent.** Source A can be 99% reliable but highly forgeable; Source B can be 90% reliable but tamper-proof. Model them as separate fields, not `manip_risk = 1 - reliability`.

##### [NEW] [hades/simulator/observations.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/simulator/observations.py)
Explicit observation-likelihood model for each (source, hypothesis) pair.

##### [NEW] [hades/simulator/scenarios.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/simulator/scenarios.py)
Required synthetic test cases:
- **A — No reliability difference**: IG/IG-cost/HADES should converge
- **B — Reliability reverses query order**: raw IG → Q1, reliability-aware → Q2
- **C — Cost reverses query order**: IG → expensive Q1, IG/cost → Q2
- **D — Manipulation risk reverses query order**: strong source becomes unsafe
- **E — No useful distinction**: all policies behave similarly

##### [NEW] [scripts/run_orderflip_test.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/scripts/run_orderflip_test.py)
Enumerate simulator states; run IG vs IG/cost vs HADES; report order-flip rate.

**G1 Criterion** (qualitative, not an arbitrary threshold):
> At least one non-degenerate class of states exists in which reliability/manipulability changes the preferred query relative to IG/IG-cost, and the phenomenon persists across multiple independently generated simulator configurations. Report the actual observed order-flip rate.

---

### Phase 1B — Hypothesis Tracking Engine (Week 3–5)

##### [NEW] [hades/hypothesis/model.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/hypothesis/model.py)
```python
@dataclass
class AttackHypothesis:
    id: str
    description: str
    prior: float
    posterior: float
    evidence_requirements: Set[str]
    evidence_for: List[EvidenceItem]
    evidence_against: List[EvidenceItem]
    candidate_timestamps: Set[str]
```

##### [NEW] [hades/hypothesis/tracker.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/hypothesis/tracker.py)
- `initialize(scenario_obs)` → seed hypotheses
- `update(source, observation, timestamps)` → Bayesian posterior
- `get_discrimination_value(source)` → IG for source
- `get_reliable_ig(source)` → IG × reliability
- `get_submission_timestamps(threshold)` → high-posterior timestamps only
- **Probability invariant**: `sum(posteriors) == 1.0` validated at every step; violations fail loudly

##### [NEW] [hades/hypothesis/belief_update.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/hypothesis/belief_update.py)
Transparent Bayesian update using observation likelihoods from relevance model.

##### [NEW] [hades/hypothesis/relevance.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/hypothesis/relevance.py)
`RELEVANCE: Dict[(attack_type, source_name), float]` — 7 attack types × 7 sources.

> [!WARNING]
> **Relevance provenance matters.** Document whether each value is expert-assigned or empirically derived. Use a calibration/training subset if deriving from data — never estimate from the same campaigns used for evaluation (leakage). For v1, treat explicitly as a **fixed expert heuristic baseline**.

##### [NEW] [hades/benchmark/candidate_extractor.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/benchmark/candidate_extractor.py)
`EvidenceItem(timestamp, event_id, computer, source, metadata)` — structured extraction replacing naive [_extract_timestamps](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/harness.py#36-46).

#### Query Schema Updates

##### [MODIFY] [query_menu.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/query_menu.py)
Add to [QuerySpec](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/query_menu.py#36-56):
```python
reliability_estimated: float      # what the policy sees
manipulation_risk_true: float     # evaluator only
manipulation_risk_estimated: float # what the policy sees
```

**Anti-leakage rule**: policies read ONLY `reliability_estimated` and `manipulation_risk_estimated`. Tests must verify `reliability_true` and `manipulation_risk_true` are inaccessible to any policy code path.

##### [MODIFY] [base.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/policies/base.py)
Add `hypothesis_tracker: Optional[HypothesisTracker]` to [InvestigationState](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/policies/base.py#29-39). Extend with `ground_truth_hidden` (evaluator-only object).

##### [MODIFY] [harness.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/harness.py)
- Instantiate `HypothesisTracker` for hypothesis-aware policies
- Use `hypothesis_tracker.get_submission_timestamps()` for submission
- **Decision trace logging**: at each step, record which query each ablation variant *would* choose (required for order-flip measurement)

---

### Phase 2 — Policy Ladder P2–P5 (Week 5–8)

All implement `Policy.select_query(state, menu) → Optional[str]` with deterministic tie-breaking and JSON decision logging.

##### [NEW] [relevance_policy.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/policies/relevance_policy.py) — P2
`argmax_s relevance[leading_hypothesis][s]`, cooldown on recently queried sources.

##### [NEW] [information_gain_policy.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/policies/information_gain_policy.py) — P3
`argmax_s IG(s | H_t)` — raw information gain. Validate: unit-test entropy, analytical 2-hypothesis cases, symmetric cases, irrelevant-evidence-produces-zero-IG.

##### [NEW] [ig_cost_policy.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/policies/ig_cost_policy.py) — P4
`argmax_s IG(s) / cost(s)`. Handle zero/tiny cost explicitly.

##### [NEW] [ig_cost_reliability_policy.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/policies/ig_cost_reliability_policy.py) — P4b (Ablation)
`argmax_s IG(s) * reliability_estimated(s) / cost(s)` — no manipulation-risk penalty. This is ablation step A2.

##### [NEW] [hades_policy.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/policies/hades_policy.py) — P5
```
U(q | H_t) = ERHG(q, H_t) − λ·Cost(q) − μ·ManipulationRisk_estimated(q)
q* = argmax_q U(q | H_t)
STOP when max_q U(q | H_t) < τ
```
- `lambda_`, `mu`, `tau` are tunable hyperparameters
- `mu=0` → reduces to P4b; `lambda_=0, mu=0` → reduces to P3
- Early stopping based on τ (evaluate separately from acquisition)

##### [NEW] [llm_policy.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/policies/llm_policy.py) — P6 (Optional)
Frozen model/version/prompt/temperature. Never necessary for the paper's validity.

---

### Phase 3 — Corruption Regimes R1–R4 (Week 8–11)

**Ground-truth invariant**: corruption changes what the investigator observes, never what actually happened.

##### [NEW] [hades/corruption/base.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/corruption/base.py)
##### [NEW] [hades/corruption/missing.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/corruption/missing.py) — R1
`MissingCorruptor(drop_rate)`. Levels: 10%, 25%, 50%.

##### [NEW] [hades/corruption/stale.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/corruption/stale.py) — R2
`StaleCorruptor(max_skew_seconds)`. Preserves realistic schemas.

##### [NEW] [hades/corruption/misleading.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/corruption/misleading.py) — R3
`MisleadingCorruptor(n_decoys)`. Semantically plausible benign-looking events.

##### [NEW] [hades/corruption/targeted.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/corruption/targeted.py) — R4
`TargetedCorruptor(target_sources, mode)`. Adaptive to current policy — document attacker model explicitly.

##### [NEW] [hades/reliability/estimator.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/reliability/estimator.py)
- `CleanEstimator`: estimated = true
- `NoisyEstimator`: estimated = true + N(0, σ²), clipped [0,1]
- `AdversarialEstimator`: inverts reliability ranking
- Test correlated vs independent reliability/risk

Each corruption mode needs written justification: assumed attacker capability, modifiable telemetry, plausibility rationale, what the benchmark abstracts away.

---

### Phase 4 — Batched Reset + Pilot + Full Sweep (Week 10–15)

##### [NEW] [hades/benchmark/fast_db.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/benchmark/fast_db.py)
`FastLogDatabase` — `executemany` with 5K batches. Benchmark before/after; verify semantically equivalent outputs.

##### [NEW] [configs/experiments/pilot_v1.yaml](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/configs/experiments/pilot_v1.yaml)
Small subset (2 policies, 2 budgets, 3 seeds). Verifies: all policies terminate, no leakage, valid probabilities, corruption preserves ground truth, metrics non-degenerate, reproducible.

##### [NEW] [configs/experiments/main_v1.yaml](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/configs/experiments/main_v1.yaml)
```yaml
policies: [P0, P1, P2, P3, P4, P4b, P5]
budgets: [5, 10, 20, 40, 80]
stress_regimes: [R0, R1, R2, R3, R4]
seeds: {count: 30, base: 1000}
statistics: {bootstrap: 10000, alpha: 0.05, correction: holm}
```
**Freeze before the main run.** Config is version-controlled; changing it post-run requires a new experiment ID.

##### [NEW] [scripts/run_pilot.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/scripts/run_pilot.py)
##### [NEW] [scripts/run_full_sweep.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/scripts/run_full_sweep.py)
Paired: same campaign/seed across all policies. Checkpointing. Results → `results/raw/` (immutable).

---

### Phase 5 — All 8 Metrics + Statistics + Figures (Week 12–17)

##### [NEW] [hades/evaluation/metrics.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/evaluation/metrics.py)
All 8 metrics per proposal:
1. Campaign coverage
2. Coverage per query
3. Cost per coverage (to reach 25%, 50%, 75%)
4. Wrong-hypothesis rate
5. Time to correct hypothesis
6. **Order-flip rate** (mechanism metric, requires decision traces)
7. Targeted-attack degradation (absolute + relative)
8. Premature-stop rate

##### [NEW] [hades/evaluation/statistics.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/evaluation/statistics.py)
`bootstrap_ci`, `paired_permutation`, `wilcoxon_signed_rank`, `holm_bonferroni`, `cohens_d`. Statistical plan frozen before analysis.

##### [NEW] [hades/evaluation/ablation.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/evaluation/ablation.py)
Ablation ladder: A0 (P3: IG) → A1 (P4: +cost) → A2 (P4b: +reliability) → A3 (P5: +manipulation risk). Each transition answers: "what does this component add?"

##### [NEW] [hades/evaluation/failure_analysis.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/hades/evaluation/failure_analysis.py)
Collect and categorize: HADES loses to P0, HADES loses to P3, HADES loses to P4, HADES changes query but outcome unchanged, HADES makes confidently wrong hypothesis.

##### [NEW] [scripts/run_sensitivity.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/scripts/run_sensitivity.py)
λ ∈ {0.25, 0.5, 1.0, 2.0}, μ ∈ {0.25, 0.5, 1.0, 2.0}, τ sweep. Is HADES robust or fragile?

##### [NEW] [scripts/make_figures.py](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/scripts/make_figures.py)
7 publication figures:
1. HADES architecture diagram
2. Policy pipeline
3. Coverage vs budget (CI bands)
4. Clean vs adversarial degradation
5. Order-flip heatmap
6. Ablation bar chart (A0→A3)
7. Failure-case decision trace (success + failure)

8 tables generated from scripts (never manually edited):
1. Dataset/benchmark characteristics
2. Policy definitions
3. Query-source characteristics
4. Main performance results (mean, CI, coverage/query, WHR)
5. Stress-regime results
6. Ablation results
7. Statistical comparison matrix
8. Failure-analysis summary

**Gates G2/G3/G4 evaluated here.**

---

### Phase 6 — External Validation (Week 17–20) — Stretch

Port HADES policy to a second hunting environment if licensing permits. **Gate G5.**

---

### Phase 7 — Paper + Artifact Freeze (Week 20–24)

#### Paper: 10 sections (IEEE venue-mapped at submission time)

| § | Title | Key Content |
|---|---|---|
| I | Introduction | Problem, gap, RQ1–RQ5, contributions |
| II | Related Work | By dimension: hunting benchmarks, sequential acquisition, cost-aware selection, adversarial evidence, gap table |
| III | Problem Formulation | H_t, Q_t, Cost, Reliability, ManipRisk, U(q\|H_t), stopping |
| IV | HADES Policy | Algorithm pseudocode, decision trace example, complexity |
| V | Experimental Methodology | CDB, R0–R4, P0–P5, all 8 metrics, statistical design |
| VI | Results | RQ1 efficiency, RQ2 order-flip, RQ3 robustness, RQ4 ablation, RQ5 stopping |
| VII | Ablation & Failure Analysis | A0→A3 decomposition, failure cases with traces |
| VIII | Threats to Validity | Internal, construct, external, statistical, benchmark |
| IX | Reproducibility | Code, configs, seeds, Docker, one-command smoke test |
| X | Conclusion | Only what experiments establish — and don't |

#### Result-to-Paper Provenance Chain

Every paper statement traces through:
```
paper claim → figure/table → analysis script → processed data → raw run → config → seed → git commit → benchmark version
```
Never manually edit numbers in the manuscript.

#### [NEW] [docs/literature_matrix.csv](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/docs/literature_matrix.csv)
Final novelty audit before submission. **Gate G6.**

#### Mock Reviewer Simulation

Before submission, answer concretely:
1. **Novelty**: What exactly is new? (one paragraph)
2. **Methodology**: Why isn't HADES simply IG/cost + penalty? (answered by ablation)
3. **Threat model**: Why should attackers be able to manipulate these sources? (source-by-source)
4. **Benchmark validity**: Why should CDB results generalize? (honest answer)
5. **Statistics**: Are differences meaningful? (CIs, effect sizes, correction)
6. **Reproducibility**: Can another researcher reproduce? (clean-machine test)
7. **Negative cases**: When does HADES fail? (real traces)

---

## Project Architecture

```
hades-bench-v1/
├── hades/
│   ├── policies/
│   │   ├── base.py, random_policy.py, fixed_heuristic.py
│   │   ├── relevance_policy.py, information_gain_policy.py
│   │   ├── ig_cost_policy.py, ig_cost_reliability_policy.py
│   │   └── hades_policy.py, [llm_policy.py]
│   ├── hypothesis/
│   │   ├── model.py, tracker.py, belief_update.py, relevance.py
│   ├── simulator/
│   │   ├── environment.py, observations.py, scenarios.py
│   ├── corruption/
│   │   ├── base.py, missing.py, stale.py, misleading.py, targeted.py
│   ├── reliability/
│   │   ├── estimator.py, calibration.py
│   ├── benchmark/
│   │   ├── cdb_adapter.py, fast_db.py, candidate_extractor.py
│   ├── evaluation/
│   │   ├── metrics.py, statistics.py, ablation.py, failure_analysis.py
│   ├── provenance/
│   │   ├── manifest.py, run_metadata.py, checksums.py
│   └── query_menu.py, harness.py
├── configs/experiments/
├── scripts/
├── tests/
├── results/{raw,processed,publication}/
├── data_manifest/
├── docs/
├── paper/{manuscript,supplementary,rebuttal}/
├── figures/, tables/
├── Dockerfile, docker-compose.yml
├── CITATION.cff, LICENSE
└── README.md
```

---

## Verification Plan

### Tests

| File | Scope |
|---|---|
| `test_simulator.py` | Order-flip, synthetic env correctness, cases A-E |
| `test_hypothesis.py` | Posterior updates, probability invariant, timestamp filtering |
| `test_policies.py` | Valid keys, budget respect, deterministic ties, stopping |
| `test_corruption.py` | Ground truth preserved, observations modified |
| `test_stats.py` | CI coverage, test calibration |
| `test_harness_integration.py` | Full CDB episode, CDB-compatible output |
| `test_leakage.py` | Policies cannot access `*_true` fields |
| `test_reproducibility.py` | Same seed → same results |
| `test_candidate_extraction.py` | Structured extraction, hypothesis association |
| `test_experiment_config.py` | Config loading, validation, freeze semantics |

### Publication Readiness Checklist

See §46 of the [end-to-end plan](file:///c:/Users/Administrator/Desktop/Major%20Project/hades-bench-v1/HADES_End_to_End_Development_and_Publication_Plan.md) — 4 categories, 30+ items covering scientific, reproducibility, security/ethics, and manuscript integrity checks.
