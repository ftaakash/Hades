"""
hades/belief/relevance.py
--------------------------
Expert relevance matrix for HADES v3.0.

RELEVANCE[(source, attack_type)] -> float in [0, 1]

v0: Explicit expert heuristic. Values are NOT derived from held-out CDB
evaluation flags. Sources: ATT&CK data-component mappings + Sigma rules
+ domain expertise (documented below).

Empirical calibration will happen on the calibration split ONLY (14 campaigns),
never on the 12 held-out evaluation campaigns. See main_v1.yaml for the split.

Provenance
~~~~~~~~~~
Every entry has a RELEVANCE_PROVENANCE entry documenting:
  source  : "attck"     = ATT&CK data component explicitly lists this detection
            "sigma"     = Sigma rule exists for this source+attack_type pair
            "expert-v0" = domain expert judgement, no rule citation
  version : "v0" for all current entries (will be versioned with calibration)
  note    : brief rationale

References
~~~~~~~~~~
* MITRE ATT&CK v15, data components: https://attack.mitre.org/datasources/
* Sigma project: https://github.com/SigmaHQ/sigma
* CDB query menu: hades/query_menu.py (7 sources)
"""
from __future__ import annotations

from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Source IDs (must match hades/query_menu.py source names)
# ---------------------------------------------------------------------------
SOURCES = [
    "auth_events",
    "process_events",
    "network_events",
    "dns_events",
    "persistence_events",
    "powershell_events",
    "object_access_events",
]

# ---------------------------------------------------------------------------
# Attack type IDs (broad MITRE tactic-level categories)
# ---------------------------------------------------------------------------
ATTACK_TYPES = [
    "H_initial_access",
    "H_execution",
    "H_persistence",
    "H_privilege_escalation",
    "H_lateral_movement",
    "H_exfiltration",
    "H_defense_evasion",
]

# ---------------------------------------------------------------------------
# Expert relevance matrix
# (source, attack_type) -> float in [0, 1]
# ATT&CK-grounded; never derived from held-out CDB evaluation data.
# ---------------------------------------------------------------------------
RELEVANCE: Dict[Tuple[str, str], float] = {
    # auth_events: logon/logoff/ticket events — strong for auth-related tactics
    ("auth_events", "H_initial_access"):         0.80,  # spear-phishing, valid accounts
    ("auth_events", "H_lateral_movement"):       0.90,  # pass-the-hash, ticket abuse
    ("auth_events", "H_privilege_escalation"):   0.75,  # token impersonation, runas
    ("auth_events", "H_execution"):              0.30,  # occasional auth checks
    ("auth_events", "H_persistence"):            0.40,  # account creation/modification
    ("auth_events", "H_exfiltration"):           0.20,  # cloud console auth may appear
    ("auth_events", "H_defense_evasion"):        0.35,  # logon type manipulation

    # process_events: process creation, injection, tree — strong for execution
    ("process_events", "H_execution"):           0.92,  # T1059 command line, T1055 injection
    ("process_events", "H_persistence"):         0.70,  # T1543 service creation, scheduled tasks
    ("process_events", "H_privilege_escalation"):0.65,  # T1548 LOLBIN elevation
    ("process_events", "H_lateral_movement"):    0.60,  # T1021 remote execution
    ("process_events", "H_defense_evasion"):     0.75,  # T1036 masquerading, T1055 injection
    ("process_events", "H_initial_access"):      0.40,  # post-phishing execution visible
    ("process_events", "H_exfiltration"):        0.30,  # exfil tools launched here

    # network_events: firewall/IDS, netflow — strong for lateral/exfil
    ("network_events", "H_lateral_movement"):    0.85,  # T1021 RDP, SMB, WinRM
    ("network_events", "H_exfiltration"):        0.90,  # T1048 external comms, T1071 C2
    ("network_events", "H_initial_access"):      0.55,  # inbound scan, phishing callback
    ("network_events", "H_execution"):           0.25,  # network rarely primary indicator
    ("network_events", "H_persistence"):         0.20,
    ("network_events", "H_privilege_escalation"):0.15,
    ("network_events", "H_defense_evasion"):     0.40,  # encrypted C2, tunneling

    # dns_events: DNS query log — exfil/C2 heavy
    ("dns_events", "H_exfiltration"):            0.85,  # DNS tunneling T1048.003
    ("dns_events", "H_initial_access"):          0.60,  # C2 callback domain resolution
    ("dns_events", "H_lateral_movement"):        0.35,  # internal name resolution
    ("dns_events", "H_execution"):               0.15,
    ("dns_events", "H_persistence"):             0.10,
    ("dns_events", "H_privilege_escalation"):    0.10,
    ("dns_events", "H_defense_evasion"):         0.50,  # DGA, fast-flux

    # persistence_events: registry, scheduled tasks, services, startup
    ("persistence_events", "H_persistence"):     0.95,  # T1053, T1543, T1547 — core
    ("persistence_events", "H_privilege_escalation"):0.45,  # service-based escalation
    ("persistence_events", "H_execution"):       0.35,  # tasks trigger execution
    ("persistence_events", "H_lateral_movement"):0.20,
    ("persistence_events", "H_initial_access"):  0.15,
    ("persistence_events", "H_exfiltration"):    0.10,
    ("persistence_events", "H_defense_evasion"): 0.60,  # T1112 registry modification

    # powershell_events: script block logging, module load
    ("powershell_events", "H_execution"):        0.88,  # T1059.001 — primary PS indicator
    ("powershell_events", "H_defense_evasion"):  0.82,  # T1027 obfuscation, T1562 disable logging
    ("powershell_events", "H_privilege_escalation"):0.60,  # T1548, UAC bypass via PS
    ("powershell_events", "H_persistence"):      0.50,  # PS-based scheduled tasks
    ("powershell_events", "H_lateral_movement"): 0.40,  # PS remoting T1021.006
    ("powershell_events", "H_initial_access"):   0.30,  # post-phishing PS execution
    ("powershell_events", "H_exfiltration"):     0.25,  # PS-based upload/download

    # object_access_events: file/share audit, SACL hits
    ("object_access_events", "H_privilege_escalation"): 0.88,  # SAM access, LSASS dump
    ("object_access_events", "H_exfiltration"):          0.70,  # file staging, bulk access
    ("object_access_events", "H_persistence"):           0.50,  # config file modification
    ("object_access_events", "H_execution"):             0.40,  # DLL planting scenarios
    ("object_access_events", "H_lateral_movement"):      0.35,  # share access
    ("object_access_events", "H_initial_access"):        0.25,
    ("object_access_events", "H_defense_evasion"):       0.55,  # log deletion, SACL bypass
}

# ---------------------------------------------------------------------------
# Provenance record for every entry
# ---------------------------------------------------------------------------
RELEVANCE_PROVENANCE: Dict[Tuple[str, str], dict] = {
    ("auth_events", "H_initial_access"):         {"source": "attck", "version": "v0", "component": "Logon Session", "note": "T1078 valid accounts"},
    ("auth_events", "H_lateral_movement"):        {"source": "attck", "version": "v0", "component": "Logon Session", "note": "T1550 pass-the-hash, T1558 Kerberoast"},
    ("auth_events", "H_privilege_escalation"):    {"source": "attck+sigma", "version": "v0", "note": "T1134 token impersonation; sigma/win_process_creation_runas.yml"},
    ("auth_events", "H_execution"):               {"source": "expert-v0", "version": "v0", "note": "Rare auth checks before execution; low weight"},
    ("auth_events", "H_persistence"):             {"source": "attck", "version": "v0", "note": "T1136 account creation in auth log"},
    ("auth_events", "H_exfiltration"):            {"source": "expert-v0", "version": "v0", "note": "Cloud console auth at exfil time"},
    ("auth_events", "H_defense_evasion"):         {"source": "expert-v0", "version": "v0", "note": "Logon type manipulation T1036"},
    ("process_events", "H_execution"):            {"source": "attck+sigma", "version": "v0", "note": "T1059 command and scripting; sigma/category/process_creation"},
    ("process_events", "H_persistence"):          {"source": "attck", "version": "v0", "note": "T1543 create/modify system process"},
    ("process_events", "H_privilege_escalation"): {"source": "attck", "version": "v0", "note": "T1548 abuse elevation control"},
    ("process_events", "H_lateral_movement"):     {"source": "attck", "version": "v0", "note": "T1021 remote services — process on target"},
    ("process_events", "H_defense_evasion"):      {"source": "attck+sigma", "version": "v0", "note": "T1036 masquerade; sigma/win_susp_process"},
    ("process_events", "H_initial_access"):       {"source": "expert-v0", "version": "v0", "note": "Post-phishing execution visible in process log"},
    ("process_events", "H_exfiltration"):         {"source": "expert-v0", "version": "v0", "note": "Exfil tool launched as process"},
    ("network_events", "H_lateral_movement"):     {"source": "attck", "version": "v0", "note": "T1021 RDP/SMB/WinRM network flow"},
    ("network_events", "H_exfiltration"):         {"source": "attck+sigma", "version": "v0", "note": "T1048 exfil over alternative protocol; T1071 C2"},
    ("network_events", "H_initial_access"):       {"source": "expert-v0", "version": "v0", "note": "Inbound scan, callback from phishing"},
    ("network_events", "H_execution"):            {"source": "expert-v0", "version": "v0", "note": "Rarely primary; low weight"},
    ("network_events", "H_persistence"):          {"source": "expert-v0", "version": "v0", "note": "Uncommon"},
    ("network_events", "H_privilege_escalation"): {"source": "expert-v0", "version": "v0", "note": "Uncommon"},
    ("network_events", "H_defense_evasion"):      {"source": "attck", "version": "v0", "note": "T1573 encrypted C2, T1090 proxy"},
    ("dns_events", "H_exfiltration"):             {"source": "attck+sigma", "version": "v0", "note": "T1048.003 DNS tunneling; sigma/net_dns_tunnel"},
    ("dns_events", "H_initial_access"):           {"source": "attck", "version": "v0", "note": "C2 domain resolution T1566 callback"},
    ("dns_events", "H_lateral_movement"):         {"source": "expert-v0", "version": "v0", "note": "Internal name resolution only"},
    ("dns_events", "H_execution"):                {"source": "expert-v0", "version": "v0", "note": "Very low"},
    ("dns_events", "H_persistence"):              {"source": "expert-v0", "version": "v0", "note": "Very low"},
    ("dns_events", "H_privilege_escalation"):     {"source": "expert-v0", "version": "v0", "note": "Very low"},
    ("dns_events", "H_defense_evasion"):          {"source": "attck", "version": "v0", "note": "T1568 DGA, fast-flux"},
    ("persistence_events", "H_persistence"):      {"source": "attck+sigma", "version": "v0", "note": "T1053 sched task; T1543 service; T1547 autorun; sigma/win_persistence_*"},
    ("persistence_events", "H_privilege_escalation"): {"source": "attck", "version": "v0", "note": "T1543 service-based escalation"},
    ("persistence_events", "H_execution"):        {"source": "attck", "version": "v0", "note": "Scheduled task triggers execution"},
    ("persistence_events", "H_lateral_movement"): {"source": "expert-v0", "version": "v0", "note": "Low"},
    ("persistence_events", "H_initial_access"):   {"source": "expert-v0", "version": "v0", "note": "Very low"},
    ("persistence_events", "H_exfiltration"):     {"source": "expert-v0", "version": "v0", "note": "Very low"},
    ("persistence_events", "H_defense_evasion"):  {"source": "attck", "version": "v0", "note": "T1112 registry modification to disable AV"},
    ("powershell_events", "H_execution"):         {"source": "attck+sigma", "version": "v0", "note": "T1059.001; sigma/win_susp_ps_script_block"},
    ("powershell_events", "H_defense_evasion"):   {"source": "attck+sigma", "version": "v0", "note": "T1027 obfuscation, T1562 disable AMSI; sigma/win_susp_ps_obfuscation"},
    ("powershell_events", "H_privilege_escalation"): {"source": "attck", "version": "v0", "note": "T1548 PS-based UAC bypass"},
    ("powershell_events", "H_persistence"):       {"source": "attck", "version": "v0", "note": "PS-based scheduled tasks / WMI subscriptions"},
    ("powershell_events", "H_lateral_movement"):  {"source": "attck", "version": "v0", "note": "T1021.006 PS remoting"},
    ("powershell_events", "H_initial_access"):    {"source": "expert-v0", "version": "v0", "note": "Post-phishing PS download cradle"},
    ("powershell_events", "H_exfiltration"):      {"source": "expert-v0", "version": "v0", "note": "PS invoke-webrequest upload"},
    ("object_access_events", "H_privilege_escalation"): {"source": "attck+sigma", "version": "v0", "note": "T1003 LSASS, SAM access; sigma/win_lsass_dump_*"},
    ("object_access_events", "H_exfiltration"):          {"source": "attck", "version": "v0", "note": "T1074 file staging, T1039 share collection"},
    ("object_access_events", "H_persistence"):           {"source": "expert-v0", "version": "v0", "note": "Config file modification for persistence"},
    ("object_access_events", "H_execution"):             {"source": "expert-v0", "version": "v0", "note": "DLL planting via file write"},
    ("object_access_events", "H_lateral_movement"):      {"source": "attck", "version": "v0", "note": "T1039 data from network share"},
    ("object_access_events", "H_initial_access"):        {"source": "expert-v0", "version": "v0", "note": "Low"},
    ("object_access_events", "H_defense_evasion"):       {"source": "attck+sigma", "version": "v0", "note": "T1070 indicator removal; sigma/win_susp_log_clear"},
}


def get_relevance(source: str, hyp: str) -> float:
    """
    Return relevance for (source, hyp) pair.
    Returns 0.0 if not in matrix (explicitly unknown = not relevant).
    """
    return RELEVANCE.get((source, hyp), 0.0)


def get_provenance(source: str, hyp: str) -> dict:
    """Return provenance metadata for a (source, hyp) entry."""
    return RELEVANCE_PROVENANCE.get(
        (source, hyp),
        {"source": "unknown", "version": "v0", "note": "No entry in matrix"},
    )
