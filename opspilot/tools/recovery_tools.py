from __future__ import annotations

import json
from typing import Any

from opspilot.tools.deployment_history import latest_deployment
from opspilot.tools.loaders import load_runtime, save_runtime
from opspilot.tools.service_metrics import latest_and_baseline


def simulate_rollback(
    service: str,
    from_version: str,
    to_version: str,
    *,
    approved: bool,
) -> dict[str, Any]:
    if not approved:
        raise PermissionError("Recovery requires explicit approval")

    deployment = latest_deployment(service)
    if deployment is None:
        raise ValueError(f"No production deployment found for {service}")
    if deployment["version"] != from_version:
        raise ValueError(
            f"Refusing rollback because latest version is {deployment['version']}, not {from_version}"
        )
    if deployment["previous_version"] != to_version:
        raise ValueError(
            "Refusing rollback to a version that is not the recorded previous version"
        )

    action_key = f"rollback:{service}:{from_version}:{to_version}"
    runtime = load_runtime()
    current = runtime["services"].get(service, {})
    if (
        current.get("current_version") == to_version
        and current.get("action_key") == action_key
    ):
        return {
            "status": "ALREADY_APPLIED",
            "action_key": action_key,
            "service": service,
            "from_version": from_version,
            "to_version": to_version,
            "simulated": True,
        }

    runtime["services"][service] = {
        "current_version": to_version,
        "rolled_back_from": from_version,
        "healthy": True,
        "action_key": action_key,
    }
    save_runtime(runtime)
    return {
        "status": "COMPLETED",
        "action_key": action_key,
        "service": service,
        "from_version": from_version,
        "to_version": to_version,
        "simulated": True,
    }


def verify_rollback(service: str, to_version: str, deployed_at: str | None) -> dict[str, Any]:
    runtime = load_runtime()["services"].get(service, {})
    _latest, baseline = latest_and_baseline(service, deployed_at)
    version_ok = runtime.get("current_version") == to_version
    healthy_ok = runtime.get("healthy") is True and baseline is not None
    observed = {
        "service": service,
        "current_version": runtime.get("current_version"),
        "healthy": bool(version_ok and healthy_ok),
    }
    if baseline and version_ok and healthy_ok:
        observed.update(
            {
                "error_rate_percent": baseline["error_rate_percent"],
                "average_latency_ms": baseline["average_latency_ms"],
                "cpu_percent": baseline["cpu_percent"],
                "memory_percent": baseline["memory_percent"],
                "baseline_timestamp": baseline["timestamp"],
            }
        )
    error_rate = observed.get("error_rate_percent")
    passed = bool(
        version_ok
        and healthy_ok
        and isinstance(error_rate, (int, float))
        and error_rate < 5
    )
    return {
        "passed": passed,
        "observed": observed,
        "reason": "Simulated service health matches the pre-deployment baseline"
        if passed
        else "Rollback simulation did not reach a healthy baseline",
    }


def simulate_pipeline_recovery(
    job_id: str,
    mapping: dict[str, str],
    *,
    approved: bool,
    task: str | None = None,
) -> dict[str, Any]:
    if not approved:
        raise PermissionError("Recovery requires explicit approval")
    if not mapping:
        raise ValueError("Pipeline correction requires a column mapping")

    action_key = f"pipeline:{job_id}:{json.dumps(mapping, sort_keys=True)}"
    runtime = load_runtime()
    existing = runtime["jobs"].get(job_id, {})
    if existing.get("status") == "SUCCEEDED" and existing.get("action_key") == action_key:
        return {
            "status": "ALREADY_APPLIED",
            "action_key": action_key,
            "job_id": job_id,
            "mapping": mapping,
            "simulated": True,
        }

    runtime["jobs"][job_id] = {
        "status": "SUCCEEDED",
        "mapping": mapping,
        "task": task,
        "action_key": action_key,
        "simulated": True,
    }
    save_runtime(runtime)
    return {
        "status": "COMPLETED",
        "action_key": action_key,
        "job_id": job_id,
        "mapping": mapping,
        "task": task,
        "simulated": True,
    }


def verify_pipeline(job_id: str, mapping: dict[str, str]) -> dict[str, Any]:
    observed = load_runtime()["jobs"].get(job_id, {})
    passed = observed.get("status") == "SUCCEEDED" and observed.get("mapping") == mapping
    return {
        "passed": passed,
        "observed": {
            "job_id": job_id,
            "status": observed.get("status", "FAILED"),
            "mapping": observed.get("mapping"),
        },
        "reason": "Simulated pipeline retry succeeded with the corrected mapping"
        if passed
        else "Pipeline simulation did not record a successful corrected run",
    }
