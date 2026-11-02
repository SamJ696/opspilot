from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from config.settings import checkpoint_path
from opspilot.orchestrator.checkpointer import reset_checkpointer
from opspilot.orchestrator.graph import get_app, reset_compiled_graph
from opspilot.orchestrator.state import blank_state
from opspilot.storage.database import close_connections
from opspilot.storage.incident_repository import next_incident_id

APPROVE = {"approve", "approved", "yes", "y"}
REJECT = {"reject", "rejected", "no", "n"}


def reset_caches() -> None:
    reset_compiled_graph()
    reset_checkpointer()
    close_connections()


def normalize_decision(decision: str) -> str:
    value = decision.strip().lower()
    if value in APPROVE:
        return "approved"
    if value in REJECT:
        return "rejected"
    raise ValueError("Decision must be approve or reject")


def thread_config(incident_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": incident_id}}


def present(snapshot: Any) -> dict[str, Any]:
    values = dict(snapshot.values or {})
    interrupts = tuple(snapshot.interrupts or ())
    values["pending_approval"] = bool(interrupts)
    values["interrupt"] = interrupts[0].value if interrupts else None
    return values


def _invoke(app: Any, payload: Any, config: dict[str, Any]) -> None:
    try:
        app.invoke(payload, config)
    except GraphInterrupt:
        return


def start_investigation(message: str, incident_id: str | None = None) -> dict[str, Any]:
    incident_id = incident_id or next_incident_id()
    config = thread_config(incident_id)
    app = get_app()
    _invoke(app, blank_state(message, incident_id), config)
    return present(app.get_state(config))


def stream_investigation(
    message: str,
    incident_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    incident_id = incident_id or next_incident_id()
    config = thread_config(incident_id)
    app = get_app()
    try:
        for chunk in app.stream(
            blank_state(message, incident_id),
            config,
            stream_mode="updates",
        ):
            yield {"type": "update", "chunk": chunk, "incident_id": incident_id}
    except GraphInterrupt:
        pass
    yield {"type": "final", "view": present(app.get_state(config)), "incident_id": incident_id}


def load_investigation(incident_id: str) -> dict[str, Any]:
    return present(get_app().get_state(thread_config(incident_id)))


def resume_investigation(incident_id: str, decision: str) -> dict[str, Any]:
    normalized = normalize_decision(decision)
    app = get_app()
    config = thread_config(incident_id)
    snapshot = app.get_state(config)
    if not snapshot.interrupts:
        raise RuntimeError(f"Incident {incident_id} is not waiting for approval")
    _invoke(
        app,
        Command(resume={"decision": normalized, "incident_id": incident_id}),
        config,
    )
    return present(app.get_state(config))


def checkpoint_file() -> str:
    return str(checkpoint_path())
