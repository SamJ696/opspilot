from __future__ import annotations

from typing import Any

SOURCE_ORDER = (
    "log_investigator",
    "deployment_investigator",
    "health_investigator",
    "pipeline_investigator",
    "sql_investigator",
)

ISSUE_LABELS = {
    "APPLICATION": "ApplicationOps",
    "DATA_PIPELINE": "DataOps",
    "UNKNOWN": "Unknown",
}


def issue_label(issue_type: str) -> str:
    return ISSUE_LABELS.get(issue_type, issue_type or "Unknown")


def opening_line(view: dict[str, Any]) -> str:
    label = issue_label(view.get("issue_type", ""))
    if view.get("issue_type") == "APPLICATION":
        next_step = "Starting parallel investigation."
    elif view.get("issue_type") == "DATA_PIPELINE":
        next_step = "Starting pipeline and SQL investigation."
    else:
        next_step = "No specialist workflow matched this report."
    return (
        f"Incident {view.get('incident_id')} created. "
        f"Classification: {label}. Severity: {view.get('severity')}. {next_step}"
    )


def specialist_lines(view: dict[str, Any]) -> list[str]:
    results = view.get("investigation_results") or {}
    lines: list[str] = []
    seen: set[str] = set()
    for key in SOURCE_ORDER:
        item = results.get(key)
        if item:
            lines.append(f"{item.get('agent', key)}: {item.get('summary', '')}")
            seen.add(key)
    for key, item in results.items():
        if key not in seen:
            lines.append(f"{item.get('agent', key)}: {item.get('summary', '')}")
    return lines


def ordered_evidence(view: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = list(view.get("evidence") or [])
    rank = {source: index for index, source in enumerate(SOURCE_ORDER)}
    evidence.sort(key=lambda item: rank.get(item.get("source", ""), len(rank)))
    return evidence


def build_approval_request(state: dict[str, Any]) -> str:
    cause = state.get("root_cause") or {}
    action = state.get("recommended_action") or {}
    confidence = state.get("confidence") or 0
    evidence_lines = "\n".join(
        f"- {item.get('summary', '')}" for item in ordered_evidence(state)
    )
    return (
        f"Root cause hypothesis: {cause.get('hypothesis', 'Not identified.')}\n\n"
        f"Evidence:\n{evidence_lines}\n\n"
        f"Recommended action:\n{action.get('summary', 'No action.')}\n\n"
        f"Confidence: {round(confidence * 100)}%.\n\n"
        "This action requires approval.\n"
        "Approve or reject?"
    )


def build_rejection_report(state: dict[str, Any]) -> str:
    action = state.get("recommended_action") or {}
    return (
        f"Incident {state.get('incident_id')} remains open.\n"
        "Recovery was not executed because the action was rejected.\n"
        f"Next recommended action: {action.get('summary', 'Review the evidence before making a change.')}"
    )


def build_final_report(state: dict[str, Any]) -> str:
    action = state.get("recommended_action") or {}
    cause = state.get("root_cause") or {}
    if action.get("action_type") in {None, "", "none"}:
        return (
            f"Incident {state.get('incident_id')} has no automated remediation.\n"
            f"Root cause: {cause.get('hypothesis', 'Not identified.')}\n"
            f"{action.get('summary', '')}"
        )

    verification = state.get("verification_result") or {}
    recovery = state.get("recovery_result") or {}
    passed = bool(verification.get("passed"))
    observed = verification.get("observed") or {}
    if action.get("action_type") == "rollback" and passed:
        headline = (
            "Rollback simulation completed. Health verification passed. "
            f"Simulated error rate returned to the pre-deployment baseline "
            f"({observed.get('error_rate_percent')}%). Incident resolved."
        )
    elif action.get("action_type") == "pipeline_correction" and passed:
        headline = (
            "Simulated correction and pipeline retry completed. "
            "Verification passed. Incident resolved."
        )
    elif passed:
        headline = f"Incident {state.get('incident_id')} resolved."
    else:
        headline = (
            f"Incident {state.get('incident_id')} recovery failed verification. "
            f"{verification.get('reason', '')}"
        ).strip()

    investigation = "\n".join(f"- {line}" for line in specialist_lines(state))
    confidence = state.get("confidence")
    confidence_text = "n/a" if confidence is None else f"{round(confidence * 100)}%"
    return (
        f"{headline}\n\n"
        f"Investigation:\n{investigation}\n\n"
        f"Root cause: {cause.get('hypothesis', '')}\n"
        f"Confidence: {confidence_text}.\n"
        f"Action: {action.get('summary', '')}\n"
        f"Recovery: {recovery.get('status', 'NOT_RUN')}."
    )
