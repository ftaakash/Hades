"""Mapper audit: analyze obs distribution from saved transfer gate JSON."""
import json
from collections import Counter, defaultdict

d = json.load(open("results/raw/5a_transfer_gate_v1.json", "r", encoding="utf-8"))

# 1. Obs class distribution
all_obs = []
rows_per_source = defaultdict(list)
for r in d["results"]:
    for t in r.get("per_turn", []):
        all_obs.append(t["obs_class"])
        rows_per_source[t["source"]].append(t["n_rows"])

print("=== 1. OBS CLASS DISTRIBUTION ===")
for cls, n in Counter(all_obs).most_common():
    pct = 100 * n / len(all_obs)
    print(f"  {cls:20} {n:>5} ({pct:.1f}%)")

print(f"\n=== 2. ROWS PER SOURCE (across all 60 episodes) ===")
for src in sorted(rows_per_source):
    rows = rows_per_source[src]
    mn = min(rows)
    mx = max(rows)
    avg = sum(rows) / len(rows)
    print(f"  {src:25} min={mn:>3} max={mx:>3} mean={avg:>5.1f} count={len(rows):>4}")

print(f"\n=== 3. n_rows HISTOGRAM (all turns) ===")
all_rows = [t["n_rows"] for r in d["results"] for t in r.get("per_turn", [])]
for val, cnt in sorted(Counter(all_rows).items()):
    bar = "#" * min(cnt, 60)
    print(f"  rows={val:>3}: {cnt:>5} {bar}")

print(f"\n=== 4. SOURCE SELECTION FREQUENCY PER POLICY ===")
pol_sources = defaultdict(lambda: Counter())
for r in d["results"]:
    for t in r.get("per_turn", []):
        pol_sources[r["model"]][t["source"]] += 1
for pol in sorted(pol_sources):
    print(f"  {pol}:")
    for src, cnt in pol_sources[pol].most_common():
        print(f"    {src:25} {cnt:>4}")

# 5. Exposure stats from first P3 episode
print(f"\n=== 5. SOURCE EXPOSURE STATS (first P3 episode) ===")
p3_first = [r for r in d["results"] if r["model"] == "p3_ig"][0]
for src, stats in p3_first.get("source_exposure_stats", {}).items():
    q = stats["queries"]
    tr = stats["total_rows"]
    mr = stats["mean_rows"]
    print(f"  {src:25} queries={q} total_rows={tr} mean_rows={mr:.1f}")

# 6. Key insight: what is the query_row_limit used?
print(f"\n=== 6. KEY INSIGHT ===")
print(f"  Total turns: {len(all_obs)}")
print(f"  All rows == 10: {sum(1 for r in all_rows if r == 10)} / {len(all_rows)}")
print(f"  All rows >= 8:  {sum(1 for r in all_rows if r >= 8)} / {len(all_rows)}")
print(f"  The mapper threshold is >= 8 -> strong_support")
print(f"  CDB query_row_limit = 10 (env.query_row_limit)")
print(f"  With 155k rows and LIMIT 10, every source saturates to 10 rows")
print(f"  -> every obs maps to strong_support -> T2 FAIL")
