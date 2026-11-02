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
