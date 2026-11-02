from __future__ import annotations

import re
from collections import Counter

from opspilot.tools.deployment_history import get_deployments
from opspilot.tools.loaders import load_json
from opspilot.tools.log_search import search_logs
from opspilot.tools.service_metrics import get_metrics


def _normalize(text: str) -> str:
    return text.lower().replace("_", " ").replace("-", " ")


def known_services() -> list[str]:
    names: set[str] = set()
    for row in get_deployments():
        names.add(row["service"])
    for row in load_json("application/application_logs.json"):
        names.add(row["service"])
    for row in get_metrics():
        names.add(row["service"])
    return sorted(names)


def service_with_most_errors() -> str | None:
    errors = search_logs(level="ERROR")
    if not errors:
        return None
    counts = Counter(entry["service"] for entry in errors)
    return counts.most_common(1)[0][0]


def resolve_service(message: str) -> tuple[str | None, str]:
    """Pick the service named in the report, otherwise the noisiest error source."""
    normalized_message = _normalize(message)
    matches = [
        service
        for service in known_services()
        if _normalize(service) in normalized_message
    ]
    if matches:
        return max(matches, key=len), "message"

    inferred = service_with_most_errors()
    if inferred:
        return inferred, "error_volume"
    return None, "unresolved"


def score_name(message: str, name: str) -> int:
    tokens = [token for token in re.split(r"[-_\s]+", name.lower()) if len(token) > 3]
    return sum(
        bool(re.search(rf"\b{re.escape(token)}\b", message.lower()))
        for token in tokens
    )
