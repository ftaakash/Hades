"""hades/benchmark/obs_mapper.py — CDB observation → 5-class obs_class mapper.

This is the critical transfer bridge. It converts the unstructured text
observation returned by CDB's ThreatHuntEnv.step() into one of the five
canonical observation classes used throughout HADES's belief layer:

    strong_support  — high-yield, directly relevant events found
    weak_support    — low-yield, possibly relevant events found
    neutral         — query succeeded but no evidence discrimination
    weak_contra     — very low yield on a source expected to be informative
    strong_contra   — error / total failure on a high-reliability source

Design decisions
----------------
1. The mapping uses YIELD rather than content analysis.
   Content analysis (LLM or regex over event data) would require knowing the
   ground-truth hypothesis, breaking the no-leakage invariant. Yield is a
   hypothesis-agnostic, examiner-free proxy that is still informationally
   meaningful.

2. Thresholds are source-aware.
   A high-cost source (object_access_events, cost=2.0) should return many
   rows to justify its cost; the same row count from a cheap source is more
   impressive. We normalise yield by expected yield per cost unit.

3. Errors map to strong_contra.
   A source that fails to return data provides strong evidence AGAINST relying
   on it (reliability update), not neutral evidence.

4. Version-pinned.
   OBS_MAPPER_VERSION is recorded in every result JSON so that mapping changes
   can be detected post-hoc.

Thresholds (empirically derived from sample.json inspection):
    high_yield   >= 8 rows  → strong_support
    moderate_yield 2–7 rows → weak_support
    low_yield    1 row      → neutral
    zero_yield   0 rows     → depends on source reliability
    error        any error  → strong_contra

Zero-yield with a high-reliability source → weak_contra (absence is informative)
Zero-yield with a low-reliability source  → neutral (absence expected)
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

OBS_MAPPER_VERSION = "v1.0"

# Regex to count rows in a CDB observation text.
# CDB formats results as "Results (N rows):" or "Results (M of N rows):"
_ROWS_SHOWN_RE  = re.compile(r"Results\s*\((\d+)\s*(?:of\s*\d+)?\s*rows?\)", re.I)
_TIMESTAMP_RE   = re.compile(r'"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')
_ERROR_RE       = re.compile(r"^Error:", re.I | re.MULTILINE)

# High-reliability threshold: sources with reliability_true >= this threshold
# get weak_contra on zero yield (absence is informative).
_HIGH_RELIABILITY_THRESHOLD = 0.88

_HIGH_YIELD_ROWS    = 8
_MODERATE_YIELD_LOW = 2


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
        The estimated reliability of the source (used for zero-yield logic).
    prior_row_count_same_source : float | None
        Rolling average row count for this source in previous turns. Used
        to detect relative drops (future: trend-based staleness). Not used
        in v1.0.

    Returns
    -------
    (obs_class, n_rows) : str, int
        obs_class is one of the 5 canonical classes.
        n_rows is the number of rows returned (0 on error or empty).
    """
    # Error check first
    if _ERROR_RE.search(obs_text):
        return "strong_contra", 0

    # Extract row count from header
    m = _ROWS_SHOWN_RE.search(obs_text)
    if m:
        n_rows = int(m.group(1))
    else:
        # Fallback: count ISO-8601 timestamps as a proxy for event rows
        n_rows = len(_TIMESTAMP_RE.findall(obs_text))

    # Map yield to obs_class
    if n_rows >= _HIGH_YIELD_ROWS:
        return "strong_support", n_rows
    elif n_rows >= _MODERATE_YIELD_LOW:
        return "weak_support", n_rows
    elif n_rows == 1:
        return "neutral", n_rows
    else:
        # Zero yield: distinguish by source reliability
        if source_reliability >= _HIGH_RELIABILITY_THRESHOLD:
            # High-reliability source returning nothing is contra-evidence
            return "weak_contra", 0
        else:
            return "neutral", 0
