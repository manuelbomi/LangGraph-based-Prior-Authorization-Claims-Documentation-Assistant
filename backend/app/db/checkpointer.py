"""Wiring for LangGraph's Postgres checkpointer.

This is what makes a PA request's drafting run durable: `AsyncPostgresSaver`
persists the full graph state after every node executes, keyed by
`thread_id` (one thread per PA request being drafted). A run paused at
`staff_review` (via `interrupt()`) -- an item in a staff member's review
queue -- can be resumed hours, days, or even next week, from a brand new
process, by opening a fresh `AsyncPostgresSaver` against the same Postgres
database and calling
`graph.astream(Command(resume=...), config={"configurable": {"thread_id": ...}})`.

That durability matters specifically here: prior-authorization requests
genuinely have a lifecycle spanning days to weeks (drafted -> reviewed ->
submitted -> awaiting payer decision -> approved/denied/more info
requested), and a staff member reviews their queue asynchronously, not
necessarily right after a chart is uploaded. Nothing produced by this graph
should ever be submitted to a payer without that explicit, possibly-delayed
staff review.

We open ONE saver for the lifetime of the FastAPI process (see
`app/main.py` lifespan) rather than one per request, since it owns a
connection pool.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings


def _psycopg_dsn(database_url: str) -> str:
    """Strip the SQLAlchemy "+psycopg" driver suffix -> a plain psycopg DSN."""
    return database_url.replace("postgresql+psycopg://", "postgresql://")


@asynccontextmanager
async def build_checkpointer():
    """Yield a ready-to-use (schema already set up) AsyncPostgresSaver."""
    settings = get_settings()
    dsn = _psycopg_dsn(settings.database_url)
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
        yield saver
