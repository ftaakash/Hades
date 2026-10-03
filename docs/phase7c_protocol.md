# Phase 7C Protocol — φ-Channel Integration Repair

## Experiment ID
`phase7c_phi_repair`

## Phase 7B Reference
- Commit: `60c9a25`
- Tests: 357 passed
- Status: FROZEN (see STATUS_PHASE7B_FROZEN.md)

## Objective
Determine whether the manipulation-risk path φ_hat → likelihood → EIG → VoI → P5
actually functions when the integration gap is repaired.

## Semantic Contract (7C.2)

For candidate q with estimated manipulation risk φ_hat(q):

```
contaminated_likelihood(e | H, q) =
    r_hat * p_nominal(e | H, q)
  + (1 - r_hat) * p_noise(e)
  + phi_hat * p_forged(e)          ← always applied, not gated by boolean
```

This is the model already defined in likelihood.py. The repair removes the
`under_targeted_attack` gate from the policy-visible path.

## Constraints
- P5 must NOT access φ_true, attack-regime labels, or true hypothesis
- Only φ_hat (policy-visible estimate) enters the computation
- No threshold tuning (e.g. "if phi_hat > X then activate")
- P3 semantics must be unchanged
- φ_hat = 0 must reproduce prior P5 behavior exactly

## Execution Order
1. Dataflow audit (7C.1) — DONE
2. Semantic contract (7C.2) — THIS DOCUMENT
3. Deterministic tests (7C.3)
4. Minimal repair (7C.4)
5. Regression (7C.5)
6. 50-seed micro-pilot (7C.6)
7. PHI gates (7C.7)
8. If PASS: freeze → 100-seed D evaluation (7C.9-7C.12)
