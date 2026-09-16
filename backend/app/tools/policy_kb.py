"""Embedded vector-store payer medical-necessity criteria lookup, backed by
Milvus Lite.

Milvus Lite (`pymilvus[milvus_lite]`) runs the vector database in-process
against a local file -- no Docker, no server, no network hop. This mirrors
`langgraph-tutorial-01`'s knowledge-base pattern and
`langgraph-tutorial-04`'s ICD-10 lookup pattern, applied here to fictitious
payer policy criteria (see `sample-data/payer-policies/` and
`sample-data/README.md` for provenance).

IMPORTANT (platform note): Milvus Lite's native binary is published for
Linux and macOS only. It works out of the box inside this repo's Linux
backend Docker image / CI, but will fail to import on native Windows
Python -- run the backend via Docker or WSL on Windows.

IMPORTANT (safety note): the results of `search_policy_criteria` feed a
DRAFT met/unmet/unclear assessment for staff review -- never a coverage or
medical-necessity determination. See `app/graph/nodes.py::match_policy_criteria_node`
and the root README's "Scope & Safety" section.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.llm import get_embeddings
from app.tools.policy_documents import PolicyCriterionChunk, load_policy_chunks

logger = logging.getLogger(__name__)

_client_lock = threading.Lock()
_client = None  # lazily-created MilvusClient singleton


@dataclass
class PolicyCriterionResult:
    criterion_id: str
    payer_name: str
    service: str
    policy_title: str
    criterion_label: str
    text: str
    score: float


def _get_client():
    """Lazily create (and cache) the Milvus Lite client.

    Lazy + cached so importing this module never requires milvus_lite to be
    installed (unit tests monkeypatch `search_policy_criteria` directly and
    never call this), and so the file-backed client is opened at most once
    per process.
    """
    global _client
    with _client_lock:
        if _client is None:
            from pymilvus import MilvusClient

            settings = get_settings()
            db_path = Path(settings.milvus_lite_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _client = MilvusClient(str(db_path))
        return _client


def ensure_collection(dim: int = 1536) -> None:
    """Create the policy-criteria collection if it doesn't already exist."""
    settings = get_settings()
    client = _get_client()
    if not client.has_collection(settings.milvus_collection):
        client.create_collection(
            collection_name=settings.milvus_collection,
            dimension=dim,
            metric_type="COSINE",
            auto_id=False,
        )


def seed_policy_criteria(force: bool = False) -> int:
    """Embed and upsert every payer policy criterion into Milvus Lite.

    Returns the number of criteria (re)inserted. No-op if the collection
    already has data, unless `force=True`.
    """
    settings = get_settings()
    client = _get_client()

    if client.has_collection(settings.milvus_collection) and not force:
        stats = client.get_collection_stats(settings.milvus_collection)
        if int(stats.get("row_count", 0)) > 0:
            logger.info("Policy criteria collection already seeded (%s rows); skipping.", stats["row_count"])
            return 0

    chunks: list[PolicyCriterionChunk] = load_policy_chunks(settings.sample_data_dir)

    embeddings = get_embeddings()
    texts = [f"{c.payer_name} | {c.service} | {c.text}" for c in chunks]
    vectors = embeddings.embed_documents(texts)

    ensure_collection(dim=len(vectors[0]))

    rows = [
        {
            "id": idx,
            "vector": vector,
            "criterion_id": chunk.criterion_id,
            "payer_name": chunk.payer_name,
            "service": chunk.service,
            "policy_title": chunk.policy_title,
            "criterion_label": chunk.criterion_label,
            "text": chunk.text,
        }
        for idx, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    client.insert(collection_name=settings.milvus_collection, data=rows)
    logger.info("Seeded %d payer policy criteria into Milvus Lite.", len(rows))
    return len(rows)


def search_policy_criteria(
    query: str, payer_name: str | None = None, top_k: int | None = None
) -> list[PolicyCriterionResult]:
    """Embed `query` (requested service + diagnosis) and return the top-k
    closest-matching payer policy criteria, optionally filtered to a single
    payer.

    Returns [] on any failure (e.g. collection not yet seeded, or -- on
    native Windows -- milvus_lite not being installed at all) so the graph
    degrades gracefully to an empty criteria checklist rather than crashing;
    staff can still evaluate the request manually against the payer's
    published policy during review.
    """
    settings = get_settings()
    k = top_k or settings.policy_search_top_k
    try:
        client = _get_client()
        if not client.has_collection(settings.milvus_collection):
            logger.warning("Policy criteria collection does not exist yet; returning no matches.")
            return []

        embeddings = get_embeddings()
        query_vector = embeddings.embed_query(query)

        filter_expr = f'payer_name == "{payer_name}"' if payer_name else ""

        hits = client.search(
            collection_name=settings.milvus_collection,
            data=[query_vector],
            limit=k,
            filter=filter_expr,
            output_fields=["criterion_id", "payer_name", "service", "policy_title", "criterion_label", "text"],
        )
        results: list[PolicyCriterionResult] = []
        for hit in hits[0]:
            entity = hit.get("entity", hit)
            results.append(
                PolicyCriterionResult(
                    criterion_id=entity.get("criterion_id", ""),
                    payer_name=entity.get("payer_name", ""),
                    service=entity.get("service", ""),
                    policy_title=entity.get("policy_title", ""),
                    criterion_label=entity.get("criterion_label", ""),
                    text=entity.get("text", ""),
                    score=float(hit.get("distance", 0.0)),
                )
            )
        return results
    except Exception:  # noqa: BLE001 - deliberate, see docstring
        logger.exception("payer policy criteria search failed for query=%r", query)
        return []


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-embed and re-insert even if already seeded.")
    args = parser.parse_args()
    inserted = seed_policy_criteria(force=args.force)
    print(f"Inserted {inserted} payer policy criteria into Milvus Lite.")
