"""Shared data contract for the whole pipeline.

Two layers live here:

* **Internal ingestion types** (dataclasses) — the intermediate representation
  every parser converges to, plus the ``Chunk`` produced by chunking/enrichment.
  See the insurance-rag-pipeline skill, section 1.
* **Qdrant payload + API models** (pydantic) — what gets stored per point and
  what the HTTP surface accepts/returns.

The Qdrant payload fields MUST stay in sync with CLAUDE.md (Chunk fields /
"Qdrant payload") — change both together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocType(str, Enum):
    """Allowed document types (CLAUDE.md: ``doc_type`` domain)."""

    POLICY = "policy"
    PROCEDURE = "procedure"
    FORM = "form"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    FIGURE = "figure"
    GLOSSARY = "glossary"
    OTHER = "other"


# --------------------------------------------------------------------------- #
# Internal ingestion representation (parsers -> enrichment -> indexing)
# --------------------------------------------------------------------------- #


@dataclass
class ParsedFigure:
    """A chart/diagram image extracted from a document."""

    image_path: str
    page: int | None = None
    caption: str | None = None  # original caption text if present


@dataclass
class ParsedSection:
    """One ordered section of a parsed document.

    ``text`` is canonical Markdown + LaTeX (``$...$`` inline, ``$$...$$``
    display); Markdown tables stay as Markdown tables.
    """

    section_path: str  # e.g. "Chương II > Điều 5 > Khoản 2"
    text: str
    page: int | None = None


@dataclass
class ParsedDocument:
    """The single intermediate format every parser returns."""

    doc_title: str
    doc_type: DocType
    sections: list[ParsedSection] = field(default_factory=list)
    figures: list[ParsedFigure] = field(default_factory=list)
    # Provenance / metadata carried into each chunk's payload.
    source_path: str | None = None
    department: str | None = None


@dataclass
class Chunk:
    """A retrievable unit after chunking + enrichment.

    ``embed_text`` is what bge-m3 sees (doc/section prefix + display text +
    Vietnamese verbalizations); ``display_text`` is clean Markdown+LaTeX that
    goes into the generation context and UI. Only ``display_text`` is stored in
    the payload — ``embed_text`` exists solely to produce the vectors.
    """

    doc_id: str
    doc_title: str
    section_path: str
    doc_type: DocType
    display_text: str
    embed_text: str
    chunk_index: int
    page: int | None = None
    department: str | None = None
    figure_image_path: str | None = None
    # Set when OCR/formula extraction confidence is low (skill, section 1).
    needs_review: bool = False

    def to_payload(self, ingested_at: datetime | None = None) -> "QdrantPayload":
        """Build the Qdrant payload for this chunk."""
        return QdrantPayload(
            doc_id=self.doc_id,
            doc_title=self.doc_title,
            section_path=self.section_path,
            page=self.page,
            department=self.department,
            doc_type=self.doc_type,
            display_text=self.display_text,
            figure_image_path=self.figure_image_path,
            needs_review=self.needs_review,
            chunk_index=self.chunk_index,
            ingested_at=(ingested_at or datetime.now(timezone.utc)).isoformat(),
        )


# --------------------------------------------------------------------------- #
# Qdrant payload
# --------------------------------------------------------------------------- #


class QdrantPayload(BaseModel):
    """Payload stored alongside each vector point.

    Mirrors CLAUDE.md's field list. ``display_text`` is included so retrieval
    can assemble the generation context without a second lookup.
    """

    doc_id: str
    doc_title: str
    section_path: str
    page: int | None = None
    department: str | None = None
    doc_type: DocType
    display_text: str
    figure_image_path: str | None = None
    needs_review: bool = False
    chunk_index: int
    ingested_at: str  # ISO-8601 UTC


# --------------------------------------------------------------------------- #
# Retrieval (retriever -> reranker -> generation)
# --------------------------------------------------------------------------- #


@dataclass
class Hit:
    """A retrieved chunk carrying its fused (RRF) or reranked relevance score.

    ``score`` is overwritten in place by the reranker once it runs, so a single
    ``Hit`` flows retriever -> reranker -> generation without copying.
    """

    point_id: str
    score: float
    payload: QdrantPayload


# --------------------------------------------------------------------------- #
# HTTP API models (ingestion surface)
# --------------------------------------------------------------------------- #


class IngestResponse(BaseModel):
    """Result of ingesting a single uploaded document."""

    doc_id: str
    doc_title: str
    doc_type: DocType
    n_chunks: int = Field(..., ge=0)
    n_figures: int = Field(default=0, ge=0)


class DocumentDeleteResponse(BaseModel):
    """Result of ``DELETE /documents/{doc_id}``."""

    doc_id: str
    deleted_chunks: int = Field(..., ge=0)


class DocumentInfo(BaseModel):
    """Summary of one indexed document (``GET /documents``)."""

    doc_id: str
    doc_title: str
    doc_type: DocType
    department: str | None = None
    n_chunks: int = Field(..., ge=0)
    ingested_at: str | None = None


# --------------------------------------------------------------------------- #
# Chat models (OpenAI-compatible ``/v1/chat/completions`` surface)
# --------------------------------------------------------------------------- #

Role = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    """One turn in the OpenAI-style ``messages`` array."""

    role: Role
    content: str


class ChatCompletionRequest(BaseModel):
    """Request body for ``POST /v1/chat/completions``.

    ``model`` is accepted for OpenAI-client compatibility (Open WebUI always
    sends one) but ignored — this deployment only ever serves ``settings.chat_model``.
    Unknown OpenAI fields (``top_p``, ``presence_penalty``, ...) are ignored rather
    than rejected.
    """

    model_config = ConfigDict(extra="ignore")

    model: str = ""
    messages: list[ChatMessage]
    stream: bool = True
    temperature: float | None = None


class ChatCompletionChoice(BaseModel):
    """One choice in a non-streaming chat completion response."""

    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    """Non-streaming ``POST /v1/chat/completions`` response (``stream: false``)."""

    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]


class ModelCard(BaseModel):
    """One entry in the OpenAI-compatible ``GET /v1/models`` list.

    ``name`` is a non-standard extra field that Open WebUI reads to show a
    friendly label in its model dropdown; plain OpenAI clients ignore it.
    """

    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str = "bao-viet-life"
    name: str | None = None


class ModelList(BaseModel):
    """``GET /v1/models`` response envelope."""

    object: Literal["list"] = "list"
    data: list[ModelCard]
