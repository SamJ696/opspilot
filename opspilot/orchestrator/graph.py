from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, START, StateGraph

from opspilot.orchestrator.checkpointer import get_checkpointer
from opspilot.orchestrator.nodes import (
    approval_node,
    deployment_node,
    health_node,
    intake_node,
    log_node,
    pipeline_node,
    recovery_node,
    rejection_node,
    remediation_node,
    report_node,
    root_cause_node,
    sql_node,
    triage_node,
    unsupported_node,
    verification_node,
)
from opspilot.orchestrator.router import (
    route_after_approval,
    route_after_remediation,
    route_after_triage,
)
from opspilot.orchestrator.state import OpsPilotState

_app = None
_path: Path | None = None


def build_graph(checkpointer=None):
    graph = StateGraph(OpsPilotState)

    graph.add_node("intake", intake_node)
    graph.add_node("triage", triage_node)
    graph.add_node("log_investigator", log_node)
    graph.add_node("deployment_investigator", deployment_node)
    graph.add_node("health_investigator", health_node)
    graph.add_node("pipeline_investigator", pipeline_node)
    graph.add_node("sql_investigator", sql_node)
    graph.add_node("root_cause", root_cause_node)
    graph.add_node("remediation", remediation_node)
    graph.add_node("approval", approval_node)
    graph.add_node("recovery", recovery_node)
    graph.add_node("verification", verification_node)
    graph.add_node("report", report_node)
    graph.add_node("rejection", rejection_node)
    graph.add_node("unsupported", unsupported_node)

    graph.add_edge(START, "intake")
    graph.add_edge("intake", "triage")
    graph.add_conditional_edges("triage", route_after_triage)
    # Each list is a barrier: root cause runs once, after every specialist
    # that was actually scheduled for that workflow.
    graph.add_edge(
        ["log_investigator", "deployment_investigator", "health_investigator"],
        "root_cause",
    )
    graph.add_edge(["pipeline_investigator", "sql_investigator"], "root_cause")
    graph.add_edge("root_cause", "remediation")
    graph.add_conditional_edges("remediation", route_after_remediation)
    graph.add_conditional_edges("approval", route_after_approval)
    graph.add_edge("recovery", "verification")
    graph.add_edge("verification", "report")
    graph.add_edge("report", END)
    graph.add_edge("rejection", END)
    graph.add_edge("unsupported", END)

    if checkpointer is None:
        checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


def get_app():
    global _app, _path
    from config.settings import checkpoint_path

    path = checkpoint_path()
    if _app is not None and _path == path:
        return _app
    _app = build_graph(get_checkpointer())
    _path = path
    return _app


def reset_compiled_graph() -> None:
    global _app, _path
    _app = None
    _path = None
