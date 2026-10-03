# Phase 7C Kill Gates

## Micro-Pilot Gates (7C.7)

### PHI-1 — Integration
φ_hat reaches contaminated_likelihood without boolean gate.
**Test**: deterministic unit test showing likelihood changes with φ_hat.

### PHI-2 — Value sensitivity
Changing φ_hat changes candidate VoI value.
**Test**: deterministic unit test.

### PHI-3 — Ranking sensitivity
Candidate ranking changes under φ variation in a constructed case.
**Test**: deterministic policy test with two candidates differing in φ_hat.

### PHI-4 — D decision relevance
P5_full and P5_no_phi diverge in at least one D-oriented pilot config.
**Test**: micro-pilot (50 seeds, σ={0.10, 0.30}).

### PHI-5 — No oracle leakage
No true-state (φ_true, attack label, true hypothesis) reaches P5.
**Test**: source inspection + leakage guard test.

## Confirmatory D Gates (7C.12)

### G7C-1 — Integration
Deterministic φ sensitivity demonstrated.

### G7C-2 — D decision relevance
P5_full vs P5_no_phi shows reproducible nonzero effect under ≥1 sigma.

### G7C-3 — D performance
P5_full − P3 > 0 with 95% CI excluding zero (under ≥1 sigma).

### G7C-4 — Practical magnitude
Cliff's δ and absolute TPM difference reported. Negligible effects noted.

### G7C-5 — Reliability isolation
D improvement must not be reproducible by P5_no_phi if claiming φ contribution.
