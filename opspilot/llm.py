from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def narrate_report(state: dict) -> str | None:
    """Optionally rewrite the incident report. Facts stay in the deterministic report."""
    if os.getenv("OPSPILOT_ENABLE_LLM", "").lower() not in {"1", "true", "yes"}:
        return None
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.info("LLM narration is enabled but OPENAI_API_KEY is empty")
        return None

    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are OpsPilot's incident narrator. Use only the JSON facts provided. "
                    "Do not invent metrics, versions, columns, or actions. Write at most 120 words."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "incident_id": state.get("incident_id"),
                        "issue_type": state.get("issue_type"),
                        "severity": state.get("severity"),
                        "root_cause": state.get("root_cause"),
                        "confidence": state.get("confidence"),
                        "recommended_action": state.get("recommended_action"),
                        "recovery_result": state.get("recovery_result"),
                        "verification_result": state.get("verification_result"),
                    }
                ),
            },
        ],
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        logger.warning("LLM narration failed; keeping the deterministic report")
        return None
    return text[:1200] if text else None
