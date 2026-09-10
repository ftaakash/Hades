# AGENTS.md — hades-bench-v1

Budgeted evidence acquisition for cyber threat hunting (CDB benchmark).
Researcher: Aakash G.S. Target: IEEE empirical paper. See `README.md`.

## Commands (Windows PowerShell 5.1, Python 3.14.3)

- `py` is the interpreter (`python` resolves to the Store stub — do not use).
- Tests: `py -m pytest tests/ -q`
- Single file: `py -m pytest tests/test_simulator.py -q`
- Order-flip gate: `py scripts/run_orderflip_test.py --seeds 5` (note: `--seeds 20` is default)
- Baseline vs real CDB: `py scripts/run_baseline_comparison.py` (needs `../cdb` + unpacked dataset, ~28s/reset)
- Dataset hash: `py scripts/hash_dataset.py`

Do not use `tail`/`head` (not on Windows) — use `| Select-Object -First/Last N`.
Do not pipe agent long-runs through `Select-Object -First N` — it kills the pipe early. Redirect to file instead.

## Layout

- `hades/query_menu.py` — 7-source fixed SQL menu (isolates acquisition policy from SQL skill)
- `hades/harness.py` — CDB `run(env, model)` contract, P0/P1 only
- `hades/policies/` — `base.py` (interface), `random_policy.py` (P0), `fixed_heuristic.py` (P1). P2–P5 not built yet
- `hades/simulator/` — `environment.py` (SimEnv), `observations.py`, `scenarios.py` (A–E for G1 gate)
- `scripts/run_orderflip_test.py` — G1 order-flip measurement
- `configs/experiments/{pilot_v1,main_v1}.yaml` — frozen experiment configs
- `data_manifest/benchmark_lock.json` — CDB version/checksum provenance (pinned)
- `../cdb` (sibling) — Cyber Defense Benchmark dependency, not part of this repo

## Conventions

- Reliability vs manipulation risk are INDEPENDENT fields (`reliability_true/estimated`, `manipulation_risk_true/estimated`). Never derive one from the other.
- Policies read ONLY `*_estimated` fields. `*_true` is evaluator-only. `tests/test_simulator.py::TestLeakage` enforces this.
- Probability invariant: beliefs sum to 1.0, validated loudly every step (`SimEnv._validate_beliefs`).
- Deterministic tie-break: alphabetical max `(score, name)`.
- Utility: `U(q) = ERHG(q) - λ·Cost(q) - μ·ManipRisk_est(q)`, STOP when `max U < τ` (λ=μ=1.0, τ=0.05 defaults).
- Never fabricate results, never change scorer semantics (`benchmark.scorer.score_hunt`), never rewrite a failed gate as pass.

## Gates

G0 baseline reproducible: PASS. G1 order-flip exists: OPEN (see below). G2–G6 pending.

## Known failures (do not paper over)

- `tests/test_simulator.py`: 5 failures — Scenario B IG ordering, Scenario C IG/cost ordering, Scenario D tie-break, targeted-override leak (`observations.py:99`). Fix the `expected_ig` heuristic + observation model, not the assertions.
- `scripts/run_orderflip_test.py:141` — `UnicodeEncodeError` on `λ/μ` under Windows cp1252. Use ASCII in prints.
- `pyproject.toml` uses `setuptools.backends.legacy:build` — `pip install -e .` fails on modern setuptools. Prefer plain `py -m pytest` / `PYTHONPATH=.`.
- `ThreatHuntEnv.reset()` inserts 155K rows one-at-a-time (~28s). Batching (`fast_db.py`) is planned, not built.

## Provenance

Every paper claim must trace: claim → figure/table → analysis script → processed data → raw run → config → seed → git commit → benchmark version. `main_v1.yaml` is frozen before sweeps; post-run changes need a new experiment ID.
