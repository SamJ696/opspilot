import logging

from opspilot.orchestrator.runner import (
    load_investigation,
    resume_investigation,
    stream_investigation,
)
from opspilot.reporting import opening_line, specialist_lines
from opspilot.storage.incident_repository import list_by_status

logger = logging.getLogger(__name__)


def _print_update(name: str, update: dict, incident_id: str) -> None:
    if not update:
        return
    if name == "triage":
        print()
        print(
            opening_line(
                {
                    "incident_id": incident_id,
                    "issue_type": update.get("issue_type", ""),
                    "severity": update.get("severity", ""),
                }
            )
        )
        print()
        return

    results = update.get("investigation_results") or {}
    for item in results.values():
        print(f"- {item.get('agent', name)}: {item.get('summary', '')}")

    if name == "remediation" and update.get("approval_request"):
        print()
        print(update["approval_request"])
        print()

    if update.get("final_report") and name in {"report", "rejection", "unsupported"}:
        print()
        print(update["final_report"])
        print()


def _show_pending(view: dict) -> None:
    print(opening_line(view))
    print()
    for line in specialist_lines(view):
        print(f"- {line}")
    print()
    if view.get("approval_request"):
        print(view["approval_request"])
        print()


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    print("\n================================")
    print("       OPSPILOT STARTED")
    print("================================\n")

    pending = []
    try:
        pending = list_by_status("AWAITING_APPROVAL")
    except Exception:
        logger.exception("Could not read pending incidents")
    if pending:
        print("Pending approvals:")
        for item in pending:
            print(f"- {item['incident_id']}: {item['user_message']}")
        print("Resume one with: resume INC-1001\n")

    waiting_for: str | None = None

    while True:
        try:
            if waiting_for:
                message = input(f"Decision for {waiting_for} (approve/reject): ")
            else:
                message = input("Report an issue: ")
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down OpsPilot...")
            break

        if message.lower().strip() in {"exit", "quit"}:
            print("Shutting down OpsPilot...")
            break
        if not message.strip():
            print("Enter an incident description.")
            continue

        try:
            if waiting_for:
                view = resume_investigation(waiting_for, message)
                waiting_for = None
                print()
                print(view.get("final_report") or f"Status: {view.get('status')}")
                print()
                continue

            if message.lower().startswith("resume "):
                incident_id = message.split(maxsplit=1)[1].strip()
                snapshot_view = load_investigation(incident_id)
                if not snapshot_view.get("pending_approval"):
                    print(f"{incident_id} is not waiting for approval.")
                    continue
                _show_pending(snapshot_view)
                waiting_for = incident_id
                continue

            printed_final = False
            final_view = None
            for event in stream_investigation(message):
                if event["type"] == "update":
                    for name, update in event["chunk"].items():
                        if not isinstance(update, dict):
                            continue
                        _print_update(name, update, event["incident_id"])
                        if update.get("final_report") and name in {
                            "report",
                            "rejection",
                            "unsupported",
                        }:
                            printed_final = True
                else:
                    final_view = event["view"]

            if final_view and final_view.get("pending_approval"):
                waiting_for = final_view["incident_id"]
            elif final_view and not printed_final:
                print()
                print(final_view.get("final_report") or f"Status: {final_view.get('status')}")
                print()
        except ValueError as exc:
            print(exc)
        except RuntimeError as exc:
            print(exc)
            waiting_for = None
        except Exception:
            logger.exception("OpsPilot failed to handle the request")
            print("OpsPilot hit an unexpected error. The incident was not changed.")


if __name__ == "__main__":
    main()
