from langgraph.types import Command

from config.settings import runtime_path
from opspilot.orchestrator.graph import get_app
from opspilot.orchestrator.runner import (
    normalize_decision,
    reset_caches,
    resume_investigation,
    start_investigation,
    thread_config,
)
from opspilot.storage.incident_repository import get_incident
from tests.base import IsolatedCase

CHECKOUT = "Our checkout API is returning HTTP 500 errors after the latest production deployment."


class OrchestratorTests(IsolatedCase):
    def test_unknown_report_does_not_investigate_or_recover(self) -> None:
        view = start_investigation("hello there, can you help?")
        self.assertEqual(view["issue_type"], "UNKNOWN")
        self.assertEqual(view["status"], "UNCLASSIFIED")
        self.assertEqual(view["investigation_results"], {})
        self.assertFalse(view["pending_approval"])
        self.assertIn("did not investigate", view["final_report"])
        self.assertFalse(runtime_path().exists())

    def test_invalid_decision_leaves_the_incident_waiting(self) -> None:
        view = start_investigation(CHECKOUT)
        with self.assertRaises(ValueError):
            normalize_decision("maybe later")
        with self.assertRaises(ValueError):
            resume_investigation(view["incident_id"], "drop the database")
        snapshot = get_app().get_state(thread_config(view["incident_id"]))
        self.assertTrue(snapshot.interrupts)
        self.assertFalse(runtime_path().exists())

    def test_mismatched_incident_id_blocks_recovery(self) -> None:
        view = start_investigation(CHECKOUT)
        get_app().invoke(
            Command(resume={"decision": "approved", "incident_id": "INC-9999"}),
            thread_config(view["incident_id"]),
        )
        stored = get_incident(view["incident_id"])
        assert stored is not None
        self.assertEqual(stored["status"], "REJECTED")
        self.assertIn("different incident", stored["final_report"])
        self.assertFalse(runtime_path().exists())

    def test_approval_survives_a_new_process_checkpoint(self) -> None:
        view = start_investigation(CHECKOUT)
        incident_id = view["incident_id"]
        reset_caches()
        resolved = resume_investigation(incident_id, "approve")
        self.assertEqual(resolved["status"], "RESOLVED")
        self.assertTrue(resolved["verification_result"]["passed"])
        stored = get_incident(incident_id)
        assert stored is not None
        self.assertEqual(stored["status"], "RESOLVED")
        self.assertEqual(stored["approval_status"], "APPROVED")
