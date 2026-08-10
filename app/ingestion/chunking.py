"""Heading-aware, equation-safe chunking.

Structural split happens upstream (sectionizer builds ``section_path``); here we
pack each section's content into 500-800 token chunks with light overlap, under
hard equation/table constraints (skill, section 3):

* Never split inside ``$...$`` or ``$$...$$``.
* A display equation stays with the paragraph immediately before it AND any
  "trong đó: ..." definition list after it (one "equation unit").
* Never split a Markdown table mid-row; oversized tables split by row groups with
  the header repeated.
* A Markdown table stays with the paragraph immediately before it (caption /
  intro) so "%"-by-year schedules keep their metric label (e.g. lãi suất cam
  kết) instead of becoming an orphaned number grid.
* If a single unit exceeds the budget it becomes its own oversized chunk —
  correctness beats budget.

Optionally the packing runs twice (parent-child chunking, ``child_max_tokens``):
each 500-800 token chunk becomes a PARENT that is packed again into smaller
children, and one indexed chunk is emitted per child carrying its parent's
text. The child is what gets embedded and reranked (a short passage matches a
short question far more precisely than an 800-token block), the parent is what
generation reads. Both passes consume the same units, so the rules above hold
at either size.

Token counting is injectable so tests run without the embedding model; the
indexer passes the real bge-m3 tokenizer.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.models.schemas import Chunk, ParsedDocument

TokenCounter = Callable[[str], int]


def default_token_counter(text: str) -> int:
    """Rough token estimate for tests/fallback (no model needed).

    Blends a char-based and word-based estimate; good enough to exercise the
    budget logic. The indexer injects the real bge-m3 tokenizer in production.
    """
    words = len(text.split())
    chars = len(text)
    return max(words, math.ceil(chars / 4))


@dataclass
class _Block:
    kind: str  # "para" | "list" | "table" | "table_unit" | "equation" | "equation_unit"
    text: str


def _raw_blocks(text: str) -> list[_Block]:
    """Split section text into blank-line-separated blocks and classify each."""
    blocks: list[_Block] = []
    for raw in re.split(r"\n\s*\n", text.strip()):
        chunk = raw.strip("\n")
        if not chunk.strip():
            continue
        lines = [ln for ln in chunk.split("\n") if ln.strip()]
        if lines and all(ln.lstrip().startswith("|") for ln in lines):
            kind = "table"
        elif "$$" in chunk:
            kind = "equation"
        elif lines and all(ln.lstrip().startswith(("-", "*", "+")) for ln in lines):
            kind = "list"
        else:
            kind = "para"
        blocks.append(_Block(kind, chunk))
    return blocks


def _bind_equation_units(blocks: list[_Block]) -> list[_Block]:
    """Merge display equations with their defining paragraph + "trong đó" list."""
    out: list[_Block] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b.kind != "equation":
            out.append(b)
            i += 1
            continue
        parts: list[str] = []
        # Absorb the immediately preceding paragraph.
        if out and out[-1].kind == "para":
            parts.append(out.pop().text)
        parts.append(b.text)
        # Absorb following "trong đó:" intro and its definition list.
        j = i + 1
        while j < len(blocks):
            nb = blocks[j]
            low = nb.text.strip().lower()
            if (
                nb.kind == "list"
                or low.startswith("trong đó")
                or low.startswith("trong do")
            ):
                parts.append(nb.text)
                j += 1
            else:
                break
        out.append(_Block("equation_unit", "\n\n".join(parts)))
        i = j
    return out


def _bind_table_units(blocks: list[_Block]) -> list[_Block]:
    """Merge each Markdown table with the paragraph immediately before it.

    Captions like "Lãi suất cam kết tối thiểu theo năm hợp đồng:" must travel
    with the grid — otherwise retrieval sees a bare `%`-by-year table that a
    claim-% question can misread as bồi thường.
    """
    out: list[_Block] = []
    for b in blocks:
        if b.kind != "table":
            out.append(b)
            continue
        parts: list[str] = []
        if out and out[-1].kind == "para":
            parts.append(out.pop().text)
        parts.append(b.text)
        out.append(_Block("table_unit", "\n\n".join(parts)))
    return out


def _split_caption_and_table(text: str) -> tuple[str, str]:
    """Split ``caption\\n\\n| table…`` into (caption, table); caption may be empty."""
    lines = text.split("\n")
    table_start = next(
        (i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")),
        None,
    )
    if table_start is None:
        return "", text
    caption = "\n".join(lines[:table_start]).strip()
    table = "\n".join(lines[table_start:]).strip()
    return caption, table


def _split_table(text: str, count_tokens: TokenCounter, max_tokens: int) -> list[str]:
    """Split an oversized Markdown table into row groups, repeating the header.

    When ``text`` is a caption+table unit, the caption is prepended to every
    group so the metric label survives the split.
    """
    caption, table = _split_caption_and_table(text)
    lines = [ln for ln in table.split("\n") if ln.strip()]
    if len(lines) < 2:
        return [text]
    header, sep, body = lines[0], lines[1], lines[2:]
    header_block = f"{header}\n{sep}"
    groups: list[str] = []
    cur: list[str] = []
    for row in body:
        candidate = "\n".join([header_block, *cur, row])
        if cur and count_tokens(candidate) > max_tokens:
            groups.append("\n".join([header_block, *cur]))
            cur = [row]
        else:
            cur.append(row)
    if cur:
        groups.append("\n".join([header_block, *cur]))
    if not groups:
        return [text]
    if caption:
        return [f"{caption}\n\n{g}" for g in groups]
    return groups


def _overlap_suffix(
    units: list[_Block], count_tokens: TokenCounter, budget: int
) -> list[_Block]:
    """Return the trailing units whose cumulative tokens fit the overlap budget."""
    if budget <= 0:
        return []
    suffix: list[_Block] = []
    total = 0
    for unit in reversed(units):
        t = count_tokens(unit.text)
        if total + t > budget:
            break
        suffix.insert(0, unit)
        total += t
    # Don't let the overlap be the entire chunk (would loop forever).
    if len(suffix) >= len(units):
        suffix = suffix[1:]
    return suffix


def _pack_units(
    units: list[_Block],
    count_tokens: TokenCounter,
    max_tokens: int,
    overlap_tokens: int,
) -> list[list[_Block]]:
    """Greedily pack units into <=max_tokens groups with block-level overlap.

    Returns the units per group rather than joined text so a group can be packed
    again at a smaller budget (parent -> children) without losing the unit
    boundaries that make the equation/table rules hold.
    """
    groups: list[list[_Block]] = []
    cur: list[_Block] = []
    cur_tokens = 0

    def flush() -> None:
        if cur:
            groups.append(cur)

    for unit in units:
        # Oversized table / caption+table -> split by row groups; other
        # oversized units stand alone.
        pieces = (
            _split_table(unit.text, count_tokens, max_tokens)
            if unit.kind in ("table", "table_unit")
            and count_tokens(unit.text) > max_tokens
            else [unit.text]
        )
        for piece in pieces:
            pt = count_tokens(piece)
            # Keep the unit's kind: re-packing a parent's units into children
            # must still recognize a table it may have to row-split again.
            block = _Block(unit.kind, piece)
            if pt > max_tokens:
                flush()
                groups.append([block])  # oversized: correctness beats budget
                cur, cur_tokens = [], 0
                continue
            if cur and cur_tokens + pt > max_tokens:
                flush()
                cur = _overlap_suffix(cur, count_tokens, overlap_tokens)
                cur_tokens = sum(count_tokens(u.text) for u in cur)
            cur.append(block)
            cur_tokens += pt
    flush()
    return groups


def _join(units: list[_Block]) -> str:
    return "\n\n".join(u.text for u in units)


def chunk_document(
    doc: ParsedDocument,
    doc_id: str,
    *,
    count_tokens: TokenCounter = default_token_counter,
    max_tokens: int = 800,
    overlap_pct: float = 0.12,
    child_max_tokens: int | None = None,
) -> list[Chunk]:
    """Chunk a parsed document into retrievable ``Chunk`` objects.

    Chunks never cross section boundaries, so each carries a single
    ``section_path`` for clean citations. ``embed_text`` is seeded with the
    document/section prefix + display text; enrichment appends verbalizations.

    With ``child_max_tokens`` set, each ``max_tokens`` chunk becomes a PARENT
    that is packed again into smaller children, and one ``Chunk`` is emitted per
    child carrying its parent's text. Retrieval then matches the narrow child
    while generation reads the parent. Children are cut from the same units as
    parents, so the equation and table rules hold at both sizes. Leaving it None
    produces the flat one-chunk-per-parent output.
    """
    overlap_tokens = int(max_tokens * overlap_pct)
    source_filename = Path(doc.source_path).name if doc.source_path else None
    chunks: list[Chunk] = []
    idx = 0
    parent_idx = 0
    for section in doc.sections:
        units = _bind_table_units(_bind_equation_units(_raw_blocks(section.text)))
        prefix = f"Tài liệu: {doc.doc_title} > {section.section_path}\n\n"
        for parent_units in _pack_units(
            units, count_tokens, max_tokens, overlap_tokens
        ):
            parent_text = _join(parent_units)
            # Children tile their parent with NO overlap: overlap exists to keep
            # context across a cut, and here the parent itself restores it.
            child_groups = (
                _pack_units(parent_units, count_tokens, child_max_tokens, 0)
                if child_max_tokens
                else [parent_units]
            )
            for child_units in child_groups:
                child_text = _join(child_units)
                # A child that is the whole parent has nothing to widen to.
                widens = child_text != parent_text
                chunks.append(
                    Chunk(
                        doc_id=doc_id,
                        doc_title=doc.doc_title,
                        section_path=section.section_path,
                        doc_type=doc.doc_type,
                        display_text=child_text,
                        embed_text=prefix + child_text,
                        parent_text=parent_text if widens else None,
                        parent_index=parent_idx if widens else None,
                        chunk_index=idx,
                        page=section.page,
                        department=doc.department,
                        source_filename=source_filename,
                        source_url=doc.source_url,
                    )
                )
                idx += 1
            parent_idx += 1
    return chunks
