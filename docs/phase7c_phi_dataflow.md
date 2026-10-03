# Phase 7C — φ-Channel Dataflow Audit

## Complete Data Path

```
φ_true (scenario definition)
  │
  ├─ SimEvidenceSource.manipulation_risk_true      [scenarios.py L362-395]
  │
  ├─ ReliabilityEstimator estimates φ_hat           [estimator.py]
  │   └─ runner.py L125: manipulation_risk_estimated=est.phi_hat
  │
  ├─ QuerySpec.manipulation_risk_estimated          [runner.py → policy menu]
  │
  ├─ P5.select_query reads φ_hat                   [p5_robust_voi.py L79]
  │   └─ phi_hat = getattr(spec, "manipulation_risk_estimated", 0.0)
  │
  ├─ P5 calls voi()                                [p5_robust_voi.py L104-114]
  │   └─ voi(..., phi_hat=phi_hat, under_targeted_attack=False)  ← BREAKPOINT
  │
  ├─ voi() calls eig()                             [value.py L213-221]
  │   └─ eig(..., phi_hat=phi_hat, under_targeted_attack=under_targeted_attack)
  │
  ├─ eig() calls contaminated_likelihood()         [value.py L145-151]
  │   └─ contaminated_likelihood(..., phi_hat=phi_hat, under_targeted_attack=...)
  │
  └─ contaminated_likelihood()                     [likelihood.py L217]
      └─ if under_targeted_attack and phi_hat > 0:    ← φ ONLY ACTIVATES HERE
              result += phi_hat * p_forged
```

## Breakpoint Analysis

**Location**: `p5_robust_voi.py`, line 113

```python
score = voi(
    ...,
    r_hat=r_hat,
    phi_hat=phi_hat,           # ← φ_hat IS passed
    ...,
    under_targeted_attack=False,  # ← but attack flag is always False
)
```

**Effect in contaminated_likelihood** (likelihood.py L217):

```python
if under_targeted_attack and phi_hat > 0.0:
    p_for = forged.get(obs_class, 0.0)
    result = result + phi_hat * p_for
```

Because `under_targeted_attack=False`, the forged injection term is **never added**.

## Root Cause

The `under_targeted_attack` boolean was designed as an environment-level truth flag
("is the attacker currently targeting this source?"). P5 correctly does NOT have
access to this ground truth.

However, the contaminated likelihood model uses this flag as a **gate** for the
φ_hat contribution. This means φ_hat is passed through the entire pipeline but
has zero mathematical effect.

## Semantic Fix Required

The model already defines the intended formula:

```
p(e|H,q) = r_hat * p_nominal + (1-r_hat) * p_noise + phi_hat * p_forged
```

The fix is: **remove the boolean gate**. When `phi_hat > 0`, the forged term
should always be added (scaled by phi_hat). The policy-visible `phi_hat` itself
serves as the "estimated probability of manipulation" — it should NOT require
a separate oracle flag to activate.

This is the minimal repair: change `contaminated_likelihood()` so that the
forged term is always added when `phi_hat > 0`, regardless of `under_targeted_attack`.

The `under_targeted_attack` parameter can be retained for the EVALUATOR
(environment-side belief update) but must not gate the POLICY-side computation.

## Repair as Implemented (7C.4) - supersedes "Semantic Fix Required" above

The global gate removal proposed above was implemented first and then **rejected**:
it made phi_hat active in P3/P4/P4b/P7 and in the evaluator's belief update
(SimEnv._update_beliefs), which changed the baselines and the environment dynamics.
Two existing invariant tests failed (Scenario C cost-flip, Scenario D clean-regime equality).
That violates the 7C.5 requirement that P3 stay unchanged.

A second defect also showed up: the old phi branch esult + phi_hat * p_forged is
**unnormalized** (sums to 1 + phi_hat over obs classes). EIG computed from it is biased
and clamps to 0 at high phi_hat (e.g. EIG = 0.0 at phi_hat = 0.9).

Final repair (two changes):

1. `hades/belief/likelihood.py`: the gate is kept. The phi branch is now a proper mixture:
   `(1 - phi_hat) * [r_hat * p_nom + (1 - r_hat) * p_noise] + phi_hat * p_forged`.
   This only affects callers that pass `under_targeted_attack=True`, i.e. `robust_voi`
   and P5 after this repair.
2. `hades/policies/p5_robust_voi.py`: P5 calls `voi(..., under_targeted_attack=(phi_hat > 0.0))`.
   The flag comes only from the policy-visible estimate, never from ground truth.

Invariants verified by tests (`tests/test_phi_channel.py`, 362/362 passing):
- phi-aware likelihood sums to 1 for every (phi, relevance).
- EIG strictly decreases in phi_hat and stays > 0.
- P5 choice flips on phi_hat alone (PHI-3). P3 is unaffected.
- phi_hat = 0 gives the same score as pre-7C P5.
- P5 `select_query` references no `*_true` fields (PHI-5).
- Evaluator belief update and P3/P4/P4b/P7 are unchanged (all pre-existing tests pass).

Caveat for interpretation: the environment injects forged observations only when the
corruption regime is targeted (`runner.py`: `under_targeted_attack=isinstance(corruptor, TargetedCorruptor)`).
In non-targeted regimes P5's phi-modelling is a misspecification and may cost performance.
The pilot (7C.6) must report this rather than engineer around it.
