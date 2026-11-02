from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class SwitchMessageSender:
    """HTTP client for Agent Bridge outbound messages."""

    def __init__(self, bridge_url: str, agent_id: str, api_key: str) -> None:
        self._base = bridge_url.rstrip("/")
        self._agent_id = agent_id
        self._api_key = api_key

    def send_room_message(
        self,
        room_id: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        payload = {
            "room_id": room_id,
            "content": content,
            "metadata": metadata or {},
        }
        url = f"{self._base}/agents/{self._agent_id}/message"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.error(
                "Switch send failed (%s): %s",
                exc.code,
                detail[:300],
            )
            raise RuntimeError(f"Switch message send failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            logger.error("Switch send unreachable: %s", exc.reason)
            raise RuntimeError("Switch Agent Bridge unreachable") from exc

        event_id = body.get("event_id")
        return str(event_id) if event_id is not None else None
