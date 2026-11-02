import os
import unittest
from unittest.mock import MagicMock, patch

from opspilot.switch_integration.adapter import SwitchAdapter
from opspilot.switch_integration.command_handler import CommandKind, parse_command
from opspilot.switch_integration.connection import build_ws_url
from opspilot.switch_integration.dedupe import claim_message
from opspilot.switch_integration.event_handler import SwitchEventHandler
from opspilot.switch_integration.protocol_models import IncomingRoomMessage, WebSocketFrame
from opspilot.switch_integration.service import OpsPilotSwitchService
from tests.base import IsolatedCase

CHECKOUT = "Our checkout API is returning HTTP 500 errors after the latest production deployment."
DATABRICKS = "Our Databricks customer analytics pipeline failed because of a SQL schema mismatch."


def _incoming(body: str, *, room: str = "room-1", message_id: str = "msg-1") -> IncomingRoomMessage:
    return IncomingRoomMessage(
        room_id=room,
        message_id=message_id,
        body=body,
        sender="user-1",
        sender_name="Samyak",
        sender_kind="user",
        addressed=True,
        thread_id=None,
        reply_thread_id=message_id,
    )


def _frame(body: str, **kwargs) -> WebSocketFrame:
    incoming = _incoming(body, **kwargs)
    return WebSocketFrame(
        event="message",
        data={
            "type": "message",
            "room_id": incoming.room_id,
            "payload": {
                "addressed": incoming.addressed,
                "sender": incoming.sender,
                "sender_name": incoming.sender_name,
                "sender_kind": incoming.sender_kind,
                "message_id": incoming.message_id,
                "body": incoming.body,
                "timestamp": 1,
                "thread_id": incoming.thread_id,
            },
        },
    )


class CommandParserTests(unittest.TestCase):
    def test_application_incident(self) -> None:
        cmd = parse_command("@opspilot " + CHECKOUT)
        self.assertEqual(cmd.kind, CommandKind.INCIDENT)
        self.assertIn("checkout API", cmd.incident_text)

    def test_data_incident(self) -> None:
        cmd = parse_command("!opspilot " + DATABRICKS)
        self.assertEqual(cmd.kind, CommandKind.INCIDENT)

    def test_approve_requires_incident_id(self) -> None:
        self.assertEqual(parse_command("approve").kind, CommandKind.IGNORE)
        cmd = parse_command("approve INC-1001")
        self.assertEqual(cmd.kind, CommandKind.APPROVE)
        self.assertEqual(cmd.incident_id, "INC-1001")

    def test_bare_approve_word_is_not_approval(self) -> None:
        self.assertEqual(parse_command("please approve rollback").kind, CommandKind.IGNORE)


class EventHandlerTests(IsolatedCase):
    def test_agent_messages_are_ignored(self) -> None:
        seen = []
        handler = SwitchEventHandler(allowed_rooms={"room-1"}, on_command=lambda *args: seen.append(args))
        incoming = _incoming("approve INC-1001")
        incoming = incoming.model_copy(update={"sender_kind": "agent"})
        handler.handle_incoming(incoming)
        self.assertEqual(seen, [])

    def test_unapproved_room_is_ignored(self) -> None:
        seen = []
        handler = SwitchEventHandler(allowed_rooms={"room-allowed"}, on_command=lambda *args: seen.append(args))
        handler.handle_frame(_frame(CHECKOUT, room="room-other"))
        self.assertEqual(seen, [])

    def test_duplicate_message_is_processed_once(self) -> None:
        seen = []
        handler = SwitchEventHandler(allowed_rooms={"room-1"}, on_command=lambda *args: seen.append(args))
        handler.handle_frame(_frame(CHECKOUT, message_id="dup-1"))
        handler.handle_frame(_frame(CHECKOUT, message_id="dup-1"))
        self.assertEqual(len(seen), 1)
        self.assertTrue(claim_message("dup-1") is False)

    def test_malformed_frame_is_safe(self) -> None:
        seen = []
        handler = SwitchEventHandler(allowed_rooms={"room-1"}, on_command=lambda *args: seen.append(args))
        handler.handle_frame(WebSocketFrame(event="message", data={"broken": True}))
        self.assertEqual(seen, [])


class ServiceTests(IsolatedCase):
    def test_valid_approval_resumes_incident(self) -> None:
        sender = MagicMock()
        service = OpsPilotSwitchService(sender)
        from opspilot.orchestrator.runner import start_investigation

        view = start_investigation(CHECKOUT)
        incoming = _incoming("approve " + view["incident_id"])
        service._dispatch(incoming, parse_command(incoming.body))
        self.assertTrue(any("approve" in str(call.args[1]).lower() or "resolved" in str(call.args[1]).lower()
                            for call in sender.send_room_message.call_args_list))

    def test_rejection_does_not_touch_runtime(self) -> None:
        from config.settings import runtime_path
        from opspilot.orchestrator.runner import start_investigation

        sender = MagicMock()
        service = OpsPilotSwitchService(sender)
        view = start_investigation(CHECKOUT)
        incoming = _incoming("reject " + view["incident_id"])
        service._dispatch(incoming, parse_command(incoming.body))
        self.assertFalse(runtime_path().exists())

    def test_approval_for_non_pending_incident_is_rejected(self) -> None:
        sender = MagicMock()
        service = OpsPilotSwitchService(sender)
        from opspilot.orchestrator.runner import start_investigation, resume_investigation

        view = start_investigation(CHECKOUT)
        resume_investigation(view["incident_id"], "approve")
        incoming = _incoming("approve " + view["incident_id"])
        service._dispatch(incoming, parse_command(incoming.body))
        last = sender.send_room_message.call_args.args[1].lower()
        self.assertIn("not waiting", last)

    def test_status_for_missing_incident(self) -> None:
        sender = MagicMock()
        service = OpsPilotSwitchService(sender)
        incoming = _incoming("status INC-9999")
        service._dispatch(incoming, parse_command(incoming.body))
        sender.send_room_message.assert_called()
        self.assertIn("not found", sender.send_room_message.call_args.args[1].lower())


class AdapterTests(unittest.TestCase):
    def test_missing_config_does_not_break_cli_import(self) -> None:
        self.assertIsInstance(SwitchAdapter.validate_config(), list)

    @patch.dict(os.environ, {}, clear=False)
    def test_ws_url_uses_documented_path(self) -> None:
        url = build_ws_url(
            "http://127.0.0.1:8080",
            "agent-123",
            connection_id="conn-uuid",
            room_id="room-abc",
            protocol_version=9,
        )
        self.assertIn("/agents/agent-123/connection/ws", url)
        self.assertIn("connection_id=conn-uuid", url)
        self.assertIn("filter=addressed", url)

    @patch("opspilot.switch_integration.adapter.SwitchConnection")
    def test_disconnect_triggers_reconnect_loop(self, connection_cls: MagicMock) -> None:
        calls = {"count": 0}

        def _factory(*_args, **_kwargs) -> MagicMock:
            calls["count"] += 1
            conn = MagicMock()
            if calls["count"] == 1:
                conn.run_forever.side_effect = RuntimeError("disconnect")
            else:
                conn.run_forever.side_effect = lambda: adapter._stop.set()
            return conn

        adapter = SwitchAdapter.__new__(SwitchAdapter)
        adapter._stop = __import__("threading").Event()
        adapter._rooms = ["room-1"]
        adapter._bridge_url = "http://127.0.0.1:8080"
        adapter._agent_id = "agent-1"
        adapter._api_key = "key"
        adapter._protocol = None
        adapter._connection_id = "conn-1"
        adapter._reconnect_delay = 0
        adapter._handler = MagicMock()
        adapter._service = MagicMock()
        connection_cls.side_effect = _factory
        adapter._run()
        self.assertGreaterEqual(calls["count"], 2)
