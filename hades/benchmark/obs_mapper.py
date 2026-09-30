"""hades/benchmark/obs_mapper.py — CDB observation → 5-class obs_class mapper.

v3.0: Per-source computer-spread mapper (replaces v2.0 content-feature mapper).

Mapper Version History
----------------------
v1.0: Row-count threshold. FAILED — LIMIT=10 saturates against CDB's 155k rows.
      All 647/647 turns → strong_support. Root cause: absolute row count cannot
      discriminate when LIMIT is always the binding constraint.

v2.0: Content-feature (null_rate + EventID variety). FAILED — CDB query filters
      fix EventID sets per source (dns_events always has EventID 22, auth_events
      always has 4624/4634/4648/4672, etc.) and null rates are structurally
      fixed at ~50-60% per source. No episodic variation in these features.
      All 654/654 turns → neutral. Root cause: the neutral OR clause is too
      broad because even query-fixed EventID variety ≥ 2 triggers neutral.

v3.0: Computer-spread (Distinct Computers / n_rows) + fallback to null_rate.
      Computer diversity IS a genuine episodic signal:
      - An attack spanning multiple hosts (TA0008 L. Movement / TA0004 PrivEsc)
        will produce high computer spread → strong_support.
      - A single-host session → low spread → weaker evidence.
      - No events on this source → contra class (source not activated in episode).
      This does NOT require labels, ground truth, or hidden hypothesis info.
      Computer field is observed directly from the SQL result.

Per-Source Baseline Computer Counts (from development-episode audit):
    Development episodes (seed 0-14), 1 env.reset each — all sources returned
    n_rows=10 (LIMIT saturated). Source-level baseline is NOT used for thresholds;
    the mapper classifies relative to the within-result computer spread.

    Source                Typical distinct_computers (development audit)
    ──────────────────────────────────────────────────────────────────────
    auth_events           3-7 (multiple hosts log auth across a session)
    process_events        2-5
    network_events        2-4
    dns_events            1-3
    persistence_events    1-3 (rarer lateral movement footprint)
    powershell_events     1-2 (often targeted single-host)
    object_access_events  1-2 (usually single-object context)

Mapping rules (v3.0, frozen from development audit):
    spread = distinct_computers / n_rows

    spread >= 0.40  → strong_support  (≥40% rows from different hosts)
    spread >= 0.20  → weak_support    (some multi-host activity)
    spread >= 0.10  → neutral         (mostly single-host with some spread)
    n_rows > 0 AND spread < 0.10 → weak_contra (one host, concentrated)
    n_rows == 0 AND high_rel  → weak_contra
    n_rows == 0 AND low_rel   → neutral
    error                     → strong_contra

    Tie-break: if Computer field is entirely absent from this source's select
    (no computer field extracted), fall back to single_computer_heuristic.

CONSTRUCT BOUNDARY — read before using this module:
    Computer spread proxies observation INFORMATIVENESS (breadth of activity
    visible in this query result) only. It is NOT a measure of source reliability.
    Reliability (r_hat) must come from hades.reliability.estimator ONLY.
    Do NOT use OBS_MAPPER outputs to infer that a source is reliable or
    unreliable for security-evidentiary purposes.

Thresholds frozen from the development audit of 5a_transfer_gate_v1.json
(15 episodes, seeds 0-14). Final evaluation must use held-out episodes.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

OBS_MAPPER_VERSION = "v3.0"

# CONSTRUCT BOUNDARY — read full module docstring above.
OBS_MAPPER_CAVEAT = (
    "Computer spread proxies observation informativeness only. "
    "It is not a reliability measure. r_hat must come from the estimator."
)

# ── Regex ──────────────────────────────────────────────────────────────────────
_ROWS_SHOWN_RE  = re.compile(r"Results\s*\((\d+)\s*(?:of\s*\d+)?\s*rows?\)", re.I)
_TIMESTAMP_RE   = re.compile(r'"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')
_ERROR_RE       = re.compile(r"^Error:", re.I | re.MULTILINE)
# Matches both "Computer": "value" and "\"Computer\"": "value" (CDB uses both)
_COMPUTER_RE    = re.compile(
    r'"(?:\\\")?Computer(?:\\\")?"\s*:\s*"([^"]+)"', re.I
)

# Thresholds (frozen from development audit — do not adjust after held-out run)
_HIGH_RELIABILITY_THRESHOLD = 0.88
_SPREAD_STRONG   = 0.40   # >= 40% rows from distinct hosts → strong_support
_SPREAD_WEAK     = 0.20   # >= 20% rows from distinct hosts → weak_support
_SPREAD_NEUTRAL  = 0.10   # >= 10% rows from distinct hosts → neutral


def map_observation(
    obs_text: str,
    *,
    source_reliability: float = 0.85,
    prior_row_count_same_source: Optional[float] = None,
) -> Tuple[str, int]:
    """Convert a CDB text observation to a 5-class obs_class.

    Parameters
    ----------
    obs_text : str
        Raw observation text returned by ThreatHuntEnv.step().
    source_reliability : float
        Estimated reliability of the source (used for zero-yield logic only).
    prior_row_count_same_source : float | None
        Reserved for future use (relative yield signal).

    Returns
    -------
    (obs_class, n_rows) : str, int
        obs_class is one of the 5 canonical classes.
        n_rows is the number of rows returned (0 on error or empty result).
    """
    # Error check first
    if _ERROR_RE.search(obs_text):
        return "strong_contra", 0

    # Extract row count
    m = _ROWS_SHOWN_RE.search(obs_text)
    if m:
        n_rows = int(m.group(1))
    else:
        # Fallback: count ISO-8601 timestamps
        n_rows = len(_TIMESTAMP_RE.findall(obs_text))

    # Zero rows
    if n_rows == 0:
        if source_reliability >= _HIGH_RELIABILITY_THRESHOLD:
            return "weak_contra", 0
        else:
            return "neutral", 0

    # ── Computer-spread feature ──────────────────────────────────────────────
    computers = _COMPUTER_RE.findall(obs_text)
    distinct_computers = len(set(computers))

    if distinct_computers == 0:
        # Computer field not present for this source (e.g., DNS only has QueryName)
        # Fall back: single-host heuristic → neutral
        return "neutral", n_rows

    spread = distinct_computers / n_rows

    # ── Classification ────────────────────────────────────────────────────────
    if spread >= _SPREAD_STRONG:
        return "strong_support", n_rows
    elif spread >= _SPREAD_WEAK:
        return "weak_support", n_rows
    elif spread >= _SPREAD_NEUTRAL:
        return "neutral", n_rows
    else:
        return "weak_contra", n_rows
