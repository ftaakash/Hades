# HADES Reframing Document (v3.0, 2026-09-20)

## What Changed and Why

### Old Approach (v0, retired at tag `hades-v0-baseline`)

The v0 implementation used a scalarized utility formula:

```
U(q) = ERHG(q) - lambda * Cost(q) - mu * ManipulationRisk_estimated(q)
```

where `ERHG = IG * reliability_estimated`. This formulation has two fundamental problems:

1. **Dimensionally inconsistent**: `IG * reliability` double-counts reliability. The raw
   IG approximation (`expected_ig`) used `reliability_estimated` as `p_informative`,
   then `expected_reliable_ig` multiplied by it again.

2. **Conceptually wrong**: manipulation risk should not be a separate additive penalty.
   Whether an attacker can forge an observation is a fact about the *observation process* —
   it belongs inside the likelihood model `p(e | H, q, r, phi)`, not outside it.

The order-flip result (G1, Scenario B: 90/90 flips) **is real** but was demonstrated
with a heuristic mechanism. It is retained as `results/raw/g1_v0_legacy.json` for
historical reference but is NOT cited as evidence for the reframed claim.

### New Approach (v3.0)

**Objective**: Value of Information under contaminated telemetry.

```
V(q) = E_{e ~ p(e | H_t, q, phi_hat)} [ U_terminal(H_{t+1}(e)) ] - lambda * Cost(q)
```

where:
- `p(e | H, q, r_hat, phi_hat)` is the **contaminated likelihood**:
  `r_hat * p_nominal(e|H,q) + (1 - r_hat) * p_noise(e)` mixed with `phi_hat * p_forged`
- `U_terminal(beliefs)` = expected utility of optimal terminal decision (max-belief or -entropy)
- `lambda` = single free parameter (budget-normalized); `mu` is **deleted**
- Robust variant: `P5 = max_q min_{phi in Phi_budget} V(q; phi)` (minimax, Stage C only)

**Key invariant**: `r_hat` and `phi_hat` are policy-side estimates. `r_true` and `phi_true`
are evaluator-only. Policies NEVER access `*_true` fields.

### Baselines Correctly Cited

| Policy | Rule | Citation |
|--------|------|----------|
| P0 | Random | Floor |
| P1 | Fixed heuristic priority | Floor+ |
| P2 | argmax relevance[leading_hyp][s] | Static baseline |
| P3 | argmax EIG | Naghshvar & Javidi 2013; ECC-AHT 2026 |
| P4 | argmax EIG / cost | Cost-aware baseline |
| P4b | argmax EIG(r_hat-likelihood) / cost | Settles et al. 2008 — **NOT novel** |
| P7 | Expected error reduction / Thompson sampling | Anti-strawman (Settles 2008, §4) |
| P5 | argmax V(q) / robust_voi | **HADES under test** |

### Ablation Ladder (replaces A0-A3)

| Step | What is added relative to previous | Answers |
|------|-------------------------------------|---------|
| V0 | Raw IG (P3) | Baseline |
| V1 | +cost (P4) | Does cost normalization help? |
| V2 | +r_hat in contaminated likelihood (P4b) | Does reliability in likelihood help? |
| V3 | +phi_hat non-adaptive (P5, Stage A) | Does corruption modeling help? |
| V4 | +robust minimax (P5, Stage C) | Does robustness help? |

### Kill / Pivot Protocol

- **F1 ~ 0** (no flip→outcome lift in simulator): kill method claim; publish artifact/measurement or pivot to H4 negative-results.
- **F1 passes, F5 fails** (collapses at 10–25% noise): estimator paper reframe.
- **F2/F6/F10 fail**: narrow to non-adaptive or CDB-specific with acknowledged limits.
- **G6 fails**: don't submit as novel-method paper; submit as empirical evaluation/benchmark.

### What Carries Over Unchanged

- `hades/query_menu.py` — 7-source fixed menu (keep, extend with new fields)
- `hades/harness.py` — CDB `run(env, model)` contract (keep, extend)
- `hades/simulator/` — SimEnv A–E, 35 tests (keep mechanics, replace IG/utility internals)
- `data_manifest/benchmark_lock.json` — CDB provenance pin (keep, re-verify)
- `docs/threat_model.md` — R0–R4 definitions (keep)
- All infrastructure: `.gitignore`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`
