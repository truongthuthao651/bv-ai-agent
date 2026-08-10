"""Report parent/child chunk sizes for a folder of documents.

Diagnostic for tuning CHUNK_MAX_TOKENS / CHUNK_CHILD_MAX_TOKENS: shows how many
parents actually get split into several children, which is the only case where
parent-child chunking changes retrieval. Runs the real parser + tokenizer and
touches no vector store, so it is safe to run while the API is up.

    python scripts/chunk_stats.py data/synthetic
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.ingest import doc_id_for_filename  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.ingestion import indexer  # noqa: E402
from app.ingestion.chunking import chunk_document  # noqa: E402
from app.ingestion.router import route_to_parser  # noqa: E402

_SUPPORTED = {".md", ".markdown", ".docx", ".xlsx", ".pdf", ".yaml", ".yml"}


def main() -> None:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/synthetic")
    child_max = settings.chunk_child_max_tokens
    print(
        f"chunk_max_tokens={settings.chunk_max_tokens} "
        f"child_max_tokens={child_max} "
        f"parent_child={settings.parent_child_chunking_enabled}\n"
    )
    total_parents = total_children = split_parents = 0
    for path in sorted(p for p in target.iterdir() if p.suffix.lower() in _SUPPORTED):
        doc = route_to_parser(path, doc_type=None)
        chunks = chunk_document(
            doc,
            doc_id_for_filename(path.name),
            count_tokens=indexer.count_tokens,
            max_tokens=settings.chunk_max_tokens,
            overlap_pct=settings.chunk_overlap_pct,
            child_max_tokens=child_max,
        )
        windows: dict[object, list[int]] = {}
        for c in chunks:
            key = (
                c.parent_index if c.parent_index is not None else f"flat{c.chunk_index}"
            )
            windows.setdefault(key, []).append(indexer.count_tokens(c.display_text))
        n_split = sum(1 for sizes in windows.values() if len(sizes) > 1)
        parent_sizes = [
            indexer.count_tokens(c.parent_text or c.display_text) for c in chunks
        ]
        total_parents += len(windows)
        total_children += len(chunks)
        split_parents += n_split
        print(
            f"{path.name}\n"
            f"  parents={len(windows):<3} children={len(chunks):<3} "
            f"split_parents={n_split}\n"
            f"  parent tokens: max={max(parent_sizes, default=0)} "
            f"median={sorted(parent_sizes)[len(parent_sizes) // 2] if parent_sizes else 0}"
        )
    print(
        f"\nTOTAL parents={total_parents} children={total_children} "
        f"parents actually split={split_parents}"
    )


if __name__ == "__main__":
    main()
