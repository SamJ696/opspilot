# Switch integration notes (Core 0.31.0)

Source of truth: `%APPDATA%\switchdash\local-switch-server\native\switch-core\0.31.0\src\core\switch_core\`.

## Registration

| Path | Module |
|------|--------|
| `POST /gateway/agents/register-other` | `switch_core/gateway/agents.py` |
| `POST /agents` (registration bearer) | `switch_core/bridges/agent/api/handlers.py` |

External agents use `connector_type="external"` and `IntegrationProfile(connection_model="session_passive", message_exchange=True, ...)`.

## Agent Bridge HTTP

| Operation | Route | Auth |
|-----------|-------|------|
| Send room message | `POST /agents/{agent_id}/message` | `Authorization: Bearer <agent api key>` |
| Subscribe room | `POST /agents/{agent_id}/connection/subscribe` | Bearer |

Body for send: `{ "room_id", "content", "metadata" }` (`api/schemas.py`).

## WebSocket event stream

| Item | Location |
|------|----------|
| Route | `GET /agents/{agent_id}/connection/ws` |
| Handler | `bridges/agent/api/handlers.py` → `connection_socket` |

Required query: `connection_id` (UUID, reused on reconnect).

Typical query params: `scope=single`, `filter=addressed`, `start_from=head`, `rooms=<room_id>`, optional `protocol`, `client`, `client_version`.

Frames: `{"event": "<name>", "data": {...}, "id": <seq>?}` (`protocol/stream.py` → `encode_ws`).

First frame: `event=connection_state` (includes `heartbeat_interval_seconds`, usually `2.0`).

Server heartbeat: `{"event": "ping", "data": {}}` → client replies `{"type": "pong"}` (`handlers.py` → `_receive_pongs`).

Room messages: `event=message`, `data` is `AgentEvent.model_dump()` with nested `payload` (`protocol/types.py` → `MessagePayload`).

## Limitation (0.31.0)

The HTTP `POST /agents/{id}/message` handler does not pass `thread_id` into `protocol.send_message`. OpsPilot tracks thread anchors locally for future API support; replies are posted to the room with incident IDs in the text.
