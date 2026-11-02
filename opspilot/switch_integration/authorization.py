from __future__ import annotations

from config import settings
from opspilot.switch_integration.incident_context import get_origin


def can_decide_incident(
    *,
    incident_id: str,
    room_id: str,
    actor_sender: str,
    actor_name: str,
    actor_role: str | None,
) -> tuple[bool, str]:
    origin = get_origin(incident_id)
    if origin is None:
        return False, f"Incident {incident_id} has no Switch origin metadata."

    if origin["room_id"] != room_id:
        return (
            False,
            f"Incident {incident_id} belongs to another room. "
            f"Approve or reject it in the room where it was opened.",
        )

    policy = settings.switch_approval_policy()
    role = (actor_role or "").lower()
    requester = origin["requester_sender"]

    if policy == "requester_only":
        if actor_sender != requester:
            return (
                False,
                f"Only the original reporter ({origin['requester_name']}) may "
                f"approve or reject {incident_id} under policy requester_only.",
            )
        return True, ""

    if policy == "allowlist":
        allowed = settings.switch_approver_senders()
        if actor_sender == requester or actor_sender in allowed:
            return True, ""
        return (
            False,
            f"Sender {actor_name} is not authorized to decide {incident_id}. "
            "Configure OPSPILOT_APPROVER_SENDERS or use policy requester_only.",
        )

    if policy == "role_based":
        allowed_roles = settings.switch_approver_roles()
        if actor_sender == requester:
            return True, ""
        if role and role in allowed_roles:
            return True, ""
        return (
            False,
            f"Sender {actor_name} lacks an authorized role for {incident_id}. "
            f"Allowed roles: {', '.join(sorted(allowed_roles))}.",
        )

    if policy == "room_members":
        return True, ""

    return False, f"Unknown approval policy: {policy}"
