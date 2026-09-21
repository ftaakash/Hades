# HADES

## Reliability-Aware Evidence Acquisition under Contaminated Security Telemetry

HADES is an experimental research framework for studying **evidence acquisition when security telemetry may be noisy, unreliable, or adversarially manipulated**.

The project models telemetry reliability inside the Bayesian observation model and studies how that reliability should influence which evidence is acquired next, how beliefs are updated, and when a telemetry source should be trusted or discounted.

HADES is currently a **research prototype and experimental framework**. It does not claim to be a production threat-hunting system, a universal attack detector, or a proof that one acquisition policy is always superior.

---

## 1. Research Motivation

Security investigation systems rarely receive perfectly trustworthy evidence.

A telemetry source may be:

- incomplete,
- noisy,
- stale,
- operationally unreliable, or
- deliberately manipulated by an attacker.

A conventional information-gain policy can treat a highly informative observation as valuable without adequately accounting for the possibility that the observation itself has been corrupted.

This creates a research question:

> **When security evidence can be manipulated, how should uncertainty about telemetry reliability change the value of acquiring that evidence?**

HADES studies this problem as a Bayesian evidence-acquisition problem.

The central design principle is:

```text
security hypotheses
        ↓
candidate evidence sources
        ↓
reliability-aware observation model
        ↓
belief update
        ↓
value of information
        ↓
acquisition decision
        ↓
updated investigation state
```

---

## 2. Evidence Acquisition as Value of Information

HADES evaluates the **Value of Information (VoI)** under contaminated likelihood models.

Instead of a fixed heuristic score, HADES computes:

`V(q) = EIG(q | r_hat, phi_hat) - λ·Cost(q)`

Where:
- `EIG` is Expected Information Gain using a contaminated likelihood function.
- `r_hat` is the estimated operational reliability of the source.
- `phi_hat` is the estimated risk of adversarial manipulation.
- `Cost(q)` is the latency, dollar, or cognitive cost to acquire `q`.
- `λ` Normalizes cost against bits of information gain.

---

## 3. Quick Start (Smoke Test)

```bash
# 1. Clone CDB (sibling directory)
git clone https://github.com/simbianai/cyber_defense_benchmark.git ../cdb
pip install -e ../cdb

# 2. Unpack CDB dataset
python -c "from benchmark.dataset_prep import ensure_unpacked; from pathlib import Path; ensure_unpacked(Path('../cdb/datasets'))"

# 3. Install HADES dependencies
pip install -r requirements.txt

# 4. Pin benchmark provenance
python scripts/hash_dataset.py

# 5. Smoke test (Baseline check)
PYTHONPATH=.;../cdb python scripts/run_smoke.py
```

---

## 4. Benchmark & Provenance

HADES is evaluated against the [Cyber Defense Benchmark (CDB)](https://github.com/simbianai/cyber_defense_benchmark).

Every result must trace cleanly:
`claim → figure/table → analysis script → processed data → raw run → config.yaml → seed → git commit → dataset_hash`

---

## 5. Repository Structure

```
hades-bench-v1/
├── hades/               # Core packages
│   ├── belief/          # Bayesian update, likelihood, EIG, VoI
│   ├── policies/        # Acquisition policies (P0..P5)
│   ├── simulator/       # Local experimental testbed
│   ├── query_menu.py    # 7 canonical evidence sources
│   └── harness.py       # Interacts with CDB
├── scripts/             # Experiment runners
├── configs/             # Frozen experiment definitions
├── tests/               # Test suite
└── docs/                # Architecture and reframing notes
```

---

## 6. Citation

```bibtex
@software{hades2026,
  author = {G.S., Aakash},
  title  = {HADES: Budgeted Evidence Acquisition for Cyber Threat Hunting Under Adversarial Telemetry},
  year   = {2026},
  url    = {https://github.com/ftaakash/Hades}
}
```
