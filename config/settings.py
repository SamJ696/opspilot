"""Paths and environment settings.

Values are read on each call so tests can point storage at temporary files
without reimporting the application.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def data_dir() -> Path:
    return Path(os.getenv("OPSPILOT_DATA_DIR", ROOT / "data"))


def db_path() -> Path:
    return Path(os.getenv("OPSPILOT_DB_PATH", data_dir() / "opspilot.db"))


def checkpoint_path() -> Path:
    return Path(os.getenv("OPSPILOT_CHECKPOINT_PATH", data_dir() / "checkpoints.sqlite"))


def runtime_path() -> Path:
    return Path(os.getenv("OPSPILOT_RUNTIME_PATH", data_dir() / "runtime" / "state.json"))


def switch_agent_bridge_url() -> str:
    return os.getenv("SWITCH_AGENT_BRIDGE_URL", "http://127.0.0.1:8080").rstrip("/")


def switch_gateway_url() -> str:
    return os.getenv("SWITCH_GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")


def switch_agent_id() -> str:
    return os.getenv("SWITCH_AGENT_ID", "").strip()


def switch_api_key() -> str:
    return os.getenv("SWITCH_API_KEY", "").strip()


def switch_room_allowlist() -> list[str]:
    raw = os.getenv("SWITCH_ROOM_IDS", os.getenv("SWITCH_ROOM_ID", "")).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def switch_connection_id_path() -> Path:
    return Path(
        os.getenv(
            "SWITCH_CONNECTION_ID_PATH",
            data_dir() / "runtime" / "switch_connection_id",
        )
    )


def switch_reconnect_delay_seconds() -> float:
    return float(os.getenv("SWITCH_RECONNECT_DELAY_SECONDS", "3"))


def switch_protocol_version() -> int | None:
    raw = os.getenv("SWITCH_PROTOCOL_VERSION", "").strip()
    return int(raw) if raw.isdigit() else None
