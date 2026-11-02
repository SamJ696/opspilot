from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Incident(BaseModel):
    incident_id: str
    user_message: str
    issue_type: str = ""
    severity: str = ""
    status: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    investigation_results: dict[str, Any] = Field(default_factory=dict)
    root_cause: dict[str, Any] | None = None
    confidence: float | None = None
    recommended_action: dict[str, Any] | None = None
    approval_status: str = "PENDING"
    approval_request: str = ""
    recovery_result: dict[str, Any] | None = None
    verification_result: dict[str, Any] | None = None
    final_report: str = ""
    created_at: str
    updated_at: str
