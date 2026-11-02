import os
import tempfile
import unittest
from pathlib import Path


class IsolatedCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self._previous = {
            "OPSPILOT_DB_PATH": os.environ.get("OPSPILOT_DB_PATH"),
            "OPSPILOT_CHECKPOINT_PATH": os.environ.get("OPSPILOT_CHECKPOINT_PATH"),
            "OPSPILOT_RUNTIME_PATH": os.environ.get("OPSPILOT_RUNTIME_PATH"),
            "OPSPILOT_ENABLE_LLM": os.environ.get("OPSPILOT_ENABLE_LLM"),
            "OPSPILOT_APPROVAL_POLICY": os.environ.get("OPSPILOT_APPROVAL_POLICY"),
            "OPSPILOT_APPROVER_SENDERS": os.environ.get("OPSPILOT_APPROVER_SENDERS"),
            "OPSPILOT_APPROVER_ROLES": os.environ.get("OPSPILOT_APPROVER_ROLES"),
        }
        os.environ["OPSPILOT_DB_PATH"] = str(root / "incidents.db")
        os.environ["OPSPILOT_CHECKPOINT_PATH"] = str(root / "checkpoints.sqlite")
        os.environ["OPSPILOT_RUNTIME_PATH"] = str(root / "runtime.json")
        os.environ["OPSPILOT_ENABLE_LLM"] = "false"
        from opspilot.orchestrator.runner import reset_caches

        reset_caches()

    def tearDown(self) -> None:
        from opspilot.orchestrator.runner import reset_caches

        reset_caches()
        for key, value in self._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()
