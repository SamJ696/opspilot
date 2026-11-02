from __future__ import annotations

import re
from typing import Any

from opspilot.tools.loaders import load_json

_COLUMN_PATTERNS = (
    re.compile(r"column\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE),
    re.compile(r"cannot resolve\s+`?([A-Za-z_][A-Za-z0-9_]*)`?", re.IGNORECASE),
)


def get_schemas() -> dict[str, Any]:
    return load_json("dataops/schemas.json")


def get_quality_checks(table: str | None = None) -> list[dict[str, Any]]:
    rows = load_json("dataops/data_quality.json")
    if table is None:
        return list(rows)
    return [row for row in rows if row["table"] == table]


def extract_column(*texts: str | None) -> str | None:
    for text in texts:
        if not text:
            continue
        for pattern in _COLUMN_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1)
    return None


def similar_column(missing: str, source_columns: list[str]) -> str | None:
    missing_name = missing.lower()
    candidates = [
        column
        for column in source_columns
        if column.lower() != missing_name
        and (column.lower() in missing_name or missing_name in column.lower())
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


def diagnose_schema(job_name: str, error_text: str | None) -> dict[str, Any]:
    schemas = get_schemas()
    contract_job = schemas.get("job_name")
    source = schemas["source_table"]
    expected = schemas["expected_schema"]
    applies = contract_job in (None, job_name)
    source_columns = list(source["columns"])
    expected_columns = list(expected["columns"])
    missing = [column for column in expected_columns if column not in source_columns]
    source_only = [column for column in source_columns if column not in expected_columns]
    error_column = extract_column(error_text) if applies else None

    mapping: dict[str, str] = {}
    if applies and error_column and error_column in missing:
        match = similar_column(error_column, source_columns)
        if match:
            mapping[error_column] = match

    source_checks = get_quality_checks(source["name"]) if applies else []
    unrelated = [
        check
        for check in get_quality_checks()
        if check["table"] != source["name"] and check["status"].upper() != "PASSED"
    ]
    return {
        "applies": applies,
        "contract_job": contract_job,
        "source_table": source["name"],
        "expected_table": expected["name"],
        "source_columns": source_columns,
        "expected_columns": expected_columns,
        "missing_columns": missing if applies else [],
        "source_only_columns": source_only if applies else [],
        "error_column": error_column,
        "likely_mapping": mapping,
        "source_quality_checks": source_checks,
        "source_quality_passed": bool(source_checks)
        and all(check["status"].upper() == "PASSED" for check in source_checks),
        "unrelated_failures": unrelated if applies else [],
    }
