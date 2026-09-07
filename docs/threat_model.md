# HADES Threat Model

**Version**: 0.1.0  
**Status**: Initial draft — Phase 0  
**Author**: Aakash G.S.

---

## 1. Setting

HADES evaluates investigation policies in an environment where:

- A defender (the policy) investigates a Windows-event telemetry store
- The environment is provided by CDB (Cyber Defense Benchmark)
- The attacker controls the attack campaign that generated the telemetry
- In adversarial regimes (R1–R4), the attacker also influences what the defender observes

---

## 2. Attacker Capabilities

| Capability | Clean (R0) | Missing (R1) | Stale (R2) | Misleading (R3) | Targeted (R4) |
|---|:---:|:---:|:---:|:---:|:---:|
| Generate attack telemetry | ✓ | ✓ | ✓ | ✓ | ✓ |
| Suppress selected evidence classes | ✗ | ✓ | ✗ | ✗ | ✓ |
| Inject historical (stale) records | ✗ | ✗ | ✓ | ✗ | ✓ |
| Inject semantically plausible decoys | ✗ | ✗ | ✗ | ✓ | ✓ |
| Adapt to current investigation policy | ✗ | ✗ | ✗ | ✗ | ✓ |

---

## 3. Out of Scope

The attacker **cannot**:

- Modify CDB ground-truth labels or the evaluation scorer
- Alter trusted defender-only telemetry (unless explicitly modeled)
- Attack real infrastructure or third-party systems
- Access the policy's internal belief state directly

---

## 4. Corruption Modes — Justification

### R1 — Missing

**Attacker capability**: Log deletion, anti-forensics, SIEM filter manipulation, agent failure on compromised host.

**Modifiable telemetry**: Any event class where the attacker has host or pipeline access.

**Not modifiable**: Events from defender-controlled, isolated collection infrastructure.

**Assumption**: Drop rate `d` is uniform across the targeted event class. A more sophisticated attacker would selectively suppress, but uniform dropping is a conservative first model.

### R2 — Stale

**Attacker capability**: Timestamp manipulation (timestomping), delayed log forwarding, clock skew injection on compromised hosts.

**Modifiable telemetry**: `TimeCreated` field in Windows events on compromised hosts.

**Not modifiable**: Network-level timestamps from independent sensors.

**Assumption**: Skew is bounded; realistic clock manipulation is typically minutes to hours, not days.

### R3 — Misleading

**Attacker capability**: Generating benign-looking activity that resembles a competing hypothesis (noise injection, LOLBin abuse that looks like legitimate admin work).

**Modifiable telemetry**: Application logs, attacker-controlled process events, DNS queries.

**Not modifiable**: Events from clean hosts unrelated to the attack.

**Assumption**: Decoy events are semantically plausible — they match valid Windows event schemas. They favor an incorrect hypothesis but are not anomalous by themselves.

### R4 — Targeted

**Attacker capability**: All of R1–R3, *plus* knowledge of the defender's current investigation policy (e.g., through insider knowledge or public code).

**Targeted**: The evidence source currently most likely to be selected by the policy.

**Assumption**: This is a strong, idealized adversary. Real attackers rarely have precise knowledge of the defender's query algorithm. R4 is a worst-case bound, not a typical scenario.

---

## 5. What HADES Does NOT Model

- The attacker cannot compromise the benchmark evaluation system
- No real credentials are used; all attack campaigns are synthetic/controlled (CDB)
- No public or third-party infrastructure is contacted
- HADES does not test detection against live threat actors

---

## 6. Reliability vs Manipulation Risk

These are **independent** properties:

- `reliability_true`: probability that a source's output accurately reflects ground truth (affected by data quality, coverage gaps, etc.)
- `manipulation_risk_true`: probability that an attacker can introduce false or suppressed evidence into this source

A source can be highly reliable (99% accurate in clean conditions) but highly manipulable (attacker can forge records), or vice versa. See `hades/reliability/estimator.py` for how policies receive estimated versions of these values.
