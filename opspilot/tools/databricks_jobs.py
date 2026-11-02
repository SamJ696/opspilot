from __future__ import annotations

from typing import Any

from opspilot.tools.loaders import load_json
from opspilot.tools.targeting import score_name


def get_job_runs(
    job_name: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    rows = load_json("dataops/databricks_jobs.json")
    matched = []
    for row in rows:
        if job_name and row["job_name"] != job_name:
            continue
        if status and row["status"].upper() != status.upper():
            continue
        matched.append(row)
    matched.sort(key=lambda item: item["started_at"], reverse=True)
    return matched


def get_pipeline_logs(
    job_id: str | None = None,
    level: str | None = None,
) -> list[dict[str, Any]]:
    rows = load_json("dataops/pipeline_logs.json")
    matched = []
    for row in rows:
        if job_id and row["job_id"] != job_id:
            continue
        if level and row["level"].upper() != level.upper():
            continue
        matched.append(row)
    matched.sort(key=lambda item: item["timestamp"])
    return matched


def select_job(message: str) -> dict[str, Any] | None:
    jobs = get_job_runs()
    if not jobs:
        return None

    scored = [(score_name(message, job["job_name"]), job) for job in jobs]
    best_score = max(score for score, _job in scored)
    if best_score > 0:
        candidates = [job for score, job in scored if score == best_score]
    else:
        failed = [job for job in jobs if job["status"] == "FAILED"]
        candidates = failed or jobs

    return max(
        candidates,
        key=lambda job: (1 if job["status"] == "FAILED" else 0, job["started_at"]),
    )
