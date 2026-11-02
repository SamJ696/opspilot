from __future__ import annotations

from datetime import datetime
from typing import Any

from opspilot.schemas.remediation import RootCause

APPLICATION_WEIGHTS = {
    "repeated_errors": 15,
    "identified_error": 12,
    "started_after_deploy": 20,
    "deploy_change_matches_error": 25,
    "metrics_degraded": 20,
}

DATA_WEIGHTS = {
    "job_failed": 20,
    "task_log_matches_error": 15,
    "missing_column": 25,
    "source_column_rename": 22,
    "relevant_quality_checks_passed": 10,
}

CHANGE_TERMS = ("pool", "connection", "timeout", "memory", "deadlock", "schema")


def analyze(issue_type: str, investigation_results: dict[str, Any]) -> dict[str, Any]:
    if issue_type == "APPLICATION":
        return _analyze_application(investigation_results)
    if issue_type == "DATA_PIPELINE":
        return _analyze_data(investigation_results)
    cause = RootCause(
        hypothesis="The report did not match an ApplicationOps or DataOps workflow.",
        explanation="Triage found equal or empty evidence for both workflows, so no specialist investigation ran.",
        supporting_evidence_ids=[],
        signals=[],
    )
    return {"root_cause": cause.model_dump(), "confidence": 0.0}


def _analyze_application(results: dict[str, Any]) -> dict[str, Any]:
    logs = results.get("log_investigator") or {}
    deploy = results.get("deployment_investigator") or {}
    health = results.get("health_investigator") or {}
    top_error = logs.get("top_error") or ""
    changes = deploy.get("changes") or []
    matched_terms = _matching_terms(top_error, changes)
    delta = _minutes_between(deploy.get("deployed_at"), logs.get("first_error_at"))
    same_service = bool(logs.get("service") and logs.get("service") == deploy.get("service") == health.get("service"))

    signals = [
        _signal(
            "repeated_errors",
            APPLICATION_WEIGHTS["repeated_errors"],
            same_service and (logs.get("error_count") or 0) >= 3,
            f"{logs.get('error_count', 0)} ERROR events for {logs.get('service')}",
        ),
        _signal(
            "identified_error",
            APPLICATION_WEIGHTS["identified_error"],
            same_service and bool(top_error),
            top_error or "No dominant error message",
        ),
        _signal(
            "started_after_deploy",
            APPLICATION_WEIGHTS["started_after_deploy"],
            same_service and delta is not None and 0 <= delta <= 60,
            "First error was not within 60 minutes after the latest deployment"
            if delta is None
            else f"First error arrived {delta:.1f} minutes after deployment",
        ),
        _signal(
            "deploy_change_matches_error",
            APPLICATION_WEIGHTS["deploy_change_matches_error"],
            same_service and bool(matched_terms),
            "Deployment changes overlap the error text on: " + ", ".join(matched_terms)
            if matched_terms
            else "Deployment changes do not overlap the top error",
        ),
        _signal(
            "metrics_degraded",
            APPLICATION_WEIGHTS["metrics_degraded"],
            same_service and bool(health.get("degraded")),
            (
                f"Error rate {health.get('error_rate_percent')}%, "
                f"latency {health.get('average_latency_ms')} ms, healthy={health.get('healthy')}"
            ),
        ),
    ]
    confidence = _confidence(signals)
    service = logs.get("service") or deploy.get("service") or "the service"
    version = deploy.get("version")
    if "pool" in matched_terms and version:
        hypothesis = (
            f"Database connection pool exhaustion on {service} started after deployment "
            f"{version}, which changed connection pool settings."
        )
    elif version and top_error:
        hypothesis = (
            f"{service} errors increased after deployment {version}. Top error: {top_error}."
        )
    else:
        hypothesis = f"No corroborated application failure was found for {service}."

    versions = logs.get("versions") or []
    version_note = ""
    if version and versions and all(item == version for item in versions):
        version_note = f" All {logs.get('error_count')} error logs are tagged with {version}."

    explanation = _explanation(signals, [logs, deploy, health]) + version_note
    evidence_ids = [
        item.get("evidence_id")
        for item in (logs, deploy, health)
        if item.get("evidence_id")
    ]
    cause = RootCause(
        hypothesis=hypothesis,
        explanation=explanation.strip(),
        supporting_evidence_ids=evidence_ids,
        signals=signals,
    )
    return {"root_cause": cause.model_dump(), "confidence": confidence}


def _analyze_data(results: dict[str, Any]) -> dict[str, Any]:
    pipeline = results.get("pipeline_investigator") or {}
    sql = results.get("sql_investigator") or {}
    error_column = sql.get("error_column")
    log_messages = pipeline.get("log_messages") or []
    logs_match = bool(error_column) and any(error_column in message for message in log_messages)
    mapping = sql.get("likely_mapping") or {}

    signals = [
        _signal(
            "job_failed",
            DATA_WEIGHTS["job_failed"],
            pipeline.get("status") == "FAILED",
            f"{pipeline.get('job_id')} status is {pipeline.get('status')}",
        ),
        _signal(
            "task_log_matches_error",
            DATA_WEIGHTS["task_log_matches_error"],
            logs_match,
            "Task logs mention the unresolved column"
            if logs_match
            else "Task logs do not mention a missing column from the schema contract",
        ),
        _signal(
            "missing_column",
            DATA_WEIGHTS["missing_column"],
            bool(error_column) and error_column in (sql.get("missing_columns") or []),
            f"Column {error_column} is absent from {sql.get('source_table')}"
            if error_column
            else "The job error does not name a column in the schema contract",
        ),
        _signal(
            "source_column_rename",
            DATA_WEIGHTS["source_column_rename"],
            bool(mapping),
            f"Likely mapping {mapping}" if mapping else "No similar source column was found",
        ),
        _signal(
            "relevant_quality_checks_passed",
            DATA_WEIGHTS["relevant_quality_checks_passed"],
            bool(sql.get("source_quality_passed")),
            f"{sql.get('source_table')} quality checks passed"
            if sql.get("source_quality_passed")
            else "Relevant quality checks did not pass or did not apply",
        ),
    ]
    confidence = _confidence(signals)
    if mapping and pipeline.get("failed_task"):
        expected_column, source_column = next(iter(mapping.items()))
        hypothesis = (
            f"Pipeline {pipeline.get('job_name')} failed in task {pipeline.get('failed_task')} "
            f"because column {expected_column} is not in {sql.get('source_table')}. "
            f"The source column {source_column} is the likely rename."
        )
    elif pipeline.get("status") == "FAILED":
        hypothesis = (
            f"Pipeline {pipeline.get('job_name')} failed in task {pipeline.get('failed_task')} "
            f"with error: {pipeline.get('error') or 'unknown'}."
        )
    else:
        hypothesis = "No failed pipeline run was corroborated."

    cause = RootCause(
        hypothesis=hypothesis,
        explanation=_explanation(signals, [pipeline, sql]).strip(),
        supporting_evidence_ids=[
            item["evidence_id"]
            for item in (pipeline, sql)
            if item.get("evidence_id")
        ],
        signals=signals,
    )
    return {"root_cause": cause.model_dump(), "confidence": confidence}


def _signal(name: str, weight: int, matched: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "weight": weight, "matched": matched, "detail": detail}


def _confidence(signals: list[dict[str, Any]]) -> float:
    return round(sum(signal["weight"] for signal in signals if signal["matched"]) / 100, 2)


def _explanation(signals: list[dict[str, Any]], results: list[dict[str, Any]]) -> str:
    lines = [result["summary"] for result in results if result.get("summary")]
    matched = [signal["detail"] for signal in signals if signal["matched"]]
    if matched:
        lines.append("Matched signals: " + "; ".join(matched) + ".")
    else:
        lines.append("No corroborating signals met the investigation threshold.")
    return " ".join(lines)


def _matching_terms(error: str, changes: list[str]) -> list[str]:
    haystack = " ".join(changes).lower()
    needle = error.lower()
    return [term for term in CHANGE_TERMS if term in needle and term in haystack]


def _minutes_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        left = datetime.fromisoformat(start.replace("Z", "+00:00"))
        right = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (right - left).total_seconds() / 60
