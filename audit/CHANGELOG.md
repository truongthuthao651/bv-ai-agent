# Phase 7 implementation changelog

Tracks what changed, why, and what was deliberately skipped, per `AUDIT_PROMPT.md` Phase 7.
One entry per commit. Findings IDs reference `audit/REPORT.md` §6.3.

---

## Wave 0 — Ship blockers

### `fbaafec` — Redesign: bespoke React frontend, RBAC accounts, retire Open WebUI
Not a Phase 7 fix — this finally commits the entire redesign + RBAC + Open-WebUI-removal
changeset that had been sitting uncommitted in the working tree since earlier in this session
(the audit itself evaluated this exact state, see `audit/00-system-map.md` §0.4). Landing it was
a prerequisite for every subsequent Wave 0+ commit. 440 tests pass, ruff clean, frontend rebuilt
and verified before committing.

**Side effect: resolves OPS-A.** `app/static/dist/` is now tracked in git — a fresh clone once
again serves the frontend. No separate commit needed for this finding.

### `ad26e20` — security: require a session for /documents/{id}/view and /file (SEC-A)
**Fixed.** These two citation-link routes had no session check at all — matched into
`auth.PUBLIC_PREFIXES` via a regex, they were reachable by anyone, not just employees. Since
`doc_id` is a deterministic `uuid5` of the uploaded filename, anyone who could guess a real
filename could read full document content with zero credentials, on the default LAN-open config.
Removed the public-path carve-out so both routes now require any signed-in account (not
admin-only — employees still need to open citations from `/chat`). Added regression tests:
sessionless → 401/redirect; employee session → reaches the real handler (404 for a nonexistent
doc, not a 401/403 from the auth layer). 442 tests pass (2 new), ruff clean, npm lint clean.

**Skipped for now**: the zip/XML-bomb resilience question flagged alongside this in
`audit/01-engineering.md` §1.4 remains an unverified suspicion, not a confirmed gap — no fix
attempted without first confirming there's something to fix.

### `5558dbf` — security: default API_HOST to loopback, not LAN-exposed (SEC-B)
**Fixed.** `settings.py`'s code-level fallback default was `api_host="0.0.0.0"` (LAN-exposed),
contradicting its own neighboring comment which already claimed loopback was the default.
Combined with `api_shared_secret` defaulting to empty, a fresh install with no `.env` (or one
missing this line) came up LAN-reachable with no auth on `/v1/chat/completions` by default.
Flipped to `"127.0.0.1"`, matching `.env.example`'s already-correct documented value — this is a
fail-safe-default fix, not a behavior change for any real deployment (which already sets
`API_HOST` explicitly). 442 tests pass, ruff clean.

Wave 0 complete: **SEC-A** and **SEC-B** fixed; **OPS-A** resolved as a side effect of the
foundational redesign commit.

## Wave 1 — Smoothness

### `dd88582` — fix: refusal recovery message was dead code (REFUSAL-UI)
**Fixed.** `isRefusal`'s exact-string comparison never matched because the server always appends
a timing footer. Stripped the footer before comparing. Verified live: an out-of-scope query now
shows the intended "Hãy thử nêu rõ tên sản phẩm..." recovery message instead of a dead-ended raw
sentence. Screenshot: `audit/screenshots/after/chat-refusal-recovery-message-fixed.png`.

### `9bc9a7d` — feat: loading indicator during the first-token wait (WAIT-1)
**Fixed.** Added a "Đang tìm trong tài liệu…" status line with a reduced-motion-aware dot cue,
shown while `streaming && !body`. Verified live with a screenshot taken ~1.5s into a real request
(before first token). `audit/screenshots/after/chat-thinking-indicator-during-wait.png`.

### `e732c47` — feat: cancel an in-flight generation (CHAT-1)
**Fixed.** `AbortController` threaded through `askStreaming` → a "Dừng" stop button that replaces
the send button while busy. Verified live: cancelling ~1s into an otherwise-8s+ request produced
no new `logs/query_timings.jsonl` entry — confirms Starlette's built-in disconnect-cancellation
already interrupts the server-side generator before it reaches its completion/logging path, so no
separate `request.is_disconnected()` poll was needed (this resolves Phase 4's unverified
suspicion #4, not just the client-side half of the finding).

### `241ea90` — feat: persist the conversation across refresh (P2-F1)
**Fixed.** `messages` now round-trips through `sessionStorage` (keyed per tab, cleared when the
thread is emptied or a new chat is started) — no backend change, nothing leaves the browser.
Verified live twice: (1) reload mid-request (before any token arrived) — the interrupted,
still-empty assistant turn is dropped on load rather than persisted as a permanently-blank bubble
(a small polish addition beyond the minimal fix, since the plain version of this fix would have
shown exactly that); (2) reload after a full completed answer — text, citations, and the citation
chips all survive intact. Screenshot: `audit/screenshots/after/chat-persistence-after-reload.png`.

### `<pending>` — fix: Modal consistency — themed delete confirm, Enter-submit, Esc-close (P2-C1/C2/C3)
**Fixed, all three.** (1) Delete-document confirmation now uses the app's own `Modal` +
`Button variant="danger"` instead of native `window.confirm`/`window.alert` — verified live with
a screenshot (`audit/screenshots/after/admin-delete-confirmation-modal.png`) showing the themed,
backdrop-blurred dialog, not an OS dialog. (2) `EditModal`'s text fields now submit on Enter
(IME-safe, matches `Composer`/the Overview quick-ask panel), verified live: pressing Enter in the
title field closed the modal (save succeeded) without touching the Save button. (3) `Modal.jsx`
gained an Escape-to-close handler (one fix, every modal in the app benefits) — verified live:
Escape closed the delete-confirmation dialog.

**Deferred, not in scope for this commit**: P2-C4 (focus trap / focus-return on modal close) is
a real M-effort implementation (Tab-cycling within the modal, not a one-liner like C3) —
audit/REPORT.md places it in Wave 4 alongside the rest of the accessibility batch, not Wave 1.


