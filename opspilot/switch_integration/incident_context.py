from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

from opspilot.storage.database import connect, transaction

_claim_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def remember_origin(
    incident_id: str,
    *,
    room_id: str,
    requester_sender: str,
    requester_name: str,
    requester_role: str | None,
    thread_id: str,
) -> None:
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO incident_origin (
                incident_id, room_id, requester_sender, requester_name,
                requester_role, thread_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(incident_id) DO UPDATE SET
                room_id = excluded.room_id,
                requester_sender = excluded.requester_sender,
                requester_name = excluded.requester_name,
                requester_role = excluded.requester_role,
                thread_id = excluded.thread_id,
                created_at = excluded.created_at
            """,
            (
                incident_id,
                room_id,
                requester_sender,
                requester_name,
                requester_role,
                thread_id,
                _now(),
            ),
        )


def get_origin(incident_id: str) -> dict[str, str] | None:
    row = connect().execute(
        """
        SELECT incident_id, room_id, requester_sender, requester_name,
               requester_role, thread_id
        FROM incident_origin
        WHERE incident_id = ?
        """,
        (incident_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "incident_id": row["incident_id"],
        "room_id": row["room_id"],
        "requester_sender": row["requester_sender"],
        "requester_name": row["requester_name"],
        "requester_role": row["requester_role"] or "",
        "thread_id": row["thread_id"],
    }


class ApprovalClaimResult:
    __slots__ = ("ok", "reason")

    def __init__(self, ok: bool, reason: str = "") -> None:
        self.ok = ok
        self.reason = reason


def try_claim_approval_decision(
    incident_id: str,
    *,
    message_id: str,
    decision: str,
    actor_sender: str,
    actor_name: str,
    room_id: str,
) -> ApprovalClaimResult:
    """Atomically record one approval decision per incident."""
    with _claim_lock, transaction() as connection:
        existing = connection.execute(
            "SELECT decision FROM switch_approval_decisions WHERE incident_id = ?",
            (incident_id,),
        ).fetchone()
        if existing is not None:
            return ApprovalClaimResult(
                False,
                f"Incident {incident_id} already has decision '{existing['decision']}'.",
            )

        try:
            connection.execute(
                """
                INSERT INTO switch_approval_decisions (
                    incident_id, message_id, decision, actor_sender,
                    actor_name, room_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    message_id,
                    decision,
                    actor_sender,
                    actor_name,
                    room_id,
                    _now(),
                ),
            )
        except sqlite3.IntegrityError:
            return ApprovalClaimResult(
                False,
                f"Incident {incident_id} is already being processed.",
            )
    return ApprovalClaimResult(True)
