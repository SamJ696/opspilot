from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from urllib.parse import urlencode, urlparse, urlunparse

from opspilot.switch_integration.protocol_models import ConnectionState, WebSocketFrame

logger = logging.getLogger(__name__)


def load_or_create_connection_id(path) -> str:
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = str(uuid.uuid4())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return value


def http_to_ws_url(http_base: str, path: str) -> str:
    parsed = urlparse(http_base.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def build_ws_url(
    bridge_url: str,
    agent_id: str,
    *,
    connection_id: str,
    room_id: str,
    protocol_version: int | None,
) -> str:
    path = f"/agents/{agent_id}/connection/ws"
    query: dict[str, str] = {
        "connection_id": connection_id,
        "scope": "single",
        "filter": "addressed",
        "start_from": "head",
        "rooms": room_id,
        "client": "opspilot",
        "client_version": "1.0.0",
    }
    if protocol_version is not None:
        query["protocol"] = str(protocol_version)
        query["protocol_accepts"] = str(protocol_version)
    return f"{http_to_ws_url(bridge_url, path)}?{urlencode(query)}"


class SwitchConnection:
    """Synchronous WebSocket client for the Agent Bridge event stream."""

    def __init__(
        self,
        ws_url: str,
        api_key: str,
        *,
        on_frame: Callable[[WebSocketFrame], None],
        on_connected: Callable[[ConnectionState], None] | None = None,
        on_disconnect: Callable[[Exception | None], None] | None = None,
        stop: threading.Event | None = None,
    ) -> None:
        self._ws_url = ws_url
        self._api_key = api_key
        self._on_frame = on_frame
        self._on_connected = on_connected
        self._on_disconnect = on_disconnect
        self._stop = stop or threading.Event()
        self._connection_state: ConnectionState | None = None

    @property
    def connection_state(self) -> ConnectionState | None:
        return self._connection_state

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        try:
            from websockets.sync.client import connect
        except ImportError as exc:
            raise RuntimeError(
                "The websockets package is required for Switch integration"
            ) from exc

        headers = {"Authorization": f"Bearer {self._api_key}"}
        error: Exception | None = None
        try:
            with connect(
                self._ws_url,
                additional_headers=headers,
                open_timeout=30,
            ) as websocket:
                logger.info("Switch WebSocket connected")
                interval = 2.0
                while not self._stop.is_set():
                    timeout = min(1.0, interval)
                    try:
                        raw = websocket.recv(timeout=timeout)
                    except TimeoutError:
                        continue

                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Ignoring non-JSON WebSocket frame")
                        continue

                    frame = WebSocketFrame.model_validate(payload)
                    if frame.event == "connection_state":
                        self._connection_state = ConnectionState.model_validate(frame.data)
                        interval = self._connection_state.heartbeat_interval_seconds
                        if self._on_connected:
                            self._on_connected(self._connection_state)
                    elif frame.event == "ping":
                        websocket.send(json.dumps({"type": "pong"}))
                    elif frame.event == "refused":
                        detail = frame.data.get("detail", frame.data)
                        raise RuntimeError(f"Switch refused connection: {detail}")
                    elif frame.event == "evicted":
                        raise RuntimeError(f"Switch evicted connection: {frame.data}")
                    else:
                        self._on_frame(frame)
        except Exception as exc:
            if not self._stop.is_set():
                error = exc
                logger.warning("Switch WebSocket ended: %s", exc)
                raise
        finally:
            if self._on_disconnect:
                self._on_disconnect(error)
