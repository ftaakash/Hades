"""Canonical evidence-source -> SQL query menu for the HADES harness.

CDB's native action space is freeform SQL: a policy (or LLM) writes any
SELECT it wants against the `logs` table. That's a problem for a clean
acquisition-*policy* ablation, because two policies can differ in query
quality for reasons that have nothing to do with acquisition strategy
(one writes better SQL than the other). HADES constrains the action
space to a small, fixed menu of evidence-source queries so that P0-P6
are only ever choosing *which* source to query next, never *how* to
phrase the query. See the design rationale in README.md.

Each QuerySpec carries:
  - a canonical SQL template (fixed projection + WHERE + ORDER BY, with
    an optional Computer-scoping filter spliced in by `.render()`)
  - a declared acquisition cost (arbitrary relative units)
  - a *ground-truth* reliability `reliability_true` in [0, 1], assigned
    by us for the controlled experiment (not inferred). The corruption
    layer (missing / stale / misleading / targeted -- not yet
    implemented, see README "Status") will use this to decide how
    aggressively to degrade a given source; policies only ever see an
    *estimated* reliability, which may or may not match ground truth
    depending on the experiment condition.

EventID groupings are grounded in the actual distribution observed in
CDB's public `datasets/sample.json` (seed 176, n=155,350 events) -- see
`scripts/inspect_sample.py` for how they were derived -- and are
standard Windows Security/Sysmon event IDs, so they should transfer to
the full (gated) dataset, which shares the same `log_schema.json`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class QuerySpec:
    name: str
    description: str
    event_ids: Tuple[str, ...]
    cost: float
    reliability_true: float
    sql_template: str  # uses {event_ids} and {limit} placeholders

    def render(self, *, limit: int = 10, computer: Optional[str] = None) -> str:
        ids = ", ".join(f"'{e}'" for e in self.event_ids)
        sql = self.sql_template.format(event_ids=ids, limit=limit)
        if computer:
            marker = "ORDER BY"
            if marker in sql:
                head, tail = sql.split(marker, 1)
                sql = f"{head} AND \"Computer\" = '{computer}' {marker}{tail}"
            else:
                sql = sql.rstrip(";") + f" AND \"Computer\" = '{computer}'"
        return sql


_MENU: Dict[str, QuerySpec] = {}


def _register(spec: QuerySpec) -> None:
    _MENU[spec.name] = spec


_register(QuerySpec(
    name="auth_events",
    description="Logon/logoff/privilege events (4624/4625/4634/4648/4672/4768/4769).",
    event_ids=("4624", "4625", "4634", "4648", "4672", "4768", "4769"),
    cost=1.0,
    reliability_true=0.95,
    sql_template=(
        'SELECT "TimeCreated", "EventID", "Computer", "AccountName", "IpAddress" '
        'FROM logs WHERE "EventID" IN ({event_ids}) '
        'ORDER BY "TimeCreated" LIMIT {limit}'
    ),
))

_register(QuerySpec(
    name="process_events",
    description="Process creation/exit (Sysmon 1/5, Security 4688/4689).",
    event_ids=("1", "5", "4688", "4689"),
    cost=1.0,
    reliability_true=0.90,
    sql_template=(
        'SELECT "TimeCreated", "EventID", "Computer", "Image", "CommandLine", "ParentImage" '
        'FROM logs WHERE "EventID" IN ({event_ids}) '
        'ORDER BY "TimeCreated" LIMIT {limit}'
    ),
))

_register(QuerySpec(
    name="network_events",
    description="Network connections + WFP filtering (Sysmon 3, Security 5145/5154/5156/5158).",
    event_ids=("3", "5145", "5154", "5156", "5158"),
    cost=1.5,
    reliability_true=0.85,
    sql_template=(
        'SELECT "TimeCreated", "EventID", "Computer", "DestinationIp", "DestinationPort", "Image" '
        'FROM logs WHERE "EventID" IN ({event_ids}) '
        'ORDER BY "TimeCreated" LIMIT {limit}'
    ),
))

_register(QuerySpec(
    name="dns_events",
    description="DNS queries (Sysmon 22).",
    event_ids=("22",),
    cost=1.0,
    reliability_true=0.85,
    sql_template=(
        'SELECT "TimeCreated", "EventID", "Computer", "QueryName", "QueryResults" '
        'FROM logs WHERE "EventID" IN ({event_ids}) '
        'ORDER BY "TimeCreated" LIMIT {limit}'
    ),
))

_register(QuerySpec(
    name="persistence_events",
    description=(
        "Registry/file/scheduled-task/service persistence artifacts "
        "(Sysmon 11/12/13, Security 4698, System 7045)."
    ),
    event_ids=("11", "12", "13", "4698", "7045"),
    cost=1.5,
    reliability_true=0.80,
    sql_template=(
        'SELECT "TimeCreated", "EventID", "Computer", "TargetObject", "TargetFilename", "Details" '
        'FROM logs WHERE "EventID" IN ({event_ids}) '
        'ORDER BY "TimeCreated" LIMIT {limit}'
    ),
))

_register(QuerySpec(
    name="powershell_events",
    description="PowerShell script-block / module / pipeline logging (Security 4103/4104, PowerShell 800).",
    event_ids=("4103", "4104", "800"),
    cost=1.0,
    reliability_true=0.90,
    sql_template=(
        'SELECT "TimeCreated", "EventID", "Computer", "ScriptBlockText", "Payload" '
        'FROM logs WHERE "EventID" IN ({event_ids}) '
        'ORDER BY "TimeCreated" LIMIT {limit}'
    ),
))

_register(QuerySpec(
    name="object_access_events",
    description=(
        "Handle/privilege/object-access events, useful for privilege-escalation "
        "hypotheses (Security 4656/4658/4661/4663/4670/4673/4703)."
    ),
    event_ids=("4656", "4658", "4661", "4663", "4670", "4673", "4703"),
    cost=2.0,
    reliability_true=0.75,
    sql_template=(
        'SELECT "TimeCreated", "EventID", "Computer", "ObjectName", "ProcessName", "AccessMask" '
        'FROM logs WHERE "EventID" IN ({event_ids}) '
        'ORDER BY "TimeCreated" LIMIT {limit}'
    ),
))


def get_menu() -> Dict[str, QuerySpec]:
    """Return the canonical evidence-source menu (name -> QuerySpec)."""
    return dict(_MENU)
