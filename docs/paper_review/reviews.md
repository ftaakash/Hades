# Simulated hostile peer review of the HADES 2.0 paper (draft v1, commit 196cb3a)

Three independent hostile reviewers read draft v1 on 2026-10-07, each with the repository. Summaries of their findings
follow; every finding is answered in `response_and_revisions.md`.

## Reviewer 1 (methods and statistics). Score 2 (reject as drafted)

- R1.1 The C-vs-R contrast is not "one change": R differs from C in four ways (symmetric-noise compromise model,
  marginal r-hat without the H-S coupling kappa, no S update in its look-ahead, zero H-value for probes).
- R1.2 "Held-out" attackers still share the defender's model: every family is present under benign with probability
  kappa, and collude-cheap's lies are half cover-ups. C may win by model match.
- R1.3 C vs J is an objective effect, and J is weak (C beats J by 0.69 on clean worlds). E2's wrappers wrap the weak J.
- R1.4 Missing comparators: cost-aware P3_NOM in E3, horizon > 2, Thompson / expected-error reduction, forge-rate
  sensitivity.
- R1.5 Gate rule is stated imprecisely: PF-3 used a Holm p, several gates are not RRR gates, and a two-sided 95%
  percentile CI is a one-sided alpha 0.025 test. Report calibration requirements (139 / 531 / 432).
- R1.6 Factual: five attacker families with three held out (not six / two); on E2 trust-harvest P_RAND_JEIG (0.115)
  was lowest, not random (0.120); the abstract's "absent against trust-harvest" holds only vs J (vs R: 0.12
  [0.07, 0.18]); "three of four ideas failed" is wrong.
- R1.7 World parameters missing (benign prior, degradation prior, probe detection of degradation, compromise cap).
  Add Cliff's delta.

## Reviewer 2 (security realism). Score 2

- R2.1 No SOC grounding: name the sources, the probes, and the ATT&CK techniques.
- R2.2 Limitations missing: conditional independence of sources; compromise priors far above real prevalence.
- R2.3 Conclusion must open with scope.
- R2.4 E4: P is best on HAI (0.105), say what that implies; E4 tested the detector more than acquisition; justify the
  50% base rate; a stale spoof produces no change, so the alarm sees only process effects; mention the excluded 22.04
  attacks.
- R2.5 Related work misses optimal-stopping intrusion response (Hammar & Stadler), Byzantine sequential testing
  (Li et al.), stealthy ICS attacks (Urbina et al.), secure audit logs (Schneier & Kelsey).
- R2.6 Add practical implications; name the two validity checks distinctly; say "in this simulator"; add a verdict
  column to Table I; discuss uniform vs score-proportional randomisation; scope sentence at the end of the intro.

## Reviewer 3 (reproducibility). Recompute: 18/18 headline numbers match

- R3.1 "C was markedly lower than R and J in E1 and E2" is wrong: R (two-step) was not run in E2. Use the 7U protocol's
  numbers (28% lower than one-step P3_RHAT_COST over v2 cells, 55% on the 7T held-out attacker, 52% lower than J there).
- R3.2 Minimax "tied", not "lost", on the held-out attacker.
- R3.3 E4: state that INVALID takes precedence; had V-1 passed, HG-2 would have killed it.
- R3.4 Paper pipeline scripts untracked at review time (committed in 196cb3a).
- R3.5 Bibliography: three entries had no authors; Andersson & Dan title/authors wrong.
- R3.6 Repo errata needed: 7T report bolds random on trust-harvest; 7U report line 60 says "absent" without "vs J".
- R3.7 7L manifest commit (a88c60c) differs from the run commit (eb586c6).
