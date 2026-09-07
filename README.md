# HADES — Budgeted Evidence Acquisition for Cyber Threat Hunting Under Adversarial Telemetry

**Researcher**: Aakash G.S.  
**Target**: IEEE-style empirical cybersecurity research paper  
**Benchmark**: [Cyber Defense Benchmark (CDB)](https://github.com/simbianai/cyber_defense_benchmark)

---

## What is HADES?

HADES is a research framework for studying **budgeted sequential evidence acquisition** in cyber threat hunting.

The core research question:

> Can a budget-aware investigation policy select the next telemetry acquisition action that maximizes reliable discrimination among competing cyberattack hypotheses, while accounting for acquisition cost and adversarial evidence risk?

HADES constrains CDB's freeform SQL action space to a **fixed evidence-source menu** (7 canonical Windows telemetry sources), isolating *acquisition policy quality* from *SQL generation quality*. This allows clean comparison of policies P0–P5.

---

## Policy Ladder

| ID | Policy | Purpose |
|---|---|---|
| P0 | Random | Non-adaptive lower bound |
| P1 | Fixed heuristic | Deterministic operational baseline |
| P2 | Relevance | Hypothesis-relevance-driven |
| P3 | Information gain | Uncertainty-reduction baseline |
| P4 | IG / cost | Cost-aware IG baseline |
| P4b | IG + cost + reliability | Ablation variant |
| P5 | **HADES** | Full policy: `U(q) = ERHG(q) − λ·Cost(q) − μ·ManipRisk(q)` |
| P6 | LLM investigator | Optional external reference |

---

## Current Status (Phase 0 — G0 PASSED)

```
G0 Baseline reproducible:   PASS
G1 Order-flip exists:        PENDING (Phase 1A)
G2 HADES improves outcomes:  PENDING
G3 No major clean penalty:   PENDING
G4 Robustness advantage:     PENDING
G5 Generalizes:              PENDING
G6 Literature gap survives:  PENDING
```

**Verified baseline result** (budget=20, CDB public sample, 155,350 events):

| Policy | Coverage | Queries |
|---|---:|---:|
| P0 Random (mean, 3 seeds) | 0.0761 ± 0.0060 | 20 |
| P1 Fixed heuristic | 0.0839 | 20 |

This is a sanity / infrastructure result, not evidence the HADES method works.

---

## Quick Start

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

# 5. Smoke test (P0 vs P1)
PYTHONPATH=.;../cdb python scripts/run_baseline_comparison.py
```

**With Docker:**
```bash
docker compose run hades python scripts/run_baseline_comparison.py
```

---

## Repository Structure

```
hades-bench-v1/
├── hades/               # Core package
│   ├── policies/        # P0, P1, (P2-P5 coming in Phase 2)
│   ├── query_menu.py    # 7 canonical evidence sources
│   └── harness.py       # CDB-contract run() function
├── scripts/             # Experiment scripts
├── configs/experiments/ # Frozen YAML experiment configs
├── tests/               # Test suite
├── docs/                # Threat model, literature matrix
├── data_manifest/       # Benchmark version lock
├── results/             # {raw, processed, publication}
├── paper/               # Manuscript (Phase 8)
└── Dockerfile
```

---

## Reproducibility

Every paper result traces through:

```
claim → figure/table → analysis script → processed data → raw run → config.yaml → seed → git commit → benchmark version
```

See `data_manifest/benchmark_lock.json` for the current benchmark identity.

---

## Gates & What They Mean

| Gate | What it tests | Action if failed |
|---|---|---|
| G1 | Reliability can change the optimal next query | Reformulate or abandon |
| G2 | HADES choices improve outcomes vs P3/P4 | Downgrade to measurement study |
| G3 | No major clean-regime penalty | Tune λ/μ |
| G4 | Robustness advantage under adversarial telemetry | Drop manipulation-risk term |
| G5 | Effect generalizes beyond CDB | Narrow claims |
| G6 | Novelty gap survives final literature audit | Don't submit as novel-method paper |

---

## Citation

```bibtex
@software{hades2026,
  author = {G.S., Aakash},
  title  = {HADES: Budgeted Evidence Acquisition for Cyber Threat Hunting Under Adversarial Telemetry},
  year   = {2026},
  url    = {https://github.com/ftaakash/Hades}
}
```
