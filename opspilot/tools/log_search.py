from __future__ import annotations

from typing import Any

from opspilot.tools.loaders import load_json


def search_logs(
    service: str | None = None,
    level: str | None = None,
    query: str | None = None,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    logs = load_json("application/application_logs.json")
    query_text = query.lower() if query else None
    matched: list[dict[str, Any]] = []
    for entry in logs:
        if service and entry["service"] != service:
            continue
        if level and entry["level"].upper() != level.upper():
            continue
        if environment and entry["environment"] != environment:
            continue
        if query_text:
            haystack = f"{entry['message']} {entry.get('trace_id', '')}".lower()
            if query_text not in haystack:
                continue
        matched.append(entry)
    matched.sort(key=lambda item: item["timestamp"])
    return matched
