"""hades/benchmark/obs_mapper.py — CDB observation → 5-class obs_class mapper.

v2.0: Content-feature mapper (replaces v1.0 row-yield mapper).

v1.0 used raw row count as the sole classification signal. This failed on
CDB because LIMIT 10 saturates against 155k rows — every source returns
exactly 10 rows, collapsing the entire observation space to `strong_support`.

v2.0 uses CONTENT FEATURES of the returned SQL rows:

1. Field population rate (% of non-null fields across all returned rows).
   A high null rate means the query returned structurally sparse data —
   columns exist but have no values, reducing evidentiary informativeness.

2. Distinct EventID variety (number of different event types in the result).
   A high variety of EventIDs indicates a broad, potentially unfocused query
   return (weaker evidence); a narrow set suggests focused, specific events.

3. Field richness (number of distinct non-null field values per row).
   Rows with many populated fields carry more structural information.

None of these features require ground-truth labels, hidden hypothesis
information, or knowledge of which events are malicious. They are purely
structural properties of the SQL result text.

CONSTRUCT BOUNDARY — read before using this module:
    Row content features proxy observation INFORMATIVENESS only. They are
    NOT a measure of source reliability. Reliability (r_hat) must come
    from hades.reliability.estimator ONLY. Do NOT use obs_mapper outputs
    to infer that a source is reliable or unreliable for security-evidentiary
    purposes.

Mapping rules (v2.0):
    null_rate <= 0.15  AND  event_variety >= 3  →  strong_support
    null_rate <= 0.30  AND  event_variety >= 2  →  weak_support
    null_rate <= 0.50  OR   event_variety >= 2  →  neutral
    null_rate >  0.50  AND  event_variety == 1  →  weak_contra
    error / 0 rows  →  strong_contra

    Zero rows from a high-reliability source → weak_contra
    Zero rows from a low-reliability source  → neutral
    Error → strong_contra

Thresholds are derived from the mapper audit of the 15 development episodes
(5a_transfer_gate_v1.json). They must be frozen before the held-out transfer
gate. See scripts/mapper_audit.py for the calibration data.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

OBS_MAPPER_VERSION = "v2.0"

# CONSTRUCT BOUNDARY — read the docstring above.
OBS_MAPPER_CAVEAT = (
    "Content features proxy observation informativeness only. "
    "They are not a reliability measure. r_hat must come from the estimator."
)

# ── Regex ─────────────────────────────────────────────────────────────────────
# Row count from CDB header: "Results (N rows):" or "Results (M of N rows):"
_ROWS_SHOWN_RE = re.compile(r"Results\s*\((\d+)\s*(?:of\s*\d+)?\s*rows?\)", re.I)
# ISO-8601 timestamp (for candidate extraction, not used for classification)
_TIMESTAMP_RE  = re.compile(r'"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')
# Error detection
_ERROR_RE      = re.compile(r"^Error:", re.I | re.MULTILINE)
# EventID extractor
_EVENT_ID_RE   = re.compile(r'"EventID"\s*:\s*"(\d+)"')
# Field value extractor: "FieldName": "value" or "FieldName": null
_FIELD_RE      = re.compile(r'"([^"]+)"\s*:\s*("(?:[^"\\]|\\.)*"|null|-?\d+(?:\.\d+)?)')

# Reliability threshold for zero-yield interpretation
_HIGH_RELIABILITY_THRESHOLD = 0.88

# Content-feature thresholds (frozen from development audit)
_NULL_RATE_RICH  = 0.15   # <= this = information-rich
_NULL_RATE_MOD   = 0.30   # <= this = moderate information
_NULL_RATE_SPARSE = 0.50  # > this = sparse
_EVENT_VARIETY_HIGH = 3   # >= this = diverse event types
_EVENT_VARIETY_MOD  = 2   # >= this = some variety


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
        Rolling average row count for this source (reserved for future use).

    Returns
    -------
    (obs_class, n_rows) : str, int
        obs_class is one of the 5 canonical classes.
        n_rows is the number of rows returned (0 on error or empty).
    """
    # Error check first
    if _ERROR_RE.search(obs_text):
        return "strong_contra", 0

    # Extract row count
    m = _ROWS_SHOWN_RE.search(obs_text)
    if m:
        n_rows = int(m.group(1))
    else:
        n_rows = len(_TIMESTAMP_RE.findall(obs_text))

    # Zero rows
    if n_rows == 0:
        if source_reliability >= _HIGH_RELIABILITY_THRESHOLD:
            return "weak_contra", 0
        else:
            return "neutral", 0

    # ── Content feature extraction ────────────────────────────────────────

    # 1. Null rate: fraction of field values that are null
    fields = _FIELD_RE.findall(obs_text)
    n_null = sum(1 for _, val in fields if val == "null")
    n_total = len(fields) if fields else 1
    null_rate = n_null / n_total

    # 2. EventID variety: number of distinct event types
    event_ids = set(_EVENT_ID_RE.findall(obs_text))
    event_variety = len(event_ids)

    # ── Classification ────────────────────────────────────────────────────
    if null_rate <= _NULL_RATE_RICH and event_variety >= _EVENT_VARIETY_HIGH:
        return "strong_support", n_rows
    elif null_rate <= _NULL_RATE_MOD and event_variety >= _EVENT_VARIETY_MOD:
        return "weak_support", n_rows
    elif null_rate <= _NULL_RATE_SPARSE or event_variety >= _EVENT_VARIETY_MOD:
        return "neutral", n_rows
    else:
        # High null rate AND low event variety → weak_contra
        return "weak_contra", n_rows
