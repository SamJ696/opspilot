from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import data_dir, runtime_path


def load_json(relative: str) -> Any:
    path = data_dir() / relative
    if not path.exists():
        raise FileNotFoundError(f"Operational fixture not found: {path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def empty_runtime() -> dict[str, Any]:
    return {"services": {}, "jobs": {}}


def load_runtime() -> dict[str, Any]:
    path = runtime_path()
    if not path.exists():
        return empty_runtime()
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    payload.setdefault("services", {})
    payload.setdefault("jobs", {})
    return payload


def save_runtime(state: dict[str, Any]) -> None:
    path: Path = runtime_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(path)
