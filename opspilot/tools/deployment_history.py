from __future__ import annotations

from typing import Any

from opspilot.tools.loaders import load_json


def get_deployments(
    service: str | None = None,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    rows = load_json("application/deployments.json")
    matched = []
    for row in rows:
        if service and row["service"] != service:
            continue
        if environment and row["environment"] != environment:
            continue
        matched.append(row)
    matched.sort(key=lambda item: item["deployed_at"], reverse=True)
    return matched


def latest_deployment(
    service: str,
    environment: str = "production",
) -> dict[str, Any] | None:
    rows = get_deployments(service=service, environment=environment)
    return rows[0] if rows else None
