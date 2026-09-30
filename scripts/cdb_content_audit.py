"""scripts/cdb_content_audit.py
Connects to CDB once, runs each source query, extracts content features,
writes results to scripts/cdb_content_audit_result.txt
"""
import sys, re
from pathlib import Path

_CDB = Path(__file__).parent.parent.parent / "cdb"
sys.path.insert(0, str(_CDB))
sys.path.insert(0, str(Path(__file__).parent.parent))

from hades.benchmark.fast_db import patch_db
patch_db(cdb_path=_CDB)

from benchmark.gym import ThreatHuntEnv
from hades.query_menu import get_menu

FIELD_RE    = re.compile(r'"([^"]+)"\s*:\s*("(?:[^"\\]|\\.)*"|null|-?\d+(?:\.\d+)?)')
EVENT_ID_RE = re.compile(r'"EventID"\s*:\s*"(\d+)"')
ROWS_RE     = re.compile(r"Results\s*\((\d+)\s*(?:of\s*\d+)?\s*rows?\)", re.I)

DATA = _CDB / "datasets" / "sample.json"
env = ThreatHuntEnv(DATA, max_queries=50)
env.reset(seed=0)
menu = get_menu()

lines = []
lines.append("SOURCE                     ROWS  NULL  TOT  NULL%  EIDS  VARIETY  CLASS_v2")
lines.append("-" * 80)

for name, spec in menu.items():
    sql = spec.render(limit=10)
    obs, _, _, _, _ = env.step(sql)

    m = ROWS_RE.search(obs)
    n_rows = int(m.group(1)) if m else 0

    fields = FIELD_RE.findall(obs)
    n_null  = sum(1 for _, v in fields if v == "null")
    n_total = len(fields) if fields else 1
    null_rate = n_null / n_total

    event_ids = set(EVENT_ID_RE.findall(obs))
    variety   = len(event_ids)

    # v2 classification (replicated)
    if n_rows == 0:
        cls = "weak_contra" if spec.reliability_true >= 0.88 else "neutral"
    elif null_rate <= 0.15 and variety >= 3:
        cls = "strong_support"
    elif null_rate <= 0.30 and variety >= 2:
        cls = "weak_support"
    elif null_rate <= 0.50 or variety >= 2:
        cls = "neutral"
    else:
        cls = "weak_contra"

    lines.append(
        f"{name:25s}  {n_rows:>4}  {n_null:>4}  {n_total:>3}  "
        f"{100*null_rate:>4.0f}%  {','.join(sorted(event_ids)):<20}  {variety:>7}  {cls}"
    )

    # Print 1 row sample
    first_row = obs[:600].split("\n")[:6]
    for r_line in first_row:
        lines.append("    " + r_line[:120])
    lines.append("")

env.close()

out = Path(__file__).parent / "cdb_content_audit_result.txt"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Done. Results in {out}")
