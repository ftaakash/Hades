"""
hades/probe_experiment/hai.py
-----------------------------
Phase 7V: real-data replication of the 7U joint-belief result on the HAI industrial-control security
dataset (docs/phase7v_hai_replication_protocol.md).

Mapping (fixed before any confirmatory data were processed; designed on HAI 20.07 only):

  Episode       one attack segment (contiguous attack==1 rows) or a sampled attack-free window.
  Hypothesis    0 NORMAL, 1 attack confined to process P1, 2 attack touching P2 or P3.
  Sources       nine process points (SOURCES). A query of source q returns a cheap per-sensor
                alarm computed from q's own stream only: the change of its 30 s sub-window mean
                from a pre-onset reference, scaled by its train-data distribution. An alarm reports
                the source's process class (1 for P1 points, 2 for P2/P3 points), else 0.
  Compromise    a PV the attacker holds at its previous value ("stale-value spoofing", from the
                HAI manual; configs/data/hai_attack_metadata.json). Its own-stream alarm stays quiet:
                a real cover-up.
  Probe         an integrity cross-check of source q against the other points of its process: the
                residual of a ridge regression fitted on attack-free train data. FAIL when the
                sub-window residual exceeds its train 99th percentile.

The k-th query (probe) of a source reads sub-window k of the episode; up to MAX_READS per source.
Every threshold is a train-data (attack-free) percentile; nothing is fitted on attack labels here.
Likelihoods that need attack data are estimated in hai_model.py from the development version only.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

HAI_VERSION = "probe-hai-1.0"
DATA_ROOT = Path("/mnt/project-files/data")
META = Path(__file__).resolve().parents[2] / "configs" / "data" / "hai_attack_metadata.json"

SUB = 30                 # seconds per sub-window (one reading)
MAX_READS = 6            # readings per source per episode -> 180 s after onset
REF = (-300, -60)        # pre-onset reference window, seconds relative to onset
GUARD = 900              # normal-episode onsets keep this many seconds from any attack row
QUERY_Q = 0.99           # query alarm threshold: train percentile of the change statistic
PROBE_Q = 0.99           # probe FAIL threshold: train percentile of the residual statistic
RIDGE = 1.0
TRAIN_STRIDE = 5         # subsample train rows for fitting
N_TRAIN_ONSETS = 3000

# name, process class (1 = P1, 2 = P2/P3), spoofable PV, per-version column
SOURCES: List[Tuple[str, int, bool]] = [
    ("P1_PIT01", 1, True), ("P1_FT03", 1, True), ("P1_LIT01", 1, True),
    ("P1_PCV01D", 1, False), ("P1_FCV03D", 1, False), ("P1_LCV01D", 1, False),
    ("P2_SIT01", 2, True), ("P3_LEVEL", 2, True), ("P3_LCV01D", 2, False),
]
SOURCE_NAMES = [s[0] for s in SOURCES]
COLUMN_ALIAS = {"hai-20.07": {"P3_LEVEL": "P3_LT01"}, "hai-21.03": {"P3_LEVEL": "P3_LIT01"},
                "hai-22.04": {"P3_LEVEL": "P3_LIT01"}}
VERSIONS = {
    "hai-20.07": {"train": ["train1", "train2"], "test": ["test1", "test2"], "sep": ";", "code": 2007},
    "hai-21.03": {"train": ["train1", "train2", "train3"], "test": ["test1", "test2", "test3", "test4", "test5"],
                  "sep": ",", "code": 2103},
    "hai-22.04": {"train": ["train1", "train2", "train3", "train4", "train5", "train6"],
                  "test": ["test1", "test2", "test3", "test4"], "sep": ",", "code": 2204},
}
LABELS = {"attack", "attack_p1", "attack_p2", "attack_p3"}


def _read(version: str, name: str) -> pd.DataFrame:
    v = VERSIONS[version]
    df = pd.read_csv(DATA_ROOT / version / f"{name}.csv.gz", sep=v["sep"])
    df = df.rename(columns={df.columns[0]: "time"})
    df.columns = [c if c == "time" else (c.lower() if c.lower() in LABELS else c) for c in df.columns]
    alias = {v_: k for k, v_ in COLUMN_ALIAS[version].items()}
    return df.rename(columns=alias)


def _process_columns(df: pd.DataFrame, proc_prefixes: Sequence[str], exclude: str) -> List[str]:
    return [c for c in df.columns if c != "time" and c not in LABELS and c != exclude
            and any(c.startswith(p) for p in proc_prefixes)]


def _window_mean(x: np.ndarray, start: np.ndarray, length: int) -> np.ndarray:
    cs = np.concatenate([[0.0], np.cumsum(x)])
    return (cs[start + length] - cs[start]) / length


@dataclass
class SourceDetectors:
    """Train-only detectors for one HAI version."""
    version: str
    q_scale: np.ndarray                          # robust scale of the change statistic per source
    q_thresh: np.ndarray                         # alarm threshold on the scaled statistic
    p_cols: List[List[str]] = field(default_factory=list)
    p_coef: List[np.ndarray] = field(default_factory=list)
    p_mu: List[np.ndarray] = field(default_factory=list)
    p_sd: List[np.ndarray] = field(default_factory=list)
    p_scale: np.ndarray = None
    p_thresh: np.ndarray = None


def _change_stat(x: np.ndarray, onsets: np.ndarray, k: int) -> np.ndarray:
    ref = _window_mean(x, onsets + REF[0], REF[1] - REF[0])
    cur = _window_mean(x, onsets + k * SUB, SUB)
    return np.abs(cur - ref)


def _proc_prefixes(cls: int) -> Tuple[str, ...]:
    return ("P1_",) if cls == 1 else ("P2_", "P3_")


def fit_detectors(version: str, rng_seed: int = 0) -> SourceDetectors:
    trains = [_read(version, n) for n in VERSIONS[version]["train"]]
    rng = np.random.default_rng([7_7_5_0, VERSIONS[version]["code"], rng_seed])
    K = len(SOURCES)
    stats = [[] for _ in range(K)]
    for df in trains:
        n = len(df)
        lo, hi = -REF[0], n - MAX_READS * SUB - 1
        on = rng.integers(lo, hi, size=N_TRAIN_ONSETS // len(trains))
        for q, (name, _, _) in enumerate(SOURCES):
            x = df[name].to_numpy(float)
            stats[q].append(np.concatenate([_change_stat(x, on, k) for k in range(MAX_READS)]))
    q_scale, q_thresh = np.zeros(K), np.zeros(K)
    for q in range(K):
        s = np.concatenate(stats[q])
        q_scale[q] = max(np.median(s), 1e-9)
        q_thresh[q] = np.quantile(s / q_scale[q], QUERY_Q)
    det = SourceDetectors(version, q_scale, q_thresh)
    # probes: ridge regression of each source on the other points of its process(es)
    full = pd.concat(trains, ignore_index=True)
    sub = full.iloc[::TRAIN_STRIDE]
    pres = [[] for _ in range(K)]
    for q, (name, cls, _) in enumerate(SOURCES):
        cols = [c for c in _process_columns(full, _proc_prefixes(cls), name) if sub[c].std() > 1e-9]
        X = sub[cols].to_numpy(float)
        mu, sd = X.mean(0), X.std(0)
        Z = (X - mu) / sd
        y = sub[name].to_numpy(float)
        A = np.c_[Z, np.ones(len(Z))]
        coef = np.linalg.solve(A.T @ A + RIDGE * np.eye(A.shape[1]), A.T @ y)
        det.p_cols.append(cols)
        det.p_coef.append(coef)
        det.p_mu.append(mu)
        det.p_sd.append(sd)
    for df in trains:
        n = len(df)
        on = rng.integers(-REF[0], n - MAX_READS * SUB - 1, size=N_TRAIN_ONSETS // len(trains))
        for q in range(K):
            r = np.abs(residual(det, df, q))
            pres[q].append(np.concatenate([_window_mean(r, on + k * SUB, SUB) for k in range(MAX_READS)]))
    det.p_scale, det.p_thresh = np.zeros(K), np.zeros(K)
    for q in range(K):
        s = np.concatenate(pres[q])
        det.p_scale[q] = max(np.median(s), 1e-9)
        det.p_thresh[q] = np.quantile(s / det.p_scale[q], PROBE_Q)
    return det


def residual(det: SourceDetectors, df: pd.DataFrame, q: int) -> np.ndarray:
    name = SOURCES[q][0]
    Z = (df[det.p_cols[q]].to_numpy(float) - det.p_mu[q]) / det.p_sd[q]
    return df[name].to_numpy(float) - (np.c_[Z, np.ones(len(Z))] @ det.p_coef[q])


@dataclass
class Episode:
    version: str
    file: str
    onset: str
    h_true: int
    attack_index: int          # 1-based chronological attack number, 0 for normal
    compromised: List[int]     # source indices held at stale values
    query_obs: np.ndarray      # [K, MAX_READS] in {0, 1, 2}
    probe_obs: np.ndarray      # [K, MAX_READS] in {0 PASS, 1 FAIL}


def _segments(att: np.ndarray) -> List[Tuple[int, int]]:
    d = np.diff(np.r_[0, (att > 0).astype(int), 0])
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def build_episodes(version: str, det: SourceDetectors) -> List[Episode]:
    meta = json.loads(META.read_text())[version]
    excluded = set(meta.get("excluded", []))
    rng = np.random.default_rng([7_7_5_1, VERSIONS[version]["code"]])
    K = len(SOURCES)
    eps: List[Episode] = []
    idx = 0
    pending_normals: List[tuple] = []
    for fname in VERSIONS[version]["test"]:
        df = _read(version, fname)
        att = df["attack"].to_numpy(float)
        segs = _segments(att)
        resid = [residual(det, df, q) for q in range(K)]
        xs = [df[s[0]].to_numpy(float) for s in SOURCES]

        def observe(onset: int, xs=xs, resid=resid):
            on = np.array([onset])
            qo = np.zeros((K, MAX_READS), int)
            po = np.zeros((K, MAX_READS), int)
            for q, (_, cls, _) in enumerate(SOURCES):
                for k in range(MAX_READS):
                    s = _change_stat(xs[q], on, k)[0] / det.q_scale[q]
                    qo[q, k] = cls if s > det.q_thresh[q] else 0
                    r = _window_mean(np.abs(resid[q]), on + k * SUB, SUB)[0] / det.p_scale[q]
                    po[q, k] = int(r > det.p_thresh[q])
            return qo, po

        for (s, e) in segs:
            idx += 1
            key = str(idx)
            if key in excluded or s + REF[0] < 0 or s + MAX_READS * SUB > len(df):
                continue
            if "processes" in meta:
                procs = set(meta["processes"][key])
            else:
                procs = {p for p in (1, 2, 3) if df[f"attack_p{p}"].to_numpy()[s:e].max() > 0}
            h = 1 if procs == {1} else 2
            comp = [SOURCE_NAMES.index(n) for n in meta["spoofed"].get(key, [])]
            qo, po = observe(s)
            eps.append(Episode(version, fname, str(df["time"].iloc[s]), h, idx, comp, qo, po))
        # candidate normal onsets: far from every attack row
        near = np.convolve((att > 0).astype(float), np.ones(2 * GUARD + 1), mode="same") > 0
        ok = ~near
        ok[: -REF[0]] = False
        ok[len(df) - MAX_READS * SUB - 1:] = False
        pending_normals.append((fname, df, np.where(ok)[0], observe))
    n_attack = len(eps)
    sizes = np.array([len(c) for _, _, c, _ in pending_normals], float)
    alloc = np.floor(n_attack * sizes / sizes.sum()).astype(int)
    alloc[np.argmax(sizes)] += n_attack - alloc.sum()
    for (fname, df, cand, observe), m in zip(pending_normals, alloc):
        for onset in np.sort(rng.choice(cand, size=m, replace=False)):
            qo, po = observe(int(onset))
            eps.append(Episode(version, fname, str(df["time"].iloc[onset]), 0, 0, [], qo, po))
    return eps


def save_episodes(eps: List[Episode], path: Path, det: SourceDetectors) -> None:
    out = {"hai_version": HAI_VERSION, "dataset_version": eps[0].version if eps else None,
           "sources": SOURCE_NAMES, "sub_seconds": SUB, "max_reads": MAX_READS,
           "detectors": {"q_thresh": det.q_thresh.tolist(), "p_thresh": det.p_thresh.tolist()},
           "episodes": [{"file": e.file, "onset": e.onset, "h_true": e.h_true, "attack_index": e.attack_index,
                         "compromised": e.compromised, "query_obs": e.query_obs.tolist(),
                         "probe_obs": e.probe_obs.tolist()} for e in eps]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt") as fh:
        json.dump(out, fh)


def load_episodes(path: Path) -> List[Episode]:
    with gzip.open(path, "rt") as fh:
        d = json.load(fh)
    return [Episode(d["dataset_version"], e["file"], e["onset"], e["h_true"], e["attack_index"], e["compromised"],
                    np.array(e["query_obs"]), np.array(e["probe_obs"])) for e in d["episodes"]]
