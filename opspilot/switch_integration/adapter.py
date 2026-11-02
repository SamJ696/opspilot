from __future__ import annotations

import logging
import threading

from config import settings
from opspilot.switch_integration.connection import (
    SwitchConnection,
    build_ws_url,
    load_or_create_connection_id,
)
from opspilot.switch_integration.event_handler import SwitchEventHandler
from opspilot.switch_integration.message_sender import SwitchMessageSender
from opspilot.switch_integration.protocol_models import WebSocketFrame
from opspilot.switch_integration.service import OpsPilotSwitchService

logger = logging.getLogger(__name__)


class SwitchAdapter:
    def __init__(self) -> None:
        self._bridge_url = settings.switch_agent_bridge_url()
        self._agent_id = settings.switch_agent_id()
        self._api_key = settings.switch_api_key()
        self._rooms = settings.switch_room_allowlist()
        self._protocol = settings.switch_protocol_version()
        self._base_delay = settings.switch_reconnect_base_seconds()
        self._max_delay = settings.switch_reconnect_max_seconds()
        self._connection_id = load_or_create_connection_id(settings.switch_connection_id_path())
        self._sender = SwitchMessageSender(self._bridge_url, self._agent_id, self._api_key)
        self._service = OpsPilotSwitchService(self._sender)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active_connection: SwitchConnection | None = None
        self._attempt = 0

        allowed = set(self._rooms)
        self._handler = SwitchEventHandler(
            allowed_rooms=allowed,
            on_command=self._service.handle,
        )

    @staticmethod
    def validate_config() -> list[str]:
        missing = []
        if not settings.switch_agent_id():
            missing.append("SWITCH_AGENT_ID")
        if not settings.switch_api_key():
            missing.append("SWITCH_API_KEY")
        if not settings.switch_room_allowlist():
            missing.append("SWITCH_ROOM_ID or SWITCH_ROOM_IDS")
        return missing

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._attempt = 0
        self._thread = threading.Thread(target=self._run, name="switch-adapter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._active_connection is not None:
            self._active_connection.stop()
        if self._thread:
            self._thread.join(timeout=5)
        self._service.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            room_id = self._rooms[0]
            ws_url = build_ws_url(
                self._bridge_url,
                self._agent_id,
                connection_id=self._connection_id,
                room_id=room_id,
                protocol_version=self._protocol,
            )

            def on_frame(frame: WebSocketFrame) -> None:
                self._handler.handle_frame(frame)

            def on_connected(_state) -> None:
                self._attempt = 0

            connection = SwitchConnection(
                ws_url,
                self._api_key,
                on_frame=on_frame,
                on_connected=on_connected,
                stop=self._stop,
            )
            self._active_connection = connection
            try:
                connection.run_forever()
            except Exception:
                if self._stop.is_set():
                    break
                self._attempt += 1
                delay = min(
                    self._max_delay,
                    self._base_delay * (2 ** min(self._attempt - 1, 5)),
                )
                logger.info(
                    "Switch reconnect attempt %s in %.1fs",
                    self._attempt,
                    delay,
                )
                if self._stop.wait(delay):
                    break
            finally:
                self._active_connection = None
