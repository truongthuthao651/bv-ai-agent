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

### `fbaf3ca` — fix: Modal consistency — themed delete confirm, Enter-submit, Esc-close (P2-C1/C2/C3)
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

### `e4bbb99` — feat: composer autogrow (CHAT-3)
**Fixed.** The textarea was a fixed `rows={2}` with no `scrollHeight`-driven resize — a long
multi-line question scrolled inside a cramped box instead of the box growing with it. Added a
`useEffect` that resizes on every `value` change, capped at 200px (scrolls internally past that
rather than growing unbounded and pushing the send button off-screen). Verified live: height grew
64px → 184px typing a long multi-paragraph question, and returned to 64px when cleared.
Screenshot: `audit/screenshots/after/chat-composer-autogrow.png`.

**Wave 1 complete.** All 6 items fixed and verified live: WAIT-1, CHAT-1, REFUSAL-UI, P2-F1,
P2-C1/C2/C3, CHAT-3.

## Wave 2 — Visual polish and design-system compliance

### `fd4a6b2` — fix: admin console responsive layout (F3-4)
**Fixed — the highest-value visual fix in the audit.** Ported `chat/ChatScreen.jsx`'s proven
`useIsMobile()`/slide-over-drawer pattern to `AdminShell.jsx` (640px threshold, same as chat): the
264px rail now collapses to a hamburger-triggered drawer below that width instead of eating 70%
of a phone screen. `OverviewView.jsx`'s 5-card KPI grid changed from a fixed `repeat(5, 1fr)` to
`repeat(auto-fit, minmax(150px, 1fr))` — reflows continuously instead of truncating every label to
"Số...". The 12-column panel grid keeps its exact desktop spans (deliberately, per
`audit/02-product.md`'s "don't touch the structure") but each `Panel` now stacks to a full-width
single column below 640px via its own `useIsMobile()` call, so no prop-threading through the 8
call sites was needed.

Verified live at the exact viewports the audit screenshotted: 375px mobile (KPI labels now fully
readable, hamburger drawer opens correctly with the full nav+footer) and 768px tablet (KPI grid
reflows to 2 columns, no truncation). Screenshots in `audit/screenshots/after/` —
`admin-overview-mobile-responsive-fixed.png`, `admin-overview-tablet-responsive-fixed.png`,
`admin-mobile-drawer-open.png` — compare directly against the original
`audit/screenshots/admin-overview-{mobile,tablet}-light-full.png`.

Bonus (found while touching the same button): added the missing `aria-label="Đăng xuất"` to both
copies of the icon-only logout button (`AdminShell.jsx` and `chat/Sidebar.jsx`) — this is F5-1,
originally slated for Wave 4, but one line each while already in this exact code.

### `511e9d3` — fix: light-mode `--text-muted` contrast (F3-3)
**Fixed.** `--text-muted` (light theme) was `#8CA0B3` — computed at 2.58:1 against `--bg`, well
below WCAG AA's 4.5:1 for normal text (dark theme's `--text-muted` already passed at 5.54:1,
untouched). Changed to `#5B7184`, computed at ~4.80:1 — real margin above the threshold, not a
borderline value. Verified the new value is actually served (`getComputedStyle` on the live page
returned `#5b7184`) and visually: composer placeholder text and suggestion-card labels are
legibly darker in the screenshot. `frontend/src/tokens/colors.css` is nominally vendored/never-
hand-edited per CLAUDE.md's design-system convention — added a comment flagging this specific
line so a future re-vendor doesn't silently regress it back to the failing value.
Screenshot: `audit/screenshots/after/chat-text-muted-contrast-fixed.png`.

### `8ab0bce` — docs: confirm landing/login theming is deliberate (F3-1)
**Resolved as documentation, not a code change.** Checked `app/templates/login.html` alongside
`LandingScreen.jsx`: neither renders a `ThemeToggle`, and both use the identical fixed navy-hero
gradient regardless of `prefers-color-scheme` — a consistent pattern (pre-authentication surfaces
stay on-brand navy; only the post-login product respects the signed-in user's theme), not a
half-finished token migration on one page. Documented this explicitly in `LandingScreen.jsx`'s
header comment per the audit's own suggested resolution path, rather than rewiring `onInk`/`INK`
to theme tokens — that would be a deliberate redesign decision for later, not a bug fix now.
No visual or functional change; `app/static/dist` is byte-identical (comment-only edit, stripped
by minification) — no rebuild commit needed for this one.

### `6c31e20` — fix: empty department donut shows an honest message, not a 100% pie of nothing (CHART-1)
**Fixed.** `documents_by_department` correctly labels untagged documents `"Không đặt"`
(`app/api/metrics.py:257`, confirmed by reading it) — the frontend just rendered that as a
literal 100%-one-color donut, which reads as real data rather than "nothing tagged yet". Added a
check in `OverviewView.jsx`: when the breakdown is exactly one `"Không đặt"` segment, show
"Chưa gắn phòng ban cho tài liệu nào." instead of the donut. The moment a real department tag
exists, this falls through to the actual chart unchanged — verified by reading the condition, not
just asserted. Screenshot: `audit/screenshots/after/admin-overview-donut-fixed.png` (also
re-confirms F3-4's KPI grid fix holds cleanly at the standard 1440px desktop width the original
audit screenshot used — full labels, no truncation).

### `d6ca766` — fix: /chat adopts the Button component instead of hand-rolled buttons (ENG-1)
**Fixed, with one prerequisite fix to the design-system component itself.** `Button.jsx` had no
`...rest` passthrough at all — no way to set `aria-label`/`title` on it, which is exactly why
`/chat`'s icon-only buttons (send, stop, close, hamburger) had stayed hand-rolled despite the
design system existing (audit/01-engineering.md finding ENG-1 flagged this as the likely root
cause without confirming it — confirmed here by reading the component). Added `...rest` spread
onto the underlying `<button>`; this benefits every future icon-only `Button` usage app-wide, not
just this fix.

Swapped onto `Button` where its shape genuinely fits (single-line label or icon, not a
multi-line compound element): `Composer.jsx`'s send/stop buttons (`variant="primary"`/`"danger"`),
`ChatScreen.jsx`'s mobile hamburger, `SourcePanel.jsx`'s close button, `ChatMessage.jsx`'s
Copy/Regenerate actions. Left `EmptyState.jsx`'s prompt-suggestion cards as their own thing —
they're title+subtitle compound cards, not a fit for `Button`'s single-line `inline-flex` shape,
and forcing them in would fight the component rather than reuse it.

Verified live: sent a real question end-to-end (Copy/Regenerate render and the answer completes
normally), and opened the mobile drawer (hamburger → drawer, unaffected). Screenshot:
`audit/screenshots/after/chat-buttons-using-design-system.png`.

**Wave 2 complete.** All 5 items fixed and verified live: F3-4, F3-3, F3-1, CHART-1, ENG-1.


