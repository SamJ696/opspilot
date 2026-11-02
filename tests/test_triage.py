import unittest

from opspilot.agents.triage_agent import classify_issue, triage_agent


CHECKOUT = "Our checkout API is returning HTTP 500 errors after the latest production deployment."
DATABRICKS = "Our Databricks customer analytics pipeline failed because of a SQL schema mismatch."


class TriageTests(unittest.TestCase):
    def test_checkout_incident_is_application(self) -> None:
        result = classify_issue(CHECKOUT)
        self.assertEqual(result["issue_type"], "APPLICATION")
        self.assertGreater(result["application_score"], result["data_score"])

    def test_pipeline_incident_is_data(self) -> None:
        result = classify_issue(DATABRICKS)
        self.assertEqual(result["issue_type"], "DATA_PIPELINE")
        self.assertGreater(result["data_score"], result["application_score"])

    def test_equal_scores_are_unknown(self) -> None:
        result = classify_issue("the service pipeline needs a look")
        self.assertEqual(result["issue_type"], "UNKNOWN")

    def test_severity_follows_the_report(self) -> None:
        self.assertEqual(triage_agent(CHECKOUT)["severity"], "HIGH")
        self.assertEqual(triage_agent(DATABRICKS)["severity"], "HIGH")
        self.assertEqual(triage_agent("checkout api latency is climbing")["severity"], "MEDIUM")
        self.assertEqual(triage_agent("production is down")["severity"], "CRITICAL")
        self.assertEqual(triage_agent("hello there")["severity"], "LOW")
        self.assertEqual(triage_agent(CHECKOUT)["status"], "TRIAGING")
