# Future CDB Full-Access Evaluation Plan

**Status:** DEFERRED / FUTURE WORK
**Prerequisite:** Authorized access to full CDB benchmark dataset/environment
**Relationship to current work:** This is a NEW experiment, independent of the
killed public-sample transfer (`STATUS_CDB_SAMPLE_KILLED.md`).

---

## Why a Fresh Experiment

The public CDB sample (`sample.json`) was found to contain placeholder
values (Computer = literal `"Computer"`, AccountName/IpAddress = null),
making it structurally impossible to construct a semantically meaningful
five-class observation model. The current public-sample results must NOT
be presented as a full-CDB result, and the full-CDB experiment must NOT
be treated as a "continuation" of the killed sample experiment.

---

## Required Steps

### 1. Data Access

Obtain authorized access to the full CDB dataset or a live evaluation
environment. Document the access method, license, and any restrictions.

### 2. Dataset Freeze

Freeze the exact CDB snapshot before any mapper development:
- Record CDB version / git commit / release tag
- Compute and record `sha256` hash of the primary data files
- Pin the version in `data_manifest/benchmark_lock.json`
- No dataset changes after freeze

### 3. Telemetry Schema Audit

**Before designing a mapper**, audit the available telemetry:
- What fields are populated (not placeholder)?
- What is the Computer / hostname variety across episodes?
- What is the AccountName / IpAddress population rate?
- What EventID sets appear per source and do they vary by episode?
- Are there any fields that provide genuine episodic content signal?

Document the audit results to justify the mapper design.

### 4. Ground-Truth Isolation

Verify that the mapper does not use any information that constitutes
ground-truth leakage:
- No attack labels
- No hidden hypothesis information
- No knowledge of which events are malicious
- No flag timestamps or scoring information

The mapper must use only observable structural properties of the SQL
query results.

### 5. Mapper Development

Develop a non-leaky observation mapper that maps CDB query results into
the HADES five-class representation:

```
strong_support / weak_support / neutral / weak_contra / strong_contra
```

The mapping signal must be justified by the schema audit (step 3) and
must produce episodic variation — i.e., different episodes should
produce different obs_class distributions.

### 6. Development-Set Validation

Validate the mapper on a designated development set:
- Confirm obs_class variety (T2 gate: ≥ 3 distinct classes per policy)
- Confirm no ground-truth leakage (T5 gate)
- Confirm budget conservation (T3)
- Confirm belief normalization (T4)

### 7. Mapper Freeze

Freeze the mapper implementation before held-out evaluation:
- Record the commit hash
- Do NOT adjust thresholds after seeing held-out results

### 8. Held-Out Evaluation

Run the full T1–T8 transfer gate on a fresh held-out episode set:
- Use `scripts/run_transfer_gate.py` with the frozen mapper
- All 8 gates must pass for Phase 5B authorization
- Record exact command, configuration, and seed

### 9. Independent Gate Evaluation

Re-run the transfer gates without modifying any gate thresholds or
rules from the killed sample experiment. The gates themselves
(T1–T8) are the same; only the data and mapper change.

### 10. Provenance

Record full provenance in the output JSON:
- `hades_commit` (HADES repo HEAD)
- `cdb_commit` (CDB repo/snapshot identity)
- `data_hash` (sha256 of primary data file)
- `mapper_version`
- `experiment_id` (new, distinct from the killed sample experiment)

---

## Preserved Infrastructure

The following CDB integration code is retained and ready for the future
experiment:

| File | Purpose |
|------|---------|
| `hades/benchmark/__init__.py` | Package marker |
| `hades/benchmark/obs_mapper.py` | Observation mapper (will need new calibration) |
| `hades/benchmark/candidate_extractor.py` | Timestamp extraction + per-source stats |
| `hades/benchmark/fast_db.py` | `executemany` patch for CDB's bulk insert |
| `hades/harness.py` | CDB `run(env, model)` contract, policy registry |
| `scripts/run_transfer_gate.py` | T1–T8 gate runner with provenance |
| `tests/test_benchmark.py` | 25 unit tests for benchmark bridge |

---

## Anti-Contamination Rule

The public-sample results (`5a_transfer_gate_v1.json`, etc.) are the
record of a **killed** experiment. They must not be:
- Cited as evidence of CDB validation
- Used to calibrate the future mapper
- Included in any comparative analysis against future full-CDB results
- Presented as "preliminary CDB results" in a publication

The future full-CDB experiment should cite the kill finding as
motivation for the fresh evaluation, not as a baseline.
