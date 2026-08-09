"""Shared data contract for the whole pipeline.

Two layers live here:

* **Internal ingestion types** (dataclasses) — the intermediate representation
  every parser converges to, plus the ``Chunk`` produced by chunking/enrichment.
  See the insurance-rag-pipeline skill, section 1.
* **Qdrant payload + API models** (pydantic) — what gets stored per point and
  what the HTTP surface accepts/returns.

The Qdrant payload fields MUST stay in sync with TEAMMATE_GUIDE.md (Chunk fields /
"Qdrant payload") — change both together.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocType(str, Enum):
    """Allowed document types (TEAMMATE_GUIDE.md: ``doc_type`` domain)."""

    POLICY = "policy"
    PROCEDURE = "procedure"
    FORM = "form"
    SPREADSHEET = "spreadsheet"
    IMAGE = "image"
    FIGURE = "figure"
    GLOSSARY = "glossary"
    # Public reference material ingested as an offline "knowledge pack" (law,
    # circulars, public product brochures). Same retrieval path as any other
    # document, but its citations link to the public ``source_url`` it was
    # downloaded from instead of an internal viewer page.
    REFERENCE = "reference"
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
    # Public URL this document was downloaded from (knowledge-pack material
    # only). Never fetched at runtime — it exists purely so citations can link
    # to the public original. None for internal company documents.
    source_url: str | None = None
    # How doc_title was obtained ("heading" | "heading+filename" | "filename"),
    # or None for parsers whose title isn't heading-derived (XLSX/glossary).
    # Lets ingestion warn on a title taken purely from a generic heading.
    title_source: str | None = None


@dataclass
class Chunk:
    """A retrievable unit after chunking + enrichment.

    ``embed_text`` is what bge-m3 sees (doc/section prefix + display text +
    Vietnamese verbalizations); ``display_text`` is clean Markdown+LaTeX that
    identifies this chunk in retrieval, reranking, and the UI. ``embed_text`` is
    not stored in the payload — it exists solely to produce the vectors.

    With parent-child chunking (settings.parent_child_chunking_enabled) the
    chunk is a small CHILD and ``parent_text`` carries the larger window it was
    cut from, which is what generation reads. ``parent_text`` is None when the
    child is the whole parent (nothing to widen to) or the feature is off.
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
    # Parent window for generation, and the index identifying it within the
    # document so several retrieved children of one parent can be collapsed.
    parent_text: str | None = None
    parent_index: int | None = None
    # Basename of the originally uploaded file (under data/uploads), so
    # citations can link back to the source document. None for sources that
    # were never an uploaded file (e.g. glossary entries built in-memory).
    source_filename: str | None = None
    # Public URL of the original (knowledge-pack documents only) — citations
    # link here instead of the internal viewer. See ParsedDocument.source_url.
    source_url: str | None = None
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
            parent_text=self.parent_text,
            parent_index=self.parent_index,
            figure_image_path=self.figure_image_path,
            source_filename=self.source_filename,
            source_url=self.source_url,
            needs_review=self.needs_review,
            chunk_index=self.chunk_index,
            ingested_at=(ingested_at or datetime.now(timezone.utc)).isoformat(),
        )


# --------------------------------------------------------------------------- #
# Qdrant payload
# --------------------------------------------------------------------------- #


class QdrantPayload(BaseModel):
    """Payload stored alongside each vector point.

    Mirrors TEAMMATE_GUIDE.md's field list. ``display_text`` — and, under parent-child
    chunking, ``parent_text`` — are included so retrieval can assemble the
    generation context without a second lookup. Both parent fields default to
    None, so points indexed before parent-child chunking existed still load.
    """

    doc_id: str
    doc_title: str
    section_path: str
    page: int | None = None
    department: str | None = None
    doc_type: DocType
    display_text: str
    parent_text: str | None = None
    parent_index: int | None = None
    figure_image_path: str | None = None
    source_filename: str | None = None
    source_url: str | None = None
    needs_review: bool = False
    chunk_index: int
    ingested_at: str  # ISO-8601 UTC

    @property
    def context_text(self) -> str:
        """The text generation should read: the parent window when there is one.

        Retrieval and reranking work on the narrow ``display_text``; only the
        prompt widens to the parent, so a match on a short passage still gives
        the model the definitions and conditions around it.
        """
        return self.parent_text or self.display_text


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
    # Non-fatal advisory shown after upload — set when the title was auto-taken
    # from the document's own heading with no product name added, so the user can
    # re-upload with the "Tên tài liệu" override if the product name is missing.
    title_warning: str | None = None


class DocumentDeleteResponse(BaseModel):
    """Result of ``DELETE /documents/{doc_id}``."""

    doc_id: str
    deleted_chunks: int = Field(..., ge=0)


class DocumentUpdateRequest(BaseModel):
    """Partial metadata update for ``PATCH /documents/{doc_id}``.

    Every field is optional; only the fields actually present in the request
    body are applied (the endpoint inspects ``model_fields_set``). Changing
    ``doc_title`` re-ingests the document from its source file so the new title
    flows into the embeddings/reranking (title is part of ``embed_text``);
    ``doc_type``/``department``/``source_url`` are a metadata-only payload
    update. An empty ``department`` / ``source_url`` string clears that field.
    """

    doc_title: str | None = None
    doc_type: DocType | None = None
    department: str | None = None
    source_url: str | None = None


class DocumentInfo(BaseModel):
    """Summary of one indexed document (``GET /documents``)."""

    doc_id: str
    doc_title: str
    doc_type: DocType
    department: str | None = None
    source_url: str | None = None
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

    ``name`` is a non-standard extra field for a friendly display label;
    plain OpenAI clients ignore it. Kept for compatibility with any
    OpenAI-compatible client — /chat itself doesn't call this endpoint.
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


class FeedbackRequest(BaseModel):
    """``POST /feedback`` (P2-F2, audit/REPORT.md) — a thumbs-down signal on
    one streamed answer. Deliberately metadata-only: no query or answer text
    field exists here at all, matching query_timing.py's established
    no-content-logging design (see that module's docstring) rather than the
    audit's own suggested payload shape, which named query/answer text —
    this codebase's existing privacy convention wins over a generic
    recommendation. ``completion_id`` is the same id every SSE chunk of that
    answer already carried (``chatcmpl-...``), so a later admin-side view
    could join this against logs/query_timings.jsonl if that log is ever
    extended to record completion_id too (it doesn't yet — see the fix's
    changelog entry for why that join isn't wired up in this first version).
    """

    completion_id: str
    reason: str | None = None


class ChangePasswordRequest(BaseModel):
    """``POST /change-password`` (P2-J6, audit/REPORT.md — the minimum viable
    self-service surface: any signed-in account changes its OWN password,
    never someone else's — the target account always comes from the session,
    never from this body)."""

    current_password: str
    new_password: str


class UpdateMeRequest(BaseModel):
    """``PATCH /me`` — server-side profile prefs for the signed-in account."""

    display_name: str | None = None
    avatar_swatch: str | None = None
