# Phase 7F — Probe-Value Problem Specification

**Status**: FROZEN before any pilot run. Governs `phase7l_probe_pilot_v2`.
**Protocol**: `docs/phase7g_probe_value_falsification_protocol.md` · **Gates**: `docs/hades2_kill_gates.md`
**Config**: `configs/experiments/phase7l_probe_pilot_v2.json` · **Code**: `hades/probe_experiment/`
**Novelty record**: `docs/hades2_novelty_audit_record.md` (see its 2026-10-07 addendum on troubleshooting / GDE prior art)

## 1. Research question

When an information source may be strategically compromised, does an acquisition policy that values
source-state information **by its effect on the downstream decision** reduce decision regret at matched
spend, compared with a policy that values the **same source-state information as information**
(cost-aware joint-state EIG)?

### Why the comparator changed (from the plan's first revision)

`P3_RHAT_COST` scores actions by myopic EIG over `H`. A probe reveals `S_q`, not `H`, so it scores ≈ 0 by
construction. Any policy that values `S_q` at all would beat it on a probe-favouring world, which proves
nothing beyond "a myopic H-only heuristic can't see diagnostic value". Two baselines that *can* value
probes are therefore added, and the primary comparator is the stronger, closer one:

| Baseline | Can it value a probe? | Through what? |
|---|---|---|
| `P3_RHAT_COST_LA2` | yes | two-step lookahead: "probe now, then query the cleared source" |
| **`P_JOINT_EIG_COST`** (primary) | yes | information gain over the joint `(H, S_1..S_K)` |
| `P_JOINT_HEIG_COST` | yes | information gain over `H` under the exact joint model (explaining away) |

Beating `P_JOINT_EIG_COST` would show that the decision-relevance of source-state information matters
beyond information about source state. Losing to it, or tying, is also informative: "decision-relevance
adds nothing over joint-state information gain".

## 2. Hypotheses

- **H1**: `P_PROBE` has ≥ 10% lower regret than `P_JOINT_EIG_COST` at identical spend, pooled over attacked
  worlds drawn from the pre-registered world distribution, and the advantage is caused by source-state value
  (it collapses under the `P_PROBE_NO_S` ablation).
- **H0**: the advantage is < 10%, absent, or not attributable to source-state value. H0 surviving kills HADES 2.0.

## 3. State, actions and cyber grounding

| Symbol | Values | Cyber meaning |
|---|---|---|
| `H` | BENIGN, INTRUSION_LATERAL, INTRUSION_EXFIL | is there an intrusion, and which kind |
| `D` | CLOSE, CONTAIN_HOST, BLOCK_EGRESS | dismiss, isolate the host, cut egress |
| `S_q` | HEALTHY, DEGRADED, COMPROMISED | source works / forwarder fault (drops, stale, noise) / attacker controls what it reports |
| `query(q)` | outcome `o ∈ {indicates h}` | pull evidence from source q (EDR, Sysmon, auth log, DNS, proxy, NetFlow, CloudTrail, mail gateway) |
| `probe(q)` | outcome PASS / FAIL | **source-integrity check**: inject a canary event on the host and verify it arrives intact in q; check the log forwarder's heartbeat and hash chain; cross-check q against an independent sensor (EDR vs Sysmon) |

The probe is grounded in practice: canary and heartbeat checks are how SOCs detect log tampering and
broken pipelines (MITRE ATT&CK T1562 "Impair Defenses" and T1070 "Indicator Removal" are what it detects).
It is also the action the CloudBlind Probe idea needs, so the two lines of work share one primitive.

The probe reveals `S_q`, not `H`, **except** through two real couplings, both in the model:
explaining away (a FAIL on a source that reported BENIGN re-opens the intrusion hypotheses), and
benign coupling `κ` (tampering is less likely when nothing is going on: `P(S=C | BENIGN) = κ·P(S=C | intrusion)`).

## 4. Defender model (shared by every policy)

Sources are conditionally independent given `H`; every action touches one source. Exact Bayesian inference on
`P(H, S_1..S_K | E)` is used by **every** policy, and the terminal decision `D* = argmax_D E[U(D,H)|E]` is the
same for every policy. Policies differ only in how they score the next action.

- HEALTHY: `p(o=h | h) = acc_q`, the rest split evenly. DEGRADED: uniform.
- COMPROMISED (defender's assumed model, which matches the design attacker): with prob 0.90 a forged output
  (BENIGN under intrusion = cover-up; a random intrusion class under BENIGN = false flag), otherwise nominal.
- Probe: `P(FAIL | HEALTHY, DEGRADED, COMPROMISED) = (fp, d_deg, d_comp)`.
- Utility: 0 if correct; `−L_miss` for CLOSE under intrusion; `−0.5·L_miss` for the wrong containment;
  `−1` for a false alarm.

## 5. Worlds are generated, not hand-designed

Each pilot unit is a world drawn from frozen distributions (protocol §4). The five axes the phase map reports:
compromise prior, probe-cost ratio, probe accuracy, source informativeness, loss asymmetry. No scenario is
hand-built for the pilot; hand-built cases appear only in the deterministic tests (7K).

## 6. Attacker (evaluator side, isolated from policies)

Budget `B ∈ {0, 1, 2, 3}` controlled sources. Families: `A_COVER` (design), `A_MISATTRIB` (held-out:
targets the most *trusted* informative sources and pushes the wrong containment), `A_TRUST_HARVEST`
(adaptive: honest until queried, then takes the source over; lies low right after a probe; lets canaries
through with prob 0.5). Details: `hades/probe_experiment/attacker.py`.

## 7. Regret and cost

- Regret = `U(D*(H_true), H_true) − U(D, H_true)`, normalised by the world's largest loss `L_miss` (range 0–1).
- Cost: integer action costs, minimum 1, fixed integer budget 12, every policy must act while it can afford
  an action. **Every policy spends exactly 12** in every episode (checked; PF-2).

## 8. Policies

| Policy | Objective | Scoring model | Horizon | Role |
|---|---|---|---|---|
| P0_RANDOM_COST_MATCHED | random | — | — | floor |
| P3_NOM / P3_NOM_COST | H-information (/cost) | all HEALTHY | 1 | lineage |
| P3_RHAT / P3_RHAT_COST | H-information (/cost) | contaminated `r̂·p_nom + (1−r̂)·uniform` | 1 | HADES 1.0 lineage |
| **P3_RHAT_COST_LA2** | H-information / cost | same; probes update `r̂` | 2 | lookahead baseline (new) |
| P5_LEGACY | H-information − λ·cost/B | HADES 1.0 φ-mixture | 1 | lineage only |
| P_JOINT_HEIG_COST | H-information / cost | exact joint | 2 | secondary |
| **P_JOINT_EIG_COST** | joint (H,S)-information / cost | exact joint | 2 | **primary comparator** (new) |
| **P_PROBE** | decision value / cost | exact joint | 2 | candidate |
| P_PROBE_NO_S | decision value / cost | contaminated H-only, `r̂` frozen | 2 | PF-5 ablation |
| P_PROBE_NO_PROBE | decision value / cost | exact joint, no probe actions | 2 | probe-action ablation, phase-map reference |

Horizon is matched (2) between the candidate and the three serious comparators, so the primary contrast
changes the objective only. Two-step score: `max(V1(a)/c_a, max_b V2(a,b)/(c_a+c_b))`. Decision-objective
policies fall back to their own model's H-information when every score is 0 (VoI plateau); the fallback rate
is reported. Ties: alphabetical max of (score, action name).

## 9. Primary endpoint

Relative regret reduction `RRR = 1 − Σ_w ȳ_w(P_PROBE) / Σ_w ȳ_w(P_JOINT_EIG_COST)` over worlds, pooled over the
nine attacked cells (3 families × B ∈ {1,2,3}). Practical threshold **RRR ≥ 0.10**. Seed count from the power
analysis (protocol §7.2).

## 10. Kill criteria

PF-1 … PF-10 in `docs/hades2_kill_gates.md`. Any decisive failure → KILL. **No pilot verdict by 2026-11-11 → KILL.**
