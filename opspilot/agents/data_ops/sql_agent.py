from __future__ import annotations

from typing import Any

from opspilot.schemas.evidence import make_evidence
from opspilot.tools.databricks_jobs import select_job
from opspilot.tools.sql_diagnostics import diagnose_schema

AGENT_NAME = "SQL and Data Quality Agent"
SOURCE = "sql_investigator"


def investigate_sql(message: str) -> dict[str, Any]:
    job = select_job(message)
    if job is None:
        summary = "No pipeline run was available for SQL diagnosis."
        diagnosis = _empty_diagnosis()
    else:
        diagnosis = diagnose_schema(job["job_name"], job.get("error"))
        diagnosis["job_id"] = job["job_id"]
        diagnosis["job_name"] = job["job_name"]
        summary = _summary(diagnosis, job)

    result = {
        "agent": AGENT_NAME,
        "summary": summary,
        "evidence_id": "sql-primary",
        **diagnosis,
    }
    return {
        "evidence": [
            make_evidence(SOURCE, "schema", summary, result, evidence_id="sql-primary")
        ],
        "result": result,
    }


def _summary(diagnosis: dict[str, Any], job: dict[str, Any]) -> str:
    if not diagnosis["applies"]:
        return (
            f"No schema contract matched {job['job_name']}. "
            f"Job error: {job.get('error') or 'none'}."
        )

    mapping = diagnosis["likely_mapping"]
    if mapping:
        source_column = next(iter(mapping.values()))
        expected_column = next(iter(mapping))
        quality = (
            f"{diagnosis['source_table']} quality checks passed."
            if diagnosis["source_quality_passed"]
            else f"{diagnosis['source_table']} quality checks did not all pass."
        )
        unrelated = diagnosis["unrelated_failures"]
        unrelated_text = ""
        if unrelated:
            names = ", ".join(
                f"{item['check']} on {item['table']}" for item in unrelated
            )
            unrelated_text = f" Unrelated failing check ignored: {names}."
        return (
            f"Expected column {expected_column} is missing from {diagnosis['source_table']}. "
            f"The source schema contains {source_column} instead. {quality}{unrelated_text}"
        )

    return (
        f"Schema contract for {diagnosis['contract_job']} does not explain "
        f"the {job['job_name']} error: {job.get('error') or 'none'}."
    )


def _empty_diagnosis() -> dict[str, Any]:
    return {
        "applies": False,
        "contract_job": None,
        "source_table": None,
        "expected_table": None,
        "source_columns": [],
        "expected_columns": [],
        "missing_columns": [],
        "source_only_columns": [],
        "error_column": None,
        "likely_mapping": {},
        "source_quality_checks": [],
        "source_quality_passed": False,
        "unrelated_failures": [],
        "job_id": None,
        "job_name": None,
    }
