"""Live Switch connectivity smoke test (no incident workflow)."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from config import settings
from opspilot.switch_integration.adapter import SwitchAdapter
from opspilot.switch_integration.connection import build_ws_url


def _check_bridge_health(base: str) -> tuple[bool, str]:
    url = f"{base.rstrip('/')}/health"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
            return True, f"HTTP {response.status} {body[:120]}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return False, str(exc.reason)


def _check_credentials(base: str, agent_id: str, api_key: str) -> tuple[bool, str]:
    url = f"{base.rstrip('/')}/agents/{agent_id}/message"
    payload = {
        "room_id": settings.switch_room_allowlist()[0],
        "content": "OpsPilot smoke test: connectivity check only.",
        "metadata": {"opspilot_smoke_test": True},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
            return True, f"send ok={body.get('ok')}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {detail[:200]}"
    except urllib.error.URLError as exc:
        return False, str(exc.reason)


def _check_websocket(base: str, agent_id: str, api_key: str, room_id: str) -> tuple[bool, str]:
    try:
        from websockets.sync.client import connect
    except ImportError:
        return False, "websockets package missing"

    ws_url = build_ws_url(
        base,
        agent_id,
        connection_id=str(uuid.uuid4()),
        room_id=room_id,
        protocol_version=settings.switch_protocol_version(),
    )
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        with connect(ws_url, additional_headers=headers, open_timeout=15) as websocket:
            for _ in range(5):
                raw = websocket.recv(timeout=5)
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                frame = json.loads(raw)
                if frame.get("event") == "connection_state":
                    rooms = frame.get("data", {}).get("rooms", [])
                    return True, f"connection_state rooms={rooms}"
                if frame.get("event") == "ping":
                    websocket.send(json.dumps({"type": "pong"}))
        return False, "connection_state not received"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    missing = SwitchAdapter.validate_config()
    if missing:
        print("Smoke test skipped. Missing configuration:")
        for item in missing:
            print(f"  - {item}")
        return 2

    base = settings.switch_agent_bridge_url()
    agent_id = settings.switch_agent_id()
    api_key = settings.switch_api_key()
    room_id = settings.switch_room_allowlist()[0]

    checks = [
        ("Agent Bridge health", *_check_bridge_health(base)),
        ("Agent credentials", *_check_credentials(base, agent_id, api_key)),
        ("WebSocket connection", *_check_websocket(base, agent_id, api_key, room_id)),
    ]

    print("OpsPilot Switch smoke test\n")
    failed = 0
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        if not ok:
            failed += 1

    if failed:
        print(f"\n{failed} check(s) failed.")
        return 1
    print("\nAll smoke checks passed against the configured Switch instance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
