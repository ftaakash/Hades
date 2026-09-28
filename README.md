<div align="center">

# ⚔️ HADES

### **H**ypothesis-**A**ware **D**ecision making for **E**vidence acquisition under adversarial **S**ecurity telemetry

[![Python 3.14](https://img.shields.io/badge/python-3.14-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-325%20passing-brightgreen?style=flat-square)](./tests/)
[![Phase](https://img.shields.io/badge/phase-4%20complete-success?style=flat-square)](./docs/REFRAME.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)](./LICENSE)
[![Target: IEEE](https://img.shields.io/badge/target-IEEE%20empirical-orange?style=flat-square)](./docs/literature_matrix.csv)

*A Bayesian evidence-acquisition framework for cyber threat hunting under contaminated, unreliable, or adversarially manipulated telemetry.*

</div>

---

## The Problem

Security investigations rely on telemetry that can be **incomplete, stale, or actively forged**.

A conventional information-gain (EIG) policy acquires the most *nominally* informative evidence next — without accounting for the possibility that the evidence itself has been corrupted. An attacker who understands this can suppress or forge the exact source the policy most wants to query.

> **HADES asks: how should uncertainty about telemetry reliability change the value of acquiring that evidence?**

---

## The Approach

HADES models reliability **inside** the Bayesian observation model rather than as a post-hoc penalty. The acquisition objective is:

$$V(q) = \underbrace{\text{EIG}(q \mid \hat{r}, \hat{\phi})}_{\text{reliability-aware gain}} - \lambda \cdot \underbrace{\text{Cost}(q)}_{\text{acquisition cost}}$$

| Symbol | Meaning |
|--------|---------|
| `EIG(q)` | Expected Information Gain under *contaminated* likelihood |
| `r̂` | Estimated operational reliability of source `q` |
| `φ̂` | Estimated adversarial manipulation risk of source `q` |
| `λ` | Budget normalisation parameter (pre-registered: `{0.5, 1.0, 2.0}`) |

> **μ is retired.** Manipulation risk enters through the contaminated likelihood function, not as an additive penalty.

---

## Research Status

| Phase | Description | Status |
|-------|-------------|--------|
| **0** | Freeze & repair — architecture snapshot | ✅ Complete |
| **1** | Bayesian belief + contaminated likelihood layer | ✅ Complete |
| **2** | Policy ladder (P0–P7) as cited baselines | ✅ Complete |
| **3** | F1/F5 kill-gate sweep on simulator | ✅ **GO** |
| **4** | Corruption engine (R1–R4) + reliability estimators + integration gate | ✅ **GO** |
| **5** | CDB transfer — `fast_db`, `candidate_extractor`, hypothesis tracker | 🔲 Next |
| **6** | Main sweep + statistics (Wilcoxon, bootstrap CI, Cliff's δ) | ⛔ Gated |
| **7** | Hardening, conformal stopping, sensitivity sweeps | ⛔ Gated |
| **8** | IEEE paper + reproducibility artifact | ⛔ Gated |

**Current result (Phase 3 kill gate):**

```
F1 PASS — P5 meaningfully diverges from P3 at low reliability noise (flip ≥ 0.10)
F5 PASS — divergence does not collapse monotonically as corruption grows
Clean OK — P5 introduces no drift in zero-corruption baseline scenarios (A, E)
```

---

## Policy Ladder

Each policy is a distinct acquisition strategy, cited to the literature it implements.

| Policy | Strategy | Reference |
|--------|----------|-----------|
| **P0** | Random | Baseline floor |
| **P1** | Fixed heuristic priority | Baseline floor+ |
| **P2** | argmax relevance\[leading_hyp\]\[s\] | Static adaptive |
| **P3** | argmax EIG | Naghshvar & Javidi 2013; ECC-AHT 2026 |
| **P4** | argmax EIG / cost | Cost-aware |
| **P4b** | argmax EIG(r̂-likelihood) / cost | Settles et al. 2008 |
| **P7** | Expected error reduction / Thompson | Anti-strawman (Settles 2008 §4) |
| **P5** | argmax V(q) — robust VoI | **HADES under test** |

---

## Corruption Regimes

HADES evaluates policies under four qualitatively distinct corruption regimes:

| Regime | Model | What it tests |
|--------|-------|---------------|
| **R0** | Clean | Baseline; no corruption |
| **R1** | Missing (drop rate `p ∈ {0.10, 0.25, 0.50}`) | Availability failure, sensor outage |
| **R2** | Stale (`0h → 1h → 24h` lag) | Pipeline delay, cached evidence |
| **R3** | Misleading (contra injection, mild/severe) | Plausible false-positive injection |
| **R4a** | Targeted — architecture-aware (p_attack) | Attacker suppresses highest-affinity source |

Corruption is orthogonal to reliability estimation. A source can be **both** corrupted (R4) **and** mis-estimated (Adversarial estimator), modelling the most challenging threat scenario.

---

## Reliability Estimator Regimes

| Estimator | Description | Key use case |
|-----------|-------------|--------------|
| **Clean** | `r̂ = r_true` (oracle) | Upper-bound baseline |
| **Noisy** | `r̂ = r_true + N(0, σ)` | Realistic estimation error |
| **Miscalibrated** | `r̂ = scale·r_true + bias` | Systematic over/under-trust |
| **Adversarial** | Attacker spoofs `r̂↑ φ̂↓` for high-risk sources | Looks safe, is forgeable |

The explicit misspecification cases tested: `φ_true = 0.70 → φ̂ = 0.20` (under-trust) and `φ̂ = 0.90` (over-caution).

---

## Repository Structure

```
hades-bench-v1/
├── hades/
│   ├── belief/          # Bayesian update, EIG, VoI, contaminated likelihood
│   │   ├── likelihood.py
│   │   ├── posterior.py
│   │   ├── value.py     # eig(), voi(), robust_voi()
│   │   └── relevance.py
│   ├── corruption/      # R1–R4 telemetry corruptors
│   │   ├── base.py      # Corruptor ABC + ObsContext
│   │   ├── missing.py   # R1
│   │   ├── stale.py     # R2
│   │   ├── misleading.py# R3
│   │   └── targeted.py  # R4a
│   ├── reliability/     # Reliability estimation regimes
│   │   └── estimator.py # Clean / Noisy / Miscalibrated / Adversarial
│   ├── integration/     # End-to-end pipeline runner
│   │   └── runner.py    # IntegrationRunner
│   ├── policies/        # P0–P7 acquisition policies
│   ├── simulator/       # Synthetic testbed (sub-ms per step, no SQLite)
│   │   ├── environment.py
│   │   ├── observations.py
│   │   └── scenarios.py # 5 canonical scenarios (A–E)
│   ├── query_menu.py    # 7-source fixed SQL menu
│   └── harness.py       # CDB run(env, model) contract
├── scripts/
│   ├── run_f1_sweep.py  # Phase 3 kill-gate sweep (20 seeds × 4 noise levels × 3 λ)
│   ├── run_smoke.py
│   └── run_baseline_comparison.py
├── tests/               # 325 tests — all passing
├── configs/experiments/ # pilot_v1.yaml, main_v1.yaml (frozen before sweeps)
├── results/raw/         # f1_sweep_*.json (canonical, versioned)
├── docs/
│   ├── REFRAME.md       # v0 → v3 architectural change
│   ├── threat_model.md  # R0–R4 corruption regime definitions
│   └── literature_matrix.csv
└── data_manifest/
    └── benchmark_lock.json  # CDB version + checksum (pinned)
```

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/ftaakash/Hades.git
cd Hades

# Install dependencies (Python 3.14, Windows: use 'py' not 'python')
pip install -e .

# Run full test suite
py -m pytest tests/ -q

# Run Phase 3 kill-gate sweep (20 seeds, all scenarios)
py scripts/run_f1_sweep.py --seeds 20 --noise 0,0.10,0.25,0.50

# Smoke test (requires ../cdb sibling)
py scripts/run_smoke.py
```

---

## Provenance Chain

Every paper claim must trace cleanly:

```
claim
  → figure / table
    → analysis script
      → processed data
        → raw run (results/raw/*.json)
          → config (configs/experiments/*.yaml)
            → seed
              → git commit
                → dataset hash (data_manifest/benchmark_lock.json)
```

`main_v1.yaml` is frozen before any sweep. Post-run changes require a new experiment ID.

---

## Kill Gate Protocol

| Signal | Action |
|--------|--------|
| F1 ~ 0 | Kill method claim → artifact or negative-results paper |
| F1 pass + collapse at 10–25% noise | Estimator paper reframe |
| G6 fails | Do not submit as novel-method paper |
| P5 ≤ P3 on CDB outcomes | K1 kill — P5 behaviorally distinct but not useful |

---

## Citation

```bibtex
@software{hades2026,
  author = {G.S., Aakash},
  title  = {HADES: Budgeted Evidence Acquisition for Cyber Threat Hunting
            Under Adversarial Telemetry},
  year   = {2026},
  url    = {https://github.com/ftaakash/Hades}
}
```

---

<div align="center">

*HADES is a research prototype. No production deployment. No superiority claims without Phase 5–6 evidence.*

**Researcher:** Aakash G.S. · **Target:** IEEE empirical paper · **Corpus:** [ftaakash/Hades](https://github.com/ftaakash/Hades)

</div>
