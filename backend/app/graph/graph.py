"""Assembles the LangGraph `StateGraph` for the Prior-Authorization & Claims
Documentation Assistant.

    START -> ingest -> extract_clinical_summary -> match_policy_criteria
          -> draft_pa_request -> staff_review -> finalize -> END

Every chart excerpt follows the same straight-line pipeline -- there's no
classification/branching step, since the input is always "one referral
needing a PA drafted" rather than one of several document types.
`staff_review`'s `interrupt()` is the load-bearing piece of control flow
here -- see `app/graph/nodes.py::staff_review_node`.
"""
from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    draft_pa_request_node,
    extract_clinical_summary_node,
    finalize_node,
    ingest_node,
    match_policy_criteria_node,
    staff_review_node,
)
from app.graph.state import PAIntakeState


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build (and optionally compile-with-checkpointer) the PA intake graph.

    Pass `checkpointer=None` to get an uncompiled-but-still-runnable graph
    with LangGraph's default in-memory checkpointing (handy for unit tests
    that don't need durability/interrupts across processes). Pass a real
    `AsyncPostgresSaver` in the FastAPI app for durable, resumable runs.
    """
    builder = StateGraph(PAIntakeState)

    builder.add_node("ingest", ingest_node)
    builder.add_node("extract_clinical_summary", extract_clinical_summary_node)
    builder.add_node("match_policy_criteria", match_policy_criteria_node)
    builder.add_node("draft_pa_request", draft_pa_request_node)
    builder.add_node("staff_review", staff_review_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "extract_clinical_summary")
    builder.add_edge("extract_clinical_summary", "match_policy_criteria")
    builder.add_edge("match_policy_criteria", "draft_pa_request")
    builder.add_edge("draft_pa_request", "staff_review")
    builder.add_edge("staff_review", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)
