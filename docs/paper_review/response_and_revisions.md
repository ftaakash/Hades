# Response to the simulated reviews and revision log (draft v1 -> v2, 2026-10-07)

| Finding | Action in v2 |
|---|---|
| R1.1 | Sec. III lists R's four differences and calls the C-vs-R difference a "package"; Threats: decomposition is future work. Contribution 3 rewritten. |
| R1.2 | Threats "Model match" paragraph; Sec. IV states attackers appear under benign with prob. kappa; scope result (i) orders the gain by model match. |
| R1.3 | Sec. V-B: C-vs-J is an objective effect against a comparator weak on clean worlds (0.69); E2 notes wrappers were built on J only. |
| R1.4 | Threats "Missing comparators" paragraph. Not run: any new run needs a new protocol. |
| R1.5 | Sec. IV "Endpoint and statistics" rewritten: 95% two-sided = one-sided 0.025; 97.5% in E2; non-RRR gates named; PF-3 Holm; calibration 139/531/432 and under-power stated. |
| R1.6 | Fixed: five families / three held out; E2 trust-harvest best is randomised J (0.115) then random (0.120); abstract says "survives only relative to reliability weighting"; conclusion says two of three simulator ideas failed. |
| R1.7 | World parameters completed in Sec. IV; Cliff's delta 0.23 / 0.22 added. |
| R2.1 | Sec. III "Operational picture": EDR, Sysmon, auth, DNS, proxy, NetFlow, cloud audit, mail gateway; canary, heartbeat, hash chain, cross-sensor probes; ATT&CK T1562. |
| R2.2 | Threats "External validity": independence and high priors. |
| R2.3 | Conclusion opens "Among cost-aware Bayesian acquisition rules in our simulator". |
| R2.4 | Sec. VI: P best on 21.03 (0.105) but never probed, so not E1 evidence; "tested our detector more than our acquisition rules"; balanced base rate by design; stale spoof invisible to the alarm; nine 22.04 attacks excluded before the run. |
| R2.5 | Related work cites hammar2021, li2021byz, urbina2016, schneier1999 (fields as in citation_check.md). |
| R2.6 | Practical-implications paragraph; V-sim / V-real named; verdict column in Table I; "in this simulator" throughout; scope paragraph ends the intro. Uniform vs score-proportional randomisation: both reported (scope result ii); no claim that either is better. |
| R3.1 | Sec. V-B "Origin, disclosed" uses the 7U protocol's figures. |
| R3.2 | "minimax policy tied". |
| R3.3 | Sec. VI: "an invalid run decides nothing"; "Had V-real passed, the E3 replication would have been killed". |
| R3.4 | Committed in 196cb3a; v2 adds the new macros. |
| R3.5 | Authorless entries removed and not cited; Andersson & Dan corrected from alphaXiv 2604.11410. See citation_check.md. |
| R3.6 | Dated errata appended to docs/phase7t_robust_kill_report.md and docs/phase7u_joint_belief_report.md; original text left. |
| R3.7 | Not a defect: the only commit between them, eb586c6, adds the 7L seed manifest itself (git diff a88c60c eb586c6 = that one file). Recorded in docs/paper_stage7_verdict.md. |

Other v2 fixes: tables included with the primitive `\@@input` (v1's `\input` before `\bottomrule` raised LaTeX errors);
figure and table rows relabelled E1-E4 to match the text; zero LaTeX errors and zero overfull boxes in the v2 build.
