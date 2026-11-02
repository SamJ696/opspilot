from __future__ import annotations

from opspilot.orchestrator.state import OpsPilotState

APPLICATION_NODES = [
    "log_investigator",
    "deployment_investigator",
    "health_investigator",
]
DATA_NODES = ["pipeline_investigator", "sql_investigator"]


def route_after_triage(state: OpsPilotState) -> list[str] | str:
    if state.get("issue_type") == "APPLICATION":
        return APPLICATION_NODES
    if state.get("issue_type") == "DATA_PIPELINE":
        return DATA_NODES
    return "unsupported"


def route_after_remediation(state: OpsPilotState) -> str:
    action = state.get("recommended_action") or {}
    if action.get("requires_approval"):
        return "approval"
    return "report"


def route_after_approval(state: OpsPilotState) -> str:
    if state.get("approval_status") == "APPROVED":
        return "recovery"
    return "rejection"
