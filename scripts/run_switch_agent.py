"""Run OpsPilot connected to Switch / Mattermost."""

from __future__ import annotations

import logging
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from opspilot.switch_integration.adapter import SwitchAdapter


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    missing = SwitchAdapter.validate_config()
    if missing:
        print("Missing Switch configuration:")
        for key in missing:
            print(f"  - {key}")
        print("\nRegister the agent with scripts/register_switch_agent.py and update .env.")
        raise SystemExit(1)

    adapter = SwitchAdapter()
    print("OpsPilot Switch adapter starting (Ctrl+C to stop)...")
    adapter.start()

    def _stop(_signum, _frame) -> None:
        adapter.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
