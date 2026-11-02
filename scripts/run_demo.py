"""Run both hackathon scenarios against a disposable local database."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEMO_DIR = ROOT / "data" / "demo"
if "OPSPILOT_DB_PATH" not in os.environ:
    os.environ["OPSPILOT_DB_PATH"] = str(DEMO_DIR / "incidents.db")
    os.environ["OPSPILOT_CHECKPOINT_PATH"] = str(DEMO_DIR / "checkpoints.sqlite")
    os.environ["OPSPILOT_RUNTIME_PATH"] = str(DEMO_DIR / "runtime.json")
os.environ.setdefault("OPSPILOT_ENABLE_LLM", "false")

from opspilot.orchestrator.runner import reset_caches, resume_investigation, start_investigation
from opspilot.reporting import opening_line, specialist_lines

SCENARIOS = (
    "Our checkout API is returning HTTP 500 errors after the latest production deployment.",
    "Our Databricks customer analytics pipeline failed because of a SQL schema mismatch.",
)


def _prepare() -> None:
    if Path(os.environ["OPSPILOT_DB_PATH"]).parent != DEMO_DIR:
        return
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("incidents.db", "checkpoints.sqlite", "checkpoints.sqlite-wal", "checkpoints.sqlite-shm", "runtime.json"):
        path = DEMO_DIR / name
        if path.exists():
            path.unlink()
    reset_caches()


def _show(view: dict) -> None:
    print(opening_line(view))
    print()
    for line in specialist_lines(view):
        print(f"- {line}")
    print()
    if view.get("pending_approval"):
        print(view["approval_request"])
        print()


def main() -> None:
    _prepare()
    print("OpsPilot local demo\n")
    for message in SCENARIOS:
        print("=" * 72)
        print(f"Report: {message}\n")
        view = start_investigation(message)
        _show(view)
        if not view["pending_approval"]:
            print(view["final_report"])
            raise SystemExit(f"{view['incident_id']} did not reach approval")
        resolved = resume_investigation(view["incident_id"], "approve")
        print(resolved["final_report"])
        print()
        if resolved["status"] != "RESOLVED":
            raise SystemExit(f"{view['incident_id']} ended as {resolved['status']}")
    print("Both scenarios resolved.")


if __name__ == "__main__":
    main()
