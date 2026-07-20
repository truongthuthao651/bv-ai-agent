"""Render a stored document as a scrollable HTML page for citation links.

Citations in an answer link to ``GET /documents/{doc_id}/view``. For sources the
browser renders natively (PDF, images) the endpoint serves the original file
inline; for everything else — and for documents with no backing upload file
(e.g. a batch-ingested corpus) — this module rebuilds a readable rendering from
the indexed chunks so the link always resolves to something viewable.

Everything here is pure and self-contained (no CDN, no external calls — the app
must stay air-gapped, CLAUDE.md rule 4): Markdown+LaTeX from ``display_text`` is
turned into a standalone HTML page. LaTeX spans are preserved verbatim (shown as
styled monospace, not rendered) so the source stays faithful even without KaTeX.
"""

from __future__ import annotations

import html
import re
from typing import Any

from markdown_it import MarkdownIt

# CommonMark + GFM tables, raw HTML disabled (display_text is trusted, but
# escaping raw HTML costs nothing and keeps the viewer XSS-safe by construction).
_MD = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")

# Same math-span shape used across the pipeline: $$...$$ display, $...$ inline.
_MATH_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.DOTALL)
_PLACEHOLDER_RE = re.compile(r"\x1bMATH(\d+)\x1b")


def _blocks(text: str) -> list[str]:
    """Split section text into blank-line-separated blocks (mirrors chunking)."""
    return [b.strip("\n") for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def _merge_overlap(emitted: list[str], new: list[str]) -> list[str]:
    """Append ``new`` blocks to ``emitted``, dropping the overlapping prefix.

    Consecutive chunks of one section share a block-level overlap (chunking's
    ``_overlap_suffix`` re-emits whole trailing blocks at the next chunk's
    start). Find the longest suffix of ``emitted`` equal to a prefix of ``new``
    and splice, so the rebuilt section text has no duplicated paragraphs.
    """
    for k in range(min(len(emitted), len(new)), 0, -1):
        if emitted[-k:] == new[:k]:
            return emitted + new[k:]
    return emitted + new


def reconstruct_sections(
    chunks: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Rebuild (doc_title, ordered sections) from a document's stored chunks.

    ``chunks`` must be ordered by ``chunk_index`` (indexer.get_document_chunks
    does this). Chunks of one section are contiguous; their ``display_text`` is
    de-overlapped and joined back into a single Markdown blob per section.
    """
    doc_title = chunks[0].get("doc_title", "") if chunks else ""
    sections: list[dict[str, Any]] = []
    for ch in chunks:
        section_path = ch.get("section_path", "") or ""
        blocks = _blocks(ch.get("display_text", "") or "")
        if sections and sections[-1]["section_path"] == section_path:
            sections[-1]["blocks"] = _merge_overlap(sections[-1]["blocks"], blocks)
        else:
            sections.append(
                {
                    "section_path": section_path,
                    "page": ch.get("page"),
                    "blocks": blocks,
                }
            )
    for section in sections:
        section["text"] = "\n\n".join(section["blocks"])
    return doc_title, sections


def render_markdown(md_text: str) -> str:
    """Markdown+LaTeX -> HTML, keeping math spans verbatim and styled.

    Math is stashed behind placeholders before Markdown parsing so tokens like
    ``A_{x+t}`` aren't mangled into emphasis, then restored as styled spans
    (``display:block`` for ``$$...$$``) — valid even inside a ``<p>``.
    """
    stash: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        stash.append(match.group(0))
        return f"\x1bMATH{len(stash) - 1}\x1b"

    protected = _MATH_RE.sub(_stash, md_text)
    rendered = _MD.render(protected)

    def _restore(match: re.Match[str]) -> str:
        raw = stash[int(match.group(1))]
        cls = "math-block" if raw.startswith("$$") else "math"
        return f'<span class="{cls}">{html.escape(raw)}</span>'

    return _PLACEHOLDER_RE.sub(_restore, rendered)


_PAGE_CSS = """
:root {
  --navy: #00559b; --navy-dark: #003a63; --blue: #0072bc; --gold: #f7b928;
  --bg: #f3f7fb; --card: #ffffff; --border: #dbe6ef; --text: #1e2b33;
  --muted: #6b7c85; --hl: #fff6d9; --hl-border: var(--gold);
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6;
}
header {
  position: sticky; top: 0; z-index: 5;
  background: linear-gradient(135deg, var(--navy), var(--navy-dark));
  border-bottom: 4px solid var(--gold); color: #fff;
  padding: 14px 24px; display: flex; align-items: center; gap: 14px;
}
.brand-mark {
  display: inline-flex; align-items: center; justify-content: center;
  width: 38px; height: 38px; border-radius: 9px; background: var(--blue);
  border-bottom: 3px solid var(--gold); color: #fff; font-weight: 800;
  font-size: 15px; flex-shrink: 0;
}
header h1 { font-size: 16px; margin: 0; font-weight: 600; }
header .sub { margin: 2px 0 0; font-size: 12px; color: #cfe0ea; }
header .spacer { flex: 1; }
header a.dl {
  color: var(--navy-dark); background: var(--gold); text-decoration: none;
  padding: 6px 12px; border-radius: 6px; font-size: 12.5px; font-weight: 700;
  white-space: nowrap;
}
main { max-width: 900px; margin: 26px auto; padding: 0 20px 80px; }
section.doc-section {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 6px 24px 18px; margin-bottom: 18px;
  scroll-margin-top: 80px;
}
section.doc-section.target {
  border-color: var(--hl-border); box-shadow: 0 0 0 3px #f7b92833;
}
.section-path {
  font-size: 12px; font-weight: 700; color: var(--navy);
  text-transform: uppercase; letter-spacing: .03em;
  border-bottom: 1px solid var(--border); padding: 12px 0 8px; margin-bottom: 8px;
}
.section-path .page { color: var(--muted); font-weight: 500; text-transform: none; }
.doc-section :is(h1,h2,h3,h4) { color: var(--navy-dark); margin: 16px 0 8px; }
.doc-section table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 14px; }
.doc-section th, .doc-section td { border: 1px solid var(--border); padding: 7px 10px; text-align: left; }
.doc-section th { background: #eef6fc; color: var(--navy); }
.doc-section code { background: #eef2f6; padding: 1px 5px; border-radius: 4px; font-size: 90%; }
.math, .math-block { font-family: "SFMono-Regular", Consolas, monospace; color: var(--navy-dark); }
.math-block { display: block; text-align: center; background: #f8fafb;
  border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin: 10px 0; }
.empty { color: var(--muted); text-align: center; padding: 60px 20px; }
""".strip()


def render_page(
    doc_title: str,
    sections: list[dict[str, Any]],
    *,
    doc_id: str,
    highlight_section: str | None = None,
    has_source_file: bool = False,
) -> str:
    """Assemble the full standalone HTML viewer page (self-contained)."""
    safe_title = html.escape(doc_title or "Tài liệu")
    parts: list[str] = []
    matched = False
    for i, section in enumerate(sections):
        path = section.get("section_path") or "(toàn văn)"
        is_target = (
            not matched
            and highlight_section is not None
            and section.get("section_path") == highlight_section
        )
        if is_target:
            matched = True
        page = section.get("page")
        page_html = f' <span class="page">· trang {int(page)}</span>' if page else ""
        body_html = render_markdown(section.get("text", ""))
        parts.append(
            f'<section id="sec-{i}" class="doc-section{" target" if is_target else ""}">'
            f'<div class="section-path">{html.escape(path)}{page_html}</div>'
            f"{body_html}</section>"
        )
    body = "\n".join(parts) or '<p class="empty">Tài liệu này chưa có nội dung.</p>'

    download = (
        f'<a class="dl" href="/documents/{html.escape(doc_id)}/file">Tải bản gốc ↓</a>'
        if has_source_file
        else ""
    )
    # Scroll the highlighted section into view once loaded (inline, no CDN).
    scroll_js = (
        '<script>document.addEventListener("DOMContentLoaded",function(){'
        'var t=document.querySelector(".doc-section.target");'
        'if(t){t.scrollIntoView({behavior:"smooth",block:"start"});}});</script>'
        if matched
        else ""
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="vi"><head><meta charset="UTF-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'
        f"<title>{safe_title}</title><style>{_PAGE_CSS}</style></head><body>"
        '<header><span class="brand-mark">BV</span>'
        f"<div><h1>{safe_title}</h1>"
        '<p class="sub">Trợ lý AI Bảo Việt Life · tài liệu nguồn</p></div>'
        f'<span class="spacer"></span>{download}</header>'
        f"<main>{body}</main>{scroll_js}</body></html>"
    )
