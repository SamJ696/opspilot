from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RecommendedAction(BaseModel):
    action_type: str
    summary: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = True
    risk: str = "MEDIUM"


class RootCause(BaseModel):
    hypothesis: str
    explanation: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    signals: list[dict[str, Any]] = Field(default_factory=list)
