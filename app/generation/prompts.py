"""Vietnamese system prompts (STUB — Phase 1 placeholder).

The system prompt MUST preserve four properties (see skill section 6 and
CLAUDE.md answering rules):
  1. Answer only from provided context.
  2. Cite sources as ``[Tên tài liệu, mục X]``.
  3. Refuse with "Tôi không tìm thấy thông tin trong tài liệu" when context is
     insufficient.
  4. For math: show formula (LaTeX) + substitution steps, and ALWAYS append that
     results must be verified — "Kết quả cần được kiểm tra lại bằng công cụ tính
     phí chính thức".
Any prompt edit must keep all four. Never weaken these.
"""

from __future__ import annotations

# TODO(phase-generation): define SYSTEM_PROMPT and context-assembly templates.
