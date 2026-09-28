"""hades/integration — End-to-end pipeline integration (Phase 4 gate).

This package connects the corruption/reliability/belief/policy layers
into a complete verifiable pipeline for pre-CDB integration testing.
"""
from hades.integration.runner import IntegrationRunner, EpisodeResult

__all__ = ["IntegrationRunner", "EpisodeResult"]
