from __future__ import annotations

from typing import Any

from opspilot.schemas.remediation import RecommendedAction
from opspilot.tools.recovery_tools import (
    simulate_pipeline_recovery,
    simulate_rollback,
    verify_pipeline,
    verify_rollback,
)

APPLICATION_REQUIRED = {
    "repeated_errors",
    "started_after_deploy",
    "deploy_change_matches_error",
}
DATA_REQUIRED = {"job_failed", "missing_column", "source_column_rename"}


def plan_recovery(
    issue_type: str,
    root_cause: dict[str, Any],
    investigation_results: dict[str, Any],
    confidence: float | None,
) -> dict[str, Any]:
    matched = {
        signal["name"]
        for signal in root_cause.get("signals", [])
        if signal.get("matched")
    }
    score = confidence or 0
    if issue_type == "APPLICATION" and APPLICATION_REQUIRED <= matched and score >= 0.7:
        deploy = investigation_results.get("deployment_investigator") or {}
        if deploy.get("service") and deploy.get("version") and deploy.get("previous_version"):
            return RecommendedAction(
                action_type="rollback",
                summary=(
                    f"Rollback {deploy['service']} from {deploy['version']} "
                    f"to {deploy['previous_version']}."
                ),
                parameters={
                    "service": deploy["service"],
                    "from_version": deploy["version"],
                    "to_version": deploy["previous_version"],
                    "deployed_at": deploy.get("deployed_at"),
                },
                requires_approval=True,
                risk="HIGH",
            ).model_dump()

    if issue_type == "DATA_PIPELINE" and DATA_REQUIRED <= matched and score >= 0.7:
        pipeline = investigation_results.get("pipeline_investigator") or {}
        sql = investigation_results.get("sql_investigator") or {}
        mapping = sql.get("likely_mapping") or {}
        if pipeline.get("job_id") and mapping:
            expected_column, source_column = next(iter(mapping.items()))
            task = pipeline.get("failed_task") or "the failed task"
            return RecommendedAction(
                action_type="pipeline_correction",
                summary=(
                    f"Update the {task} mapping so {expected_column} reads source column "
                    f"{source_column}, then retry {pipeline.get('job_name')} ({pipeline['job_id']})."
                ),
                parameters={
                    "job_id": pipeline["job_id"],
                    "job_name": pipeline.get("job_name"),
                    "task": pipeline.get("failed_task"),
                    "mapping": mapping,
                },
                requires_approval=True,
                risk="MEDIUM",
            ).model_dump()

    return RecommendedAction(
        action_type="none",
        summary="No safe automated remediation was identified. Keep the incident open for manual investigation.",
        parameters={},
        requires_approval=False,
        risk="LOW",
    ).model_dump()


def execute_recovery(action: dict[str, Any], *, approved: bool) -> dict[str, Any]:
    """Run a simulated recovery. Callers must already have a matching approval."""
    if not approved:
        raise PermissionError("Recovery requires explicit approval")

    kind = action.get("action_type")
    parameters = action.get("parameters") or {}
    if kind == "rollback":
        return simulate_rollback(
            service=parameters["service"],
            from_version=parameters["from_version"],
            to_version=parameters["to_version"],
            approved=True,
        )
    if kind == "pipeline_correction":
        return simulate_pipeline_recovery(
            job_id=parameters["job_id"],
            mapping=parameters["mapping"],
            task=parameters.get("task"),
            approved=True,
        )
    raise ValueError(f"Unsupported recovery action: {kind}")


def verify_recovery(action: dict[str, Any], recovery_result: dict[str, Any] | None) -> dict[str, Any]:
    if not recovery_result or recovery_result.get("status") not in {"COMPLETED", "ALREADY_APPLIED"}:
        return {
            "passed": False,
            "observed": {},
            "reason": "Recovery did not complete",
        }

    parameters = action.get("parameters") or {}
    kind = action.get("action_type")
    if kind == "rollback":
        return verify_rollback(
            service=parameters["service"],
            to_version=parameters["to_version"],
            deployed_at=parameters.get("deployed_at"),
        )
    if kind == "pipeline_correction":
        return verify_pipeline(parameters["job_id"], parameters["mapping"])
    return {"passed": False, "observed": {}, "reason": f"Unknown action {kind}"}
