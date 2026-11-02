from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from opspilot.orchestrator.runner import (
    load_investigation,
    resume_investigation,
    stream_investigation,
)
from opspilot.reporting import opening_line, specialist_lines
from opspilot.storage.incident_repository import add_audit, get_incident
from opspilot.switch_integration.command_handler import CommandKind, HELP_TEXT, ParsedCommand
from opspilot.switch_integration.dedupe import remember_thread
from opspilot.switch_integration.message_sender import SwitchMessageSender
from opspilot.switch_integration.protocol_models import IncomingRoomMessage

logger = logging.getLogger(__name__)

NODE_LABELS = {
    "triage": "Triage completed.",
    "log_investigator": "Log investigation complete.",
    "deployment_investigator": "Deployment investigation complete.",
    "health_investigator": "Service health investigation complete.",
    "pipeline_investigator": "Pipeline investigation complete.",
    "sql_investigator": "SQL and data-quality investigation complete.",
    "root_cause": "Root cause identified.",
    "remediation": "Remediation prepared.",
}


class OpsPilotSwitchService:
    """Routes Switch commands to the existing LangGraph runner."""

    def __init__(self, sender: SwitchMessageSender) -> None:
        self._sender = sender
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="opspilot")

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def handle(self, incoming: IncomingRoomMessage, command: ParsedCommand) -> None:
        self._executor.submit(self._dispatch, incoming, command)

    def _dispatch(self, incoming: IncomingRoomMessage, command: ParsedCommand) -> None:
        try:
            if command.kind == CommandKind.HELP:
                self._send(incoming.room_id, HELP_TEXT)
                return
            if command.kind == CommandKind.STATUS:
                self._status(incoming.room_id, command.incident_id)
                return
            if command.kind == CommandKind.APPROVE:
                self._resume(incoming, command.incident_id, "approve")
                return
            if command.kind == CommandKind.REJECT:
                self._resume(incoming, command.incident_id, "reject")
                return
            if command.kind == CommandKind.INCIDENT:
                self._investigate(incoming, command.incident_text)
                return
        except Exception as exc:
            logger.exception("OpsPilot Switch handling failed")
            self._send(
                incoming.room_id,
                f"OpsPilot could not complete that request: {exc}",
            )

    def _send(self, room_id: str, content: str) -> None:
        self._sender.send_room_message(room_id, content)

    def _status(self, room_id: str, incident_id: str) -> None:
        stored = get_incident(incident_id)
        if stored is None:
            self._send(room_id, f"Incident {incident_id} was not found.")
            return
        lines = [
            f"Incident {incident_id}",
            f"Status: {stored['status']}",
            f"Severity: {stored.get('severity') or 'n/a'}",
            f"Type: {stored.get('issue_type') or 'n/a'}",
            f"Approval: {stored.get('approval_status') or 'n/a'}",
        ]
        if stored.get("root_cause"):
            lines.append(f"Root cause: {stored['root_cause'].get('hypothesis', '')}")
        if stored.get("final_report"):
            lines.append("")
            lines.append(stored["final_report"])
        self._send(room_id, "\n".join(lines))

    def _resume(
        self,
        incoming: IncomingRoomMessage,
        incident_id: str,
        decision: str,
    ) -> None:
        stored = get_incident(incident_id)
        if stored is None:
            self._send(incoming.room_id, f"Incident {incident_id} was not found.")
            return
        view = load_investigation(incident_id)
        if not view.get("pending_approval"):
            self._send(
                incoming.room_id,
                f"Incident {incident_id} is not waiting for approval (status: {stored['status']}).",
            )
            return
        add_audit(incident_id, "switch_decision", decision)
        view = resume_investigation(incident_id, decision)
        self._send(
            incoming.room_id,
            view.get("final_report") or f"Incident {incident_id} status: {view.get('status')}",
        )

    def _investigate(self, incoming: IncomingRoomMessage, text: str) -> None:
        self._send(incoming.room_id, "Incident received. Starting triage.")
        incident_id: str | None = None
        for event in stream_investigation(text):
            if event["type"] != "update":
                continue
            incident_id = event["incident_id"]
            for name, update in event["chunk"].items():
                if not isinstance(update, dict):
                    continue
                if name == "triage":
                    self._send(
                        incoming.room_id,
                        opening_line(
                            {
                                "incident_id": incident_id,
                                "issue_type": update.get("issue_type", ""),
                                "severity": update.get("severity", ""),
                            }
                        ),
                    )
                    continue
                label = NODE_LABELS.get(name)
                results = update.get("investigation_results") or {}
                if results:
                    for item in results.values():
                        self._send(
                            incoming.room_id,
                            f"- {item.get('agent', name)}: {item.get('summary', '')}",
                        )
                elif label:
                    self._send(incoming.room_id, label)

                if name == "root_cause" and update.get("root_cause"):
                    hypothesis = update["root_cause"].get("hypothesis", "")
                    confidence = update.get("confidence")
                    confidence_text = (
                        "n/a" if confidence is None else f"{round(confidence * 100)}%"
                    )
                    self._send(
                        incoming.room_id,
                        f"Root cause hypothesis: {hypothesis}\nConfidence: {confidence_text}.",
                    )

                if name == "remediation":
                    action = update.get("recommended_action") or {}
                    if action.get("summary"):
                        self._send(
                            incoming.room_id,
                            f"Recommended action: {action['summary']}",
                        )
                    if update.get("approval_request"):
                        self._send(incoming.room_id, update["approval_request"])

        if not incident_id:
            self._send(incoming.room_id, "OpsPilot did not create an incident.")
            return

        remember_thread(incident_id, incoming.room_id, incoming.reply_thread_id)
        final = load_investigation(incident_id)
        if final.get("final_report") and not final.get("pending_approval"):
            if final.get("status") in {"UNCLASSIFIED", "ROOT_CAUSE_IDENTIFIED"}:
                self._send(incoming.room_id, final["final_report"])
        elif not final.get("pending_approval"):
            for line in specialist_lines(final):
                pass  # already streamed
            if final.get("status") == "UNCLASSIFIED":
                self._send(incoming.room_id, final.get("final_report", "Unable to classify incident."))
