# CDB Public-Sample Transfer — KILLED

**Status:** KILLED
**Date:** 2026-09-30
**Kill commit:** `896d2f4`
**Implementation freeze:** `95a91c6`

---

## Reason

The publicly available CDB sample does not expose sufficient observable
telemetry semantics to construct the HADES five-class observation model
without leakage or artificial assumptions. The transfer experiment is
terminated rather than forcing an artificial encoding.

---

## Mapper History

Three distinct mapper architectures were attempted. Each one collapsed
to a single observation class across all episodes.

### v1 — Row-Count Mapping (`9c702e3`)

| Signal | Threshold | Result |
|--------|-----------|--------|
| `n_rows` returned by SQL query | `≥ 8 → strong_support` | **647/647 = strong_support** |

**Root cause:** CDB `sample.json` contains 155,350 rows. With `LIMIT 10`,
every source returns exactly 10 rows. The threshold is trivially saturated.
Row count cannot discriminate when the LIMIT is always the binding constraint.

### v2 — Content Features: null_rate + EventID Variety (`9c702e3`)

| Signal | Threshold | Result |
|--------|-----------|--------|
| `null_rate = null_fields / total_fields` | `≤ 0.15 AND variety ≥ 3 → strong_support` | **654/654 = neutral** |
| `event_variety = len(distinct EventIDs)` | `OR variety ≥ 2 → neutral` | |

**Root cause:** EventID sets are **query-fixed** — determined by the SQL
`WHERE EventID IN (...)` clause, not by forensic context. DNS always
returns EventID 22 (variety=1), auth always returns 4624/4634/4648/4672
(variety=4), etc. Null rates are structurally fixed at 50–60% per source
by the column schema. Neither feature has episodic variation.

### v3 — Computer Spread (`896d2f4`)

| Signal | Threshold | Result |
|--------|-----------|--------|
| `spread = distinct_computers / n_rows` | `≥ 0.40 → strong_support` | **654/654 = neutral** |

**Root cause:** The `Computer` field in `sample.json` contains the literal
string `"Computer"` — a schema/column-name placeholder, not a hostname.
`AccountName` and `IpAddress` are universally `null`. There is **no genuine
episodic content signal** in `sample.json`.

Raw evidence (`scripts/cdb_raw_obs_result.txt`):

```json
{
  "TimeCreated": "2026-01-14T00:22:31Z",
  "EventID": "4624",
  "\"Computer\"": "Computer",
  "AccountName": null,
  "IpAddress": null
}
```

---

## Scientific Consequence

The accessible sample cannot support a semantically defensible five-class
observation representation (`strong_support / weak_support / neutral /
weak_contra / strong_contra`). Forcing class diversity through arbitrary
thresholds or binary collapsing would invalidate the observation semantics
that HADES's Bayesian update depends on.

**The transfer experiment is terminated because the sample was insufficient,
not because HADES's architecture or policies are flawed.**

---

## What Is KILLED

- The current public-CDB sample transfer experiment
- All scientific claims that would depend on CDB-transferred results
- The specific mapper calibrations developed against `sample.json`

## What Is NOT KILLED

- The HADES research program and core architecture
- The HADES five-class observation representation
- The CDB adapter and integration infrastructure (`hades/benchmark/`)
- The transfer gate machinery (`scripts/run_transfer_gate.py`)
- The possibility of a future evaluation against the full CDB benchmark

---

## Preserved Artifacts

These files are the exact historical record of the failed transfer and
**must not** be deleted, rewritten, or overwritten:

| Artifact | Commit | Content |
|----------|--------|---------|
| `results/raw/5a_transfer_gate_v1.json` | `c386dda` | Standard (MITRE) transfer, mapper v1 |
| `results/raw/5a_transfer_gate_uniform_v1.json` | `c386dda` | Uniform-affinity ablation, mapper v1 |
| `results/raw/5a1_regression_v2.json` | `896d2f4` | Regression with mapper v2 |
| `results/raw/5a1_regression_v3.json` | `896d2f4` | Regression with mapper v3 |
| `scripts/cdb_raw_obs_result.txt` | `896d2f4` | Raw CDB observation proof |
| `scripts/cdb_content_audit_result.txt` | `896d2f4` | Content-feature audit |

---

## Future CDB Evaluation

A future evaluation against the full CDB benchmark/environment is an
**independent experiment** that must not reuse the current sample-based
calibration or results. See `docs/future/cdb_full_access_plan.md`.

---

## Status Summary

```
CDB SAMPLE TRANSFER:   KILLED
FULL CDB TRANSFER:     DEFERRED / FUTURE WORK
HADES CORE:            ACTIVE (Phases 0–4 complete, F1/F5 passed)
```
