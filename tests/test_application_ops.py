import json

from config.settings import data_dir, runtime_path
from opspilot.agents.shared.recovery_agent import execute_recovery
from opspilot.orchestrator.runner import resume_investigation, start_investigation
from opspilot.storage.incident_repository import list_audit
from opspilot.tools.deployment_history import get_deployments, latest_deployment
from opspilot.tools.log_search import search_logs
from opspilot.tools.service_metrics import latest_and_baseline
from tests.base import IsolatedCase

CHECKOUT = "Our checkout API is returning HTTP 500 errors after the latest production deployment."
UNNAMED = "production API is returning HTTP 500 errors"
PAYMENTS = "payments api latency is climbing"


class ApplicationToolTests(IsolatedCase):
    def test_log_search_reads_the_fixture(self) -> None:
        fixture = json.loads((data_dir() / "application" / "application_logs.json").read_text(encoding="utf-8"))
        expected = sorted(
            (
                row
                for row in fixture
                if row["service"] == "checkout-api" and row["level"] == "ERROR"
            ),
            key=lambda row: row["timestamp"],
        )
        self.assertEqual(search_logs(service="checkout-api", level="ERROR"), expected)
        self.assertEqual(search_logs(query="trace-1001")[0]["trace_id"], "trace-1001")

    def test_latest_checkout_deployment_is_the_pool_change(self) -> None:
        deployment = latest_deployment("checkout-api")
        self.assertIsNotNone(deployment)
        assert deployment is not None
        self.assertEqual(deployment["version"], "v2.4.1")
        self.assertEqual(deployment["previous_version"], "v2.4.0")
        self.assertIn("connection pooling", " ".join(deployment["changes"]))
        self.assertGreater(len(get_deployments()), 1)

    def test_metrics_show_the_post_deploy_regression(self) -> None:
        latest, baseline = latest_and_baseline("checkout-api", "2026-11-05T10:10:00Z")
        assert latest is not None and baseline is not None
        self.assertEqual(latest["error_rate_percent"], 28.5)
        self.assertEqual(latest["average_latency_ms"], 4200)
        self.assertFalse(latest["healthy"])
        self.assertEqual(baseline["error_rate_percent"], 0.4)
        self.assertTrue(baseline["healthy"])


class ApplicationWorkflowTests(IsolatedCase):
    def test_checkout_incident_pauses_for_rollback_approval(self) -> None:
        view = start_investigation(CHECKOUT)

        self.assertEqual(view["issue_type"], "APPLICATION")
        self.assertEqual(view["severity"], "HIGH")
        self.assertEqual(view["status"], "AWAITING_APPROVAL")
        self.assertTrue(view["pending_approval"])
        self.assertEqual(
            set(view["investigation_results"]),
            {"log_investigator", "deployment_investigator", "health_investigator"},
        )
        self.assertIn("Connection pool exhausted", view["investigation_results"]["log_investigator"]["summary"])
        self.assertIn("v2.4.1", view["investigation_results"]["deployment_investigator"]["summary"])
        self.assertIn("28.5", view["investigation_results"]["health_investigator"]["summary"])
        self.assertIn("4200", view["investigation_results"]["health_investigator"]["summary"])
        self.assertIn("connection pool", view["root_cause"]["hypothesis"].lower())
        self.assertEqual(view["confidence"], 0.92)
        self.assertEqual(
            view["recommended_action"]["summary"],
            "Rollback checkout-api from v2.4.1 to v2.4.0.",
        )
        self.assertIn("approve INC-", view["approval_request"])
        self.assertFalse(runtime_path().exists())

    def test_generic_http_500_is_inferred_from_error_volume(self) -> None:
        view = start_investigation(UNNAMED)
        self.assertEqual(view["investigation_results"]["log_investigator"]["service"], "checkout-api")
        self.assertEqual(view["investigation_results"]["log_investigator"]["match_source"], "error_volume")
        self.assertEqual(view["recommended_action"]["action_type"], "rollback")

    def test_healthy_service_does_not_get_a_rollback(self) -> None:
        view = start_investigation(PAYMENTS)
        self.assertEqual(view["investigation_results"]["health_investigator"]["service"], "payments-api")
        self.assertEqual(view["recommended_action"]["action_type"], "none")
        self.assertFalse(view["pending_approval"])
        self.assertEqual(view["status"], "ROOT_CAUSE_IDENTIFIED")
        self.assertFalse(runtime_path().exists())

    def test_approval_simulates_rollback_and_verification(self) -> None:
        deployment_file = data_dir() / "application" / "deployments.json"
        before = deployment_file.read_bytes()
        view = start_investigation(CHECKOUT)
        resolved = resume_investigation(view["incident_id"], "approve")

        self.assertEqual(resolved["status"], "RESOLVED")
        self.assertTrue(resolved["verification_result"]["passed"])
        self.assertIn("Incident resolved.", resolved["final_report"])
        self.assertEqual(deployment_file.read_bytes(), before)
        runtime = json.loads(runtime_path().read_text(encoding="utf-8"))
        self.assertEqual(runtime["services"]["checkout-api"]["current_version"], "v2.4.0")
        actions = [entry["action"] for entry in list_audit(view["incident_id"])]
        self.assertIn("approved", actions)
        self.assertIn("recovery", actions)

    def test_rejection_does_not_change_runtime_state(self) -> None:
        view = start_investigation(CHECKOUT)
        rejected = resume_investigation(view["incident_id"], "reject")
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertIn("not executed", rejected["final_report"])
        self.assertFalse(runtime_path().exists())

    def test_recovery_tool_requires_approval_and_is_idempotent(self) -> None:
        action = {
            "action_type": "rollback",
            "parameters": {
                "service": "checkout-api",
                "from_version": "v2.4.1",
                "to_version": "v2.4.0",
            },
        }
        with self.assertRaises(PermissionError):
            execute_recovery(action, approved=False)
        self.assertFalse(runtime_path().exists())
        first = execute_recovery(action, approved=True)
        second = execute_recovery(action, approved=True)
        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(second["status"], "ALREADY_APPLIED")
        with self.assertRaises(ValueError):
            execute_recovery(
                {
                    "action_type": "rollback",
                    "parameters": {
                        "service": "checkout-api",
                        "from_version": "v2.4.1",
                        "to_version": "v9.9.9",
                    },
                },
                approved=True,
            )
