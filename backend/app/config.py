import os
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["development", "production"] = "production"
    database_url: str = "postgresql://mazmi:mazmi_local_change_me@localhost:55432/mazmi_ops"
    # Local AI only. Generation and embeddings run on the configured Ollama server; there
    # are no paid providers, API keys or automatic fallbacks.
    generation_provider: Literal["ollama"] = "ollama"
    embedding_provider: Literal["ollama"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_num_ctx: int = Field(default=4096, ge=1024, le=32768)
    ollama_timeout_seconds: float = Field(default=120, ge=1, le=300)
    ollama_chat_model: str = "qwen3:4b"
    ollama_embedding_model: str = "embeddinggemma"
    # How long Ollama keeps a model in memory after a request ("0" unloads at once).
    ollama_keep_alive: str = Field(default="5m", pattern=r"^(0|-1|\d{1,4}[smh])$")
    # Short "Respuesta:" line above the quoted evidence, only when the model's answer span
    # appears verbatim in the quote shown to the user (see evidence.literal_lead).
    answer_lead: bool = True
    # Load both models into memory when the backend starts, so the first question of the day
    # does not pay the cold-start cost (15-30 s on an 8 GB machine). Best effort, never blocks.
    ollama_warmup: bool = True
    # Qwen3 reasoning phase. "off" (measured default, see VALIDATION.md) disables it and
    # relies on the quote-verified evidence schema; "on" keeps the model's own default.
    ollama_reasoning: Literal["off", "on"] = "off"
    embedding_dimensions: int | None = Field(default=None, ge=1, le=4096)
    stt_model_path: str = ""
    piper_model_path: str = ""
    piper_executable: str = "piper"
    retrieval_min_score: float = Field(default=0.25, ge=-1, le=1)
    max_document_chunks: int = Field(default=2000, ge=1)
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:3000"
    # Database pool and server-side safety limits (see db.py).
    db_pool_max: int = Field(default=10, ge=2, le=100)
    db_pool_timeout_seconds: float = Field(default=10, gt=0, le=120)
    db_statement_timeout_ms: int = Field(default=30000, ge=1000, le=600000)
    db_idle_transaction_timeout_ms: int = Field(default=60000, ge=1000, le=600000)
    # Model-backed chat turns admitted at once. One local model serves one turn at a time;
    # queued requests wait at most chat_queue_timeout_seconds.
    chat_max_concurrent: int = Field(default=1, ge=1, le=32)
    chat_queue_timeout_seconds: float = Field(default=20, ge=0, le=300)
    # Upper bound for one streamed chat turn, including queueing and inference.
    chat_stream_timeout_seconds: float = Field(default=330, ge=10, le=900)
    # RAG pipeline revisions. Previous behaviour stays selectable so every change can be
    # compared against its baseline (see backend/evals/).
    chunking_strategy: Literal["structured_v2", "flat_v1"] = "structured_v2"
    lexical_query_mode: Literal["any_terms_v2", "all_terms_v1"] = "any_terms_v2"
    retrieval_max_chunks_per_document: int = Field(default=3, ge=1, le=20)
    answer_style: Literal["focused_v5", "full_passages_v4"] = "focused_v5"
    # quoted_v6: the model must copy a literal quote per question part and the server
    # verifies it. passage_ids_v5: the previous ID-only sufficiency decision.
    evidence_mode: Literal["quoted_v6", "passage_ids_v5"] = "quoted_v6"

    @field_validator("ollama_reasoning", mode="before")
    @classmethod
    def legacy_reasoning_names(cls, value):
        # Names used by MAZMI 2.0 profiles.
        return {"model_default": "on", "no_think_directive": "off"}.get(value, value)

    @property
    def generation_model(self):
        return self.ollama_chat_model

    @property
    def embedding_model(self):
        return self.ollama_embedding_model

    @property
    def vector_dimensions(self):
        return self.embedding_dimensions or 768

    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parents[2] / ".env",)
        + ((Path(os.environ["MAZMI_ENV_FILE"]),) if os.getenv("MAZMI_ENV_FILE") else ()),
        extra="ignore",
        env_ignore_empty=True,
    )


settings = Settings()
