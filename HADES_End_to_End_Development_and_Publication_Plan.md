---
title: "HADES — End-to-End Development, Experimental, and Publication Master Plan"
researcher: "Aakash G.S."
version: "HADES v2.0 — Execution Master Plan"
status: "Implementation + research execution plan"
date: "07 September 2026"
primary_benchmark: "Cyber Defense Benchmark (CDB)"
paper_target: "IEEE-style empirical cybersecurity research paper"
---

# HADES — End-to-End Development, Experimental, and Publication Master Plan

> **Purpose:** This file is the execution contract for an agent implementing HADES and producing the final research paper and reproducibility artifact.
>
> **Core research idea:** Budgeted Evidence Acquisition for Cyber Threat Hunting Under Adversarial Telemetry.
>
> **Current state:** The experimental plumbing / G1 sanity gate is substantially complete: the CDB integration works end-to-end, the policy interface exists, P0 (random) and P1 (fixed heuristic) run against the CDB scoring path, and an initial baseline result has been recorded. **HADES itself has not yet been validated.**
>
> **Immediate priority:** Implement hypothesis tracking, then P2/P3, before building a polished agent or interface.
>
> **Non-negotiable rule:** Never fabricate numerical results, never silently change the benchmark/scoring semantics, and never turn a failed go/no-go gate into a success by changing the protocol after seeing the result.

---

# 0. Executive Research Contract

## 0.1 Core research question

> **Can a budget-aware investigation policy select the next telemetry acquisition action that maximizes reliable discrimination among competing cyberattack hypotheses while accounting for acquisition cost and adversarial evidence risk?**

## 0.2 Load-bearing proposition

The research does **not** claim novelty for any one component in isolation.

The load-bearing empirical proposition is:

> **When evidence sources differ in reliability/manipulability, reliability-aware evidence acquisition can choose a different next query than information-gain-only or information-gain-per-cost policies, and those different choices can produce better investigation outcomes under a finite query budget.**

If this proposition is false, HADES must be downgraded or abandoned rather than forced into a novelty narrative.

## 0.3 What HADES is NOT claiming

Do not claim that HADES is the first system to use:

- information gain
- sequential evidence acquisition
- cost-aware retrieval
- stopping rules
- adversarial evidence
- uncertainty
- cyber threat hunting benchmarks
- agentic security investigation

These are established components / research directions.

The intended contribution is the **specific integration and empirical test of query-order decisions under the joint interaction of hypothesis discrimination, cost, reliability, and evidence manipulation risk in cyber investigation**.

## 0.4 Research artifact philosophy

The implementation must remain:

- transparent
- deterministic where intended
- configurable
- model-independent for the core contribution
- benchmark-compatible
- reproducible
- auditable
- statistically analyzable
- simple enough that another researcher can understand why every query was selected

The first successful version should not depend on an LLM.

---

# 1. Current Baseline: What Is Already Done

## 1.1 Completed infrastructure

The current HADES codebase already establishes:

```text
CDB
  |
  v
ThreatHuntEnv
  |
  v
fixed evidence-source menu
  |
  +--> P0 Random
  |
  +--> P1 Fixed Heuristic
  |
  v
query execution
  |
  v
candidate extraction
  |
  v
CDB-native scoring
  |
  v
coverage result
```

The policy architecture exposes a common policy interface and an investigation state, allowing P0/P1/P2/P3/P4/P5 to be compared using the same environment and scoring path.

## 1.2 Current baseline result

The initial recorded result contains:

- P0 random, 3 runs:
  - 0.07495870641703976
  - 0.08393669932360409
  - 0.06946461276818419
- P0 mean ≈ **0.0761200062**
- P0 population standard deviation ≈ **0.005965**
- P1 fixed heuristic:
  - 0.08393669932360409

Rounded:

| Policy | Budget | Coverage |
|---|---:|---:|
| P0 Random | 20 | 0.0761 ± 0.0060 |
| P1 Fixed heuristic | 20 | 0.0839 |

Observed absolute difference:

```text
0.0839366993 - 0.0761200062
≈ 0.0078166931
```

Relative improvement versus the P0 mean:

```text
≈ 10.27%
```

## 1.3 How to describe the baseline scientifically

At the current stage, write:

> “At budget 20, the fixed heuristic produced higher observed coverage than the three recorded random-policy runs.”

Do **not** write:

> “P1 significantly outperformed P0.”

Statistical significance has not yet been established.

The baseline is a **sanity / infrastructure result**, not evidence that the HADES method works.

## 1.4 Current known engineering issue

The existing candidate extraction submits timestamps in a deliberately naive way: timestamps appearing in observations can be submitted one at a time.

This currently creates a performance burden because `ThreatHuntEnv.reset()` inserts the large sample row-by-row.

The performance problem should be fixed without changing CDB itself:

- add batching/caching where allowed in the HADES wrapper
- use `executemany` or equivalent insertion batching in the local wrapper where possible
- avoid modifying benchmark semantics
- retain a benchmark-version/commit record
- benchmark the optimization before/after
- ensure that the optimized path returns byte-for-byte / semantically equivalent observations and scoring results where applicable

---

# 2. Non-Negotiable Research Gates

These gates control whether the project proceeds.

| Gate | Requirement | Failure action |
|---|---|---|
| G0 | Baseline reproducible | Fix environment |
| G1 | Order-flip phenomenon exists | Reformulate or abandon mechanism |
| G2 | HADES choices improve outcomes | Downgrade to measurement/benchmark study if false |
| G3 | No major clean-regime penalty | Tune objective or reject method |
| G4 | Robustness advantage exists | Remove adversarial-risk term if useless |
| G5 | Effect generalizes | Narrow claims if necessary |
| G6 | Literature gap survives | Do not submit as a novel-method paper if not |

**Important:** G1 refers to the conceptual mechanism demonstrated in a controlled simulator: adding reliability can change the preferred query. The current P0/P1 CDB run is not the same as proving G1.

---

# 3. Immediate Next Objective: Hypothesis Tracking

Do this before P2/P3.

## 3.1 Why hypothesis tracking is required

HADES is supposed to optimize evidence acquisition **for discriminating among competing explanations**.

Without explicit hypotheses, a policy cannot honestly compute:

- relevance
- information gain
- uncertainty reduction
- wrong-hypothesis rate
- time to correct hypothesis
- stopping based on residual uncertainty

The current system has query history and candidate timestamps, but does not yet maintain a first-class hypothesis state.

## 3.2 Required state model

Extend `InvestigationState` to include:

```python
InvestigationState:
    hypotheses
    belief_distribution
    observations
    query_history
    evidence_support
    remaining_budget
    candidate_timestamps
    current_step
    ground_truth_hidden
    metadata
```

Recommended hypothesis representation:

```python
Hypothesis:
    id: str
    description: str
    prior: float
    evidence_requirements: set[str]
    discriminators: dict
```

Example:

```text
H1: credential abuse
H2: lateral movement
H3: persistence
H4: command execution
```

Do not assume these example labels are correct for all CDB campaigns. Build a campaign-specific ground-truth mapping layer.

## 3.3 Probability invariant

At every step:

```text
sum(P(H_i)) = 1
```

The implementation must validate this.

Invalid states must fail loudly rather than silently normalize without a log.

## 3.4 Ground truth separation

Maintain two separate objects:

```text
Evaluator truth:
    actual attack hypothesis
    actual malicious events
    actual corruption mode

Policy-visible state:
    observations
    estimated beliefs
    reliability estimates
    query history
```

Never leak evaluator-only information into the policy.

This is one of the most important anti-leakage rules in the entire project.

---

# 4. Build the Query Semantics Layer

Before P2/P3, every query needs a machine-readable description.

## 4.1 Query schema

Each query should expose:

```yaml
id:
name:
source:
description:
cost:
latency_estimate:
nominal_reliability:
manipulation_risk:
hypothesis_affinity:
returns:
candidate_fields:
```

Separate:

```text
true properties
```

from:

```text
policy estimates
```

For example:

```yaml
reliability_true: 0.85
reliability_estimate: 0.80
```

The policy must never read `reliability_true`.

## 4.2 Query cost definition

Choose one cost definition and freeze it.

Possible cost units:

1. budget units
2. execution time
3. normalized resource cost

For the first paper, the cleanest design is to use the benchmark's query budget as the primary constrained resource and optionally report actual latency separately.

Do not mix wall-clock time with logical query cost unless the relationship is explicitly modeled.

---

# 5. Evidence → Hypothesis Mapping

This is the bridge between CDB observations and the decision problem.

## 5.1 Required mapping

For each evidence source, define which hypotheses it can discriminate.

Example conceptual structure:

```text
auth_events
    strong for:
        H1 credential abuse
        H2 lateral movement

process_events
    strong for:
        H2 lateral movement
        H3 persistence

dns_events
    medium for:
        H1
        H2
```

Do not hard-code these strengths without validation.

## 5.2 Mapping provenance

Every affinity score needs:

```text
source
rationale
author
version
campaign scope
```

Possible origins:

- CDB ground-truth-derived construction
- domain expert annotation
- empirically estimated from pilot data

Do not call expert assumptions “measured.”

---

# 6. Build P2 — Relevance Policy

## 6.1 Purpose

P2 is the first adaptive baseline.

It should answer:

> “Which available evidence source is most directly relevant to the current leading hypotheses?”

## 6.2 Required implementation

Inputs:

```text
current belief distribution
candidate query set
query-hypothesis affinity
already-used queries
remaining budget
```

Output:

```text
next query
```

## 6.3 Deterministic tie-breaking

Freeze a deterministic rule, for example:

```text
1. highest relevance
2. lowest cost
3. fixed query ID order
```

Never use arbitrary dictionary iteration order.

## 6.4 Logging

For every decision:

```json
{
  "step": 3,
  "policy": "P2_relevance",
  "selected_query": "process_events",
  "remaining_budget_before": 18,
  "scores": {
    "auth_events": 0.41,
    "process_events": 0.67,
    "dns_events": 0.12
  },
  "tie_break": null
}
```

This is required for later failure analysis.

---

# 7. Build P3 — Information Gain Policy

## 7.1 Purpose

P3 establishes the classical adaptive baseline.

It asks:

> Which query is expected to reduce uncertainty about the competing hypotheses most?

## 7.2 Entropy

For hypothesis probabilities:

\[
H(P)=-\sum_i P(h_i)\log P(h_i)
\]

For each candidate query \(q\):

\[
IG(q)=H(H_t)-\mathbb{E}_{e\sim q}[H(H_{t+1}\mid e)]
\]

The implementation must define how expected observations are represented.

## 7.3 First implementation should be transparent

Do not use an opaque learned estimator initially.

Use:

- enumerated synthetic observations in the simulator
- explicit observation likelihoods
- deterministic probability calculations

Only later consider learned approximations if necessary.

## 7.4 Validate P3 independently

Before integrating into CDB:

- unit-test entropy
- test simple 2-hypothesis cases analytically
- verify symmetric cases produce equal information gain
- verify a perfectly discriminating query has higher IG
- verify irrelevant evidence produces near-zero IG
- verify already-resolved hypotheses cause IG to shrink

---

# 8. Build P4 — Information Gain / Cost

P4 is:

\[
P4(q)=\frac{IG(q)}{Cost(q)}
\]

## 8.1 Purpose

This separates:

```text
information value
```

from:

```text
information value per unit acquisition budget
```

## 8.2 Required safeguards

Handle:

- zero cost
- invalid cost
- extremely small cost
- floating-point ties
- exhausted budget

For zero cost, define explicit semantics rather than allowing division-by-zero.

---

# 9. Build the HADES Policy — P5

## 9.1 Do not immediately over-engineer

The first P5 must be interpretable.

Start with:

\[
U(q|H_t)=ERG(q|H_t)-\lambda Cost(q)-\mu ManipulationRisk(q)
\]

where:

```text
ERG = Expected Reliable Hypothesis Gain
```

and reliability modifies expected useful information rather than merely multiplying everything by an arbitrary constant.

## 9.2 Candidate conceptual decomposition

A query can be evaluated through:

```text
Expected information value
    × reliability
    × evidence usefulness
    -
cost
    -
manipulation risk
```

But the exact mathematical implementation must be justified by:

1. the simulator
2. the ablation
3. the observed behavior
4. sensitivity analysis

Do not introduce terms merely because they make the final method look novel.

## 9.3 Reliability must not be oracle leakage

Correct:

```text
policy sees estimated reliability
evaluator knows true reliability
```

Incorrect:

```text
policy directly receives reliability_true
```

The latter invalidates the adversarial evaluation.

---

# 10. Build the Simulator Before Full CDB

The simulator is the fastest place to falsify HADES.

## 10.1 Simulator requirements

Create:

- 5–10 hypotheses
- 10–20 evidence sources
- synthetic observation models
- query costs
- reliability values
- manipulation risks
- explicit observation likelihoods
- deterministic seeds

## 10.2 Required synthetic cases

At minimum:

### Case A — No reliability difference

IG, IG/cost and HADES should converge or differ only for justified reasons.

### Case B — Reliability reverses query order

Raw IG prefers Q1.

Reliability-aware policy prefers Q2.

### Case C — Cost reverses query order

IG prefers expensive Q1.

IG/cost prefers Q2.

### Case D — Manipulation risk reverses query order

Nominally strong source becomes unsafe.

### Case E — No useful distinction

All policies should behave similarly.

If HADES only “wins” when the simulator was obviously constructed to favor HADES, the simulator has failed as evidence.

---

# 11. Implement the Corruption Engine

This is required for the central adversarial claim.

## 11.1 Ground-truth invariant

Corruption may change:

```text
what the investigator observes
```

but must not change:

```text
what actually happened in the simulated/CDB attack
```

## 11.2 R0 — Clean

Original benchmark observations.

## 11.3 R1 — Missing

Controlled removal of selected evidence.

Examples:

```text
remove 10%
remove 25%
remove 50%
remove targeted classes
```

Freeze the exact corruption fractions before the main experiment.

## 11.4 R2 — Stale

Inject valid historical records from a different time context.

Important:

- preserve realistic schemas
- record source event timestamps
- mark evaluator provenance
- ensure the policy does not receive a “stale” label

## 11.5 R3 — Misleading

Inject plausible records that support an incorrect competing hypothesis.

Examples:

```text
benign PowerShell activity
plausible authentication from an unrelated source
normal administrative process creation
```

The misleading records must be semantically plausible.

## 11.6 R4 — Targeted manipulation

The attacker is aware of the current policy.

The attacker attempts to:

- suppress the most useful evidence source
- make another source appear stronger
- steer the policy toward the wrong hypothesis

This is the strongest stress condition.

## 11.7 Adaptive attacker caveat

If the corruption function observes policy behavior, that itself must be modeled and documented.

Otherwise the paper will overclaim “adaptive attack.”

---

# 12. Reliability Model

Maintain two values:

```text
Reliability_true
Reliability_estimate
```

## 12.1 Reliability_true

Used only by the evaluator.

Defines how trustworthy the evidence remains under the corruption regime.

## 12.2 Reliability_estimate

Used by the policy.

Possible models:

### Oracle-like controlled estimate

Useful for mechanism validation only.

### Noisy estimate

More realistic.

Example:

```text
estimate = true reliability + Gaussian noise
```

with clipping to [0,1].

### Miscalibrated estimate

Systematically optimistic or pessimistic.

## 12.3 Calibration experiment

Evaluate whether HADES is sensitive to:

```text
accurate estimates
mild noise
large noise
systematic bias
```

This should become a dedicated ablation.

---

# 13. Policy Ladder — Final Experimental Set

Freeze the policy ladder before the main experiment.

| ID | Policy | Purpose |
|---|---|---|
| P0 | Random | non-adaptive floor |
| P1 | Fixed expert | deterministic operational baseline |
| P2 | Relevance | relevance-driven adaptive baseline |
| P3 | Information Gain | uncertainty-reduction baseline |
| P4 | Information Gain / Cost | cost-aware information baseline |
| P5 | HADES | reliability + cost + manipulation-aware policy |
| P6 | LLM investigator (optional) | external reference, not the contribution |

## P6 rule

P6 must remain optional.

Never allow the LLM baseline to become necessary to the paper's validity.

If included:

- freeze model/version
- freeze prompt
- freeze tool definitions
- freeze temperature/sampling
- record exact API/model metadata
- evaluate multiple runs
- prevent it from accessing evaluator-only ground truth

---

# 14. Experimental Data Model

Every run should produce machine-readable records.

## 14.1 Run metadata

```json
{
  "run_id": "...",
  "timestamp_utc": "...",
  "git_commit": "...",
  "cdb_version": "...",
  "dataset_id": "...",
  "dataset_checksum": "...",
  "policy": "P5_HADES",
  "policy_version": "...",
  "seed": 123,
  "budget": 20,
  "stress_regime": "R3_misleading"
}
```

## 14.2 Decision record

```json
{
  "step": 4,
  "beliefs": {
    "H1": 0.61,
    "H2": 0.24,
    "H3": 0.15
  },
  "available_queries": [
    "auth_events",
    "process_events",
    "dns_events"
  ],
  "scores": {
    "auth_events": 0.31,
    "process_events": 0.27,
    "dns_events": 0.05
  },
  "selected_query": "auth_events"
}
```

## 14.3 Outcome record

Save:

```text
campaign_coverage
query_count
cost
wrong_hypothesis
time_to_correct_hypothesis
order_flip
premature_stop
targeted_attack_degradation
```

---

# 15. Reproducibility Package

The final repository should contain something like:

```text
hades/
├── README.md
├── LICENSE
├── CITATION.cff
├── pyproject.toml
├── requirements-lock.txt
├── Dockerfile
├── docker-compose.yml
│
├── hades/
│   ├── policies/
│   ├── simulator/
│   ├── corruption/
│   ├── hypothesis/
│   ├── metrics/
│   ├── evaluation/
│   └── utils/
│
├── configs/
│   ├── policies/
│   ├── simulator/
│   ├── corruption/
│   ├── experiments/
│   └── publication/
│
├── scripts/
│   ├── run_smoke.py
│   ├── run_baselines.py
│   ├── run_main_experiments.py
│   ├── run_ablation.py
│   ├── run_statistics.py
│   └── make_figures.py
│
├── tests/
│
├── data_manifest/
│
├── results/
│   ├── raw/
│   ├── processed/
│   └── publication/
│
├── figures/
├── tables/
│
├── paper/
│   ├── manuscript/
│   ├── supplementary/
│   └── rebuttal/
│
└── docs/
    ├── experimental_protocol.md
    ├── threat_model.md
    ├── reproducibility.md
    └── dataset_card.md
```

---

# 16. Experiment Configuration

Never encode the main experiment only in Python.

Use versioned YAML/JSON.

Example:

```yaml
experiment_id: main_v1

dataset:
  benchmark: CDB
  version: "..."
  checksum: "..."

policies:
  - P0_random
  - P1_fixed
  - P2_relevance
  - P3_ig
  - P4_ig_cost
  - P5_hades

budgets:
  - 5
  - 10
  - 20
  - 40
  - 80

stress_regimes:
  - R0_clean
  - R1_missing
  - R2_stale
  - R3_misleading
  - R4_targeted

seeds:
  count: 30
  base: 1000

statistics:
  bootstrap_iterations: 10000
  confidence_level: 0.95
  correction: holm
```

The exact values must be frozen before the final main run.

---

# 17. Pilot Experiment

Do not immediately launch the largest sweep.

Run a pilot.

## Pilot objective

Verify:

- all policies terminate
- no leakage
- no invalid probabilities
- corruption preserves ground truth
- metrics are non-degenerate
- query counts are within budget
- results are reproducible

## Pilot size

Use a small fixed subset of campaigns and seeds.

Do not tune the final method using the test results.

---

# 18. Main Experiment Design

## 18.1 Independent dimensions

At minimum:

```text
Policy
×
Campaign
×
Budget
×
Stress regime
×
Seed
```

## 18.2 Pairing

The same campaign and seed should be evaluated across policies wherever possible.

This is essential for paired statistical comparison.

Example:

```text
campaign_01 seed_07
    P0
    P1
    P2
    P3
    P4
    P5
```

This reduces variance caused by different attack instances.

---

# 19. Minimum Research Questions

The paper should be organized around explicit RQs.

## RQ1 — Efficiency

> Does HADES achieve higher campaign coverage per unit acquisition budget than non-adaptive and simpler adaptive policies?

## RQ2 — Query-order mechanism

> Does evidence reliability/manipulability cause HADES to choose a different next query from IG or IG/cost?

## RQ3 — Adversarial robustness

> Does HADES degrade less than the comparison policies when evidence is missing, stale, misleading, or targeted?

## RQ4 — Attribution

> Which component of HADES—cost, reliability, or manipulation risk—causes observed improvements?

## RQ5 — Stopping

> Does reliability-aware acquisition reduce premature stopping or unnecessary acquisition while maintaining sufficient campaign coverage?

Do not add RQs that the experiment cannot answer.

---

# 20. Evaluation Metrics

## 20.1 Campaign coverage

\[
Coverage =
\frac{\text{ground-truth malicious events / objectives discovered}}
{\text{total ground-truth malicious events / objectives}}
\]

Use the exact CDB-compatible definition wherever possible.

## 20.2 Coverage per query

\[
CoveragePerQuery =
\frac{Coverage}{QueriesUsed}
\]

## 20.3 Cost per coverage

Report the acquisition cost necessary to achieve defined coverage levels.

Example:

```text
cost to reach 25%
cost to reach 50%
cost to reach 75%
```

Only report thresholds actually reachable.

## 20.4 Wrong-hypothesis rate

\[
WHR =
\frac{\text{episodes converging to incorrect dominant hypothesis}}
{\text{total episodes}}
\]

## 20.5 Time/steps to correct hypothesis

Measure:

- query step
- optionally wall-clock time

Keep logical query steps and real wall-clock time separate.

## 20.6 Order-flip rate

\[
OFR =
\frac{\#\text{states where HADES chooses a different next query}}
{\#\text{comparable decision states}}
\]

This is a mechanism metric, not an outcome metric.

A high order-flip rate without better outcomes means the mechanism is different but not necessarily useful.

## 20.7 Targeted-attack degradation

\[
Degradation =
Performance_{clean} - Performance_{targeted}
\]

Report absolute and relative forms.

## 20.8 Premature-stop rate

Investigations that terminate before a predefined sufficiency criterion.

---

# 21. Statistical Analysis Plan

## 21.1 Freeze the statistical plan before main analysis

Do not choose the statistical test after seeing which result looks best.

## 21.2 Repeated observations

Use paired comparisons because the same campaign/seed can be evaluated across policies.

## 21.3 Confidence intervals

Use bootstrap confidence intervals for policy differences.

Recommended outputs:

```text
mean difference
95% bootstrap CI
```

## 21.4 Significance tests

Use a paired permutation test where practical.

Use Wilcoxon signed-rank only where its assumptions and data structure are appropriate.

## 21.5 Effect sizes

Always report effect size in addition to p-values.

The reader should be able to tell whether an improvement is practically meaningful.

## 21.6 Multiple comparisons

If comparing many policy pairs:

- define a primary comparison set
- apply multiplicity correction such as Holm
- do not report a large set of uncorrected p-values and cherry-pick one

## 21.7 Hierarchical interpretation

Avoid pretending that hundreds of per-query observations are hundreds of independent experimental units.

The independent experimental unit should be carefully defined at the campaign/episode level.

---

# 22. Power / Sample-Size Thinking

Before the expensive final run:

1. estimate variance from the pilot
2. estimate the smallest meaningful effect
3. estimate required repeated episodes/seeds
4. choose a feasible number
5. freeze it

Do not justify a tiny sample merely because it is computationally convenient.

If the project cannot afford a statistically strong scale, narrow the claim instead of exaggerating the evidence.

---

# 23. Ablation Plan

The ablation is central to proving that HADES is more than “IG/cost + arbitrary penalty.”

## Required sequence

### A0
P3 — IG only

### A1
P4 — IG + cost

### A2
IG + cost + reliability

### A3
Full HADES:

```text
IG
+ cost
+ reliability
+ manipulation risk
```

Compare:

```text
A0 → A1
What does cost add?

A1 → A2
What does reliability add?

A2 → A3
What does manipulation awareness add?
```

## Required interpretation

If a component does not improve the target outcome:

> say so.

Do not preserve the term merely because it is part of the proposed method.

---

# 24. Sensitivity Analysis

HADES may depend on:

- λ
- μ
- reliability estimates
- stopping threshold τ
- prior probabilities
- corruption intensity

Run sensitivity analyses.

Example:

```text
lambda:
0.25
0.5
1.0
2.0

mu:
0.25
0.5
1.0
2.0
```

The goal is to determine whether the result is robust or exists only in a narrow hyperparameter window.

A method that “wins” only at one fragile parameter setting is a weak result.

---

# 25. Stopping Rule Evaluation

The formal plan contains:

\[
STOP \text{ when } \max_q U(q|H_t)<\tau
\]

Do not introduce this into the first HADES version until the acquisition policy is stable.

Then test:

- no stopping
- fixed budget only
- utility threshold
- evidence sufficiency threshold

Metrics:

```text
coverage at stop
unnecessary queries
premature stop
total cost
correct-hypothesis confidence
```

---

# 26. Failure Analysis

This section can make the paper much stronger.

Collect failure cases where:

### HADES loses to P0

Why?

- unlucky random sequence?
- reliability estimate wrong?
- hypotheses poorly initialized?

### HADES loses to P3

Why?

- reliability term over-penalized useful evidence?
- manipulation risk was overestimated?

### HADES loses to P4

Why?

- cost dominated too much?
- adversarial stress not severe enough?

### HADES changes query but outcome is unchanged

Important evidence against inflated claims.

### HADES makes a confidently wrong hypothesis

Especially valuable for analysis.

Build representative traces:

```text
Step 0
belief state

Step 1
query selected
observation

Step 2
belief update

Step 3
next query

...
```

Show both successful and failed examples.

---

# 27. Ground-Truth and Leakage Audit

Before any final run, perform a dedicated leakage inspection.

Check:

- query templates
- SQL clauses
- EventID filters
- corruption generator
- hypothesis labels
- scorer
- candidate extraction
- timestamps
- seed handling
- filenames
- hidden metadata

Ensure the policy cannot access:

```text
actual campaign label
actual corruption type
actual reliability_true
actual target hypothesis
```

unless that information is explicitly part of the policy observation model.

This should be documented in the paper.

---

# 28. Corruption Realism Audit

Every corruption mechanism needs a written justification.

For each:

```text
what attacker capability is assumed?
what telemetry can be modified?
what telemetry cannot be modified?
why is this plausible?
what does the benchmark abstract away?
```

Do not claim:

> “This perfectly models real attackers.”

Use:

> “This controlled experiment models X under assumptions Y and Z.”

---

# 29. Benchmark Validity Audit

CDB is a substrate, not the novelty.

Document:

- CDB version/commit
- dataset version
- dataset checksum
- number of events actually used
- number of campaigns
- attack procedures used
- query budget semantics
- scorer version
- known CDB limitations

If CDB is not fully representative of enterprise telemetry:

> say so.

---

# 30. External Validation

Phase 7 is optional but valuable.

Port the policy to a second environment only after the CDB experiment is stable.

Possible second environments may include another reproducible threat-hunting benchmark or a controlled local telemetry simulator.

The purpose is not to create a huge second system.

The purpose is:

> **Does the phenomenon survive outside CDB?**

If the second environment produces different results, investigate why.

Do not hide negative external-validation results.

---

# 31. Reproducibility Engineering

Before paper submission, anyone should be able to:

```bash
git clone ...
docker compose up
python scripts/run_smoke.py
python scripts/run_main_experiments.py --config configs/experiments/main_v1.yaml
python scripts/run_statistics.py
python scripts/make_figures.py
```

The repository should reproduce:

- raw run logs
- processed results
- final tables
- final figures

within documented tolerance.

## Record environment

At minimum:

```text
Python version
OS/container base
package lock
CDB commit
dataset identifier/checksum
CPU/GPU if relevant
random seeds
configuration version
git commit
```

---

# 32. Result Integrity

Maintain three layers:

```text
results/raw/
results/processed/
results/publication/
```

Never manually edit final numbers in a Word/LaTeX table.

Instead:

```text
raw experiment
    ↓
analysis script
    ↓
publication CSV
    ↓
figure/table generator
    ↓
paper
```

This creates a trace from every paper number back to raw evidence.

---

# 33. Figure Plan

The paper should not be filled with dashboards.

Recommended core figures:

## Figure 1 — HADES architecture

```text
hypothesis state
   ↓
candidate queries
   ↓
utility calculation
   ↓
query
   ↓
observation
   ↓
belief update
   ↓
repeat
```

## Figure 2 — Policy pipeline

P0 → P1 → P2 → P3 → P4 → P5.

## Figure 3 — Coverage vs budget

X:

```text
budget
```

Y:

```text
coverage
```

One curve per policy.

## Figure 4 — Clean vs adversarial degradation

Compare:

```text
R0
R1
R2
R3
R4
```

## Figure 5 — Order flips

Heatmap / matrix showing when HADES changes the preferred query relative to P3/P4.

## Figure 6 — Ablation

Incremental addition:

```text
IG
IG+cost
IG+cost+reliability
full HADES
```

## Figure 7 — Failure case trace

One successful HADES trace and one failure trace.

Do not create unnecessary figures.

---

# 34. Table Plan

## Table 1 — Dataset / benchmark characteristics

## Table 2 — Policy definitions

## Table 3 — Query-source characteristics

## Table 4 — Main performance results

Columns should include:

```text
policy
mean coverage
95% CI
coverage/query
cost-to-target
wrong-hypothesis rate
```

## Table 5 — Stress-regime results

## Table 6 — Ablation results

## Table 7 — Statistical comparison

## Table 8 — Failure-analysis summary

Every table number must be generated from scripts where possible.

---

# 35. Research Paper Writing Plan

Do not write the final manuscript now.

You can build the skeleton while implementation proceeds, but leave all result claims as placeholders.

---

# 36. Section I — Introduction

Must contain:

1. threat-hunting investigation as a sequential evidence-allocation problem
2. finite query/evidence budgets
3. differing evidence reliability and manipulation risk
4. why querying the most informative source is not always rational
5. why cybersecurity provides a specific experimental setting
6. the gap
7. research question(s)
8. contributions

End with precise contributions.

Example contribution style:

> We formulate cyber threat hunting as budgeted sequential evidence acquisition over competing attack hypotheses.

> We introduce HADES, a transparent policy combining hypothesis discrimination, acquisition cost, evidence reliability, and manipulation risk.

> We evaluate HADES under controlled clean, missing, stale, misleading, and targeted telemetry conditions.

> We release reproducible policy implementations, experiment configurations, seeds, corruption generators, and analysis artifacts.

Only include contributions actually demonstrated.

---

# 37. Section II — Related Work

Organize by **problem dimension**, not just by paper chronology.

## 37.1 Cyber threat-hunting benchmarks

CDB and related evaluation environments.

## 37.2 Sequential evidence acquisition

Information gain, active evidence retrieval, stopping.

## 37.3 Cost-aware evidence selection

Why acquisition budget changes the decision problem.

## 37.4 Adversarial / insufficient evidence

OpenSec, SIR-Bench, SecRespond, DiagChain, ExCyTIn-Bench and relevant cyber-investigation work.

## 37.5 Agent authorization / information flow

Only to distinguish decision point.

## 37.6 Gap statement

End with a table:

| Dimension | Prior work | HADES |
|---|---|---|
| Cyber investigation | yes | yes |
| Sequential evidence | yes | yes |
| Cost | yes | yes |
| Reliability/manipulation | partially / adjacent | joint decision focus |
| Query-order analysis | yes | yes |
| Adversarial cyber telemetry | emerging | central evaluation axis |

Do not claim “first” without an exhaustive, final pre-submission audit.

---

# 38. Section III — Problem Formulation

Define:

```text
H_t
Q_t
Cost(q)
Latency(q)
Reliability(q)
ManipulationRisk(q)
Observation e_t
Budget B
```

Then define:

\[
q_t^*=\arg\max_q U(q|H_t)
\]

and:

\[
H_{t+1}=Update(H_t,e_t)
\]

Define stopping.

Explain which quantities are:

```text
known by evaluator
estimated by policy
observed by investigator
```

This separation is crucial.

---

# 39. Section IV — HADES Policy

Include:

- algorithm
- pseudocode
- decision trace example
- complexity discussion
- parameter definitions
- deterministic tie-breaking
- implementation assumptions

Pseudocode should be simple.

Example:

```text
Algorithm HADES

Input:
    current hypothesis beliefs H
    candidate queries Q
    remaining budget B

For each q in Q:
    estimate hypothesis-discrimination value
    adjust for reliability
    penalize acquisition cost
    penalize manipulation risk

Select q maximizing utility

Execute q
Observe evidence
Update H
Repeat until budget exhausted or stopping condition met
```

Then provide the exact mathematical version used in experiments.

---

# 40. Section V — Experimental Methodology

Specify:

- benchmark
- campaigns
- policies
- query menu
- budgets
- seeds
- stress regimes
- corruption model
- reliability model
- metrics
- statistical tests
- implementation details

A reviewer should be able to reconstruct the entire experiment from this section.

---

# 41. Section VI — Results

Organize strictly by RQ.

## RQ1
Efficiency.

## RQ2
Order-flip mechanism.

## RQ3
Adversarial robustness.

## RQ4
Ablation/component value.

## RQ5
Stopping/generalization.

Never bury negative results.

---

# 42. Section VII — Ablation and Failure Analysis

Explain:

- which component mattered
- where HADES failed
- when HADES over-trusted reliability estimates
- whether targeted manipulation defeated the method
- whether query-order changes translated into better outcomes

Use concrete traces.

---

# 43. Section VIII — Threats to Validity

Minimum categories:

## Internal validity

- implementation bugs
- random seed dependence
- scorer behavior
- leakage

## Construct validity

- reliability model is an abstraction
- manipulation risk is an abstraction
- “hypothesis correctness” definition

## External validity

- CDB is not the full security ecosystem
- Windows-event-centric benchmark
- source menu limitations

## Statistical validity

- sample size
- campaign dependence
- repeated-measures assumptions
- multiple comparisons

## Benchmark validity

- attack procedures may not represent all attacks
- corruption may not perfectly model production compromise

---

# 44. Section IX — Reproducibility

Document:

- code
- configs
- environment
- dataset
- checksums
- seeds
- exact commands
- expected outputs
- limitations

Provide a minimal reproduction path that runs quickly.

Also provide a full reproduction path.

---

# 45. Section X — Conclusion

Only conclude what the experiments establish.

Possible outcomes:

### Strong positive

HADES wins clean and adversarial.

### Qualified positive

HADES only adds value under targeted corruption.

### Mechanism-only result

HADES changes query order but not final outcomes.

### Negative

IG/cost wins everywhere.

A negative result is scientifically acceptable if the experiment is rigorous.

The conclusion must never convert:

```text
“we expected”
```

into:

```text
“we demonstrated”
```

without evidence.

---

# 46. Publication Readiness Checklist

Before submission, confirm:

## Scientific

- [ ] Research question frozen
- [ ] Hypotheses frozen
- [ ] Threat model frozen
- [ ] Main metrics frozen
- [ ] Main comparison policies frozen
- [ ] Main experimental matrix completed
- [ ] Ablation completed
- [ ] Sensitivity analysis completed
- [ ] External validation attempted or explicitly ruled out
- [ ] Statistical analysis completed
- [ ] Effect sizes reported
- [ ] Confidence intervals reported
- [ ] Multiple comparison correction applied where needed
- [ ] Negative results included

## Reproducibility

- [ ] Dataset version recorded
- [ ] Dataset checksum recorded
- [ ] CDB commit/version recorded
- [ ] Environment pinned
- [ ] Dependencies locked
- [ ] Random seeds stored
- [ ] Configuration files stored
- [ ] Raw results archived
- [ ] Processing scripts archived
- [ ] Figure-generation scripts archived
- [ ] Table-generation scripts archived
- [ ] Smoke-test reproduction path works

## Security / ethics

- [ ] No third-party infrastructure attacked
- [ ] Corruption experiments are local/controlled
- [ ] No real credentials embedded
- [ ] No secrets in repository
- [ ] No benchmark evaluator leakage
- [ ] Threat-model assumptions documented

## Manuscript integrity

- [ ] Every number traces to generated output
- [ ] Every figure traces to a script
- [ ] Every table traces to generated output
- [ ] Every citation checked
- [ ] Every “first” claim independently verified
- [ ] Every current-paper claim re-checked immediately before submission
- [ ] Terminology consistent throughout
- [ ] Abstract matches actual findings
- [ ] Conclusion matches actual findings

---

# 47. Citation and Literature Audit

Because this field is moving quickly:

## At project start

Maintain:

```text
docs/literature_matrix.csv
```

Fields:

```text
citation
year
venue
problem
decision_point
dataset
benchmark
cost
reliability
adversarial evidence
query allocation
stopping
overlap
difference
verified date
```

## Before submission

Run a final search specifically for:

```text
cyber evidence acquisition
active threat hunting query selection
cost-aware cyber investigation
adversarial telemetry investigation
reliability-aware evidence acquisition
adaptive threat-hunting query ordering
security investigation under evidence corruption
```

Then inspect:

- papers
- benchmarks
- open-source systems
- technical reports
- current product capabilities

The final novelty statement should be:

> “Based on the literature and system review completed on [date], we found no directly overlapping method that evaluates X under Y…”

rather than an absolute “first” unless genuinely justified.

---

# 48. Development Timeline

The existing proposal suggests a roughly 24-week research-first plan. The execution version should be:

## Phase 0 — Lock environment and protocol

**Target:** Week 1–2

Deliver:

- benchmark version lock
- dataset manifest
- baseline reproduction
- threat model
- initial literature matrix
- leakage checklist
- experiment config schema

**Exit gate:** G0.

---

## Phase 1 — Minimal simulator

**Target:** Week 2–4

Build:

- hypothesis state
- synthetic evidence sources
- observation model
- relevance scoring
- IG
- cost model
- reliability model
- manipulation model

Deliver:

- simulator
- unit tests
- order-flip demonstration

**Exit gate:** G1.

---

## Phase 2 — Policy ladder

**Target:** Week 4–6

Implement:

```text
P0
P1
P2
P3
P4
P5
```

All under one interface.

Deliver:

- decision logging
- deterministic seeds
- trace files
- unit tests

---

## Phase 3 — CDB integration

**Target:** Week 6–8

Connect the same policies to CDB.

Deliver:

- benchmark adapter
- compatible scoring
- comparable seeds
- dataset manifest
- run schema

---

## Phase 4 — Stress generator

**Target:** Week 8–11

Implement:

```text
R0 clean
R1 missing
R2 stale
R3 misleading
R4 targeted
```

Validate:

```text
ground truth unchanged
observations changed
```

This validation should itself have tests.

---

## Phase 5 — Main experiments

**Target:** Week 11–15

Run:

```text
policy × campaign × budget × stress × seed
```

Store raw results immutably.

---

## Phase 6 — Statistics and ablation

**Target:** Week 15–17

Produce:

- CIs
- paired tests
- effect sizes
- multiplicity corrections
- ablations
- sensitivity curves
- failure cases

**Exit gates:** G2, G3, G4.

---

## Phase 7 — External validation

**Target:** Week 17–20

Use a second environment only if:

- licensing permits
- benchmark can be reproduced
- implementation effort is justified

**Exit gate:** G5.

---

## Phase 8 — Paper and artifact freeze

**Target:** Week 20–24

Freeze:

- figures
- tables
- statistical outputs
- manuscript
- appendix
- artifact
- README
- environment

Run final literature audit.

**Exit gate:** G6.

---

# 49. Research Paper + Artifact Release Structure

Release two synchronized products.

## Paper

```text
paper/
  manuscript/
  supplementary/
```

## Artifact

```text
artifact/
  source
  configs
  scripts
  results
  README
  environment
```

The paper should point to the artifact.

The artifact should point to the paper.

---

# 50. Preprint / Submission Sequence

Use a controlled sequence:

```text
internal manuscript freeze
        ↓
internal technical review
        ↓
literature/novelty re-audit
        ↓
reproducibility test on clean machine/container
        ↓
paper formatting
        ↓
preprint if appropriate
        ↓
conference/journal submission
        ↓
review-response preparation
        ↓
camera-ready revision
        ↓
artifact publication
```

Do not publish the final preprint before the experimental protocol is genuinely frozen if doing so would expose a moving target.

---

# 51. Reviewer Simulation Before Submission

Perform a mock review with the following questions.

## Reviewer 1 — Novelty

> What exactly is new?

Answer in one paragraph.

## Reviewer 2 — Methodology

> Why is HADES not simply IG/cost plus a penalty?

This question must be answered by the ablation.

## Reviewer 3 — Threat model

> Why should attackers be able to manipulate these telemetry sources?

Answer source-by-source.

## Reviewer 4 — Benchmark validity

> Why should CDB results generalize?

Answer honestly.

## Reviewer 5 — Statistics

> Are the reported differences statistically and practically meaningful?

Provide paired analysis, CIs, effect sizes, correction.

## Reviewer 6 — Reproducibility

> Can another researcher reproduce the result?

Run the artifact from scratch.

## Reviewer 7 — Negative cases

> When does HADES fail?

Have a real answer.

---

# 52. Common Failure Modes to Avoid

## Do not

- add complexity before evidence
- tune the method on the test set
- inspect final results and then rewrite the hypothesis
- change corruption severity after seeing outcomes
- use evaluator-only information
- cherry-pick campaigns
- hide negative results
- report only p-values
- use one seed
- compare policies on different attack instances
- claim a benchmark result from one baseline run
- fabricate literature novelty
- overfit to CDB terminology
- turn the LLM baseline into the main contribution
- create a huge UI before the policy works

---

# 53. Definition of “Done” for HADES

HADES is **not done** when:

- the code runs
- the simulator works
- P5 produces a higher score once
- a graph looks good
- an LLM can explain the method

HADES is done when:

1. the research question is explicitly operationalized;
2. P0–P5 are reproducible under the same environment;
3. the corruption regimes are validated;
4. the main experimental matrix is complete;
5. the results survive statistical analysis;
6. ablations demonstrate what actually matters;
7. failure cases are documented;
8. the novelty claim survives a final literature audit;
9. the artifact reproduces the reported tables/figures;
10. the manuscript makes no claims stronger than the evidence.

---

# 54. Final Execution Order

The agent should execute work in exactly this order unless a go/no-go gate forces a change:

```text
[CURRENT]
CDB plumbing + P0/P1 baseline
        |
        v
1. Freeze baseline + provenance metadata
        |
        v
2. Fix performance bottleneck without changing semantics
        |
        v
3. Implement hypothesis representation
        |
        v
4. Implement belief update + evidence/hypothesis mapping
        |
        v
5. Build simulator
        |
        v
6. Implement P2 Relevance
        |
        v
7. Implement P3 Information Gain
        |
        v
8. Validate P2/P3 with unit tests + synthetic cases
        |
        v
9. G1 order-flip test
        |
   FAIL ───────────────> reformulate / stop
        |
       PASS
        |
        v
10. Implement P4 IG/Cost
        |
        v
11. Implement reliability estimate vs true reliability
        |
        v
12. Implement P5 HADES
        |
        v
13. Run simulator ablations
        |
        v
14. Integrate P2–P5 with CDB
        |
        v
15. Implement R1 Missing
        |
        v
16. Implement R2 Stale
        |
        v
17. Implement R3 Misleading
        |
        v
18. Implement R4 Targeted
        |
        v
19. Validate corruption preserves ground truth
        |
        v
20. Pilot experiment
        |
        v
21. Freeze main experiment configuration
        |
        v
22. Full policy × campaign × budget × stress × seed sweep
        |
        v
23. Statistical analysis
        |
        v
24. Ablations
        |
        v
25. Sensitivity analysis
        |
        v
26. Failure analysis
        |
        v
27. G2/G3/G4 decisions
        |
        v
28. External validation, if justified
        |
        v
29. G5 decision
        |
        v
30. Final literature / novelty audit
        |
        v
31. Freeze manuscript data
        |
        v
32. Generate publication figures/tables from scripts
        |
        v
33. Write final IEEE-style manuscript
        |
        v
34. Reproducibility audit
        |
        v
35. Mock peer review
        |
        v
36. Final corrections
        |
        v
37. Submission / preprint / artifact release
        |
        v
38. Review response / camera-ready
```

---

# 55. Immediate TODO List — Start Here

## Priority 0 — Freeze what already works

- [ ] Save the current P0/P1 baseline as immutable raw output
- [ ] Store all run metadata
- [ ] Record exact benchmark/code/version information
- [ ] Record dataset identifier/checksum if available
- [ ] Record wall-clock timing separately from logical query cost
- [ ] Add `n_submitted` and other currently missing metadata to result files

## Priority 1 — Hypothesis engine

- [ ] Design `Hypothesis`
- [ ] Extend `InvestigationState`
- [ ] Implement probability validation
- [ ] Implement evidence → hypothesis mapping
- [ ] Implement belief update
- [ ] Write unit tests
- [ ] Verify evaluator truth is inaccessible to policy

## Priority 2 — P2

- [ ] Implement relevance policy
- [ ] Deterministic ties
- [ ] Decision logging
- [ ] Simulator tests
- [ ] CDB adapter tests

## Priority 3 — P3

- [ ] Implement entropy
- [ ] Implement expected information gain
- [ ] Validate with analytical toy cases
- [ ] Add trace logging

## Priority 4 — G1

- [ ] Construct explicit order-flip examples
- [ ] Run repeated simulator checks
- [ ] Confirm reliability can change query ordering
- [ ] Freeze the G1 artifact

Only after this point should substantial work on corruption and the full P5 experiment proceed.

---

# 56. Expected Outcomes — Do Not Presuppose Success

The project is designed to distinguish these possibilities:

| Result | Interpretation |
|---|---|
| HADES wins clean + adversarial | strong evidence for useful acquisition policy |
| HADES matches IG/cost clean but wins targeted attacks | reliability/manipulation awareness is specifically useful under adversarial evidence |
| HADES changes query order but outcomes do not improve | mechanism differs but is not useful |
| IG/cost wins everywhere | reliability/adversarial term is unnecessary; HADES should be rejected |
| performance varies strongly by campaign | attack structure determines when reliability-aware acquisition matters |
| HADES fails badly | identify failure mode; do not force publication as a successful method |

---

# 57. Final Research Standard

The standard for this project is:

> **A smaller, rigorously falsifiable paper is better than a larger paper supported by weak evidence.**

The strongest possible outcome is not necessarily:

> “HADES wins everything.”

A strong paper can instead establish:

> “Reliability/manipulability materially changes evidence-acquisition decisions under specific adversarial conditions, but the advantage disappears under others.”

That is a useful empirical finding.

The final paper should make the **boundary of the method's usefulness** as clear as its successes.

---

# 58. Final Project Decision Rule

At the end of experimentation:

```text
IF G1 fails:
    abandon/reformulate HADES

ELIF G2 fails:
    convert project into benchmark/measurement paper

ELIF G3 fails:
    tune or simplify policy

ELIF G4 fails:
    remove manipulation-risk term

ELIF G5 fails:
    narrow external claims

ELIF G6 fails:
    do not claim novelty;
    reposition as empirical benchmark/methodology

ELSE:
    submit HADES as a reproducible empirical research contribution
```

---

# 59. One-Sentence Definition for the Agent

> **Implement and evaluate HADES as a transparent, budgeted cyber-investigation policy that chooses the next evidence source by balancing expected hypothesis discrimination, acquisition cost, evidence reliability, and manipulation risk; prove or falsify its value against P0–P4 under controlled clean and adversarial CDB conditions, then publish only what the resulting evidence supports.**

---

# 60. Canonical Deliverables

At project completion, the following must exist:

```text
1. Working HADES implementation
2. Deterministic simulator
3. CDB adapter
4. P0–P5 policy implementations
5. Corruption engine
6. Hypothesis/belief engine
7. Statistical analysis module
8. Reproducibility scripts
9. Experiment configuration set
10. Raw results
11. Processed results
12. Publication-ready figures
13. Publication-ready tables
14. Research paper
15. Supplementary material
16. Threat-model documentation
17. Dataset / benchmark manifest
18. Environment lock
19. README with one-command smoke test
20. Final novelty / literature matrix
21. Citation file
22. Artifact release package
23. Final submission package
24. Review-response / camera-ready materials
```

---

# 61. Status Ledger

Maintain this section as the project progresses.

```text
G0 Baseline reproducible:          [PASS / FAIL / PENDING]
G1 Order-flip exists:              [PASS / FAIL / PENDING]
G2 HADES improves outcomes:        [PASS / FAIL / PENDING]
G3 No major clean penalty:         [PASS / FAIL / PENDING]
G4 Robustness advantage:           [PASS / FAIL / PENDING]
G5 Generalizes:                    [PASS / FAIL / PENDING]
G6 Literature gap survives:        [PASS / FAIL / PENDING]

P0 Random:                         [IMPLEMENTED]
P1 Fixed:                          [IMPLEMENTED]
P2 Relevance:                      [PENDING]
P3 Information Gain:               [PENDING]
P4 IG/Cost:                        [PENDING]
P5 HADES:                          [PENDING]
P6 LLM baseline:                   [OPTIONAL / PENDING]

R0 Clean:                          [AVAILABLE]
R1 Missing:                        [PENDING]
R2 Stale:                          [PENDING]
R3 Misleading:                     [PENDING]
R4 Targeted:                       [PENDING]

Hypothesis tracking:               [PENDING]
Corruption engine:                 [PENDING]
Statistics:                        [PENDING]
Ablation:                          [PENDING]
External validation:               [PENDING]
Paper:                             [NOT READY]
Artifact release:                 [NOT READY]
```

---

# 62. Final Instruction to Any Implementing Agent

**Do not skip ahead.**

The current correct next action is:

```text
FREEZE BASELINE
    ↓
HYPOTHESIS TRACKING
    ↓
P2
    ↓
P3
    ↓
G1
```

Do not build:

- a web UI
- an autonomous LLM investigator
- multi-environment infrastructure
- a complex optimizer
- a polished agent framework

before the small simulator demonstrates that the underlying decision problem is real and measurable.

**The experiment is the product. The reproducible artifact is part of the paper. The paper must remain subordinate to the evidence.**
