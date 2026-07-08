"""Glossary-based query expansion.

Dictionary-based synonym expansion of the user query from ``thuat_ngu.yaml``
before hybrid search. Deliberately NO LLM call — this must stay fast (skill,
sections 4-5). If a query mentions any term/synonym from the glossary, the
other names for that concept are appended so hybrid search benefits from the
extra lexical/dense overlap (e.g. a user typing "net premium" also pulls in
"phí thuần", "phí rủi ro thuần").

The glossary loader is cached but injectable, so tests exercise
``expand_query`` with an in-memory glossary and never touch the filesystem.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class GlossaryEntry:
    """One row of ``data/glossary/thuat_ngu.yaml``."""

    term: str
    synonyms: list[str] = field(default_factory=list)
    symbol: str | None = None
    definition: str = ""

    @property
    def names(self) -> list[str]:
        """All surface forms (canonical term + synonyms) for matching/expansion."""
        return [self.term, *self.synonyms]


@lru_cache
def load_glossary(path: Path | None = None) -> tuple[GlossaryEntry, ...]:
    """Load and cache the glossary. Returns an empty tuple if the file is missing.

    Missing/unreadable glossary is a soft failure (log + empty result) rather than
    a crash — expansion is a retrieval enhancement, not a hard dependency.
    """
    resolved = path or settings.glossary_path
    if not resolved.exists():
        logger.warning("Glossary not found at %s; query expansion disabled", resolved)
        return ()
    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or []
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to load glossary from %s: %s", resolved, exc)
        return ()
    return tuple(
        GlossaryEntry(
            term=entry["term"],
            synonyms=list(entry.get("synonyms", [])),
            symbol=entry.get("symbol"),
            definition=entry.get("definition", ""),
        )
        for entry in raw
        if entry.get("term")
    )


def expand_query(
    query: str,
    *,
    glossary: tuple[GlossaryEntry, ...] | list[GlossaryEntry] | None = None,
) -> str:
    """Append glossary synonyms for any term already mentioned in ``query``.

    Matching is a case-insensitive substring check on Vietnamese/English surface
    forms (no tokenization needed for a small controlled glossary). Only names
    not already present verbatim are appended, so short queries don't balloon.
    """
    entries = load_glossary() if glossary is None else glossary
    if not entries:
        return query

    query_lower = query.lower()
    extra: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not any(name.lower() in query_lower for name in entry.names):
            continue
        for name in entry.names:
            key = name.lower()
            if key in query_lower or key in seen:
                continue
            seen.add(key)
            extra.append(name)

    if not extra:
        return query
    return f"{query} ({', '.join(extra)})"
