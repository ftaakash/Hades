# HADES 2.0 Novelty Audit — Governing Record

**Status**: LOCKED (Phase 7E)

> [!IMPORTANT]
> The full audit document `docs/hades2_novelty_audit.md`, which the revised HADES 2.0 plan marks as COMPLETE,
> **is not present in this repository**. This file does not replace it and adds no new literature
> search. It only records, verbatim in substance, the audit conclusions stated in the revised plan (§0.2, §1.2, §3)
> so that the falsification experiment has a fixed governing statement. The researcher should add the
> original audit file when available.

## Killed as a standalone novelty claim
`P(H,S|E)` + decision-theoretic VoI + acquisition cost + adversarial source state.

## Not claimable as novel (substrate)
Joint hypothesis/source-state posterior; latent source reliability; Bayesian reliability weighting; EIG;
expected value of information; downstream decision utility; cost-aware acquisition; adversarial sensor models;
POMDP formulation; cyber threat hunting as a domain; cross-domain adapters.

## Single surviving residue (empirical mechanism claim)
An acquisition policy that **values information about source state S itself**, so that probing a suspicious
source can be rational, under a strategic/budgeted attacker, and that shows **lower downstream decision regret
than cost-matched reliability-weighted EIG**.

## Reopening rule
A new novelty search is triggered only if the mechanism changes materially, not because implementation is hard.

## Addendum 2026-10-07 — coverage gap: decision-theoretic troubleshooting and GDE

**The full audit `docs/hades2_novelty_audit.md` is still not in the repository, and it is not in the local
working copy either** (checked 2026-10-07). So it cannot be verified whether the audit covered the two lines of
prior art below, where "test the component vs. observe the system" is the central trade-off:

- **de Kleer & Williams (1987)**, "Diagnosing multiple faults", *Artificial Intelligence* 32(1) — GDE. Chooses the
  next measurement by minimum expected entropy over candidate diagnoses (which components are faulty). This is
  the direct ancestor of `P_JOINT_EIG_COST`: information gain over component (source) state.
- **Heckerman, Breese & Rommelse (1995)**, "Decision-theoretic troubleshooting", *Communications of the ACM* 38(3).
  Chooses between observations and component repairs/tests by expected cost and value of information. This is
  close to `P_PROBE`: source tests valued by their effect on a cost-weighted decision.

Consequences for the claim, recorded before any pilot run:
1. "Value source-state information by its decision consequences" is **not** new in itself (Heckerman et al.).
   "Value it by entropy over component states" is **not** new either (GDE). The pilot's primary comparator is
   therefore the GDE-style policy, not the myopic H-only baseline.
2. The surviving residue narrows to: under a **strategic, budgeted, adaptive** adversary that controls source
   state (troubleshooting and GDE assume non-adversarial faults), does decision-valued probing beat
   joint-state information gain at matched cost, and in which region of world parameters?
3. Whether decision-VoI vs. minimum-entropy test selection has already been compared empirically in the
   diagnosis/troubleshooting literature is **unknown here**; a targeted search is required before any paper
   claim. This is a material change of comparator, so it meets the reopening rule above.

**Action for the researcher**: commit the original audit file (it is the document the plan rests on) and add
these two works to its prior-art table.
