# Phase 7C-A — Cost-Matched Attribution: Verdict

**Experiment**: `phase7c_cost_attribution_main` · commit `0fafa44` (clean tree) · 54,000 episodes (10,800 paired keys × 5 arms)
**Raw**: `results/raw/phase7c_cost_attribution_main.json` · **Stats**: `results/analysis/phase7c_cost_attribution_statistics.json`
**Gates**: `results/phase7c_cost_attribution_verdict.json` · **Figures**: `results/figures/{cost_decomposition,incremental_hades_effect,phi_incremental_effect}.png`
**Protocol/gates**: `docs/phase7c_cost_attribution_{protocol,gates}.md` (preregistered in `d400437`; pilot `0fafa44`)

## Pre-run finding (affects the interpretation of Phases 6–7B)
The legacy **P3 is r̂-aware EIG, not nominal EIG**. All earlier "P5 − P3" contrasts therefore had
reliability awareness on *both* sides. True nominal baselines (`P3_nom`, `P3_nom_cost`) were added.
Empirical check: P3_nom/P3_nom_cost trajectories are identical across σ (pilot 900/900), so they don't leak r̂.

## Gates (λ = 1.0, B/C/D × σ ∈ {0.10, 0.20, 0.30}, n = 400 pairs per cell)

| Gate | Result | Basis |
|------|--------|-------|
| CAG-1 cost baseline valid | **PASS** | unit tests; COST divergence 41–100% where costs differ |
| CAG-2 cost effect in C | **PASS** | C: +3.88 queries [3.75, 4.01], −0.71 cost/query, TPM +0.051 [0.018, 0.086], δ = 0.10 |
| CAG-3 incremental HADES (primary) | **POSITIVE (narrow)** | only B σ=0.10: +0.067 [0.029, 0.104], Holm p = 0.030, **δ = 0.095 (negligible)** |
| CAG-4 φ attribution | **φ effect nonzero, unfavourable** | D σ=0.20: PHI −0.020 [−0.036, −0.005], Holm p = 0.031 |
| CAG-5 no contamination | **PASS** | tests + integrity (0 pairing / normalization / budget faults) |

## Decomposition (λ = 1.0, mean ΔTPM [95% CI])

| Cell | TOTAL (P5−P3_nom) | COST | RELIABILITY | PHI | **INCREMENT** (P5−P3_nom_cost) | Case |
|------|------|------|------|------|------|------|
| B σ0.10 | +0.117* | +0.050* | +0.076* | −0.009 | **+0.067 [0.029, 0.104]*** | A |
| B σ0.20 | +0.102* | +0.050* | +0.065 | −0.013 | +0.053 [0.013, 0.092] (Holm ns) | A |
| B σ0.30 | +0.093* | +0.050* | +0.057 | −0.013 | +0.044 [0.006, 0.082] (Holm ns) | A |
| C σ0.10–0.30 | +0.05–0.06 | +0.051 | +0.01–0.03 | −0.01 to −0.03 | ≈ 0 (CI ∋ 0) | B |
| D σ0.10 | −0.039 | −0.011 | −0.008 | −0.020 | **−0.028 [−0.045, −0.011]*** | D* |
| D σ0.20 | −0.027 | −0.011 | +0.005 | −0.020* | −0.015 [−0.033, +0.002] | O |
| D σ0.30 | −0.024 | −0.011 | −0.002 | −0.011 | −0.013 [−0.032, +0.006] | O |

\* Holm-significant within its family. Cases follow the spec framework (O = INCREMENT and COST CIs contain 0 but TOTAL's excludes 0).
In D σ0.20 and σ0.30 the Wilcoxon test is significant but the mean CI contains 0. Cliff's δ is slightly positive while the mean is negative,
so the paired distribution is skewed. These cells are not counted as gate evidence in either direction.

## Interpretation

1. **Cost-awareness is a real, separate effect.** It accounts for about 43% of TOTAL in B and essentially all of it in C (Case B).
2. **The HADES increment over cost-aware nominal EIG is entirely the reliability term.** In B, INCREMENT = RELIABILITY + PHI,
   with PHI ≤ 0 everywhere. Against the r̂-aware baseline, P5 adds nothing in B (TOTAL_LEGACY +0.002 to +0.008, CI ∋ 0).
   r̂-weighted EIG is the Settles-style component that AGENTS.md lists as **not novel** (P4b).
3. **Practical magnitude is small.** Every primary effect has Cliff's δ < 0.147 ("negligible"). In B σ0.10 the correct-hypothesis rate
   rises 0.450 → 0.485 at equal total cost (10.0). At σ0.30 it is 0.450 → 0.438 despite +0.044 TPM.
4. **The φ channel is decision-relevant but harmful in its target scenario.** In D, P5 avoids high-φ sources (0.6 vs 2.8 per episode at σ0.20),
   yet PHI is negative in every D cell (−0.011 to −0.020) and the correct rate falls 0.537 → 0.49–0.51. No support for spec Case E.
5. **Phase 7B reproduced and explained.** 7B's B σ=0.30 effect (+0.022) is `P5_no_phi − P3_rhat` here (pre-repair P5 ≡ P5_no_phi):
   +0.0220 [0.006, 0.038] pooled over λ (λ=1 alone: +0.022 [−0.006, 0.050]). It is a **cost** effect on top of r̂-aware EIG,
   and adding φ removes it (TOTAL_LEGACY at λ=1: +0.008, CI ∋ 0).

## λ sensitivity (descriptive, no gate)
INCREMENT in B is positive for all λ (λ=0.5: +0.067/+0.044/+0.033; λ=2.0 matches λ=1.0, because the budget is exhausted either way).
In D, INCREMENT is negative at λ=0.5 for all σ (−0.044 to −0.027, CIs < 0) and ≈ 0 at λ=2.0.

## Bottom line for the paper
- A claim of "reliability-aware acquisition beats cost-aware nominal EIG in a reliability-flip setting" is supported, with negligible effect size.
  That component is known prior art.
- No claim of a HADES-specific (φ / manipulation-aware) advantage is supported. The φ channel is a documented negative result.
- Not done: the D-only φ confirmatory run (7C-B). This main run already contains D × 3σ × 100 seeds with the 7C-B contrasts
  (P5−P3_rhat, P5−P3_nom_cost, P5−P5_no_phi). Whether that satisfies 7C-B or a separate run is needed is a decision for the researcher.
