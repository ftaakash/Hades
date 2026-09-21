"""
hades/belief/__init__.py
-------------------------
Public API for the HADES belief/value-of-information package.

This package provides the foundational Bayesian machinery for HADES v3.0.
It replaces the heuristic expected_ig / expected_reliable_ig / hades_utility
methods in hades/simulator/environment.py.

All functions here work on plain Dict[str, float] belief distributions.
They are independent of SimEnv and can be used directly by policy classes.
"""

from hades.belief.likelihood import (
    LikelihoodTable,
    nominal_likelihood,
    contaminated_likelihood,
    make_default_table,
)
from hades.belief.posterior import update as belief_update
from hades.belief.value import (
    entropy,
    eig,
    terminal_utility,
    voi,
    robust_voi,
)
from hades.belief.relevance import RELEVANCE, RELEVANCE_PROVENANCE

__all__ = [
    # likelihood
    "LikelihoodTable",
    "nominal_likelihood",
    "contaminated_likelihood",
    "make_default_table",
    # posterior
    "belief_update",
    # value
    "entropy",
    "eig",
    "terminal_utility",
    "voi",
    "robust_voi",
    # relevance
    "RELEVANCE",
    "RELEVANCE_PROVENANCE",
]
