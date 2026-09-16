"""REAL end-to-end smoke test: actual OpenAI API calls + a real Postgres.

This is deliberately excluded from the default `pytest` run (see the `live`
marker + `addopts` in `pyproject.toml`). Run it explicitly with:

    export OPENAI_API_KEY=sk-...
    export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/prior_auth
    cd backend
    pytest -m live tests/live/test_live_smoke.py -v -s

What it proves, with no mocks anywhere in the graph/LLM/DB path:
  1. A real sample referral
     (`sample-data/referrals/lumbar_mri_referral_jordan_blake.txt`) is
     ingested, structured into a clinical summary by a real `gpt-4o-mini`
     call, matched against Meridian Health Plan's lumbar MRI policy
     criteria (embedded into Milvus Lite and semantically searched), that
     match assessed met/unmet/unclear by a second real `gpt-4o-mini` call,
     a draft PA request form assembled by a third real `gpt-4o-mini` call,
     and the run genuinely pauses at `staff_review` (`interrupt()`).
  2. The checkpointer can be torn down and a BRAND NEW `AsyncPostgresSaver`
     + freshly-compiled graph (standing in for "a new process", e.g. a
     staff member coming back to their review queue later) can resume that
     exact thread and finish the run (`finalize`), marking it
     `ready_to_submit`.

Cost note: this makes at most THREE small `gpt-4o-mini` calls (clinical
summary extraction, criteria evaluation, PA drafting) plus a handful of
small `text-embedding-3-small` calls (policy criteria collection seeding,
~15 short strings, one-time, plus one query embedding for this request) --
cheap.

Platform note: `match_policy_criteria`'s policy search silently returns no
matches if `milvus_lite` isn't installed/importable (see
`app/tools/policy_kb.py`'s broad except clause), which is expected on
native Windows -- in that case the criteria-evaluation LLM call is also
skipped (see `match_policy_criteria_node`). This test does NOT hard-assert
`criteria_checklist` is non-empty for that reason -- it only asserts on the
LLM-derived clinical summary and draft form fields, which do not depend on
Milvus.
"""
from __future__ import annotations

import asyncio
import os
import sys

import pytest

if sys.platform == "win32":
    # psycopg's async mode cannot run on Windows' default ProactorEventLoop;
    # it needs a selector-based loop. This only matters for local dev on
    # Windows -- the backend Docker image (and CI) run on Linux, where this
    # is a no-op. See: https://www.psycopg.org/psycopg3/docs/advanced/async.html
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from alembic import command
from alembic.config import Config
from langgraph.types import Command

from app.config import get_settings
from app.db.checkpointer import build_checkpointer
from app.graph.graph import build_graph
from app.prompts.seed_prompts import seed as seed_prompts
from app.tools.policy_kb import seed_policy_criteria
from scripts.seed_patients import seed as seed_patients

pytestmark = pytest.mark.live

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_migrations() -> None:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "app", "db", "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module", autouse=True)
def _prepare_schema():
    assert os.environ.get("OPENAI_API_KEY"), "OPENAI_API_KEY must be set for the live smoke test"
    assert os.environ.get("DATABASE_URL"), "DATABASE_URL must point at a real reachable Postgres"
    _run_migrations()
    seed_prompts()
    seed_patients()
    try:
        seed_policy_criteria()
    except Exception as exc:  # noqa: BLE001 - see module docstring platform note
        print(f"[live smoke] policy criteria seeding skipped/failed ({exc.__class__.__name__}): {exc}")
    yield


async def test_live_lumbar_mri_request_survives_checkpointer_restart_and_is_ready_to_submit():
    settings = get_settings()
    referral_path = os.path.join(settings.sample_data_dir, "referrals", "lumbar_mri_referral_jordan_blake.txt")
    assert os.path.exists(referral_path), f"sample referral not found at {referral_path}"

    thread_id = "live-smoke-thread"
    config = {"configurable": {"thread_id": thread_id}}
    graph_input = {
        "file_path": referral_path,
        "original_filename": "lumbar_mri_referral_jordan_blake.txt",
        "patient_id": "jordan-blake",
        "patient_name": "Jordan Blake",
        "patient_dob": "1979-03-14",
        "patient_member_id": "MHP-5521309",
        "payer_name": "Meridian Health Plan",
        "provider_name": "Dr. Alicia Munoz, MD",
        "provider_npi": "1447920033",
    }

    # --- Phase 1: run until it pauses at staff_review ----------------------
    async with build_checkpointer() as checkpointer_1:
        graph_1 = build_graph(checkpointer=checkpointer_1)

        saw_interrupt = False
        async for event in graph_1.astream(graph_input, config=config, stream_mode="updates"):
            print("EVENT:", list(event.keys()))
            if "__interrupt__" in event:
                saw_interrupt = True
                payload = event["__interrupt__"][0].value
                print("\n--- CLINICAL SUMMARY + CRITERIA + DRAFT FORM AT STAFF_REVIEW ---")
                print("clinical_summary:", payload["clinical_summary"])
                print("criteria_checklist:", payload["criteria_checklist"])
                print("draft_form:", payload["draft_form"])
                assert payload["clinical_summary"]["diagnosis"], "expected a non-empty diagnosis"
                assert payload["clinical_summary"]["requested_service"], "expected a non-empty requested service"
                assert payload["draft_form"]["clinical_justification"], "expected a non-empty draft justification"
        assert saw_interrupt, "graph should have paused at staff_review"

        state = await graph_1.aget_state(config)
        assert state.next == ("staff_review",)
    # `async with` exits here -> checkpointer_1's connection pool is fully
    # closed, simulating the backend process shutting down.

    # --- Phase 2: brand new checkpointer + graph, standing in for a --------
    # --- freshly-started process, resumes the SAME thread_id --------------
    async with build_checkpointer() as checkpointer_2:
        graph_2 = build_graph(checkpointer=checkpointer_2)

        # Prove the state genuinely persisted in Postgres, not in memory.
        resumed_state = await graph_2.aget_state(config)
        assert resumed_state.next == ("staff_review",)
        assert resumed_state.values["clinical_summary"]["diagnosis"]

        finished = False
        async for event in graph_2.astream(
            Command(resume={"decision": "approve", "feedback": "Approved by live smoke test."}),
            config=config,
            stream_mode="updates",
        ):
            print("RESUME EVENT:", list(event.keys()))
            if "finalize" in event:
                finished = True

        assert finished, "graph should have reached finalize after resume"
        final_state = await graph_2.aget_state(config)
        assert final_state.next == ()
        assert final_state.values["status"] == "ready_to_submit"
        assert final_state.values["final_status"] == "ready_to_submit"
        print("\n--- FINAL STATE ---\n", {"final_status": final_state.values["final_status"]})
