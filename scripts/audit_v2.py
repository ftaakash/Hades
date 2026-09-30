"""Quick v3 regression audit."""
import json
from collections import Counter, defaultdict

d = json.load(open("results/raw/5a1_regression_v3.json", "r", encoding="utf-8"))

print("=== GATES ===")
for k, v in d["gates"].items():
    print(f"  {k:45} {v}")

print("\n=== OBS CLASS DISTRIBUTION ===")
all_obs = []
computers_seen = []
for r in d["results"]:
    for t in r.get("per_turn", []):
        all_obs.append(t["obs_class"])
for cls, n in Counter(all_obs).most_common():
    print(f"  {cls:20} {n:>5} ({100*n/len(all_obs):.1f}%)")

print(f"\n=== COVERAGE ===")
by_pol = defaultdict(list)
for s in d["scored"]:
    by_pol[s["model"]].append(s.get("coverage_score_per_run", 0) or 0)
for pol, covs in sorted(by_pol.items()):
    nz = sum(1 for c in covs if c > 0)
    print(f"  {pol:25} avg={sum(covs)/len(covs):.4f}  nonzero={nz}/{len(covs)}")
