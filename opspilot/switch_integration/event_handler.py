from __future__ import annotations

import logging

from collections.abc import Callable

from opspilot.switch_integration.command_handler import ParsedCommand, parse_command
from opspilot.switch_integration.dedupe import claim_message
from opspilot.switch_integration.protocol_models import IncomingRoomMessage, WebSocketFrame

logger = logging.getLogger(__name__)


class SwitchEventHandler:
    def __init__(
        self,
        *,
        allowed_rooms: set[str],
        on_command: Callable[..., None],
    ) -> None:
        self._allowed_rooms = allowed_rooms
        self._on_command = on_command

    def handle_frame(self, frame: WebSocketFrame) -> None:
        if frame.event != "message":
            return
        incoming = IncomingRoomMessage.from_frame(frame)
        if incoming is None:
            logger.warning("Malformed Switch message frame")
            return
        self.handle_incoming(incoming)

    def handle_incoming(self, incoming: IncomingRoomMessage) -> None:
        if self._allowed_rooms and incoming.room_id not in self._allowed_rooms:
            logger.debug("Ignoring message from unlisted room %s", incoming.room_id)
            return

        if incoming.sender_kind == "agent":
            logger.debug("Ignoring agent-originated message %s", incoming.message_id)
            return

        if not claim_message(incoming.message_id):
            logger.debug("Duplicate Switch message ignored: %s", incoming.message_id)
            return

        command = parse_command(incoming.body)
        if command.kind.value == "ignore":
            return

        try:
            self._on_command(incoming, command)
        except Exception:
            logger.exception("Switch command handler failed for %s", incoming.message_id)
            raise
