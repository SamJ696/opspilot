from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MessagePayload(BaseModel):
    addressed: bool = False
    sender: str = ""
    sender_name: str = ""
    sender_kind: str | None = None
    on_behalf_of: str | None = None
    message_id: str = ""
    body: str = ""
    timestamp: int = 0
    thread_id: str | None = None
    opening_message: str | None = None
    sender_role: str | None = None


class AgentMessageEvent(BaseModel):
    type: Literal["message"] = "message"
    room_id: str
    bridge_id: str | None = None
    channel_type: str | None = None
    payload: MessagePayload


class ConnectionState(BaseModel):
    connection_id: str
    agent_id: str
    generation: int
    scope: str
    filter: str
    rooms: list[str] = Field(default_factory=list)
    cursor: int = 0
    protocol: int | None = None
    heartbeat_interval_seconds: float = 2.0


class WebSocketFrame(BaseModel):
    event: str
    data: dict[str, Any] = Field(default_factory=dict)
    id: int | None = None


class IncomingRoomMessage(BaseModel):
    room_id: str
    message_id: str
    body: str
    sender: str
    sender_name: str
    sender_kind: str | None
    addressed: bool
    thread_id: str | None
    reply_thread_id: str

    @classmethod
    def from_frame(cls, frame: WebSocketFrame) -> IncomingRoomMessage | None:
        if frame.event != "message":
            return None
        try:
            event = AgentMessageEvent.model_validate(frame.data)
        except Exception:
            return None
        payload = event.payload
        anchor = payload.thread_id or payload.message_id
        return cls(
            room_id=event.room_id,
            message_id=payload.message_id,
            body=payload.body,
            sender=payload.sender,
            sender_name=payload.sender_name,
            sender_kind=payload.sender_kind,
            addressed=payload.addressed,
            thread_id=payload.thread_id,
            reply_thread_id=anchor,
        )
