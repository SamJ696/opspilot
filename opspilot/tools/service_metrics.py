from __future__ import annotations

from typing import Any

from opspilot.tools.loaders import load_json


def get_metrics(service: str | None = None) -> list[dict[str, Any]]:
    rows = load_json("application/service_metrics.json")
    matched = [row for row in rows if service is None or row["service"] == service]
    matched.sort(key=lambda item: item["timestamp"])
    return matched


def latest_and_baseline(
    service: str,
    deployed_at: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    rows = get_metrics(service)
    if not rows:
        return None, None
    latest = rows[-1]
    if deployed_at:
        prior = [row for row in rows if row["timestamp"] < deployed_at]
        baseline = prior[-1] if prior else None
    else:
        healthy = [row for row in rows if row.get("healthy")]
        baseline = healthy[-1] if healthy else rows[0]
    return latest, baseline
