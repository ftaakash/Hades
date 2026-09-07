"""
scripts/run_smoke.py
--------------------
One-command smoke test: verifies the full pipeline works end-to-end.

Usage (from repo root):
    PYTHONPATH=.;../cdb python scripts/run_smoke.py

Expected output: "SMOKE TEST PASSED" if all checks clear, or specific
failure messages indicating what needs fixing.

This is intentionally minimal — it does NOT run long sweeps or require
CDB to be installed. It validates the importable HADES package, the menu,
and the policy interface.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def check_imports() -> None:
    """Verify all HADES modules import cleanly."""
    print("  [1/5] Checking imports…")
    from hades.query_menu import get_menu
    from hades.policies.base import InvestigationState, Policy
    from hades.policies.random_policy import RandomPolicy
    from hades.policies.fixed_heuristic import FixedHeuristicPolicy
    print("        OK — hades.query_menu, policies importable")


def check_query_menu() -> None:
    """Verify the query menu is sane."""
    print("  [2/5] Checking query menu…")
    from hades.query_menu import get_menu
    menu = get_menu()
    assert len(menu) == 7, f"Expected 7 sources, got {len(menu)}"
    for name, spec in menu.items():
        assert spec.cost > 0, f"{name}: cost must be > 0"
        assert 0 < spec.reliability_true <= 1, f"{name}: reliability_true out of range"
        assert len(spec.event_ids) > 0, f"{name}: must have event_ids"
        sql = spec.render(limit=5)
        assert "LIMIT 5" in sql, f"{name}: LIMIT not rendered correctly"
    print(f"        OK — {len(menu)} sources, all fields valid")


def check_policies_basic() -> None:
    """Verify P0 and P1 produce valid selections on a dummy state."""
    print("  [3/5] Checking P0/P1 policy interface…")
    from hades.query_menu import get_menu
    from hades.policies.base import InvestigationState
    from hades.policies.random_policy import RandomPolicy
    from hades.policies.fixed_heuristic import FixedHeuristicPolicy

    menu = get_menu()

    # P0 — should always pick a valid key when budget > 0
    p0 = RandomPolicy(seed=42)
    state = InvestigationState(remaining_budget=5)
    selection = p0.select_query(state, menu)
    assert selection in menu, f"P0 returned unknown key: {selection!r}"

    # P0 — should return None when budget == 0
    state_empty = InvestigationState(remaining_budget=0)
    assert p0.select_query(state_empty, menu) is None, "P0 should stop at budget=0"

    # P1 — deterministic
    p1 = FixedHeuristicPolicy()
    sel1 = p1.select_query(state, menu)
    assert sel1 in menu, f"P1 returned unknown key: {sel1!r}"

    print(f"        OK — P0→{selection!r}, P1→{sel1!r}")


def check_harness_dry_run() -> None:
    """Verify harness imports and POLICY_REGISTRY is wired."""
    print("  [4/5] Checking harness & policy registry…")
    from hades.harness import POLICY_REGISTRY, run
    assert "random" in POLICY_REGISTRY
    assert "fixed_heuristic" in POLICY_REGISTRY
    print(f"        OK — registry: {list(POLICY_REGISTRY)}")


def check_baseline_results_integrity() -> None:
    """Verify the committed baseline results file is intact."""
    print("  [5/5] Checking baseline_results.json integrity…")
    import json
    p = REPO_ROOT / "baseline_results.json"
    assert p.exists(), "baseline_results.json missing"
    with p.open() as f:
        r = json.load(f)
    assert "random" in r and "fixed_heuristic" in r
    p1_cov = r["fixed_heuristic"]["20"][0]
    p0_mean = sum(r["random"]["20"]) / len(r["random"]["20"])
    print(f"        OK — P1={p1_cov:.4f}, P0_mean={p0_mean:.4f}")


def main() -> None:
    print("\nHADES Smoke Test")
    print("=" * 40)
    try:
        check_imports()
        check_query_menu()
        check_policies_basic()
        check_harness_dry_run()
        check_baseline_results_integrity()
        print("=" * 40)
        print("SMOKE TEST PASSED\n")
    except Exception as exc:
        print(f"\n[FAIL] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
