"""Central application configuration.

ALL tunable values flow through this module (pydantic-settings reading `.env`).
Never call ``os.getenv()`` elsewhere and never hardcode URLs, model names, ports,
or paths in application code — import ``settings`` from here instead.

Usage:
    from app.config.settings import settings
    settings.chat_model  # -> "qwen3:8b"
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings, populated from environment / `.env`.

    Field names are lower_snake_case; pydantic-settings matches them
    case-insensitively to the UPPER_SNAKE_CASE variables in `.env.example`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application server (FastAPI) ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    # Warm the heavy, lazily-loaded pieces at startup (bge-m3 + reranker weights,
    # the Qdrant collection, and the Ollama chat model) so the first user request
    # doesn't pay their cold-load latency — significant on CPU-only hosts. Each
    # step is best-effort; a failure is logged and never blocks startup. Set False
    # to keep startup light (e.g. running only the ingestion CLI, or in tests).
    warmup_on_startup: bool = True

    # ---- Assistant identity / branding ----
    # Display name shown in Open WebUI (browser title/header) and the admin page.
    # The underlying local model never changes — this is presentation only.
    assistant_name: str = "Trợ lý AI Bảo Việt Life"
    # OpenAI-style model id advertised by GET /v1/models. Open WebUI lists this in
    # its model dropdown; chat_completions ignores the requested model and always
    # serves settings.chat_model, so this is purely a stable, branded label.
    assistant_model_id: str = "bao-viet-life"
    # NoDecode: keep pydantic-settings from JSON-decoding this from `.env`;
    # the validator below splits the comma-separated string instead.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"]
    )

    # ---- Ollama ----
    ollama_base_url: str = "http://ollama:11434"
    chat_model: str = "qwen3:8b"
    vision_model: str = "qwen2.5vl:7b"
    embed_model: str = "bge-m3"
    rerank_model: str = "bge-reranker-v2-m3"
    # Local weight dirs for FlagEmbedding (bge-m3 dense+sparse) and the reranker.
    # Downloaded by setup_models.sh so indexing/reranking run fully offline.
    embed_model_path: str = "/app/models/bge-m3"
    rerank_model_path: str = "/app/models/bge-reranker-v2-m3"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 2048
    llm_context_window: int = 8192
    ollama_timeout: float = 120.0
    # Ollama unloads a model after ~5 idle minutes by default, so the next
    # question after a break pays a full model reload (warmup only covers the
    # first request). Duration string ("2h", "30m") or "-1" to keep loaded
    # forever; sent with every Ollama call.
    ollama_keep_alive: str = "2h"
    # Reasoning models (e.g. qwen3) emit hidden <think> tokens before the answer.
    # On CPU these dominate latency. False sends Ollama ``think: false`` to skip
    # them entirely; any that still leak are stripped server-side before display.
    llm_thinking: bool = False

    # ---- Qdrant ----
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "insurance_docs"
    dense_vector_size: int = 1024
    dense_distance: str = "Cosine"

    # ---- Retrieval / reranking ----
    retrieve_top_k: int = 20
    rrf_k: int = 60
    rerank_top_k: int = 5
    # Reranker (bge-reranker-v2-m3, normalized 0-1) hits scoring below this are
    # dropped before generation; when nothing survives, the API returns the
    # refusal message deterministically instead of trusting the LLM to refuse
    # on irrelevant context. 0 disables the floor. Calibrated on the synthetic
    # corpus: off-topic queries score <= 0.001 everywhere, while genuinely
    # related secondary chunks (e.g. the formula article for a terse
    # "tính net premium") land around 0.05-0.15 — a higher floor starves the
    # model of usable context and causes false refusals.
    rerank_min_score: float = 0.05
    enable_query_expansion: bool = True
    enable_query_rewrite: bool = True

    # ---- Chunking ----
    chunk_min_tokens: int = 500
    chunk_max_tokens: int = 800
    chunk_overlap_pct: float = 0.12

    # ---- Ingestion / parsing ----
    ocr_language: str = "vi"
    pdf_min_chars_per_page: int = 20
    do_formula_enrichment: bool = True
    enable_enrichment: bool = True
    # Docling layout/tableformer weights pre-fetched by setup_models.sh; when
    # the directory exists (and is non-empty) the PDF parser runs offline from
    # it. Deliberately NOT named DOCLING_ARTIFACTS_PATH: docling itself reads
    # that env var and hard-fails at convert time if the dir doesn't exist.
    docling_models_path: Path = Path("/app/models/docling")

    # ---- Paths ----
    data_dir: Path = Path("/app/data")
    synthetic_dir: Path = Path("/app/data/synthetic")
    glossary_path: Path = Path("/app/data/glossary/thuat_ngu.yaml")
    asset_dir: Path = Path("/app/data/assets")

    # ---- Open WebUI / OpenAI-compatible surface ----
    open_webui_port: int = 3000
    openai_api_base_url: str = "http://api:8000/v1"
    openai_api_key: str = "local-no-auth"
    webui_auth: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow CORS_ORIGINS to be a comma-separated string in `.env`."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (parsed once per process)."""
    return Settings()


# Import-friendly singleton for the common case.
settings = get_settings()
