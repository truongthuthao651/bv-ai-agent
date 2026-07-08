"""Generation (STUB — Phase 1 placeholder).

Assembles context from ``display_text`` (numbered ``[1] Tài liệu: ...`` so
citations are checkable), calls Ollama (settings.chat_model), and streams the
answer via SSE in OpenAI format. LaTeX passes through untouched for KaTeX.
See skill section 6.
"""

from __future__ import annotations

# TODO(phase-generation): implement stream_answer(query, contexts) SSE generator.
