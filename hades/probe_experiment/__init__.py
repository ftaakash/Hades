"""
hades/probe_experiment
----------------------
HADES 2.0 Phase 7H-7J: minimal falsification experiment for source-state probing.

Scope is deliberately small (plan §7H, §8): one synthetic world family, generated
procedurally from pre-registered parameter distributions, a strategic attacker with
design / held-out / adaptive families, and the policy set frozen in
docs/phase7g_probe_value_falsification_protocol.md.

Nothing in this package imports or modifies HADES 1.0 code (frozen at tag
hades-1.0-final). See docs/phase7f_probe_value_problem.md.

Information boundary
~~~~~~~~~~~~~~~~~~~~
* ``world.DefenderModel``   — what policies may read (priors, likelihoods, costs).
* ``simulator.EpisodeTruth`` — evaluator-only (H_true, S_true, attacker identity).
Policies receive only a DefenderModel, a JointBelief and the remaining budget.
"""
SIMULATOR_VERSION = "probe-sim-1.0"
