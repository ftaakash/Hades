"""hades/corruption — Telemetry Corruption Engine (v3.0).

Implements the R0–R4 corruption regimes defined in docs/threat_model.md.

Regime taxonomy
---------------
R0  Clean        — no corruption; baseline
R1  Missing      — observations dropped with probability p_drop
R2  Stale        — signal skewed toward older (neutral) observations
R3  Misleading   — plausible decoy observations injected instead of true signal
R4  Targeted     — adaptive attacker suppresses the source the policy currently
                   considers most informative (observes query history)

Key invariants
~~~~~~~~~~~~~~
- Corruption modifies OBSERVATIONS only. Ground-truth hypotheses are never changed.
- Policy never sees the corruption regime or true corruption parameters.
- `*_true` fields are evaluator-only; corruptors operate on the observation path.
- All corruptors are deterministic given a seed (reproducibility).
"""
from hades.corruption.base import Corruptor, ObsContext
from hades.corruption.missing import MissingCorruptor
from hades.corruption.stale import StaleCorruptor
from hades.corruption.misleading import MisleadingCorruptor
from hades.corruption.targeted import TargetedCorruptor

__all__ = [
    "Corruptor",
    "ObsContext",
    "MissingCorruptor",
    "StaleCorruptor",
    "MisleadingCorruptor",
    "TargetedCorruptor",
]
