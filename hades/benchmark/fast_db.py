"""hades/benchmark/fast_db.py — Batch-insert helper for CDB's ThreatHuntEnv.

CDB's default ThreatHuntEnv.reset() inserts 155,350 rows one at a time
via cursor.execute() in a Python loop, taking ~28 seconds per reset. This
is unusable for multi-seed sweeps.

This module monkey-patches LogDatabase.insert() to use executemany() with
configurable batch sizes, reducing reset time from ~28s to <1s.

Usage
-----
from hades.benchmark.fast_db import patch_db
patch_db()  # call once at top of script, before any ThreatHuntEnv is created

import sys; sys.path.insert(0, str(cdb_path))
from benchmark.gym import ThreatHuntEnv
env = ThreatHuntEnv(data_path, max_queries=20)
env.reset()  # now fast (~0.3s for 155k rows)

How it works
------------
LogDatabase.insert() currently does:
    for log in logs:
        cursor.execute(INSERT, values(log))

We replace it with:
    cursor.executemany(INSERT, [values(log) for log in logs])

in batches of BATCH_SIZE to stay within SQLite's variable limit.

Note: patch_db() is idempotent — calling it multiple times is safe.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

BATCH_SIZE: int = 5000  # SQLite variable limit is 32766; 5000 is safe

_PATCHED: bool = False


def _fast_insert(self: Any, logs: List[Dict[str, Any]]) -> None:
    """Replacement for LogDatabase.insert() using executemany."""
    if not logs:
        return

    # CDB LogDatabase uses .conn (public); guard for both conventions
    connection = getattr(self, "conn", None) or getattr(self, "_conn", None)
    if connection is None:
        raise AttributeError("LogDatabase has neither .conn nor ._conn")

    # Derive column names from first row (same as original)
    first = logs[0]
    cols = list(first.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(f'"{c}"' for c in cols)
    sql = f"INSERT OR IGNORE INTO logs ({col_names}) VALUES ({placeholders})"

    cursor = connection.cursor()
    # Batch to avoid SQLite variable limits and keep memory low
    for start in range(0, len(logs), BATCH_SIZE):
        batch = logs[start : start + BATCH_SIZE]
        rows = [[row.get(c) for c in cols] for row in batch]
        cursor.executemany(sql, rows)
    connection.commit()


def patch_db(cdb_path: Optional[Path] = None) -> bool:
    """Monkey-patch LogDatabase.insert() to use executemany.

    Parameters
    ----------
    cdb_path : Path | None
        Path to the ../cdb directory. If None, assumes CDB is already on
        sys.path.

    Returns
    -------
    bool : True if patch was applied, False if already patched.
    """
    global _PATCHED
    if _PATCHED:
        return False

    if cdb_path is not None:
        cdb_str = str(cdb_path)
        if cdb_str not in sys.path:
            sys.path.insert(0, cdb_str)

    try:
        db_module = importlib.import_module("benchmark.db")
        LogDatabase = getattr(db_module, "LogDatabase", None)
        if LogDatabase is None:
            return False
        LogDatabase.insert = _fast_insert
        _PATCHED = True
        return True
    except ImportError:
        return False


def is_patched() -> bool:
    return _PATCHED
