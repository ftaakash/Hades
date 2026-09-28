"""hades/benchmark/candidate_extractor.py — CDB candidate timestamp extractor.

Extracts ISO-8601 timestamps from CDB text observations and classifies
them as candidate event times to submit to the scorer.

Also provides the per-turn belief update hook: after each SQL observation,
the CandidateExtractor maps the observation to an obs_class (via obs_mapper),
updates the running row-count for that source, and returns structured data
the harness uses to:
  1. Update beliefs (via SimEnv-equivalent Bayesian update on CDB sources).
  2. Accumulate submitted_timestamps.
  3. Record per_turn n_new_submitted for the scorer's per-turn trace.

No leakage guarantee
--------------------
The extractor never reads ground-truth flags. It only sees the SQL
observation text returned by env.step(). The obs_class it produces is a
purely structural signal (row yield), not a semantic match against known
malicious events. This is intentional: the HADES policy doesn't get to
cheat by reading attack-specific patterns.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from hades.benchmark.obs_mapper import map_observation

# ISO-8601 UTC timestamp pattern (matches CDB's TimeCreated format)
_TS_RE = re.compile(
    r'"?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)"?'
)


class CandidateExtractor:
    """Stateful extractor for one CDB episode.

    Tracks all candidate timestamps seen and maintains per-source yield
    statistics for the obs_mapper's adaptive threshold.

    Usage
    -----
    extractor = CandidateExtractor(menu)
    for each turn:
        obs_class, n_rows, new_timestamps = extractor.process(source_name, obs_text)
        # use obs_class for belief update
        # extend submitted_timestamps with new_timestamps
    submitted = extractor.all_candidates()
    """

    def __init__(self, menu: Dict) -> None:
        """
        Parameters
        ----------
        menu : {name: QuerySpec}
            The canonical query menu from hades.query_menu.
        """
        self._menu = menu
        self._all_timestamps: Set[str] = set()
        self._per_source_rows: Dict[str, List[int]] = defaultdict(list)

    def process(
        self,
        source_name: str,
        obs_text: str,
    ) -> Tuple[str, int, List[str]]:
        """Process one CDB step observation.

        Parameters
        ----------
        source_name : str
            The HADES evidence source that was queried.
        obs_text : str
            Raw text observation from ThreatHuntEnv.step().

        Returns
        -------
        (obs_class, n_rows, new_timestamps) : str, int, list[str]
            obs_class   — 5-class canonical observation
            n_rows      — number of rows returned
            new_timestamps — new ISO-8601 timestamps not seen before
        """
        spec = self._menu.get(source_name)
        reliability = spec.reliability_true if spec else 0.85

        # Compute rolling prior for this source
        prior_rows = self._per_source_rows[source_name]
        prior_mean = (sum(prior_rows) / len(prior_rows)) if prior_rows else None

        obs_class, n_rows = map_observation(
            obs_text,
            source_reliability=reliability,
            prior_row_count_same_source=prior_mean,
        )
        self._per_source_rows[source_name].append(n_rows)

        # Extract new timestamps
        found = _TS_RE.findall(obs_text)
        new_ts = [ts for ts in found if ts not in self._all_timestamps]
        self._all_timestamps.update(new_ts)

        return obs_class, n_rows, new_ts

    def all_candidates(self) -> List[str]:
        """Return all candidate timestamps seen so far, sorted."""
        return sorted(self._all_timestamps)

    def n_candidates(self) -> int:
        return len(self._all_timestamps)

    def source_yield_stats(self) -> Dict[str, Dict]:
        """Return per-source yield statistics for diagnostics."""
        stats = {}
        for src, counts in self._per_source_rows.items():
            if counts:
                stats[src] = {
                    "queries": len(counts),
                    "total_rows": sum(counts),
                    "mean_rows": sum(counts) / len(counts),
                    "max_rows": max(counts),
                }
        return stats
