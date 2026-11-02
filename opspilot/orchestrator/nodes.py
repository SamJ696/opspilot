from __future__ import annotations

import logging
from typing import Any

from langgraph.types import interrupt

from opspilot.agents.application_ops.deployment_agent import investigate_deployments
from opspilot.agents.application_ops.health_agent import investigate_health
from opspilot.agents.application_ops.log_agent import investigate_logs
from opspilot.agents.data_ops.pipeline_agent import investigate_pipeline
from opspilot.agents.data_ops.sql_agent import investigate_sql
from opspilot.agents.shared.recovery_agent import (
    execute_recovery,
    plan_recovery,
    verify_recovery,
)
from opspilot.agents.shared.root_cause_agent import analyze
from opspilot.agents.triage_agent import triage_agent
from opspilot.llm import narrate_report
from opspilot.orchestrator.state import OpsPilotState
from opspilot.reporting import build_approval_request, build_final_report, build_rejection_report
from opspilot.storage.incident_repository import add_audit, upsert_incident

logger = logging.getLogger(__name__)


def _save(
    state: OpsPilotState,
    updates: dict[str, Any],
    audit_action: str | None = None,
    audit_detail: str = "",
) -> dict[str, Any]:
    merged = {**state, **updates}
    upsert_incident(merged)
    if audit_action:
        add_audit(merged["incident_id"], audit_action, audit_detail)
    return updates


def _specialist(state: OpsPilotState, key: str, investigator: Any) -> dict[str, Any]:
    outcome = investigator(state["user_message"])
    return {
        "evidence": outcome["evidence"],
        "investigation_results": {key: outcome["result"]},
    }


def intake_node(state: OpsPilotState) -> dict[str, Any]:
    return _save(state, {"status": "NEW"}, "created", state["user_message"])


def triage_node(state: OpsPilotState) -> dict[str, Any]:
    result = triage_agent(state["user_message"])
    updates = {
        "issue_type": result["issue_type"],
        "severity": result["severity"],
        "status": "INVESTIGATING",
        "application_score": result["application_score"],
        "data_score": result["data_score"],
    }
    return _save(state, updates, "triaged", result["issue_type"])


def log_node(state: OpsPilotState) -> dict[str, Any]:
    return _specialist(state, "log_investigator", investigate_logs)


def deployment_node(state: OpsPilotState) -> dict[str, Any]:
    return _specialist(state, "deployment_investigator", investigate_deployments)


def health_node(state: OpsPilotState) -> dict[str, Any]:
    return _specialist(state, "health_investigator", investigate_health)


def pipeline_node(state: OpsPilotState) -> dict[str, Any]:
    return _specialist(state, "pipeline_investigator", investigate_pipeline)


def sql_node(state: OpsPilotState) -> dict[str, Any]:
    return _specialist(state, "sql_investigator", investigate_sql)


def root_cause_node(state: OpsPilotState) -> dict[str, Any]:
    analysis = analyze(state["issue_type"], state.get("investigation_results") or {})
    updates = {
        "root_cause": analysis["root_cause"],
        "confidence": analysis["confidence"],
        "status": "ROOT_CAUSE_IDENTIFIED",
    }
    return _save(state, updates, "root_cause", analysis["root_cause"]["hypothesis"])


def remediation_node(state: OpsPilotState) -> dict[str, Any]:
    action = plan_recovery(
        state["issue_type"],
        state.get("root_cause") or {},
        state.get("investigation_results") or {},
        state.get("confidence"),
    )
    updates: dict[str, Any] = {"recommended_action": action}
    if action["requires_approval"]:
        updates["status"] = "AWAITING_APPROVAL"
        updates["approval_status"] = "PENDING"
        updates["approval_request"] = build_approval_request({**state, **updates})
    else:
        updates["approval_status"] = "NOT_REQUIRED"
        updates["approval_request"] = ""
    return _save(state, updates, "remediation", action["action_type"])


def approval_node(state: OpsPilotState) -> dict[str, Any]:
    decision = interrupt(
        {
            "incident_id": state["incident_id"],
            "approval_request": state.get("approval_request", ""),
            "recommended_action": state.get("recommended_action"),
        }
    )
    supplied_id = ""
    if isinstance(decision, dict):
        raw = str(decision.get("decision", ""))
        supplied_id = str(decision.get("incident_id", ""))
    else:
        raw = str(decision)

    if supplied_id and supplied_id != state["incident_id"]:
        updates = {
            "approval_status": "REJECTED",
            "status": "REJECTED",
            "final_report": (
                f"Incident {state['incident_id']} was not changed. "
                "The approval decision referenced a different incident, so recovery was blocked."
            ),
        }
        return _save(state, updates, "approval_rejected", "incident id mismatch")

    if raw.strip().lower() in {"approve", "approved", "yes", "y"}:
        return _save(
            state,
            {"approval_status": "APPROVED", "status": "RECOVERING"},
            "approved",
            state["incident_id"],
        )

    return _save(
        state,
        {"approval_status": "REJECTED", "status": "REJECTED"},
        "approval_rejected",
        raw.strip().lower() or "rejected",
    )


def recovery_node(state: OpsPilotState) -> dict[str, Any]:
    # The graph only routes here after approval. The tool rejects approved=False.
    if state.get("approval_status") != "APPROVED":
        logger.warning("Recovery blocked for %s because approval is missing", state["incident_id"])
        return _save(
            state,
            {
                "status": "REJECTED",
                "recovery_result": {"status": "BLOCKED", "reason": "Approval missing"},
            },
            "recovery_blocked",
            "approval missing",
        )

    existing = state.get("recovery_result") or {}
    if existing.get("status") in {"COMPLETED", "ALREADY_APPLIED"}:
        return {"recovery_result": existing, "status": "VERIFYING"}

    result = execute_recovery(state["recommended_action"], approved=True)
    return _save(state, {"recovery_result": result, "status": "VERIFYING"}, "recovery", result["status"])


def verification_node(state: OpsPilotState) -> dict[str, Any]:
    if state.get("approval_status") != "APPROVED":
        return {}
    result = verify_recovery(state.get("recommended_action") or {}, state.get("recovery_result"))
    status = "RESOLVED" if result["passed"] else "RECOVERY_FAILED"
    return _save(state, {"verification_result": result, "status": status}, "verification", status)


def report_node(state: OpsPilotState) -> dict[str, Any]:
    report = build_final_report(state)
    note = narrate_report(state)
    if note:
        report = f"{report}\n\nAnalyst note:\n{note}"
    return _save(state, {"final_report": report}, "reported", state.get("status", ""))


def rejection_node(state: OpsPilotState) -> dict[str, Any]:
    report = state.get("final_report") or build_rejection_report(state)
    return _save(
        state,
        {
            "status": "REJECTED",
            "approval_status": "REJECTED",
            "final_report": report,
        },
    )


def unsupported_node(state: OpsPilotState) -> dict[str, Any]:
    report = (
        f"Incident {state['incident_id']} was not classified. "
        "OpsPilot did not investigate or change any system. "
        "Rephrase the report with the failing application or data pipeline."
    )
    return _save(
        state,
        {
            "status": "UNCLASSIFIED",
            "approval_status": "NOT_REQUIRED",
            "final_report": report,
        },
        "unclassified",
        state["user_message"],
    )
