"""Register the external OpsPilot agent with Switch."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import urllib.error
import urllib.request

from config import settings
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

INTEGRATION_PROFILE = {
    "connection_model": "session_passive",
    "message_exchange": True,
    "pre_invocation_mediation": [],
    "post_invocation_mediation": [],
    "event_reporting": [],
}


def _post(url: str, payload: dict, headers: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Registration failed HTTP {exc.code}: {body}") from exc


def register_via_agent_bridge(name: str, description: str, overwrite: bool) -> dict:
    token = os.getenv("SWITCH_REGISTRATION_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Set SWITCH_REGISTRATION_TOKEN to a Switch registration or bootstrap API key."
        )
    url = f"{settings.switch_agent_bridge_url()}/agents"
    payload = {
        "name": name,
        "description": description,
        "connector_type": "external",
        "integration_profile": INTEGRATION_PROFILE,
        "overwrite": overwrite,
    }
    return _post(url, payload, {"Authorization": f"Bearer {token}"})


def register_via_gateway(name: str, description: str, overwrite: bool) -> dict:
    cookie = os.getenv("SWITCH_GATEWAY_SESSION", "").strip()
    if not cookie:
        raise SystemExit(
            "Set SWITCH_GATEWAY_SESSION to your Switch gateway session cookie for register-other."
        )
    url = f"{settings.switch_gateway_url()}/gateway/agents/register-other"
    payload = {
        "name": name,
        "description": description,
        "overwrite": overwrite,
    }
    return _post(url, payload, {"Cookie": cookie})


def main() -> None:
    name = os.getenv("SWITCH_AGENT_NAME", "opspilot")
    description = os.getenv(
        "SWITCH_AGENT_DESCRIPTION",
        "OpsPilot AI Engineering Operations Team for incident investigation and simulated recovery.",
    )
    overwrite = os.getenv("SWITCH_REGISTER_OVERWRITE", "").lower() in {"1", "true", "yes"}
    mode = os.getenv("SWITCH_REGISTER_MODE", "bridge").lower()

    if mode == "gateway":
        result = register_via_gateway(name, description, overwrite)
    else:
        result = register_via_agent_bridge(name, description, overwrite)

    agent_id = result.get("id")
    api_key = result.get("api_key")
    if not agent_id or not api_key:
        raise SystemExit(f"Unexpected registration response: {result}")

    print("OpsPilot agent registered.")
    print(f"SWITCH_AGENT_ID={agent_id}")
    print("SWITCH_API_KEY=<saved below — copy into .env now>")
    print(api_key)
    print("\nAdd the agent to your Mattermost room in Switch Console, then set SWITCH_ROOM_ID.")


if __name__ == "__main__":
    main()
