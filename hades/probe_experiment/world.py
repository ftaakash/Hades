"""
hades/probe_experiment/world.py
-------------------------------
Procedural world generation (protocol §4) and the defender's model.

A *world* is one draw from the pre-registered parameter distributions. It fixes the
defender's model: hypothesis prior, per-source informativeness, source-state priors,
evidence/probe costs, probe accuracy and the loss matrix. Episodes (truth draws) are
sampled inside a world by ``simulator.sample_truth``.

Semantics (cyber grounding, docs/phase7f_probe_value_problem.md §3):
  H        BENIGN | INTRUSION_LATERAL | INTRUSION_EXFIL
  D        CLOSE  | CONTAIN_HOST      | BLOCK_EGRESS
  S_q      HEALTHY | DEGRADED (forwarder fault: drops/stale, emits noise)
           | COMPROMISED (attacker controls what the source reports)
  query(q) pull evidence from telemetry source q (an EDR/Sysmon/proxy/DNS/auth log query)
  probe(q) source-integrity check of q: inject a canary event and verify it arrives
           intact, plus forwarder heartbeat / hash-chain check. Reveals S_q, not H.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Tuple

import numpy as np

HYPOTHESES: Tuple[str, ...] = ("BENIGN", "INTRUSION_LATERAL", "INTRUSION_EXFIL")
DECISIONS: Tuple[str, ...] = ("CLOSE", "CONTAIN_HOST", "BLOCK_EGRESS")
SOURCE_STATES: Tuple[str, ...] = ("HEALTHY", "DEGRADED", "COMPROMISED")
HEALTHY, DEGRADED, COMPROMISED = 0, 1, 2
M = len(HYPOTHESES)
NS = len(SOURCE_STATES)
N_OBS = M                 # evidence outcome o = "indicates hypothesis o"
PASS, FAIL = 0, 1         # probe outcomes

SOURCE_NAMES: Tuple[str, ...] = (
    "edr", "sysmon", "auth_log", "dns", "proxy", "netflow", "cloudtrail", "email_gw",
)


@dataclass(frozen=True)
class WorldDistribution:
    """Pre-registered world-parameter distributions (protocol §4.1). Frozen."""
    k_min: int = 5
    k_max: int = 8
    benign_prior: Tuple[float, float] = (0.30, 0.80)           # U
    accuracy: Tuple[float, float] = (0.45, 0.95)               # U, per source
    evidence_cost: Tuple[int, int] = (1, 4)                    # integer U{1..4}, per source
    probe_cost_ratio: Tuple[float, float] = (0.25, 2.0)        # log-U, per world; probe cost = max(1, round(r*c_q))
    compromise_prior: Tuple[float, float] = (0.02, 0.40)       # U, per world
    compromise_jitter: Tuple[float, float] = (0.5, 1.5)        # U, per source multiplier
    compromise_cap: float = 0.60
    benign_coupling: Tuple[float, float] = (0.0, 1.0)          # U, kappa
    degrade_prior: Tuple[float, float] = (0.0, 0.15)           # U, per source
    probe_detect_compromised: Tuple[float, float] = (0.50, 0.99)  # U, per world
    probe_false_fail: Tuple[float, float] = (0.0, 0.10)        # U, per world
    probe_detect_degraded: Tuple[float, float] = (0.60, 0.99)  # U, per world
    loss_miss: Tuple[float, float] = (1.0, 20.0)               # log-U, per world
    loss_false_alarm: float = 1.0
    misattribution_factor: float = 0.5                          # wrong-response loss / L_miss
    assumed_forge_rate: float = 0.90                            # defender's model of a compromised source
    budget: int = 12                                            # fixed integer budget; min action cost is 1,
                                                                # so every policy spends exactly the budget


@dataclass
class DefenderModel:
    """
    Everything a policy may know about the world. No ground truth lives here.

    Arrays
      prior_h[h]                 p(H=h)
      prior_s[h, q, s]           p(S_q=s | H=h)   (sources independent given H)
      lik_query[q, o, h, s]      p(o | H=h, S_q=s) for query(q)
      lik_probe[q, z, s]         p(z | S_q=s)     for probe(q)
      utility[d, h]              U(D=d, H=h)  (0 = correct, negative = loss)
    """
    world_id: int
    source_names: List[str]
    accuracy: np.ndarray
    evidence_cost: np.ndarray
    probe_cost: np.ndarray
    prior_h: np.ndarray
    prior_s: np.ndarray
    lik_query: np.ndarray
    lik_probe: np.ndarray
    utility: np.ndarray
    budget: float
    assumed_forge_rate: float
    # descriptive world parameters (phase-map axes); all are defender-known priors
    params: Dict[str, float] = field(default_factory=dict)

    @property
    def n_sources(self) -> int:
        return len(self.source_names)

    def validate(self) -> None:
        assert abs(self.prior_h.sum() - 1.0) < 1e-9, "prior_h not normalized"
        assert np.allclose(self.prior_s.sum(-1), 1.0), "prior_s not normalized"
        assert np.allclose(self.lik_query.sum(1), 1.0), "lik_query not normalized over o"
        assert np.allclose(self.lik_probe.sum(1), 1.0), "lik_probe not normalized over z"
        assert (self.prior_s >= 0).all() and (self.lik_query >= 0).all()


def nominal_lik(acc: float) -> np.ndarray:
    """p_nom(o | h) for a healthy source with accuracy ``acc``: shape (o, h)."""
    off = (1.0 - acc) / (N_OBS - 1)
    L = np.full((N_OBS, M), off)
    np.fill_diagonal(L, acc)
    return L


def forge_dist() -> np.ndarray:
    """Defender's model of forged output F(o | h): cover-up under intrusion, false flag under benign."""
    F = np.zeros((N_OBS, M))
    F[0, 1:] = 1.0                      # intrusion -> reports BENIGN
    F[1:, 0] = 1.0 / (N_OBS - 1)        # benign -> random intrusion indicator
    return F


def build_model(
    world_id: int,
    accuracy: np.ndarray,
    evidence_cost: np.ndarray,
    probe_cost: np.ndarray,
    benign_prior: float,
    compromise: np.ndarray,
    kappa: float,
    degrade: np.ndarray,
    p_detect_c: float,
    p_false_fail: float,
    p_detect_d: float,
    loss_miss: float,
    dist: WorldDistribution = WorldDistribution(),
    params: Dict[str, float] | None = None,
) -> DefenderModel:
    K = len(accuracy)
    prior_h = np.array([benign_prior] + [(1 - benign_prior) / (M - 1)] * (M - 1))

    prior_s = np.zeros((M, K, NS))
    for h in range(M):
        pc = compromise * (kappa if h == 0 else 1.0)
        prior_s[h, :, COMPROMISED] = pc
        prior_s[h, :, DEGRADED] = degrade
        prior_s[h, :, HEALTHY] = 1.0 - pc - degrade

    rho = dist.assumed_forge_rate
    F = forge_dist()
    lik_query = np.zeros((K, N_OBS, M, NS))
    for q in range(K):
        Ln = nominal_lik(float(accuracy[q]))
        lik_query[q, :, :, HEALTHY] = Ln
        lik_query[q, :, :, DEGRADED] = 1.0 / N_OBS
        lik_query[q, :, :, COMPROMISED] = rho * F + (1 - rho) * Ln

    lik_probe = np.zeros((K, 2, NS))
    for q in range(K):
        lik_probe[q, FAIL] = [p_false_fail, p_detect_d, p_detect_c]
        lik_probe[q, PASS] = 1.0 - lik_probe[q, FAIL]

    U = np.zeros((M, M))
    lm, lfa, mis = loss_miss, dist.loss_false_alarm, dist.misattribution_factor
    for d in range(M):
        for h in range(M):
            if d == h:
                U[d, h] = 0.0
            elif d == 0:
                U[d, h] = -lm
            elif h == 0:
                U[d, h] = -lfa
            else:
                U[d, h] = -mis * lm

    model = DefenderModel(
        world_id=world_id,
        source_names=list(SOURCE_NAMES[:K]),
        accuracy=np.asarray(accuracy, float),
        evidence_cost=np.asarray(evidence_cost, float),
        probe_cost=np.asarray(probe_cost, float),
        prior_h=prior_h,
        prior_s=prior_s,
        lik_query=lik_query,
        lik_probe=lik_probe,
        utility=U,
        budget=dist.budget,
        assumed_forge_rate=rho,
        params=params or {},
    )
    model.validate()
    return model


def _loguniform(rng: np.random.Generator, lo: float, hi: float) -> float:
    return float(np.exp(rng.uniform(np.log(lo), np.log(hi))))


def generate_world(world_seed: int, dist: WorldDistribution = WorldDistribution()) -> DefenderModel:
    """Draw one world from the pre-registered distributions. Deterministic in ``world_seed``."""
    rng = np.random.default_rng([7_7_0_0, world_seed])
    K = int(rng.integers(dist.k_min, dist.k_max + 1))
    acc = rng.uniform(*dist.accuracy, size=K)
    cost = rng.integers(dist.evidence_cost[0], dist.evidence_cost[1] + 1, size=K).astype(float)
    cost[int(rng.integers(K))] = dist.evidence_cost[0]   # some action always costs 1 -> exact spend matching
    r_probe = _loguniform(rng, *dist.probe_cost_ratio)
    pi_world = float(rng.uniform(*dist.compromise_prior))
    jitter = rng.uniform(*dist.compromise_jitter, size=K)
    comp = np.minimum(pi_world * jitter, dist.compromise_cap)
    kappa = float(rng.uniform(*dist.benign_coupling))
    degr = rng.uniform(*dist.degrade_prior, size=K)
    b = float(rng.uniform(*dist.benign_prior))
    d_c = float(rng.uniform(*dist.probe_detect_compromised))
    fp = float(rng.uniform(*dist.probe_false_fail))
    d_d = float(rng.uniform(*dist.probe_detect_degraded))
    lm = _loguniform(rng, *dist.loss_miss)
    params = {
        "n_sources": K,
        "compromise_prior": pi_world,
        "probe_cost_ratio": r_probe,
        "probe_accuracy": d_c,
        "informativeness": float(acc.mean()),
        "loss_asymmetry": lm / dist.loss_false_alarm,
        "benign_coupling": kappa,
        "benign_prior": b,
    }
    return build_model(
        world_id=world_seed, accuracy=acc, evidence_cost=cost, probe_cost=np.maximum(1.0, np.round(r_probe * cost)),
        benign_prior=b, compromise=comp, kappa=kappa, degrade=degr,
        p_detect_c=d_c, p_false_fail=fp, p_detect_d=d_d, loss_miss=lm,
        dist=dist, params=params,
    )


def distribution_as_dict(dist: WorldDistribution = WorldDistribution()) -> Dict:
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(dist).items()}
