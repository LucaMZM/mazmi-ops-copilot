import os
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["development", "production"] = "production"
    demo_mode: bool = False
    database_url: str = "postgresql://mazmi:mazmi_local_change_me@localhost:55432/mazmi_ops"
    generation_provider: Literal["gemini", "ollama", "openai"] = "gemini"
    embedding_provider: Literal["gemini", "ollama", "openai"] = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-2"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_num_ctx: int = Field(default=4096, ge=1024, le=32768)
    ollama_timeout_seconds: float = Field(default=120, ge=1, le=300)
    ollama_chat_model: str = "qwen3:4b"
    ollama_embedding_model: str = "embeddinggemma"
    embedding_dimensions: int | None = Field(default=None, ge=1, le=4096)
    embedding_revision: str = "legacy"
    stt_model_path: str = ""
    tts_provider: Literal["piper", "openai"] = "piper"
    piper_model_path: str = ""
    piper_executable: str = "piper"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "marin"
    retrieval_min_score: float = Field(default=0.25, ge=-1, le=1)
    max_document_chunks: int = Field(default=2000, ge=1)
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"
    # Database pool and server-side safety limits (see db.py).
    db_pool_max: int = Field(default=10, ge=2, le=100)
    db_pool_timeout_seconds: float = Field(default=10, gt=0, le=120)
    db_statement_timeout_ms: int = Field(default=30000, ge=1000, le=600000)
    db_idle_transaction_timeout_ms: int = Field(default=60000, ge=1000, le=600000)
    # Model-backed chat turns admitted at once. Local inference on small machines
    # should stay at 1; queued requests wait at most chat_queue_timeout_seconds.
    chat_max_concurrent: int = Field(default=2, ge=1, le=32)
    chat_queue_timeout_seconds: float = Field(default=20, ge=0, le=300)
    # Upper bound for one streamed chat turn, including queueing and inference.
    chat_stream_timeout_seconds: float = Field(default=330, ge=10, le=900)
    # RAG pipeline revisions. The previous behaviour stays selectable so every change
    # can be compared against its baseline (see backend/evals/v2-*.json).
    chunking_strategy: Literal["structured_v2", "flat_v1"] = "structured_v2"
    lexical_query_mode: Literal["any_terms_v2", "all_terms_v1"] = "any_terms_v2"
    retrieval_max_chunks_per_document: int = Field(default=3, ge=1, le=20)
    answer_style: Literal["focused_v5", "full_passages_v4"] = "focused_v5"
    # Qwen3 reasoning control for Ollama. "model_default" is the historical behaviour.
    ollama_reasoning: Literal["model_default", "no_think_directive"] = "model_default"

    @model_validator(mode="after")
    def guard_demo(self):
        if self.demo_mode:
            from psycopg.conninfo import conninfo_to_dict

            database = conninfo_to_dict(self.database_url).get("dbname", "")
            if self.app_env != "development" or not database.endswith("_demo"):
                raise ValueError(
                    "DEMO_MODE requires APP_ENV=development and a dedicated database ending in _demo"
                )
        return self

    @property
    def generation_model(self):
        if self.demo_mode:
            return "demo:fixture-v1"
        if self.generation_provider == "gemini":
            return self.gemini_model
        return self.ollama_chat_model if self.generation_provider == "ollama" else self.openai_model

    @property
    def embedding_model(self):
        if self.demo_mode:
            return "demo:fixture-v1"
        if self.embedding_provider == "gemini":
            return self.gemini_embedding_model
        return (
            self.ollama_embedding_model
            if self.embedding_provider == "ollama"
            else self.openai_embedding_model
        )

    @property
    def vector_dimensions(self):
        return self.embedding_dimensions or (1536 if self.embedding_provider == "openai" else 768)

    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[2] / ".env",)
        + ((Path(os.environ["MAZMI_ENV_FILE"]),) if os.getenv("MAZMI_ENV_FILE") else ()),
        extra="ignore",
        env_ignore_empty=True,
    )


settings = Settings()
