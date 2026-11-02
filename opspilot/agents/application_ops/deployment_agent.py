from __future__ import annotations

from typing import Any

from opspilot.schemas.evidence import make_evidence
from opspilot.tools.deployment_history import latest_deployment
from opspilot.tools.targeting import resolve_service

AGENT_NAME = "Deployment Investigator"
SOURCE = "deployment_investigator"


def investigate_deployments(message: str) -> dict[str, Any]:
    service, match_source = resolve_service(message)
    deployment = latest_deployment(service) if service else None
    if deployment is None:
        summary = "No production deployment could be matched to this report."
        result = {
            "agent": AGENT_NAME,
            "summary": summary,
            "evidence_id": "deploy-primary",
            "service": service,
            "match_source": match_source,
            "version": None,
            "previous_version": None,
            "deployed_at": None,
            "changes": [],
            "environment": None,
            "status": None,
        }
    else:
        changes = "; ".join(deployment["changes"])
        summary = (
            f"Latest production deployment {deployment['version']} at {deployment['deployed_at']} "
            f"replaced {deployment['previous_version']}. Changes: {changes}."
        )
        result = {
            "agent": AGENT_NAME,
            "summary": summary,
            "evidence_id": "deploy-primary",
            "service": deployment["service"],
            "match_source": match_source,
            "version": deployment["version"],
            "previous_version": deployment["previous_version"],
            "deployed_at": deployment["deployed_at"],
            "changes": list(deployment["changes"]),
            "environment": deployment["environment"],
            "status": deployment["status"],
        }

    return {
        "evidence": [
            make_evidence(
                SOURCE,
                "deployment",
                summary,
                result,
                timestamp=result.get("deployed_at"),
                evidence_id="deploy-primary",
            )
        ],
        "result": result,
    }
