import json

from config.settings import data_dir, runtime_path
from opspilot.orchestrator.runner import resume_investigation, start_investigation
from opspilot.tools.databricks_jobs import select_job
from opspilot.tools.sql_diagnostics import diagnose_schema
from tests.base import IsolatedCase

PIPELINE = "Our Databricks customer analytics pipeline failed because of a SQL schema mismatch."
INVENTORY = "inventory sync pipeline failed"


class DataToolTests(IsolatedCase):
    def test_customer_message_selects_the_failed_run(self) -> None:
        job = select_job(PIPELINE)
        assert job is not None
        self.assertEqual(job["run_id"], "run-9001")
        self.assertEqual(job["failed_task"], "customer_transformation")

    def test_schema_tool_finds_the_segment_rename(self) -> None:
        diagnosis = diagnose_schema(
            "customer-analytics-etl",
            "AnalysisException: Cannot resolve column customer_segment",
        )
        self.assertEqual(diagnosis["likely_mapping"], {"customer_segment": "segment"})
        self.assertTrue(diagnosis["source_quality_passed"])
        self.assertEqual(diagnosis["unrelated_failures"][0]["table"], "raw_orders")

    def test_unrelated_job_does_not_inherit_the_customer_contract(self) -> None:
        diagnosis = diagnose_schema("inventory-sync", "FileNotFoundError: inventory snapshot missing")
        self.assertFalse(diagnosis["applies"])
        self.assertEqual(diagnosis["likely_mapping"], {})


class DataWorkflowTests(IsolatedCase):
    def test_schema_incident_pauses_for_a_mapping_fix(self) -> None:
        view = start_investigation(PIPELINE)

        self.assertEqual(view["issue_type"], "DATA_PIPELINE")
        self.assertEqual(view["severity"], "HIGH")
        self.assertTrue(view["pending_approval"])
        self.assertEqual(
            set(view["investigation_results"]),
            {"pipeline_investigator", "sql_investigator"},
        )
        pipeline = view["investigation_results"]["pipeline_investigator"]
        sql = view["investigation_results"]["sql_investigator"]
        self.assertIn("run-9001", pipeline["summary"])
        self.assertNotIn("run-8990", pipeline["summary"])
        self.assertIn("customer_segment", sql["summary"])
        self.assertIn("segment", sql["summary"])
        self.assertIn("order_total_positive", sql["summary"])
        self.assertIn("customer_segment", view["root_cause"]["hypothesis"])
        self.assertEqual(view["confidence"], 0.92)
        self.assertEqual(view["recommended_action"]["action_type"], "pipeline_correction")
        self.assertEqual(
            view["recommended_action"]["parameters"]["mapping"],
            {"customer_segment": "segment"},
        )

    def test_approval_retries_the_pipeline_without_editing_fixtures(self) -> None:
        jobs_file = data_dir() / "dataops" / "databricks_jobs.json"
        before = jobs_file.read_bytes()
        view = start_investigation(PIPELINE)
        resolved = resume_investigation(view["incident_id"], "yes")

        self.assertEqual(resolved["status"], "RESOLVED")
        self.assertTrue(resolved["verification_result"]["passed"])
        self.assertIn("Verification passed.", resolved["final_report"])
        self.assertEqual(jobs_file.read_bytes(), before)
        runtime = json.loads(runtime_path().read_text(encoding="utf-8"))
        self.assertEqual(runtime["jobs"]["job-501"]["status"], "SUCCEEDED")
        self.assertEqual(runtime["jobs"]["job-501"]["mapping"], {"customer_segment": "segment"})

    def test_inventory_failure_is_not_treated_as_the_customer_schema_bug(self) -> None:
        view = start_investigation(INVENTORY)
        self.assertEqual(view["investigation_results"]["pipeline_investigator"]["job_id"], "job-488")
        self.assertEqual(view["recommended_action"]["action_type"], "none")
        self.assertFalse(view["pending_approval"])
        self.assertFalse(runtime_path().exists())
