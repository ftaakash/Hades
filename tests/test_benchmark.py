"""tests/test_benchmark.py — Unit tests for hades/benchmark/*.

These tests run WITHOUT the CDB (no ThreatHuntEnv, no SQLite).
They test the benchmark bridge components in isolation:
  - obs_mapper: yield → obs_class mapping
  - candidate_extractor: timestamp extraction + per-source stats
  - fast_db: patch detection (no DB needed)
  - harness: policy registry completeness

Tests that require a live CDB environment are in scripts/run_transfer_gate.py
and are tagged as integration-level.
"""
from __future__ import annotations

import pytest
from hades.benchmark.obs_mapper import map_observation, OBS_MAPPER_VERSION
from hades.benchmark.candidate_extractor import CandidateExtractor
from hades.benchmark.fast_db import is_patched


# ---------------------------------------------------------------------------
# Fixtures for v2 content-feature mapper
# ---------------------------------------------------------------------------

def _make_obs(
    n_rows: int,
    error: bool = False,
    null_rate: float = 0.0,
    event_ids: tuple = ("4624",),
) -> str:
    """Simulate CDB observation text with controllable content features.

    v2 mapper uses null_rate + EventID variety, so fixtures must control these.
    """
    if error:
        return "Error: SyntaxError: no such column: BadCol"
    if n_rows == 0:
        return "Results (0 rows):\n[]"

    rows = []
    n_eids = len(event_ids)
    for i in range(n_rows):
        eid = event_ids[i % n_eids]
        # Control null_rate by making some fields null
        if null_rate > 0 and (i / n_rows) < null_rate:
            rows.append(
                f'  {{"TimeCreated": "2024-01-01T12:00:{i:02d}Z", '
                f'"EventID": "{eid}", '
                f'"Computer": null, "AccountName": null, "IpAddress": null}}'
            )
        else:
            rows.append(
                f'  {{"TimeCreated": "2024-01-01T12:00:{i:02d}Z", '
                f'"EventID": "{eid}", '
                f'"Computer": "DC01.corp.local", '
                f'"AccountName": "admin", '
                f'"IpAddress": "10.0.0.{i+1}"}}'
            )
    ts_block = "\n".join(rows)
    return f"Results ({n_rows} rows):\n[{ts_block}]"


def _make_rich_obs(n_rows: int) -> str:
    """Rich observation: low null rate, diverse EventIDs → strong_support."""
    return _make_obs(n_rows, null_rate=0.0, event_ids=("4624", "4625", "4634"))


def _make_moderate_obs(n_rows: int) -> str:
    """Moderate obs: low null rate, 2 EventIDs → weak_support."""
    return _make_obs(n_rows, null_rate=0.10, event_ids=("4624", "4625"))


def _make_sparse_obs(n_rows: int) -> str:
    """Sparse obs: all null fields, single EventID → weak_contra."""
    return _make_obs(n_rows, null_rate=1.0, event_ids=("4624",))


MENU_STUB = {
    "auth_events": type("Spec", (), {"reliability_true": 0.95, "cost": 1.0,
                                      "event_ids": ("4624",)})(),
    "network_events": type("Spec", (), {"reliability_true": 0.85, "cost": 1.5,
                                         "event_ids": ("3",)})(),
    "object_access_events": type("Spec", (), {"reliability_true": 0.75, "cost": 2.0,
                                               "event_ids": ("4656",)})(),
}


# ---------------------------------------------------------------------------
# ObsMapper tests (v2: content features)
# ---------------------------------------------------------------------------

class TestObsMapper:
    def test_version_is_v2(self):
        assert OBS_MAPPER_VERSION == "v2.0"

    def test_rich_obs_is_strong_support(self):
        """Low null rate + 3 distinct EventIDs → strong_support."""
        obs, n = map_observation(_make_rich_obs(10), source_reliability=0.90)
        assert obs == "strong_support"
        assert n == 10

    def test_moderate_obs_is_weak_support(self):
        """Low null rate + 2 EventIDs → weak_support."""
        obs, n = map_observation(_make_moderate_obs(10), source_reliability=0.90)
        assert obs == "weak_support"
        assert n == 10

    def test_sparse_obs_is_weak_contra(self):
        """High null rate + 1 EventID → weak_contra."""
        obs, n = map_observation(_make_sparse_obs(10), source_reliability=0.90)
        assert obs == "weak_contra"
        assert n == 10

    def test_zero_yield_high_reliability_is_weak_contra(self):
        obs, n = map_observation(_make_obs(0), source_reliability=0.95)
        assert obs == "weak_contra"
        assert n == 0

    def test_zero_yield_low_reliability_is_neutral(self):
        obs, n = map_observation(_make_obs(0), source_reliability=0.60)
        assert obs == "neutral"
        assert n == 0

    def test_error_is_strong_contra(self):
        obs, n = map_observation(_make_obs(0, error=True))
        assert obs == "strong_contra"
        assert n == 0

    def test_all_returned_classes_are_valid(self):
        from hades.corruption.base import OBS_CLASSES
        test_obs = [
            _make_rich_obs(10),
            _make_moderate_obs(10),
            _make_sparse_obs(10),
            _make_obs(0),
            _make_obs(0, error=True),
            # single EventID, moderate nulls → neutral
            _make_obs(5, null_rate=0.40, event_ids=("4624", "4625")),
        ]
        for ob in test_obs:
            cls, _ = map_observation(ob, source_reliability=0.90)
            assert cls in OBS_CLASSES, f"Invalid class: {cls}"

    def test_content_features_matter_not_row_count(self):
        """v2 invariant: same row count, different content → different class."""
        rich = map_observation(_make_rich_obs(10))[0]
        sparse = map_observation(_make_sparse_obs(10))[0]
        assert rich != sparse, "Mapper must distinguish by content, not just rows"


# ---------------------------------------------------------------------------
# CandidateExtractor tests
# ---------------------------------------------------------------------------

class TestCandidateExtractor:
    def _real_obs(self, n: int, base_minute: int = 0) -> str:
        """Obs text with real ISO-8601 timestamps and realistic fields."""
        rows = "\n".join(
            f'{{"TimeCreated": "2024-03-15T10:{base_minute:02d}:{i:02d}Z", '
            f'"EventID": "4624", '
            f'"Computer": "DC01", "AccountName": "user{i}"}}'
            for i in range(n)
        )
        return f"Results ({n} rows):\n[{rows}]"

    def test_extracts_timestamps_from_obs(self):
        ex = CandidateExtractor(MENU_STUB)
        obs_class, n_rows, new_ts = ex.process("auth_events", self._real_obs(3))
        assert len(new_ts) == 3
        assert n_rows == 3
        # With single EventID and low null → neutral or weak_contra
        assert obs_class in ("neutral", "weak_contra", "weak_support", "strong_support")

    def test_deduplicates_repeated_timestamps(self):
        ex = CandidateExtractor(MENU_STUB)
        ex.process("auth_events", self._real_obs(3, base_minute=0))
        _, _, new_ts2 = ex.process("auth_events", self._real_obs(3, base_minute=0))
        assert len(new_ts2) == 0

    def test_accumulates_across_sources(self):
        ex = CandidateExtractor(MENU_STUB)
        ex.process("auth_events", self._real_obs(3, base_minute=0))
        ex.process("network_events", self._real_obs(3, base_minute=1))
        assert ex.n_candidates() == 6

    def test_all_candidates_sorted(self):
        ex = CandidateExtractor(MENU_STUB)
        ex.process("auth_events", self._real_obs(5, base_minute=5))
        ex.process("network_events", self._real_obs(3, base_minute=2))
        candidates = ex.all_candidates()
        assert candidates == sorted(candidates)

    def test_source_yield_stats(self):
        ex = CandidateExtractor(MENU_STUB)
        ex.process("auth_events", self._real_obs(8))
        ex.process("auth_events", self._real_obs(4))
        stats = ex.source_yield_stats()
        assert "auth_events" in stats
        assert stats["auth_events"]["queries"] == 2
        assert stats["auth_events"]["total_rows"] == 12

    def test_uses_source_reliability_for_mapping(self):
        """High-reliability source (auth_events, 0.95) with 0 rows → weak_contra."""
        ex = CandidateExtractor(MENU_STUB)
        obs_class, _, _ = ex.process("auth_events", _make_obs(0))
        assert obs_class == "weak_contra"

    def test_empty_episode(self):
        ex = CandidateExtractor(MENU_STUB)
        assert ex.n_candidates() == 0
        assert ex.all_candidates() == []



# ---------------------------------------------------------------------------
# FastDB tests (no CDB required)
# ---------------------------------------------------------------------------

class TestFastDB:
    def test_is_patched_returns_bool(self):
        result = is_patched()
        assert isinstance(result, bool)

    def test_patch_db_returns_bool(self):
        from hades.benchmark.fast_db import patch_db
        # patch_db always returns a bool (True=patched, False=already patched or failed)
        result = patch_db()
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Harness policy registry test (no CDB required)
# ---------------------------------------------------------------------------

class TestHarnessRegistry:
    def test_all_expected_policies_registered(self):
        from hades.harness import _build_policy_registry
        reg = _build_policy_registry()
        expected = {
            "random", "fixed_heuristic", "p2_relevance",
            "p3_ig", "p4_ig_cost", "p4b_ig_cost_rel",
            "p5_robust_voi", "p7_bayes_al",
        }
        assert expected == set(reg.keys())

    def test_all_registered_policies_have_select_query(self):
        from hades.harness import _build_policy_registry
        for name, policy in _build_policy_registry().items():
            assert hasattr(policy, "select_query"), f"{name} missing select_query"
            assert callable(policy.select_query)

    def test_invalid_policy_name_raises(self):
        import sys
        from pathlib import Path
        # We import run() from harness and mock env
        from hades.harness import run as harness_run
        import types as t
        env = t.SimpleNamespace(
            reset=lambda **kw: ("briefing", {}),
            step=lambda sql: ("obs", 0.0, False, False, {}),
            query_row_limit=10,
        )
        with pytest.raises(ValueError, match="Unknown policy"):
            harness_run(env, model="nonexistent_policy", max_queries=2)


# ---------------------------------------------------------------------------
# Hypothesis affinity coverage test
# ---------------------------------------------------------------------------

class TestCDBHypotheses:
    def test_all_sources_have_affinity_entries(self):
        from hades.harness import _SOURCE_AFFINITY, HADES_PROXY_HYPOTHESES
        menu_names = [
            "auth_events", "process_events", "network_events",
            "dns_events", "persistence_events",
            "powershell_events", "object_access_events",
        ]
        for src in menu_names:
            assert src in _SOURCE_AFFINITY, f"Missing affinity for {src}"
            for hyp in HADES_PROXY_HYPOTHESES:
                assert hyp in _SOURCE_AFFINITY[src], (
                    f"Missing hypothesis {hyp} in affinity of {src}"
                )
                val = _SOURCE_AFFINITY[src][hyp]
                assert 0.0 <= val <= 1.0, f"{src}[{hyp}]={val} out of [0,1]"

    def test_proxy_hypotheses_are_7(self):
        from hades.harness import HADES_PROXY_HYPOTHESES, HADES_PROXY_EXCLUDED
        assert len(HADES_PROXY_HYPOTHESES) == 7
        assert "TA0007" in HADES_PROXY_EXCLUDED

    def test_old_name_not_exported(self):
        import hades.harness as h
        assert not hasattr(h, "CDB_HYPOTHESES"), (
            "CDB_HYPOTHESES should not be exported; use HADES_PROXY_HYPOTHESES"
        )
