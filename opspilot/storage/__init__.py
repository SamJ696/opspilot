"""SQLite persistence for incidents and the approval audit trail."""

from opspilot.storage.incident_repository import (
    add_audit,
    get_incident,
    list_audit,
    list_by_status,
    next_incident_id,
    upsert_incident,
)

__all__ = [
    "add_audit",
    "get_incident",
    "list_audit",
    "list_by_status",
    "next_incident_id",
    "upsert_incident",
]
