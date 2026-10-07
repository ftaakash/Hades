# Phase 7T — Literature Checklist (robust acquisition against mismatched / policy-aware attackers)

**Status**: checklist only. The search connector was unavailable in the session that wrote this (2026-10-07),
so **no search has been run**. Each entry is a line of work to check, with the specific question it must answer.
References marked *(verify)* are recalled, not checked; confirm bibliographic details before citing anything.
Nothing here is a novelty claim.

## Why this matters for the claim

The v2 pilot found, exploratorily, that a randomised/random acquisition policy beat model-based policies against
a policy-aware attacker. "A mixed strategy beats a predictable one against an adversary who observes you" is
standard game theory. A 7T result can only be a contribution if it is (a) measured against an attacker no policy
was designed for and (b) positioned against the lines below.

| # | Line of work | Must answer | Starting points *(verify)* |
|---|---|---|---|
| 1 | Stackelberg security games / randomised patrolling | Is randomised evidence acquisition against an observing attacker already formalised and evaluated? | Tambe, *Security and Game Theory* (CUP 2011); Pita et al., ARMOR, AAMAS 2008 |
| 2 | Audit games | Randomised auditing of logs/records against strategic insiders: closest cyber analogue | Blocki, Christin, Datta, Procaccia, Sinha, "Audit Games", IJCAI 2013 |
| 3 | Information-directed / probability-matching sampling | Is "sample in proportion to information value" an established policy with known robustness properties? | Russo & Van Roy, information-directed sampling (NeurIPS 2014); Thompson sampling literature |
| 4 | Robust / minimax Bayesian experimental design | Worst-case expected information over a model set: is P_MINIMAX_JEIG a known design criterion? | Chaloner & Verdinelli, Bayesian experimental design review (Stat. Sci. 1995); robust-design literature |
| 5 | Secure estimation under sensor attacks | How many corrupted sensors can be tolerated; does sensor *selection* under attack exist? | Fawzi, Tabuada & Diggavi, IEEE TAC 2014; resilient/Byzantine sensor fusion |
| 6 | Adversarial / robust active learning | Query selection when labels or oracles are adversarial | Settles, *Active Learning Literature Survey* (2009) as entry point |
| 7 | Moving target defence / unpredictability as defence | Is defender randomisation in monitoring already argued as a defence? | MTD surveys (verify) |
| 8 | Decision-theoretic troubleshooting and GDE | Carried over from 7E: test-vs-observe trade-off | de Kleer & Williams 1987; Heckerman, Breese & Rommelse 1995 |
| 9 | Log tampering detection, canaries, telemetry integrity | Cyber grounding of probes and of the decoy/migrating attacker | ATT&CK T1562 / T1070; SIEM integrity literature (verify) |
| 10 | Threat-hunting evidence acquisition (domain) | Has anyone measured how acquisition policies degrade under telemetry tampering? | HADES 1.0 `docs/literature_matrix.csv` |

## Decision rule (recorded before the 7T run)

- If line 1, 2 or 4 already shows the 7T candidate behaviour on an equivalent problem, a 7T PROCEED supports an
  **empirical, cyber-grounded replication**, not a new method.
- The measurement claim (model-based acquisition gains do not transfer to mismatched or policy-aware tampering)
  stands on HADES 1.0 + v2 + 7T regardless of how this checklist resolves.
