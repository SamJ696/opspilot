from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from opspilot.schemas.incident import Incident
from opspilot.storage.database import connect, transaction


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def next_incident_id() -> str:
    with transaction() as connection:
        row = connection.execute(
            "SELECT value FROM incident_counter WHERE id = 1"
        ).fetchone()
        value = int(row["value"]) + 1
        connection.execute(
            "UPDATE incident_counter SET value = ? WHERE id = 1",
            (value,),
        )
    return f"INC-{value}"


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "incident_id": row["incident_id"],
        "user_message": row["user_message"],
        "issue_type": row["issue_type"] or "",
        "severity": row["severity"] or "",
        "status": row["status"],
        "evidence": _loads(row["evidence_json"], []),
        "investigation_results": _loads(row["investigation_json"], {}),
        "root_cause": _loads(row["root_cause_json"], None),
        "confidence": row["confidence"],
        "recommended_action": _loads(row["recommended_action_json"], None),
        "approval_status": row["approval_status"] or "PENDING",
        "approval_request": row["approval_request"] or "",
        "recovery_result": _loads(row["recovery_json"], None),
        "verification_result": _loads(row["verification_json"], None),
        "final_report": row["final_report"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_incident(incident_id: str) -> dict[str, Any] | None:
    row = connect().execute(
        "SELECT * FROM incidents WHERE incident_id = ?",
        (incident_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def upsert_incident(state: dict[str, Any]) -> None:
    existing = get_incident(state["incident_id"])
    now = _now()
    record = Incident(
        incident_id=state["incident_id"],
        user_message=state.get("user_message", ""),
        issue_type=state.get("issue_type") or "",
        severity=state.get("severity") or "",
        status=state.get("status") or "NEW",
        evidence=list(state.get("evidence") or []),
        investigation_results=dict(state.get("investigation_results") or {}),
        root_cause=state.get("root_cause"),
        confidence=state.get("confidence"),
        recommended_action=state.get("recommended_action"),
        approval_status=state.get("approval_status") or "PENDING",
        approval_request=state.get("approval_request") or "",
        recovery_result=state.get("recovery_result"),
        verification_result=state.get("verification_result"),
        final_report=state.get("final_report") or "",
        created_at=existing["created_at"] if existing else now,
        updated_at=now,
    )
    payload = record.model_dump()
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO incidents (
                incident_id, user_message, issue_type, severity, status,
                evidence_json, investigation_json, root_cause_json, confidence,
                recommended_action_json, approval_status, approval_request,
                recovery_json, verification_json, final_report, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(incident_id) DO UPDATE SET
                user_message = excluded.user_message,
                issue_type = excluded.issue_type,
                severity = excluded.severity,
                status = excluded.status,
                evidence_json = excluded.evidence_json,
                investigation_json = excluded.investigation_json,
                root_cause_json = excluded.root_cause_json,
                confidence = excluded.confidence,
                recommended_action_json = excluded.recommended_action_json,
                approval_status = excluded.approval_status,
                approval_request = excluded.approval_request,
                recovery_json = excluded.recovery_json,
                verification_json = excluded.verification_json,
                final_report = excluded.final_report,
                updated_at = excluded.updated_at
            """,
            (
                payload["incident_id"],
                payload["user_message"],
                payload["issue_type"],
                payload["severity"],
                payload["status"],
                json.dumps(payload["evidence"]),
                json.dumps(payload["investigation_results"]),
                json.dumps(payload["root_cause"]) if payload["root_cause"] is not None else None,
                payload["confidence"],
                json.dumps(payload["recommended_action"])
                if payload["recommended_action"] is not None
                else None,
                payload["approval_status"],
                payload["approval_request"],
                json.dumps(payload["recovery_result"])
                if payload["recovery_result"] is not None
                else None,
                json.dumps(payload["verification_result"])
                if payload["verification_result"] is not None
                else None,
                payload["final_report"],
                payload["created_at"],
                payload["updated_at"],
            ),
        )


def add_audit(incident_id: str, action: str, detail: str) -> None:
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO audit_log (incident_id, action, detail, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (incident_id, action, detail, _now()),
        )


def list_by_status(status: str) -> list[dict[str, Any]]:
    rows = connect().execute(
        "SELECT * FROM incidents WHERE status = ? ORDER BY created_at",
        (status,),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def list_audit(incident_id: str) -> list[dict[str, str]]:
    rows = connect().execute(
        """
        SELECT action, detail, created_at
        FROM audit_log
        WHERE incident_id = ?
        ORDER BY id
        """,
        (incident_id,),
    ).fetchall()
    return [
        {"action": row["action"], "detail": row["detail"], "created_at": row["created_at"]}
        for row in rows
    ]
