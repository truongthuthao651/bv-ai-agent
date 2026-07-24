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
    # Base URL the API is actually reachable at, used to build citation links
    # (format_sources) back to the original source file. Defaults to loopback,
    # matching the admin API's default 127.0.0.1-only binding (README); change
    # only if API_HOST is opened up beyond this machine.
    api_public_base_url: str = "http://localhost:8000"
    # Single shared password gating the admin dashboard (app/auth.py) — upload,
    # delete, and the quick-ask test page. Empty disables the gate entirely
    # (today's default: open on loopback). Not the employee-facing login —
    # that's Open WebUI's own WEBUI_AUTH.
    admin_password: str = ""
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
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "qwen3:8b"
    vision_model: str = "qwen2.5vl:7b"
    embed_model: str = "bge-m3"
    rerank_model: str = "bge-reranker-v2-m3"
    # Local weight dirs for FlagEmbedding (bge-m3 dense+sparse) and the reranker.
    # Downloaded by setup_models.sh so indexing/reranking run fully offline.
    # Relative to the working directory: the repo root natively, /app in Docker.
    embed_model_path: str = "./models/bge-m3"
    rerank_model_path: str = "./models/bge-reranker-v2-m3"
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
    # Non-empty QDRANT_LOCAL_PATH switches the app to qdrant-client's EMBEDDED
    # local mode: the vector DB runs in-process and persists to this directory —
    # no Qdrant server (and no Docker) needed. This is the no-Docker deployment
    # mode. Caveat: the storage dir is single-process; anything else that opens
    # it (e.g. eval/run_ragas.py) must run while the API is stopped.
    # Empty (default) = classic server mode via qdrant_url.
    qdrant_local_path: str = ""
    qdrant_url: str = "http://localhost:6333"
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
    # Relative floor: also drop hits scoring below this FRACTION of the top hit's
    # score. Guards against a tangential chunk from an unrelated document (e.g. a
    # claims-payout spreadsheet row that happens to share a product name + a
    # header word) padding the context when there is a strong, coherent top hit.
    # 0.0 disables it (default — keeps the calibrated absolute-floor behavior and
    # the RAGAS baseline unchanged; raise it only after re-running run_ragas.py).
    rerank_min_ratio: float = 0.0
    enable_query_expansion: bool = True
    enable_query_rewrite: bool = True
    # Sticky product/document scope across turns (app/retrieval/conversation_scope.py):
    # when a follow-up drops the product name, reinject the last-cited doc title
    # (or prior user-named product) into the retrieval query. Also refuses the
    # hybrid general-knowledge fallback for scoped follow-ups that retrieve
    # nothing — those are company-document questions, not textbook ones.
    conversation_scope_enabled: bool = True
    # Pre-retrieval typo gate (app/retrieval/spellcheck.py): ask the user to
    # confirm before running retrieval when the query likely garbles a known
    # glossary term or document title. ``spellcheck_min_ratio`` is the similarity
    # floor; ``spellcheck_max_ratio`` is retained for backwards-compatible .env
    # files but is no longer an upper gate — habitual no-diacritics typing is
    # filtered by the typo-token check instead (folded tokens that already exist
    # in the known vocabulary are never treated as slips).
    spellcheck_enabled: bool = True
    spellcheck_min_ratio: float = 0.82
    spellcheck_max_ratio: float = 0.985
    # A phrase is only flagged if its matched span actually contains a *misspelled*
    # word: a token absent from the known vocabulary yet this close (char ratio) to
    # a token of the phrase it resembles. This distinguishes a real slip
    # ("lieen"~"liên") from a correctly-spelled partial title match (every word is
    # a known word), which must go straight to retrieval instead of being queried.
    spellcheck_typo_token_ratio: float = 0.8
    # When retrieval finds no matching company document at all, let the model
    # answer from general knowledge instead of refusing outright — always
    # labeled (HYBRID_DISCLAIMER) so it's never mistaken for a company-document
    # answer, and the model is still told to refuse for anything
    # company-specific it can't actually know (see HYBRID_SYSTEM_PROMPT).
    # False restores the old behavior: refuse deterministically on zero hits.
    hybrid_fallback_enabled: bool = True
    # Deterministic product-scope guard (app/retrieval/product_scope.py): when a
    # query names a specific product but every retrieved document is a DIFFERENT
    # product (near-identical benefit clauses fool the reranker), refuse instead
    # of answering from the wrong product. False disables the guard.
    product_scope_guard_enabled: bool = True
    # Comparison / multi-product questions (app/retrieval/comparison.py): when
    # the query names ≥2 products, retrieve + rerank per product and merge so
    # one product's overview chunks cannot crowd the other out of the global
    # top-k. False restores the single global pool (starves comparisons).
    comparison_retrieval_enabled: bool = True
    # Chunks kept per named product before merge (2 products × 3 = 6 context).
    comparison_per_product_top_k: int = 3
    # Cap how many named products get their own retrieval pass (latency).
    comparison_max_products: int = 3
    # Advisory / synthesis answers (app/generation/advisory.py): comparison and
    # "which product should the customer pick?" questions ask for a conclusion
    # no document literally states, so the strict prompt refuses them even when
    # the benefit facts were retrieved. When enabled, such questions get a
    # prompt that still sources every datum from context (and still refuses on
    # a wrong/absent product) but may compare and phrase conditional
    # recommendations, always labeled with ADVISORY_DISCLAIMER.
    # False restores the strict-only behavior.
    advisory_mode_enabled: bool = True
    # Let a grounded answer append ONE clearly-fenced "Kiến thức chung (ngoài
    # tài liệu)" section of general (textbook) insurance knowledge after the
    # document-sourced part. Never replaces it, never carries company specifics,
    # and is labeled with GENERAL_KNOWLEDGE_DISCLAIMER. Fully offline — this is
    # the model's own knowledge, not a web lookup.
    general_knowledge_supplement_enabled: bool = True
    # Drop fee / guaranteed-interest chunks from benefit-payout queries
    # (app/retrieval/metric_guard.py) so a "claim bao nhiêu%?" question cannot
    # be answered from a lãi suất cam kết table. False disables the filter.
    metric_guard_enabled: bool = True

    # ---- Chunking ----
    chunk_min_tokens: int = 500
    chunk_max_tokens: int = 800
    chunk_overlap_pct: float = 0.12

    # ---- Ingestion / parsing ----
    ocr_language: str = "vi"
    pdf_min_chars_per_page: int = 20
    # PDF text-extraction backend for Docling: "pypdfium2" or "docling-parse".
    # docling-parse mis-decodes the subsetted fonts of some professionally
    # typeset Vietnamese PDFs (e.g. InDesign policy booklets), producing wrong
    # diacritics throughout; pdfium decodes the same files correctly, so it is
    # the default.
    pdf_backend: str = "pypdfium2"
    do_formula_enrichment: bool = True
    enable_enrichment: bool = True
    # Docling layout/tableformer weights pre-fetched by setup_models.sh; when
    # the directory exists (and is non-empty) the PDF parser runs offline from
    # it. Deliberately NOT named DOCLING_ARTIFACTS_PATH: docling itself reads
    # that env var and hard-fails at convert time if the dir doesn't exist.
    docling_models_path: Path = Path("./models/docling")

    # ---- Paths ----
    # Relative to the working directory: the repo root natively, /app in Docker.
    data_dir: Path = Path("./data")
    synthetic_dir: Path = Path("./data/synthetic")
    glossary_path: Path = Path("./data/glossary/thuat_ngu.yaml")
    asset_dir: Path = Path("./data/assets")

    # ---- Open WebUI / OpenAI-compatible surface ----
    open_webui_port: int = 3000
    openai_api_base_url: str = "http://localhost:8000/v1"
    openai_api_key: str = "local-no-auth"
    webui_auth: bool = False

    # ---- Departments (phòng ban) ----
    # Selectable when uploading a document and editable per document. This is the
    # source of truth for validation; the admin UI (static/index.html) mirrors
    # the same list in its <select> options — keep the two in sync.
    departments: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["PTSP", "DP", "DVA"]
    )

    @field_validator("cors_origins", "departments", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow a comma-separated string in `.env` for list-valued settings."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (parsed once per process)."""
    return Settings()


# Import-friendly singleton for the common case.
settings = get_settings()
