# Stage 7 verdict: HADES 2.0 paper (draft v2), 2026-10-07

Audit of the committed state: `paper/manuscript/main.tex` v2, numbers from `results/processed/paper_numbers.json`
(regenerated from `results/raw/` by `scripts/paper/recompute_headlines.py`, 18/18 checks against the committed
statistics JSON match).

## Claims vs evidence

| Claim (paper) | Evidence | Status |
|---|---|---|
| E1 killed: P vs C RRR 0.02 [-0.02, 0.06]; held-out misattrib. -0.05 | results/analysis/phase7l_probe_pilot_v2_statistics.json, verdict JSON; recompute | VERIFIED |
| E1 pooled P vs J 0.11 [0.06, 0.17], driven by cover-up 0.49 | recompute (7L contrasts) | VERIFIED |
| E2 killed: rand -0.19, minimax -0.02 vs J on decoy-migrate | phase7t statistics + verdict JSON; recompute | VERIFIED |
| E3 PROCEED: C vs R 0.27 [0.23, 0.30], vs J 0.22 [0.19, 0.26]; Cliff's delta 0.23 / 0.22 | phase7u statistics + verdict JSON; recompute | VERIFIED |
| E3 trust-harvest: vs R 0.12 [0.07, 0.18], vs J -0.03 [-0.09, 0.03]; random 0.126 lowest | recompute (7U contrasts, regret) | VERIFIED |
| E2 trust-harvest: randomised J 0.115, random 0.120 the two best | recompute (7T regret) | VERIFIED |
| E4 INVALID: V-real +0.04 [-0.04, 0.12] on 21.03; -0.08 on 22.04 | phase7v statistics + verdict JSON; recompute | VERIFIED |
| E4 exploratory: J beat C on 21.03 (-0.56); P lowest regret 0.105 and never probed | recompute (7V regret, probes) | VERIFIED |
| Calibration needs 139 / 531 / 432 worlds | results/raw/*_seed_manifest.json | VERIFIED |
| Spend exactly matched; leakage tests pass | gate JSONs (spend / leakage gates PASS in all four) | VERIFIED |
| Joint belief model is not new | docs/hades2_novelty_audit.md | VERIFIED (claimed as not new) |
| "In every simulated experiment, randomising did better against the adaptive attacker" | E1 random 0.125, E2 0.115/0.120, E3 0.126 lowest on trust-harvest | VERIFIED (descriptive, not gated) |

No OVERCLAIM or UNSUPPORTED rows remain after revision (v1 had five; see paper_review/response_and_revisions.md).

## Consistency sweep

- Verdicts agree across AGENTS.md, memory, the four reports, the four verdict JSONs and Table I (KILL, KILL, PROCEED,
  INVALID).
- Two report inconsistencies found (7T bolding, 7U "absent" wording): corrected by dated errata, original text kept.
- 7L manifest commit a88c60c vs run commit eb586c6: the only change between them is the manifest file itself.
- Wording: no "first" claims; "held out" is qualified as not "model-mismatched"; CI statements are not phrased as
  "significantly above 0.10".

## Gate table

| Experiment | Validity check | Main gates | Verdict |
|---|---|---|---|
| E1 phase7l_probe_pilot_v2 | V-sim PASS | PF-1 pass; PF-3, PF-4, PF-6 fail | KILL |
| E2 phase7t_robust_pilot_v1 | V-sim PASS | RG-1 fail (both) | KILL |
| E3 phase7u_joint_belief_v1 | V-sim PASS | JG gates all pass | PROCEED |
| E4 phase7v_hai_replication_v1 | V-real FAIL | not evaluated | INVALID |

## Decision: 🟡 proceed after listed fixes

Submittable as a pre-registered negative-results / controlled-ablation paper once Aakash:
1. adds an affiliation;
2. completes zhong2025 and hallyburton2025 and confirms dekleer1987 and donmez2008 (docs/paper_review/citation_check.md);
3. picks the venue (a workshop or a negative-results track fits better than a main-track method paper; the method is
   not novel and the positive result is simulator-only).

Not to be claimed: a novel method, real-data support, or robustness to adaptive attackers.
Next phase if pursued: a new pre-registered real-data attempt whose evidence passes V-real first.
