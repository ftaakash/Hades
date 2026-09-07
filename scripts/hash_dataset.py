"""
scripts/hash_dataset.py
-----------------------
Compute SHA-256 checksums of the CDB dataset files and write them into
data_manifest/benchmark_lock.json so the benchmark identity is pinned.

Usage (from repo root, with CDB sibling directory cloned):
    python scripts/hash_dataset.py [--cdb-root ../cdb]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "data_manifest" / "benchmark_lock.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit(repo: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "UNKNOWN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Hash CDB dataset and update benchmark_lock.json")
    parser.add_argument("--cdb-root", default="../cdb", help="Path to CDB repository")
    args = parser.parse_args()

    cdb_root = (REPO_ROOT / args.cdb_root).resolve()
    if not cdb_root.exists():
        print(f"[ERROR] CDB not found at {cdb_root}. Clone it first:", file=sys.stderr)
        print(f"  git clone https://github.com/simbianai/cyber_defense_benchmark.git {cdb_root}", file=sys.stderr)
        sys.exit(1)

    sample = cdb_root / "datasets" / "sample.json"
    flags = cdb_root / "datasets" / "sample_flags.json"

    for f in (sample, flags):
        if not f.exists():
            print(f"[ERROR] Dataset file not found: {f}", file=sys.stderr)
            sys.exit(1)

    print("Computing checksums…")
    sha_sample = sha256_file(sample)
    sha_flags = sha256_file(flags)
    cdb_commit = git_commit(cdb_root)

    # Update benchmark_lock.json
    with MANIFEST_PATH.open() as f:
        lock = json.load(f)

    lock["cdb"]["git_commit"] = cdb_commit
    lock["dataset"]["sha256_sample"] = sha_sample
    lock["dataset"]["sha256_flags"] = sha_flags
    lock["hades_git_commit"] = git_commit(REPO_ROOT)

    with MANIFEST_PATH.open("w") as f:
        json.dump(lock, f, indent=2)

    print(f"  CDB commit   : {cdb_commit}")
    print(f"  sample.json  : {sha_sample}")
    print(f"  sample_flags : {sha_flags}")
    print(f"\nUpdated {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
