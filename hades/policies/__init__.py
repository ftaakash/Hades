"""Policy registry for HADES v3.0.

Importing this module registers all policy classes.

Usage:
    from hades.policies import POLICY_REGISTRY
    policy = POLICY_REGISTRY["robust_voi"]()
"""
from hades.policies.base import InvestigationState, Policy, QueryRecord, _argmax_tiebreak
from hades.policies.random_policy import RandomPolicy
from hades.policies.fixed_heuristic import FixedHeuristicPolicy
from hades.policies.p2_relevance import RelevancePolicy
from hades.policies.p3_ig import IGPolicy
from hades.policies.p4_ig_cost import IGCostPolicy
from hades.policies.p4b_ig_cost_rel import IGCostRelPolicy
from hades.policies.p5_robust_voi import RobustVoIPolicy
from hades.policies.p7_bayes_al import BayesALPolicy

# All policies that P5 must be compared against in the kill-gate sweep.
POLICY_REGISTRY: dict = {
    "random":       RandomPolicy,
    "fixed_heuristic": FixedHeuristicPolicy,
    "relevance":    RelevancePolicy,
    "ig":           IGPolicy,
    "ig_cost":      IGCostPolicy,
    "ig_cost_rel":  IGCostRelPolicy,
    "robust_voi":   RobustVoIPolicy,
    "bayes_al":     BayesALPolicy,
}

__all__ = [
    "InvestigationState",
    "Policy",
    "QueryRecord",
    "_argmax_tiebreak",
    "RandomPolicy",
    "FixedHeuristicPolicy",
    "RelevancePolicy",
    "IGPolicy",
    "IGCostPolicy",
    "IGCostRelPolicy",
    "RobustVoIPolicy",
    "BayesALPolicy",
    "POLICY_REGISTRY",
]
