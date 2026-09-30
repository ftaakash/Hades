"""scripts/cdb_raw_obs.py — Print full raw observation for one source."""
import sys, re
from pathlib import Path

_CDB = Path(__file__).parent.parent.parent / "cdb"
sys.path.insert(0, str(_CDB))
sys.path.insert(0, str(Path(__file__).parent.parent))

from hades.benchmark.fast_db import patch_db
patch_db(cdb_path=_CDB)
from benchmark.gym import ThreatHuntEnv
from hades.query_menu import get_menu

DATA = _CDB / "datasets" / "sample.json"
env  = ThreatHuntEnv(DATA, max_queries=10)
env.reset(seed=0)
menu = get_menu()

out_lines = []
# Just auth_events — get first 600 chars of raw obs
spec = menu["auth_events"]
sql  = spec.render(limit=5)
obs, _, _, _, _ = env.step(sql)
env.close()

out_lines.append("=== RAW OBS (auth_events, limit=5) ===")
out_lines.append(obs[:2000])
out_lines.append("")

# Also check regex match
COMPUTER_RE = re.compile(r'"(?:\\\")?Computer(?:\\\")?"\s*:\s*"([^"]+)"', re.I)
computers = COMPUTER_RE.findall(obs)
out_lines.append(f"=== _COMPUTER_RE matches: {computers} ===")

# Try alternative patterns
for pat in [
    r'"Computer"\s*:\s*"([^"]+)"',
    r'Computer["\s:]+([A-Za-z0-9\-_\.]+)',
    r'"([A-Za-z0-9\-_\.]+\.(?:local|corp|domain|int))"',
]:
    found = re.findall(pat, obs, re.I)
    out_lines.append(f"  pat={pat[:50]!r}: {found}")

out = Path(__file__).parent / "cdb_raw_obs_result.txt"
out.write_text("\n".join(out_lines), encoding="utf-8")
print(f"Done → {out}")
