"""Centralized application settings.

All configuration is read from environment variables (see `.env.example` at
the repo root). We use `pydantic-settings` so misconfiguration fails fast and
loudly at process startup instead of deep inside a graph node.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM provider ---------------------------------------------------
    llm_provider: str = "openai"  # "openai" | "anthropic"
    llm_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-haiku-latest"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    # Extracting facts already stated in a chart, and assembling paperwork
    # from them, should be as deterministic as possible -- this is
    # documentation assistance, not creative writing, and the whole point is
    # to avoid the model inventing clinical content or a coverage opinion.
    llm_temperature: float = 0.0

    # --- Postgres (prompts, patients/PA-request history, LangGraph checkpoints) --
    # SQLAlchemy (sync engine) uses the psycopg3 dialect: postgresql+psycopg://
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/prior_auth"
    )
    # AsyncPostgresSaver needs a plain psycopg-style DSN (no "+psycopg" driver
    # suffix); we strip it in db/checkpointer.py.

    # --- Documents -------------------------------------------------------------
    # Where uploaded chart excerpts are stored (git-ignored). Relative paths
    # are resolved from the backend/ working directory.
    upload_dir: str = "./data/uploads"
    # Where the bundled synthetic sample referrals / payer policies / patient
    # records live, so the "run a sample referral" zero-setup demo path and
    # the seed scripts can find them. Defaults to the repo-root
    # `sample-data/` folder one level up from `backend/`; overridden to
    # `/app/sample-data` in Docker (see docker-compose.yml, which mounts it
    # read-only).
    sample_data_dir: str = "../sample-data"

    # --- Milvus Lite (embedded vector store, no server/docker needed) ---
    # Used for semantic payer medical-necessity criteria matching only -- see
    # app/tools/policy_kb.py. Retrieved criteria are always surfaced as a
    # "draft assessment for staff review", never a coverage decision.
    milvus_lite_path: str = "./data/milvus_policy_criteria.db"
    milvus_collection: str = "payer_policy_criteria"
    policy_search_top_k: int = 6

    # --- API ---------------------------------------------------------------
    cors_allow_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
