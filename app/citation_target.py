"""Stable content anchors for citation deep links.

Chunk and parent indexes are positional and can change after re-ingestion. A
short hash of the exact generation context lets saved citations find the same
passage again when the content is unchanged, and safely fall back to the named
section when it has changed instead of highlighting an unrelated new chunk.
"""

from __future__ import annotations

import hashlib
import unicodedata


def citation_anchor(section_path: str, context_text: str) -> str:
    """Return a URL-safe content identity for one cited generation window."""
    section = unicodedata.normalize("NFC", section_path.strip())
    text = unicodedata.normalize("NFC", context_text.replace("\r\n", "\n").strip())
    return hashlib.sha256(f"{section}\0{text}".encode("utf-8")).hexdigest()[:20]
