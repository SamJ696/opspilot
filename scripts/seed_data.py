"""Validate the synthetic fixtures and print what the investigators can see."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opspilot.tools.databricks_jobs import get_job_runs, get_pipeline_logs
from opspilot.tools.deployment_history import get_deployments
from opspilot.tools.log_search import search_logs
from opspilot.tools.service_metrics import get_metrics
from opspilot.tools.sql_diagnostics import get_quality_checks, get_schemas


def main() -> None:
    logs = search_logs(level="ERROR")
    print(f"Application error logs: {len(logs)}")
    print(f"Deployments: {len(get_deployments())}")
    print(f"Metric samples: {len(get_metrics())}")
    print(f"Job runs: {len(get_job_runs())}")
    print(f"Pipeline logs: {len(get_pipeline_logs())}")
    schema = get_schemas()
    print(
        f"Schema contract: {schema['job_name']} "
        f"{schema['source_table']['name']} -> {schema['expected_schema']['name']}"
    )
    print(f"Data quality checks: {len(get_quality_checks())}")


if __name__ == "__main__":
    main()
