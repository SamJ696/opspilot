from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    id: str
    source: str
    category: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str | None = None


def make_evidence(
    source: str,
    category: str,
    summary: str,
    details: dict[str, Any] | None = None,
    timestamp: str | None = None,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    item = Evidence(
        id=evidence_id or f"{source}-{category}",
        source=source,
        category=category,
        summary=summary,
        details=details or {},
        timestamp=timestamp,
    )
    return item.model_dump()
