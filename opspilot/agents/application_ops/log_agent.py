from __future__ import annotations

from collections import Counter
from typing import Any

from opspilot.schemas.evidence import make_evidence
from opspilot.tools.log_search import search_logs
from opspilot.tools.targeting import resolve_service

AGENT_NAME = "Log Investigator"
SOURCE = "log_investigator"


def investigate_logs(message: str) -> dict[str, Any]:
    service, match_source = resolve_service(message)
    if service is None:
        summary = "No application service could be identified from the report or error logs."
        result = _result(summary, service=None, match_source=match_source)
        return {
            "evidence": [
                make_evidence(SOURCE, "log", summary, result, evidence_id="log-primary")
            ],
            "result": result,
        }

    errors = search_logs(service=service, level="ERROR")
    counts = Counter(entry["message"] for entry in errors)
    top_error, top_error_count = counts.most_common(1)[0] if counts else ("", 0)
    versions = sorted({entry["deployment_version"] for entry in errors})
    first_error_at = errors[0]["timestamp"] if errors else None
    last_error_at = errors[-1]["timestamp"] if errors else None

    if errors:
        summary = (
            f"Found {len(errors)} ERROR events for {service}. "
            f"Top error ({top_error_count}): {top_error}."
        )
    else:
        summary = f"Found 0 ERROR events for {service}."

    result = _result(
        summary,
        service=service,
        match_source=match_source,
        error_count=len(errors),
        top_error=top_error,
        top_error_count=top_error_count,
        first_error_at=first_error_at,
        last_error_at=last_error_at,
        versions=versions,
        sample_trace_ids=[entry["trace_id"] for entry in errors[:5]],
    )
    return {
        "evidence": [
            make_evidence(
                SOURCE,
                "log",
                summary,
                result,
                timestamp=first_error_at,
                evidence_id="log-primary",
            )
        ],
        "result": result,
    }


def _result(summary: str, **details: Any) -> dict[str, Any]:
    result = {
        "agent": AGENT_NAME,
        "summary": summary,
        "evidence_id": "log-primary",
        "error_count": 0,
        "top_error": "",
        "top_error_count": 0,
        "first_error_at": None,
        "last_error_at": None,
        "versions": [],
        "sample_trace_ids": [],
    }
    result.update(details)
    return result
