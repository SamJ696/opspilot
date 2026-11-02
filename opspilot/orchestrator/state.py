from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_dicts(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class OpsPilotState(TypedDict):
    incident_id: str
    user_message: str
    issue_type: str
    severity: str
    status: str
    application_score: int
    data_score: int
    evidence: Annotated[list[dict[str, Any]], operator.add]
    investigation_results: Annotated[dict[str, Any], merge_dicts]
    root_cause: Any
    confidence: Any
    recommended_action: Any
    approval_status: str
    approval_request: str
    recovery_result: Any
    verification_result: Any
    final_report: str


def blank_state(message: str, incident_id: str) -> OpsPilotState:
    return {
        "incident_id": incident_id,
        "user_message": message,
        "issue_type": "",
        "severity": "",
        "status": "NEW",
        "application_score": 0,
        "data_score": 0,
        "evidence": [],
        "investigation_results": {},
        "root_cause": None,
        "confidence": None,
        "recommended_action": None,
        "approval_status": "PENDING",
        "approval_request": "",
        "recovery_result": None,
        "verification_result": None,
        "final_report": "",
    }
