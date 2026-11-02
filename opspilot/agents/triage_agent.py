from __future__ import annotations

import re


APPLICATION_KEYWORDS = (
    "api",
    "server",
    "http 500",
    "deployment",
    "production",
    "latency",
    "error rate",
    "service",
)

DATA_KEYWORDS = (
    "databricks",
    "pipeline",
    "sql",
    "etl",
    "job failed",
    "schema",
    "data quality",
)


def classify_issue(message: str) -> dict:
    message_lower = message.lower()

    application_score = sum(keyword in message_lower for keyword in APPLICATION_KEYWORDS)
    data_score = sum(keyword in message_lower for keyword in DATA_KEYWORDS)

    if application_score > data_score:
        issue_type = "APPLICATION"
    elif data_score > application_score:
        issue_type = "DATA_PIPELINE"
    else:
        issue_type = "UNKNOWN"

    return {
        "issue_type": issue_type,
        "application_score": application_score,
        "data_score": data_score,
    }


def assess_severity(message: str, issue_type: str) -> str:
    text = message.lower()
    if any(token in text for token in ("outage", "sev-1", "sev1", "critical")) or re.search(
        r"\bdown\b", text
    ):
        return "CRITICAL"
    if issue_type == "UNKNOWN":
        return "LOW"
    if any(token in text for token in ("500", "failed", "failure", "errors", "exception")):
        return "HIGH"
    return "MEDIUM"


def triage_agent(message: str) -> dict:
    classification = classify_issue(message)
    return {
        **classification,
        "severity": assess_severity(message, classification["issue_type"]),
        "status": "TRIAGING",
    }
