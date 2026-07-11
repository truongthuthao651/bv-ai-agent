"""
title: Nạp tài liệu (RAG nội bộ)
author: insurance-rag-pipeline
version: 0.1.0
license: MIT
description: >
    Select this model, attach a file (paperclip icon) with
    .md/.docx/.xlsx/.yaml/.yml, and send. It forwards the attachment to the
    insurance RAG backend's
    POST /ingest and returns the result as the assistant's reply — so document
    upload happens inside the same chat UI users already use, with no separate
    admin page.
required_open_webui_version: 0.5.0
"""

# Open WebUI "Pipe" function. This file is NOT imported by the FastAPI app; it
# is pasted into Open WebUI itself (Admin Panel > Settings > Functions > "+"),
# where it runs inside the open-webui container and registers as a selectable
# "model" in the chat UI. See scripts/open_webui/README.md for install steps.
#
# Why this exists: Open WebUI's native file-attach button always goes through
# Open WebUI's OWN internal RAG (its own chunking/embedding/vector store) —
# there is no built-in way to redirect an attachment into an arbitrary external
# ingestion API (see open-webui/open-webui issue #17293, unresolved upstream).
# This Pipe is the workaround: a dedicated "model" whose only job is to fetch
# the raw bytes of an attached file from Open WebUI's own file store and POST
# them to our /ingest endpoint, so the equation-safe chunking, formula
# verbalization, and bge-m3 hybrid indexing (CLAUDE.md / the pipeline skill)
# are what actually processes the document — not Open WebUI's generic RAG.
#
# Known side effect: attaching a file to ANY chat message also makes Open
# WebUI extract+embed it into its own local vector store, regardless of which
# model/pipe is selected — this is an Open WebUI limitation (see the same
# issue), not something this Pipe can suppress. It's wasted local compute, not
# a correctness problem: our own /v1/chat/completions endpoint never reads
# Open WebUI's vector store, only our own Qdrant collection.
from __future__ import annotations

import mimetypes

import httpx
from pydantic import BaseModel, Field


class Pipe:
    class Valves(BaseModel):
        INGEST_API_BASE_URL: str = Field(
            default="http://api:8000",
            description="Base URL of the insurance RAG FastAPI backend (container-to-container hostname on the compose network).",
        )
        OPENWEBUI_INTERNAL_URL: str = Field(
            default="http://localhost:8080",
            description="Open WebUI's own internal URL (this Pipe runs inside the open-webui container, so 'localhost' is correct here, not 'open-webui').",
        )
        OPENWEBUI_API_KEY: str = Field(
            default="",
            description="Open WebUI API key: Settings (bottom-left) > Account > API Keys > Create. Required to read attached-file bytes back from Open WebUI.",
        )
        REQUEST_TIMEOUT: float = Field(
            default=280.0,
            description="Seconds to wait for /ingest. Formula verbalization calls the LLM once per math chunk and is slow on CPU-only setups.",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()
        self.id = "insurance_doc_ingest"
        self.name = "📥 Nạp tài liệu"

    @staticmethod
    def _extract_file_ref(entry: dict) -> tuple[str | None, str | None, str | None]:
        """Best-effort (file_id, filename, content_type) from an Open WebUI file entry.

        Open WebUI's exact attachment schema has changed across versions and
        isn't part of any stable public contract, so this checks the field
        names seen in both the v0.5.4 backend source and current docs rather
        than assuming one fixed shape.
        """
        inner = entry.get("file") or {}
        meta = inner.get("meta") or {}
        file_id = entry.get("id") or inner.get("id")
        filename = entry.get("name") or inner.get("filename") or meta.get("name")
        content_type = meta.get("content_type")
        return file_id, filename, content_type

    async def _fetch_file_bytes(self, client: httpx.AsyncClient, file_id: str) -> bytes:
        resp = await client.get(
            f"{self.valves.OPENWEBUI_INTERNAL_URL}/api/v1/files/{file_id}/content",
            headers={"Authorization": f"Bearer {self.valves.OPENWEBUI_API_KEY}"},
        )
        resp.raise_for_status()
        return resp.content

    async def _ingest(
        self, client: httpx.AsyncClient, filename: str, content: bytes, content_type: str | None
    ) -> str:
        resp = await client.post(
            f"{self.valves.INGEST_API_BASE_URL}/ingest",
            files={
                "file": (
                    filename,
                    content,
                    content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
                )
            },
        )
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            return f"❌ Nạp \"{filename}\" thất bại (HTTP {resp.status_code}): {detail}"

        data = resp.json()
        extra = f", {data['n_figures']} hình" if data.get("n_figures") else ""
        return (
            f"✅ Đã nạp **{data['doc_title']}** ({data['doc_type']}) — "
            f"{data['n_chunks']} đoạn{extra}.\n\n_ID: `{data['doc_id']}`_"
        )

    async def pipe(self, body: dict, __files__: list | None = None) -> str:
        files = __files__ or body.get("files") or []
        if not files:
            return (
                "Đính kèm một tệp (.md, .docx, .xlsx, .yaml/.yml — hỗ trợ PDF/ảnh "
                "đang được phát triển) vào tin nhắn này bằng biểu tượng ghim, rồi "
                "gửi lại để nạp vào hệ thống."
            )

        if not self.valves.OPENWEBUI_API_KEY:
            return (
                "⚠️ Chưa cấu hình khoá API. Vào Settings > Account > API Keys để "
                "tạo một khoá, rồi dán vào Valves của function \"Nạp tài liệu\" "
                "(Admin Panel > Settings > Functions)."
            )

        results: list[str] = []
        async with httpx.AsyncClient(timeout=self.valves.REQUEST_TIMEOUT) as client:
            for entry in files:
                file_id, filename, content_type = self._extract_file_ref(entry)
                if not file_id or not filename:
                    results.append(
                        "❌ Không xác định được tệp đính kèm từ dữ liệu Open WebUI "
                        f"gửi sang (`{entry!r}`). Gửi đoạn này cho người phát triển "
                        "để cập nhật lại cách đọc tệp đính kèm."
                    )
                    continue
                try:
                    content = await self._fetch_file_bytes(client, file_id)
                except httpx.HTTPError as exc:
                    results.append(f"❌ Không tải được nội dung tệp \"{filename}\": {exc}")
                    continue
                try:
                    results.append(await self._ingest(client, filename, content, content_type))
                except httpx.HTTPError as exc:
                    results.append(f"❌ Không kết nối được API nạp tài liệu: {exc}")

        return "\n\n---\n\n".join(results)
