# HADES 2.0 Novelty Audit (2026-10-07)

Scope: the claims HADES 2.0 can still make after 7L (KILL), 7T (KILL) and 7U (PROCEED).
The audit file Aakash referred to was never committed, so this one was rebuilt from scratch. If his original exists
locally, merge it into this file rather than replacing it.

Searches run 2026-10-07 through the Consensus and alphaXiv tools. The exa connector failed for this session.
Queries covered:
- sequential and active hypothesis testing with Byzantine, compromised or adversarial sensors;
- adaptive sensor selection with sensor trust;
- decision-theoretic troubleshooting and test selection;
- active learning with unreliable oracles;
- threat hunting and alert triage with tampered telemetry.

Each entry was checked against its abstract, or against the full text where marked. Entries marked *(not
re-checked)* are from memory and need a citation check before the paper.

## 1. Claim under audit

> In adversarial telemetry, choosing evidence by hypothesis information under a joint posterior over the hypothesis
> and every source's compromise state cuts decision regret relative to reliability-weighted EIG and joint (H, S) EIG,
> at equal spend, against attackers the model was not built for (7U: RRR 0.27 and 0.22). Scoped: large against
> cover-up, decoy and coordinated lies; small against misattribution; none against a policy-aware trust-harvest
> attacker. Plus two pre-registered negative results: probing for source state adds no decision value over
> hypothesis-only information under the joint model (7L), and randomised or minimax acquisition does not beat the
> non-robust comparator on a held-out attacker (7T).

## 2. Closest prior work

| # | Work | What it does | Overlap | What it does not do |
|---|---|---|---|---|
| 1 | de Kleer & Williams 1987, GDE *(not re-checked)* | Joint diagnosis over component health; next measurement chosen by expected entropy | Joint belief over faults; entropy-driven measurement selection | Faults are non-strategic; no decision loss; no cost-matched comparison under attack |
| 2 | Heckerman, Breese & Rommelse 1995, [Decision-theoretic troubleshooting](https://consensus.app/papers/details/f2d74a6b394a58e4926efbf6338134bd/?utm_source=claude_desktop); [Troubleshooting under uncertainty](https://consensus.app/papers/details/68729f1ce04459c2a138aed0c7b47520/?utm_source=claude_desktop) (1994); Breese & Heckerman 1996, [repair and experiment](https://consensus.app/papers/details/b70c1f33d747503c87d3d9f585e8d605/?utm_source=claude_desktop) | Bayesian-network troubleshooting; value-of-information test selection with costs | Cost-aware VoI over a joint fault model | No adversary; observations are trusted; no held-out attacker evaluation |
| 3 | Zheng, Rish & Beygelzimer 2005, [Efficient test selection in active diagnosis](https://consensus.app/papers/details/9be1400ed353569fa6ae00390ccab797/?utm_source=claude_desktop) | Greedy entropy test selection in a Bayesian network (computer-network faults) | Greedy information-gain acquisition | Tests are trusted; non-adversarial |
| 4 | Naghshvar & Javidi 2012/13, [Active sequential hypothesis testing](https://consensus.app/papers/details/a3c0052bedb15e0fafc7b71106df6a0a/?utm_source=claude_desktop) | Asymptotically optimal adaptive sensing | Our P3 baseline | Sensors are not compromised |
| 5 | Maranò et al. 2008, [Distributed detection under Byzantine attacks](https://consensus.app/papers/details/6de383ac50f254b7b95fab473e8c3cea/?utm_source=claude_desktop); Ren et al. 2017, [Byzantine sensors: security vs efficiency](https://consensus.app/papers/details/32f071f35221564e96c16d8bb0b0ac0a/?utm_source=claude_desktop); Li et al. 2019/2021, [sequential HT with Byzantine sensors](https://consensus.app/papers/details/a3b1182ee9e85d4aaf8ae5f5b1482372/?utm_source=claude_desktop) | Detection when a subset of sensors is adversarial; worst-case (flip) attacks; game-theoretic equilibria | Strategic compromised sources | All sensors are observed (no acquisition choice); asymptotic error exponents, not finite-budget regret |
| 6 | Soltanmohammadi et al. 2012, [Decentralized HT with misbehaving nodes](https://consensus.app/papers/details/7ce10d345a065ac1a61080acb9de8309/?utm_source=claude_desktop) | EM over node identity (honest / misbehaving) jointly with the hypothesis | **Joint inference over hypothesis and source state**; this is the closest inference-side match | Passive fusion; no sequential, cost-aware choice of which source to read |
| 7 | Andersson & Dán 2026, [Active Bayesian inference under sensor FDI attacks](https://www.alphaxiv.org/abs/2604.11410) (full text read) | Bayesian network over sensor attack states from detector alerts; KL-maximising probing input; threshold probing policy; CPS control (CartPole) | **Closest overall**: belief over compromised sensors plus active probing, in CPS | Goal is control recovery, not a hypothesis decision. No comparison of joint-belief vs reliability-weighted acquisition. No held-out attacker; attacks are fixed bias injections. Simulated only |
| 8 | Zhong et al. 2025, [Learning-based detection with cost control and Byzantine mitigation](https://consensus.app/papers/details/03a9557200105d33bf72751290528bb7/?utm_source=claude_desktop) | Deep RL sensor scheduling with probing costs; GAN Byzantine detector | Cost-aware sequential sensing with Byzantine sensors | Learned policy + separate detector, not a joint Bayesian belief; no held-out attacker; no ablation of belief model vs objective |
| 9 | Hallyburton et al. 2025, [MATE trust estimator](https://consensus.app/papers/details/ed7a0007e63a5c2bbc2f07810d106e4f/?utm_source=claude_desktop) | Bayesian trust as a hidden Markov state, used to reweight fusion | Per-source trust belief | Fusion, not acquisition |
| 10 | [Maximin robust Bayesian experimental design](https://www.alphaxiv.org/abs/2603.14094) (2026) | Max–min BED under misspecification | Relevant to the 7T minimax candidate (negative result) | Not adversarial telemetry; no held-out attacker |
| 11 | Chang et al. 2021, [Evasive active hypothesis testing](https://consensus.app/papers/details/f28d8c4273e656bab73e81eb3166e476/?utm_source=claude_desktop) | Active sensing against an eavesdropper | Adversary-aware acquisition | The adversary observes; it does not corrupt sources |
| 12 | Settles et al. 2008; proactive learning (Donmez & Carbonell 2008) *(not re-checked)*; [ActiveLab](https://www.alphaxiv.org/abs/2301.11856) (2023) | Active learning with unreliable or multiple annotators | Querying unreliable sources | Noise is not strategic; no hypothesis-decision loss |
| 13 | Security: [HunterAgent](https://consensus.app/papers/details/1d3058267bd35583bbaf4efcc8348773/?utm_source=claude_desktop) (2026, anti-forensics); [Custos](https://consensus.app/papers/details/2a84fe70367f5dada572220756ade1d5/?utm_source=claude_desktop) (NDSS 2020, tamper-evident logs); [NoDoze](https://consensus.app/papers/details/d4e71c3127d45efbb29f4f646254e468/?utm_source=claude_desktop) (NDSS 2019) | Hunting and triage with partially corrupted or tampered telemetry | Domain motivation; Custos grounds the "integrity probe" | No decision-theoretic acquisition; no belief over source compromise |

## 3. Verdict per claim

| Claim | Novel? | Notes |
|---|---|---|
| Joint (H, S) belief as an inference model | **No** | GDE, Heckerman et al., Soltanmohammadi et al. Cite as foundations. |
| Probing a source's integrity with Bayesian updates on its compromise state | **No** | Andersson & Dán 2026 does this for CPS control; GDE/troubleshooting does it non-adversarially. |
| Cost-aware sequential acquisition with Byzantine sensors | **Partly** | Zhong et al. 2025 does it with deep RL; nobody isolates which ingredient matters. |
| **Controlled, pre-registered evidence that, at equal spend, the joint belief model (not the objective, not probing, not robustness) is what reduces regret, measured against held-out strategic attackers, with a scope map of where it fails** | **Yes, as an empirical contribution** | No paper found that (a) holds objective, horizon and cost fixed while swapping the belief model, (b) evaluates on attackers written after the policies were frozen, (c) reports where the effect vanishes (policy-aware attacker). |
| Negative results: decision-relevant probing adds nothing over hypothesis information under the joint model (7L); randomised or minimax acquisition loses to the non-robust comparator (7T) | **Yes** | Negative pre-registered results are rare in this literature. |
| Random acquisition beats model-based policies against a policy-aware attacker (all three pilots) | Plausibly new as an observation | Connects to mixed strategies in security games; needs its own pre-registered test before being a claim. |

## 4. Consequences for the paper

1. Frame it as an empirical and benchmark paper ("what actually matters when sources lie"), not a new method.
2. Andersson & Dán 2026 and Zhong et al. 2025 must be cited and differentiated in related work. Both are in CPS, which
   is also the domain of the planned real-data replication. The replication must therefore stress what they lack:
   a hypothesis-decision loss, equal-spend comparisons, and a belief-model ablation.
3. The real-data replication is the main open risk to external validity, and the gap reviewers will point at first.

## 5. Not yet checked

- POMDP threat-hunting and active-defence work (e.g. intrusion-response POMDPs).
- Adversarial active learning and poisoning-aware acquisition.
- Sensor-selection literature after 2024 beyond what the two tools returned.
- A citation check of every *(not re-checked)* row.
