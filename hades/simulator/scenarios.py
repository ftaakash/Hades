"""
hades/simulator/scenarios.py
-----------------------------
Five canonical test scenarios for the G1 order-flip gate.

Each scenario is designed to test a specific mechanism:

  A — No reliability difference:
        IG, IG/cost, and HADES should choose identically (or for cost only).
        If HADES "wins" here, it's not due to the reliability term.

  B — Reliability reverses query order:
        Raw IG prefers Q1, but Q1 has low reliability.
        Reliability-aware (ERHG) prefers Q2.
        This is the *core mechanism* being tested (G1).

  C — Cost reverses query order:
        IG prefers expensive Q1. IG/cost prefers cheaper Q2.
        Validates that cost awareness works independently of reliability.

  D — Manipulation risk reverses query order:
        Both sources have equal IG and equal cost.
        Q1 has low manipulation_risk_estimated; Q2 has high.
        HADES (with mu > 0) prefers Q1.
        Tests that manip_risk is an INDEPENDENT term.

  E — No useful distinction:
        All sources are equally informative and equally reliable.
        All policies should behave similarly.
        Prevents simulator from being trivially constructed to favour HADES.

Each scenario has 6 hypotheses and 7–12 evidence sources, matching the
scale requested in the proposal (5–10 hyps, 10–20 sources, rounded to
be representative of CDB's 7-source menu + realistic hypothesis space).
"""
from __future__ import annotations

from hades.simulator.environment import SimEvidenceSource, SimScenario

# ---------------------------------------------------------------------------
# Shared hypothesis labels (used across all scenarios)
# ---------------------------------------------------------------------------
HYPOTHESES = [
    "H_initial_access",
    "H_execution",
    "H_persistence",
    "H_privilege_escalation",
    "H_lateral_movement",
    "H_exfiltration",
]

# ---------------------------------------------------------------------------
# Scenario A — No reliability difference
# Expected: IG ≈ ERHG; ordering driven only by cost when λ>0
# ---------------------------------------------------------------------------
SCENARIO_A_NO_RELIABILITY_DIFF = SimScenario(
    name="A_no_reliability_diff",
    description=(
        "All sources have identical reliability (0.85) and identical "
        "manipulation risk (0.15). IG and HADES should choose identically "
        "or differ only due to cost penalisation."
    ),
    hypotheses=HYPOTHESES,
    sources=[
        SimEvidenceSource(
            name="auth_events",
            cost=1.0,
            reliability_true=0.85, reliability_estimated=0.85,
            manipulation_risk_true=0.15, manipulation_risk_estimated=0.15,
            hypothesis_affinity={
                "H_initial_access": 0.8, "H_lateral_movement": 0.9,
                "H_privilege_escalation": 0.6, "H_execution": 0.3,
                "H_persistence": 0.2, "H_exfiltration": 0.2,
            },
        ),
        SimEvidenceSource(
            name="process_events",
            cost=1.0,
            reliability_true=0.85, reliability_estimated=0.85,
            manipulation_risk_true=0.15, manipulation_risk_estimated=0.15,
            hypothesis_affinity={
                "H_execution": 0.9, "H_persistence": 0.7,
                "H_lateral_movement": 0.6, "H_privilege_escalation": 0.5,
                "H_initial_access": 0.3, "H_exfiltration": 0.2,
            },
        ),
        SimEvidenceSource(
            name="network_events",
            cost=1.5,
            reliability_true=0.85, reliability_estimated=0.85,
            manipulation_risk_true=0.15, manipulation_risk_estimated=0.15,
            hypothesis_affinity={
                "H_exfiltration": 0.9, "H_lateral_movement": 0.8,
                "H_initial_access": 0.5, "H_execution": 0.3,
                "H_persistence": 0.2, "H_privilege_escalation": 0.2,
            },
        ),
        SimEvidenceSource(
            name="dns_events",
            cost=1.0,
            reliability_true=0.85, reliability_estimated=0.85,
            manipulation_risk_true=0.15, manipulation_risk_estimated=0.15,
            hypothesis_affinity={
                "H_exfiltration": 0.8, "H_initial_access": 0.6,
                "H_lateral_movement": 0.5, "H_execution": 0.2,
                "H_persistence": 0.1, "H_privilege_escalation": 0.1,
            },
        ),
        SimEvidenceSource(
            name="persistence_events",
            cost=1.5,
            reliability_true=0.85, reliability_estimated=0.85,
            manipulation_risk_true=0.15, manipulation_risk_estimated=0.15,
            hypothesis_affinity={
                "H_persistence": 0.95, "H_privilege_escalation": 0.4,
                "H_execution": 0.3, "H_lateral_movement": 0.2,
                "H_initial_access": 0.1, "H_exfiltration": 0.1,
            },
        ),
        SimEvidenceSource(
            name="powershell_events",
            cost=1.0,
            reliability_true=0.85, reliability_estimated=0.85,
            manipulation_risk_true=0.15, manipulation_risk_estimated=0.15,
            hypothesis_affinity={
                "H_execution": 0.85, "H_privilege_escalation": 0.6,
                "H_persistence": 0.5, "H_lateral_movement": 0.4,
                "H_initial_access": 0.2, "H_exfiltration": 0.1,
            },
        ),
        SimEvidenceSource(
            name="object_access_events",
            cost=2.0,
            reliability_true=0.85, reliability_estimated=0.85,
            manipulation_risk_true=0.15, manipulation_risk_estimated=0.15,
            hypothesis_affinity={
                "H_privilege_escalation": 0.9, "H_persistence": 0.5,
                "H_execution": 0.4, "H_lateral_movement": 0.3,
                "H_initial_access": 0.2, "H_exfiltration": 0.2,
            },
        ),
    ],
)

# ---------------------------------------------------------------------------
# Scenario B — Reliability reverses query order  ← CORE G1 TEST
#
# Replicates the motivating example from section 6 of the research proposal:
#   process_tree: higher raw IG, but low reliability (manipulable)
#   auth_events:  slightly lower raw IG, but high reliability
#
# Under raw IG → process_tree wins
# Under ERHG (IG × reliability) → auth_events wins
# This is the ORDER-FLIP being tested.
# ---------------------------------------------------------------------------
SCENARIO_B_RELIABILITY_FLIP = SimScenario(
    name="B_reliability_flip",
    description=(
        "process_tree is DISCRIMINATING (high affinity to H_execution only, low to all others). "
        "auth_events is BROADLY relevant but lower affinity to H_execution. "
        "Raw EIG: process_tree > auth_events (it resolves H_execution uncertainty). "
        "But process_tree reliability_estimated=0.50; auth_events=0.90. "
        "Contaminated EIG: auth_events wins (reliability degrades process_tree's signal). "
        "This is the ORDER-FLIP being tested under reframed Bayesian EIG."
    ),
    hypotheses=HYPOTHESES,
    priors={
        "H_initial_access":        0.10,
        "H_execution":             0.50,   # leading hypothesis
        "H_persistence":           0.10,
        "H_privilege_escalation":  0.10,
        "H_lateral_movement":      0.10,
        "H_exfiltration":          0.10,
    },
    sources=[
        SimEvidenceSource(
            name="auth_events",
            cost=1.0,
            reliability_true=0.95,
            reliability_estimated=0.90,
            manipulation_risk_true=0.05,
            manipulation_risk_estimated=0.05,
            hypothesis_affinity={
                # Broadly relevant: good for H_lateral_movement but also H_execution
                "H_lateral_movement": 0.90, "H_initial_access": 0.80,
                "H_execution": 0.60,  # moderately discriminating
                "H_privilege_escalation": 0.50, "H_persistence": 0.30,
                "H_exfiltration": 0.20,
            },
            description="High reliability (0.90). Moderately discriminating for H_execution.",
        ),
        SimEvidenceSource(
            name="process_tree",
            cost=1.0,
            reliability_true=0.40,
            reliability_estimated=0.50,
            manipulation_risk_true=0.65,
            manipulation_risk_estimated=0.60,
            hypothesis_affinity={
                # DISCRIMINATING: very high for H_execution, very low for others
                "H_execution": 0.95,          # specifically detects execution
                "H_privilege_escalation": 0.25,  # low for all others
                "H_persistence": 0.15,
                "H_lateral_movement": 0.10,
                "H_initial_access": 0.08,
                "H_exfiltration": 0.05,
            },
            description="Low reliability (0.50). HIGHLY discriminating for H_execution only -> high raw EIG. Reliability flip.",
        ),
        SimEvidenceSource(
            name="dns_events",
            cost=1.0,
            reliability_true=0.80, reliability_estimated=0.80,
            manipulation_risk_true=0.25, manipulation_risk_estimated=0.25,
            hypothesis_affinity={
                "H_exfiltration": 0.85, "H_initial_access": 0.60,
                "H_lateral_movement": 0.40, "H_execution": 0.20,
                "H_persistence": 0.10, "H_privilege_escalation": 0.10,
            },
        ),
        SimEvidenceSource(
            name="network_events",
            cost=1.5,
            reliability_true=0.82, reliability_estimated=0.82,
            manipulation_risk_true=0.30, manipulation_risk_estimated=0.30,
            hypothesis_affinity={
                "H_exfiltration": 0.90, "H_lateral_movement": 0.75,
                "H_initial_access": 0.50, "H_execution": 0.30,
                "H_persistence": 0.20, "H_privilege_escalation": 0.20,
            },
        ),
        SimEvidenceSource(
            name="persistence_events",
            cost=1.5,
            reliability_true=0.78, reliability_estimated=0.78,
            manipulation_risk_true=0.28, manipulation_risk_estimated=0.28,
            hypothesis_affinity={
                "H_persistence": 0.95, "H_privilege_escalation": 0.40,
                "H_execution": 0.30, "H_lateral_movement": 0.20,
                "H_initial_access": 0.10, "H_exfiltration": 0.10,
            },
        ),
        SimEvidenceSource(
            name="powershell_events",
            cost=1.0,
            reliability_true=0.88, reliability_estimated=0.88,
            manipulation_risk_true=0.20, manipulation_risk_estimated=0.20,
            hypothesis_affinity={
                "H_execution": 0.85, "H_privilege_escalation": 0.60,
                "H_persistence": 0.50, "H_lateral_movement": 0.40,
                "H_initial_access": 0.20, "H_exfiltration": 0.10,
            },
        ),
        SimEvidenceSource(
            name="object_access_events",
            cost=2.0,
            reliability_true=0.72, reliability_estimated=0.72,
            manipulation_risk_true=0.35, manipulation_risk_estimated=0.35,
            hypothesis_affinity={
                "H_privilege_escalation": 0.90, "H_persistence": 0.50,
                "H_execution": 0.40, "H_lateral_movement": 0.30,
                "H_initial_access": 0.20, "H_exfiltration": 0.20,
            },
        ),
    ],
)

# ---------------------------------------------------------------------------
# Scenario C — Cost reverses query order
# IG prefers expensive Q1; IG/cost prefers cheaper Q2 with similar IG
# ---------------------------------------------------------------------------
SCENARIO_C_COST_FLIP = SimScenario(
    name="C_cost_flip",
    description=(
        "Q1 (expensive_auth) has slightly higher raw IG but costs 4× more than "
        "Q2 (cheap_process). IG policy → Q1. IG/cost policy → Q2."
    ),
    hypotheses=HYPOTHESES,
    sources=[
        SimEvidenceSource(
            name="expensive_auth",      # high IG, high cost
            cost=4.0,
            reliability_true=0.90, reliability_estimated=0.90,
            manipulation_risk_true=0.10, manipulation_risk_estimated=0.10,
            hypothesis_affinity={
                "H_lateral_movement": 0.95, "H_initial_access": 0.85,
                "H_privilege_escalation": 0.65, "H_execution": 0.35,
                "H_persistence": 0.25, "H_exfiltration": 0.25,
            },
        ),
        SimEvidenceSource(
            name="cheap_process",       # slightly lower IG, much cheaper
            cost=1.0,
            reliability_true=0.88, reliability_estimated=0.88,
            manipulation_risk_true=0.12, manipulation_risk_estimated=0.12,
            hypothesis_affinity={
                "H_lateral_movement": 0.90, "H_execution": 0.80,
                "H_initial_access": 0.70, "H_privilege_escalation": 0.55,
                "H_persistence": 0.30, "H_exfiltration": 0.20,
            },
        ),
        SimEvidenceSource(
            name="dns_events",
            cost=1.0,
            reliability_true=0.80, reliability_estimated=0.80,
            manipulation_risk_true=0.25, manipulation_risk_estimated=0.25,
            hypothesis_affinity={
                "H_exfiltration": 0.85, "H_initial_access": 0.60,
                "H_lateral_movement": 0.40, "H_execution": 0.20,
                "H_persistence": 0.10, "H_privilege_escalation": 0.10,
            },
        ),
        SimEvidenceSource(
            name="network_events",
            cost=1.5,
            reliability_true=0.82, reliability_estimated=0.82,
            manipulation_risk_true=0.20, manipulation_risk_estimated=0.20,
            hypothesis_affinity={
                "H_exfiltration": 0.90, "H_lateral_movement": 0.70,
                "H_initial_access": 0.50, "H_execution": 0.30,
                "H_persistence": 0.20, "H_privilege_escalation": 0.20,
            },
        ),
        SimEvidenceSource(
            name="powershell_events",
            cost=1.0,
            reliability_true=0.88, reliability_estimated=0.88,
            manipulation_risk_true=0.15, manipulation_risk_estimated=0.15,
            hypothesis_affinity={
                "H_execution": 0.85, "H_privilege_escalation": 0.65,
                "H_persistence": 0.50, "H_lateral_movement": 0.35,
                "H_initial_access": 0.20, "H_exfiltration": 0.10,
            },
        ),
    ],
)

# ---------------------------------------------------------------------------
# Scenario D — Manipulation risk reverses query order
# Both sources: identical IG, identical reliability, identical cost.
# Q1 has low manip_risk; Q2 has high manip_risk.
# HADES (mu>0) chooses Q1. Other policies are indifferent (tie-break by order).
# ---------------------------------------------------------------------------
SCENARIO_D_MANIPULATION_FLIP = SimScenario(
    name="D_manipulation_flip",
    description=(
        "trusted_sensor and forgeable_sysmon have IDENTICAL reliability (r_hat=0.85) "
        "and similar affinities. "
        "trusted_sensor has manipulation_risk_estimated=0.02 (hard to forge). "
        "forgeable_sysmon has manipulation_risk_estimated=0.85 (attacker injects strong_contra). "
        "Under proper Bayesian EIG: forgeable_sysmon's contaminated likelihood is severely "
        "degraded by the phi_hat injection term -> lower EIG -> lower VoI. "
        "VoI (P5) distinguishes them; raw IG does NOT (they have equal r_hat). "
        "This is the manipulation-risk ORDER-FLIP under reframed v3.0 semantics."
    ),
    hypotheses=HYPOTHESES,
    sources=[
        SimEvidenceSource(
            name="trusted_sensor",      # low phi_hat -> contaminated likelihood stays clean
            cost=1.0,
            reliability_true=0.85, reliability_estimated=0.85,
            manipulation_risk_true=0.02, manipulation_risk_estimated=0.02,
            hypothesis_affinity={
                "H_lateral_movement": 0.85, "H_initial_access": 0.20,
                "H_privilege_escalation": 0.15, "H_execution": 0.12,
                "H_persistence": 0.10, "H_exfiltration": 0.08,
            },
        ),
        SimEvidenceSource(
            name="forgeable_sysmon",    # high phi_hat -> adversary injects strong_contra
            cost=1.0,
            reliability_true=0.85, reliability_estimated=0.85,
            manipulation_risk_true=0.90, manipulation_risk_estimated=0.85,
            hypothesis_affinity={
                "H_lateral_movement": 0.85, "H_initial_access": 0.20,
                "H_privilege_escalation": 0.15, "H_execution": 0.12,
                "H_persistence": 0.10, "H_exfiltration": 0.08,
            },
        ),
        SimEvidenceSource(
            name="dns_events",
            cost=1.0,
            reliability_true=0.80, reliability_estimated=0.80,
            manipulation_risk_true=0.20, manipulation_risk_estimated=0.20,
            hypothesis_affinity={
                "H_exfiltration": 0.85, "H_initial_access": 0.55,
                "H_lateral_movement": 0.40, "H_execution": 0.20,
                "H_persistence": 0.10, "H_privilege_escalation": 0.10,
            },
        ),
        SimEvidenceSource(
            name="network_events",
            cost=1.5,
            reliability_true=0.82, reliability_estimated=0.82,
            manipulation_risk_true=0.25, manipulation_risk_estimated=0.25,
            hypothesis_affinity={
                "H_exfiltration": 0.88, "H_lateral_movement": 0.72,
                "H_initial_access": 0.48, "H_execution": 0.28,
                "H_persistence": 0.18, "H_privilege_escalation": 0.18,
            },
        ),
    ],
)

# ---------------------------------------------------------------------------
# Scenario E — No useful distinction
# All sources equally informative, equally reliable, equally risky.
# All policies should behave similarly; prevents cherry-picking.
# ---------------------------------------------------------------------------
SCENARIO_E_NO_DISTINCTION = SimScenario(
    name="E_no_distinction",
    description=(
        "All sources have identical properties. All policies behave similarly. "
        "Prevents the simulator from being trivially constructed to favour HADES."
    ),
    hypotheses=HYPOTHESES,
    sources=[
        SimEvidenceSource(
            name=f"source_{i}",
            cost=1.0,
            reliability_true=0.80, reliability_estimated=0.80,
            manipulation_risk_true=0.20, manipulation_risk_estimated=0.20,
            hypothesis_affinity={h: 0.50 for h in HYPOTHESES},
        )
        for i in range(1, 8)
    ],
)

# Convenience collection for iteration
ALL_SCENARIOS = [
    SCENARIO_A_NO_RELIABILITY_DIFF,
    SCENARIO_B_RELIABILITY_FLIP,
    SCENARIO_C_COST_FLIP,
    SCENARIO_D_MANIPULATION_FLIP,
    SCENARIO_E_NO_DISTINCTION,
]
