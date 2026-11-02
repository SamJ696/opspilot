from __future__ import annotations

from typing import Any

from opspilot.schemas.evidence import make_evidence
from opspilot.tools.deployment_history import latest_deployment
from opspilot.tools.service_metrics import latest_and_baseline
from opspilot.tools.targeting import resolve_service

AGENT_NAME = "Service Health Agent"
SOURCE = "health_investigator"


def investigate_health(message: str) -> dict[str, Any]:
    service, match_source = resolve_service(message)
    deployment = latest_deployment(service) if service else None
    deployed_at = deployment["deployed_at"] if deployment else None
    latest, baseline = latest_and_baseline(service, deployed_at) if service else (None, None)

    if latest is None:
        summary = "No service metrics were found for this report."
        result = _empty(summary, service, match_source)
    else:
        degraded = (not latest["healthy"]) or (
            baseline is not None
            and latest["error_rate_percent"] >= baseline["error_rate_percent"] + 5
        )
        if baseline is not None:
            summary = (
                f"Service {service} is {'unhealthy' if not latest['healthy'] else 'healthy'}. "
                f"Error rate moved from {baseline['error_rate_percent']}% to {latest['error_rate_percent']}%. "
                f"Average latency moved from {baseline['average_latency_ms']} ms to {latest['average_latency_ms']} ms. "
                f"CPU {latest['cpu_percent']}%, memory {latest['memory_percent']}%."
            )
        else:
            summary = (
                f"Service {service} latest error rate is {latest['error_rate_percent']}% "
                f"and average latency is {latest['average_latency_ms']} ms."
            )
        result = {
            "agent": AGENT_NAME,
            "summary": summary,
            "evidence_id": "health-primary",
            "service": service,
            "match_source": match_source,
            "error_rate_percent": latest["error_rate_percent"],
            "average_latency_ms": latest["average_latency_ms"],
            "cpu_percent": latest["cpu_percent"],
            "memory_percent": latest["memory_percent"],
            "healthy": latest["healthy"],
            "degraded": degraded,
            "baseline_error_rate_percent": None if baseline is None else baseline["error_rate_percent"],
            "baseline_latency_ms": None if baseline is None else baseline["average_latency_ms"],
            "latest_timestamp": latest["timestamp"],
        }

    return {
        "evidence": [
            make_evidence(
                SOURCE,
                "metric",
                summary,
                result,
                timestamp=result.get("latest_timestamp"),
                evidence_id="health-primary",
            )
        ],
        "result": result,
    }


def _empty(summary: str, service: str | None, match_source: str) -> dict[str, Any]:
    return {
        "agent": AGENT_NAME,
        "summary": summary,
        "evidence_id": "health-primary",
        "service": service,
        "match_source": match_source,
        "error_rate_percent": None,
        "average_latency_ms": None,
        "cpu_percent": None,
        "memory_percent": None,
        "healthy": None,
        "degraded": False,
        "baseline_error_rate_percent": None,
        "baseline_latency_ms": None,
        "latest_timestamp": None,
    }
