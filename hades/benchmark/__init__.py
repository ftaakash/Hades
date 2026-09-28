"""hades/benchmark — CDB interface layer (Phase 5A).

This package bridges HADES's internal belief/policy machinery to the
Cyber Defense Benchmark (CDB) environment.

Components
----------
obs_mapper.py       Convert a CDB SQL observation (text) → 5-class obs_class
candidate_extractor Classify row yield and extract candidate timestamps
fast_db.py          Batch-insert helper (executemany, avoiding 155k row-at-a-time)
"""
from hades.benchmark.obs_mapper import map_observation, OBS_MAPPER_VERSION
from hades.benchmark.candidate_extractor import CandidateExtractor

__all__ = ["map_observation", "OBS_MAPPER_VERSION", "CandidateExtractor"]
