from __future__ import annotations

from datetime import datetime, timezone

from opspilot.storage.database import connect, transaction


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def claim_message(message_id: str, incident_id: str | None = None) -> bool:
    """Return True if this message_id is new and was recorded."""
    if not message_id:
        return False
    with transaction() as connection:
        existing = connection.execute(
            "SELECT message_id FROM switch_message_dedupe WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        if existing is not None:
            return False
        connection.execute(
            """
            INSERT INTO switch_message_dedupe (message_id, incident_id, created_at)
            VALUES (?, ?, ?)
            """,
            (message_id, incident_id, _now()),
        )
    return True


def remember_thread(incident_id: str, room_id: str, thread_id: str) -> None:
    with transaction() as connection:
        connection.execute(
            """
            INSERT INTO incident_threads (incident_id, room_id, thread_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(incident_id) DO UPDATE SET
                room_id = excluded.room_id,
                thread_id = excluded.thread_id,
                updated_at = excluded.updated_at
            """,
            (incident_id, room_id, thread_id, _now()),
        )


def get_thread(incident_id: str) -> tuple[str, str] | None:
    row = connect().execute(
        "SELECT room_id, thread_id FROM incident_threads WHERE incident_id = ?",
        (incident_id,),
    ).fetchone()
    if row is None:
        return None
    return row["room_id"], row["thread_id"]
