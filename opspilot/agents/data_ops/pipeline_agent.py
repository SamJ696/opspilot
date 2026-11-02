from __future__ import annotations

from typing import Any

from opspilot.schemas.evidence import make_evidence
from opspilot.tools.databricks_jobs import get_pipeline_logs, select_job

AGENT_NAME = "Pipeline Investigator"
SOURCE = "pipeline_investigator"


def investigate_pipeline(message: str) -> dict[str, Any]:
    job = select_job(message)
    if job is None:
        summary = "No Databricks job runs were found."
        result = _result(summary)
        return {"evidence": [_evidence(summary, result)], "result": result}

    error_logs = get_pipeline_logs(job_id=job["job_id"], level="ERROR")
    if job.get("run_id"):
        # Fixture logs are job-scoped. Keep errors at or after this run's start.
        error_logs = [
            entry
            for entry in error_logs
            if entry["timestamp"] >= job["started_at"]
        ]
    log_messages = [entry["message"] for entry in error_logs]
    failed_task = job.get("failed_task") or "n/a"
    error = job.get("error") or "none"
    summary = (
        f"Job {job['job_name']} ({job['job_id']}) run {job['run_id']} {job['status']}. "
        f"Failed task: {failed_task}. Error: {error}."
    )
    result = _result(
        summary,
        job_id=job["job_id"],
        job_name=job["job_name"],
        run_id=job["run_id"],
        status=job["status"],
        failed_task=job.get("failed_task"),
        error=job.get("error") or "",
        started_at=job["started_at"],
        ended_at=job.get("ended_at"),
        log_messages=log_messages,
    )
    return {"evidence": [_evidence(summary, result, job.get("ended_at"))], "result": result}


def _result(summary: str, **details: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "agent": AGENT_NAME,
        "summary": summary,
        "evidence_id": "pipeline-primary",
        "job_id": None,
        "job_name": None,
        "run_id": None,
        "status": None,
        "failed_task": None,
        "error": "",
        "started_at": None,
        "ended_at": None,
        "log_messages": [],
    }
    result.update(details)
    return result


def _evidence(summary: str, result: dict[str, Any], timestamp: str | None = None) -> dict[str, Any]:
    return make_evidence(
        SOURCE,
        "job",
        summary,
        result,
        timestamp=timestamp,
        evidence_id="pipeline-primary",
    )
